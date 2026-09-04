import csv
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"
MANIFEST_CSV = CORPUS_DIR / "manifest.csv"
MANIFESTS_ROOT = REPO_ROOT / "data" / "manifests"
MOVIES_ROOT = Path(__file__).resolve().parent / "movies"

SEGMENT_DURATION = 4.0
VTT_TIMESTAMP = re.compile(r"(\d+):(\d+):(\d+\.\d+)\s*-->\s*(\d+):(\d+):(\d+\.\d+)")


def lecture_id_from_filename(filename):
    return Path(filename).stem


def read_corpus_manifest():
    with open(MANIFEST_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def segment_index_for_time(t, n_segments):
    idx = int(t // SEGMENT_DURATION)
    return max(0, min(idx, n_segments - 1))


def parse_vtt_cues(vtt_path):
    text = vtt_path.read_text(encoding="utf-8")
    blocks = text.split("\n\n")
    cues = []
    for block in blocks:
        match = VTT_TIMESTAMP.search(block)
        if not match:
            continue
        start = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
        cues.append((start, len(block.encode("utf-8"))))
    return cues


def compute_tier0(manifest, n_segments):
    rungs = []
    for rung in manifest["tiers"]["0"]["rungs"]:
        sizes_bytes = [seg["size_bytes"] for seg in rung["segments"]]
        assert len(sizes_bytes) == n_segments, (
            f"tier0 rung {rung['resolution']} has {len(sizes_bytes)} segments, expected {n_segments}"
        )
        rungs.append({"bitrate_kbps": rung["bitrate_kbps"], "sizes_bytes": sizes_bytes})
    rungs.sort(key=lambda r: r["bitrate_kbps"])
    return rungs


def compute_slide_spike_bytes(slides_dir, slides, n_segments):
    spike = [0] * n_segments
    for slide in slides:
        image_path = slides_dir / slide["image"]
        idx = segment_index_for_time(slide["start"], n_segments)
        spike[idx] += image_path.stat().st_size
    return spike


def compute_tier1(lecture_dir, manifest, n_segments, segments_4s):
    tier1 = manifest["tiers"]["1"]
    audio_path = lecture_dir / "tier1" / tier1["audio_file"]
    audio_total_bytes = audio_path.stat().st_size
    duration = manifest["duration_seconds"]

    slide_spike = compute_slide_spike_bytes(lecture_dir / "tier1" / "slides", tier1["slides"], n_segments)

    sizes_bytes = []
    for i, seg in enumerate(segments_4s):
        audio_share = audio_total_bytes * (seg["end"] - seg["start"]) / duration
        sizes_bytes.append(round(audio_share) + slide_spike[i])
    return {"bitrate_kbps": tier1["bitrate_kbps"], "sizes_bytes": sizes_bytes}, slide_spike


def compute_tier2(lecture_dir, manifest, n_segments, slide_spike):
    tier2 = manifest["tiers"]["2"]
    vtt_path = lecture_dir / "tier2" / tier2["captions_file"]
    cues = parse_vtt_cues(vtt_path)

    caption_bytes = [0] * n_segments
    for start, byte_len in cues:
        idx = segment_index_for_time(start, n_segments)
        caption_bytes[idx] += byte_len

    sizes_bytes = [caption_bytes[i] + slide_spike[i] for i in range(n_segments)]
    return {"bitrate_kbps": tier2["bitrate_kbps"], "sizes_bytes": sizes_bytes}


def compute_tier3(manifest, n_segments):
    tier3 = manifest["tiers"]["3"]
    sizes_bytes = [0] * n_segments
    for summary in tier3["summaries"]:
        idx = segment_index_for_time(summary["start"], n_segments)
        sizes_bytes[idx] += len(summary["text"].encode("utf-8"))
    return {"bitrate_kbps": tier3["bitrate_kbps"], "sizes_bytes": sizes_bytes}


def build_movie(rungs, n_segments, content_labels=None):
    bitrates_kbps = [r["bitrate_kbps"] for r in rungs]
    tiers = [r["tier"] for r in rungs]
    # A literal 0-byte segment (observed: a genuinely empty Tier 3 summary window,
    # no transcribed speech in that window) breaks Sabre's own download-time math
    # (division by zero when transfer time rounds to 0). A true zero-byte network
    # transfer isn't physically realistic anyway - there's always some minimal
    # framing overhead - so this is a numerical-stability floor, not a claimed
    # measurement of what that overhead actually is.
    segment_sizes_bits = []
    for i in range(n_segments):
        segment_sizes_bits.append([max(1, r["sizes_bytes"][i]) * 8 for r in rungs])
    movie = {
        "segment_duration_ms": int(SEGMENT_DURATION * 1000),
        "bitrates_kbps": bitrates_kbps,
        "tiers": tiers,
        "segment_sizes_bits": segment_sizes_bits,
    }
    if content_labels is not None:
        movie["content_labels"] = content_labels
    return movie


def process_lecture(row):
    lecture_id = lecture_id_from_filename(row["filename"])
    lecture_dir = MANIFESTS_ROOT / lecture_id
    manifest_path = lecture_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"[{lecture_id}] skipped, no manifest.json", flush=True)
        return None

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    segments_4s = manifest["segments_4s"]
    n_segments = len(segments_4s)

    tier0_rungs = compute_tier0(manifest, n_segments)
    tier1_rung, slide_spike = compute_tier1(lecture_dir, manifest, n_segments, segments_4s)
    tier2_rung = compute_tier2(lecture_dir, manifest, n_segments, slide_spike)
    tier3_rung = compute_tier3(manifest, n_segments)

    for r in tier0_rungs:
        r["tier"] = 0
    tier1_rung["tier"] = 1
    tier2_rung["tier"] = 2
    tier3_rung["tier"] = 3

    full_rungs = [tier3_rung, tier2_rung, tier1_rung] + tier0_rungs
    content_labels = [s["content_label"] for s in segments_4s]

    out_dir = MOVIES_ROOT / lecture_id
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline_movie = build_movie(tier0_rungs, n_segments)
    naive_movie = build_movie(full_rungs, n_segments)
    ours_movie = build_movie(full_rungs, n_segments, content_labels=content_labels)

    (out_dir / "baseline.json").write_text(json.dumps(baseline_movie, indent=2), encoding="utf-8")
    (out_dir / "naive.json").write_text(json.dumps(naive_movie, indent=2), encoding="utf-8")
    (out_dir / "ours.json").write_text(json.dumps(ours_movie, indent=2), encoding="utf-8")

    print(f"[{lecture_id}] {n_segments} segments, {len(tier0_rungs)} tier0 rungs, "
          f"{len(full_rungs)} total quality levels", flush=True)
    return out_dir


def main():
    targets = sys.argv[1:]
    rows = read_corpus_manifest()
    if targets:
        rows = [r for r in rows if lecture_id_from_filename(r["filename"]) in targets]
    for row in rows:
        process_lecture(row)


if __name__ == "__main__":
    main()
