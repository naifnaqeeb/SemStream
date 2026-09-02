import csv
import json
import subprocess
import sys
from pathlib import Path

from scenedetect import detect, ContentDetector

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"
MANIFEST_CSV = CORPUS_DIR / "manifest.csv"
OUTPUT_ROOT = REPO_ROOT / "data" / "manifests"

CONTENT_THRESHOLD = 27.0
MIN_SCENE_LEN = "20s"
MAX_SLIDE_SECONDS = 180.0


def lecture_id_from_filename(filename):
    return Path(filename).stem


def read_corpus_manifest():
    with open(MANIFEST_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ffprobe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def extract_frame(source_path, timestamp, out_path):
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(timestamp), "-i", str(source_path),
         "-frames:v", "1", "-q:v", "2", str(out_path)],
        check=True, capture_output=True, text=True,
    )


def extract_audio(source_path, out_path):
    # Raw ADTS .aac output silently truncates on some source streams (observed
    # ~130s lost on a 1680s NPTEL source); an .m4a (AAC-in-MP4) container
    # preserves the full duration via proper timestamp/edit-list handling.
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(source_path), "-vn", "-c:a", "aac", "-b:a", "64k", str(out_path)],
        check=True, capture_output=True, text=True,
    )


def split_long_gaps(boundaries):
    # ContentDetector is a hard-cut detector; it works well on slide-deck
    # advances but can go silent for very long stretches on content that
    # changes gradually with no hard cut (e.g. a slowly-typed code editor),
    # observed as a single ~1640s "slide" spanning almost an entire lecture.
    # Any gap wider than MAX_SLIDE_SECONDS is split into equal sub-windows so
    # Tier 1 still refreshes periodically through that stretch.
    result = []
    for start, end in boundaries:
        span = end - start
        if span <= MAX_SLIDE_SECONDS:
            result.append((start, end))
            continue
        n_parts = int(span // MAX_SLIDE_SECONDS) + 1
        part_len = span / n_parts
        for i in range(n_parts):
            result.append((start + i * part_len, start + (i + 1) * part_len))
    return result


def process_video(row):
    lecture_id = lecture_id_from_filename(row["filename"])
    source_path = CORPUS_DIR / row["filename"]
    out_dir = OUTPUT_ROOT / lecture_id
    tier1_dir = out_dir / "tier1"
    slides_dir = tier1_dir / "slides"
    slides_dir.mkdir(parents=True, exist_ok=True)

    duration = ffprobe_duration(source_path)
    scene_list = detect(
        str(source_path),
        ContentDetector(threshold=CONTENT_THRESHOLD, min_scene_len=MIN_SCENE_LEN),
    )
    if scene_list:
        boundaries = [(scene[0].seconds, scene[1].seconds) for scene in scene_list]
    else:
        boundaries = [(0.0, duration)]
    boundaries = split_long_gaps(boundaries)

    slides = []
    for index, (start, end) in enumerate(boundaries):
        image_name = f"slide_{index:03d}.jpg"
        extract_frame(source_path, (start + end) / 2, slides_dir / image_name)
        slides.append({"index": index, "start": round(start, 3), "end": round(end, 3), "image": image_name})

    extract_audio(source_path, tier1_dir / "tier1_audio.m4a")

    meta = {
        "lecture_id": lecture_id,
        "duration_seconds": round(duration, 3),
        "content_threshold": CONTENT_THRESHOLD,
        "min_scene_len": MIN_SCENE_LEN,
        "max_slide_seconds": MAX_SLIDE_SECONDS,
        "audio_file": "tier1_audio.m4a",
        "slides": slides,
    }
    with open(out_dir / "tier1_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"[{lecture_id}] {len(slides)} slides detected", flush=True)
    return meta


def main():
    targets = sys.argv[1:]
    rows = read_corpus_manifest()
    if targets:
        rows = [r for r in rows if lecture_id_from_filename(r["filename"]) in targets]
    for row in rows:
        process_video(row)


if __name__ == "__main__":
    main()
