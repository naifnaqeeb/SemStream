import csv
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"
MANIFEST_CSV = CORPUS_DIR / "manifest.csv"
OUTPUT_ROOT = REPO_ROOT / "data" / "manifests"

SEGMENT_DURATION = 4.0

LADDERS = {
    1080: [("1080p", 1080, 1500), ("720p", 720, 900), ("360p", 360, 500)],
    720: [("720p", 720, 900), ("480p", 480, 700), ("360p", 360, 500)],
    480: [("480p", 480, 700), ("360p", 360, 500), ("240p", 240, 300)],
    360: [("360p", 360, 500), ("240p", 240, 300)],
    240: [("240p", 240, 300)],
}
BUCKET_HEIGHTS = sorted(LADDERS.keys(), reverse=True)


def bucket_for(source_height):
    for h in BUCKET_HEIGHTS:
        if source_height >= h:
            return h
    return BUCKET_HEIGHTS[-1]


def lecture_id_from_filename(filename):
    return Path(filename).stem


def read_corpus_manifest():
    rows = []
    with open(MANIFEST_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            width, height = row["max_source_resolution"].lower().split("x")
            row["source_height"] = int(height)
            rows.append(row)
    return rows


def ffprobe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def cut_points(duration):
    return [i * SEGMENT_DURATION for i in range(1, int(duration // SEGMENT_DURATION) + 1)]


def encode_rung(source_path, out_dir, height, bitrate_kbps, duration):
    out_dir.mkdir(parents=True, exist_ok=True)
    for existing in out_dir.glob("seg_*.mp4"):
        existing.unlink()

    intermediate = out_dir / "_full.mp4"
    maxrate = int(bitrate_kbps * 1.2)
    bufsize = int(bitrate_kbps * 2)
    keyframe_times = ",".join(str(round(t, 3)) for t in cut_points(duration))
    encode_cmd = [
        "ffmpeg", "-y", "-i", str(source_path),
        "-vf", f"scale=-2:{height}",
        "-c:v", "libx264", "-profile:v", "main", "-preset", "veryfast", "-sc_threshold", "0",
        "-b:v", f"{bitrate_kbps}k", "-maxrate", f"{maxrate}k", "-bufsize", f"{bufsize}k",
        "-force_key_frames", keyframe_times,
        "-c:a", "aac", "-b:a", "96k",
        str(intermediate),
    ]
    subprocess.run(encode_cmd, check=True, capture_output=True, text=True)

    # ffmpeg's segment muxer consumes the first entry in -segment_times as an
    # internal priming value rather than an actual cut point, so a real cut
    # requested at t=4 only takes effect starting from the second list entry.
    # A dummy near-zero entry absorbs that off-by-one.
    segment_times = "0.001," + ",".join(str(round(t, 3)) for t in cut_points(duration))
    pattern = str(out_dir / "seg_%05d.mp4")
    segment_cmd = [
        "ffmpeg", "-y", "-i", str(intermediate),
        "-c", "copy", "-f", "segment", "-segment_times", segment_times, "-reset_timestamps", "1",
        pattern,
    ]
    subprocess.run(segment_cmd, check=True, capture_output=True, text=True)
    intermediate.unlink()

    segments = []
    for index, seg_path in enumerate(sorted(out_dir.glob("seg_*.mp4"))):
        segments.append({
            "index": index,
            "start": round(index * SEGMENT_DURATION, 3),
            "duration": round(ffprobe_duration(seg_path), 3),
            "size_bytes": seg_path.stat().st_size,
        })
    return segments


def encode_video(row):
    lecture_id = lecture_id_from_filename(row["filename"])
    source_path = CORPUS_DIR / row["filename"]
    out_lecture_dir = OUTPUT_ROOT / lecture_id
    tier0_dir = out_lecture_dir / "tier0"

    duration = ffprobe_duration(source_path)
    bucket = bucket_for(row["source_height"])
    ladder = LADDERS[bucket]

    rungs = []
    for resolution, height, bitrate_kbps in ladder:
        print(f"[{lecture_id}] encoding {resolution} @ {bitrate_kbps}kbps", flush=True)
        segments = encode_rung(source_path, tier0_dir / resolution, height, bitrate_kbps, duration)
        rungs.append({
            "resolution": resolution,
            "bitrate_kbps": bitrate_kbps,
            "segments": segments,
        })

    out_lecture_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "lecture_id": lecture_id,
        "duration_seconds": round(duration, 3),
        "source_video": f"corpus/{row['filename']}",
        "segment_duration": SEGMENT_DURATION,
        "rungs": rungs,
    }
    with open(out_lecture_dir / "tier0_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"[{lecture_id}] done, {len(rungs)} rung(s)", flush=True)
    return meta


def main():
    targets = sys.argv[1:]
    rows = read_corpus_manifest()
    if targets:
        rows = [r for r in rows if lecture_id_from_filename(r["filename"]) in targets]
    for row in rows:
        encode_video(row)


if __name__ == "__main__":
    main()
