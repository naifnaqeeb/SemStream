import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"
MANIFEST_CSV = CORPUS_DIR / "manifest.csv"
OUTPUT_ROOT = REPO_ROOT / "data" / "manifests"

SEGMENT_DURATION = 4.0


def lecture_id_from_filename(filename):
    return Path(filename).stem


def read_corpus_manifest():
    with open(MANIFEST_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_segments_4s(duration):
    segments = []
    index = 0
    start = 0.0
    while start < duration:
        end = min(start + SEGMENT_DURATION, duration)
        segments.append({
            "index": index,
            "start": round(start, 3),
            "end": round(end, 3),
            "content_label": None,
            "visual_importance": None,
        })
        start = end
        index += 1
    return segments


def kbps(total_bytes, duration_seconds):
    if duration_seconds <= 0:
        return 0.0
    return round(total_bytes * 8 / duration_seconds / 1000, 2)


def assemble(row):
    lecture_id = lecture_id_from_filename(row["filename"])
    out_dir = OUTPUT_ROOT / lecture_id

    tier0_path = out_dir / "tier0_meta.json"
    tier1_path = out_dir / "tier1_meta.json"
    tier3_path = out_dir / "tier3_meta.json"
    missing = [p.name for p in (tier0_path, tier1_path, tier3_path) if not p.exists()]
    if missing:
        print(f"[{lecture_id}] skipped, missing {missing}", flush=True)
        return None

    tier0 = json.loads(tier0_path.read_text(encoding="utf-8"))
    tier1 = json.loads(tier1_path.read_text(encoding="utf-8"))
    tier3 = json.loads(tier3_path.read_text(encoding="utf-8"))

    duration = tier0["duration_seconds"]
    tier1_dir = out_dir / "tier1"
    slides_dir = tier1_dir / "slides"
    audio_bytes = (tier1_dir / tier1["audio_file"]).stat().st_size
    slide_bytes = sum((slides_dir / s["image"]).stat().st_size for s in tier1["slides"])

    captions_path = out_dir / "tier2" / "tier2_captions.vtt"
    captions_bytes = captions_path.stat().st_size if captions_path.exists() else 0

    summaries_bytes = len(json.dumps(tier3["summaries"]).encode("utf-8"))

    manifest = {
        "lecture_id": lecture_id,
        "duration_seconds": duration,
        "source_video": f"corpus/{row['filename']}",
        "tiers": {
            "0": {"rungs": tier0["rungs"]},
            "1": {
                "bitrate_kbps": kbps(audio_bytes + slide_bytes, duration),
                "audio_file": tier1["audio_file"],
                "slides": tier1["slides"],
            },
            "2": {
                "bitrate_kbps": kbps(captions_bytes + slide_bytes, duration),
                "captions_file": "tier2_captions.vtt",
                "slides": tier1["slides"],
            },
            "3": {
                "bitrate_kbps": kbps(summaries_bytes, duration),
                "summaries": tier3["summaries"],
            },
        },
        "segments_4s": build_segments_4s(duration),
    }

    with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"[{lecture_id}] manifest.json assembled", flush=True)
    return manifest


def main():
    targets = sys.argv[1:]
    rows = read_corpus_manifest()
    if targets:
        rows = [r for r in rows if lecture_id_from_filename(r["filename"]) in targets]
    for row in rows:
        assemble(row)


if __name__ == "__main__":
    main()
