import csv
import json
import sys
from pathlib import Path

from rules import classify_segment

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"
MANIFEST_CSV = CORPUS_DIR / "manifest.csv"
OUTPUT_ROOT = REPO_ROOT / "data" / "manifests"


def lecture_id_from_filename(filename):
    return Path(filename).stem


def read_corpus_manifest():
    with open(MANIFEST_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def process_video(row):
    lecture_id = lecture_id_from_filename(row["filename"])
    out_dir = OUTPUT_ROOT / lecture_id
    manifest_path = out_dir / "manifest.json"
    features_path = out_dir / "features.json"
    if not manifest_path.exists() or not features_path.exists():
        print(f"[{lecture_id}] skipped, missing manifest.json or features.json", flush=True)
        return None

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    features = json.loads(features_path.read_text(encoding="utf-8"))
    features_by_index = {s["index"]: s for s in features["segments"]}

    label_counts = {}
    for segment in manifest["segments_4s"]:
        f = features_by_index.get(segment["index"])
        if f is None:
            continue
        label, visual_importance = classify_segment(
            f["frame_diff"], f["face_count"], f["ocr_text_density"], f["code_marker_count"],
        )
        segment["content_label"] = label
        segment["visual_importance"] = visual_importance
        label_counts[label] = label_counts.get(label, 0) + 1

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"[{lecture_id}] labelled: {label_counts}", flush=True)
    return label_counts


def main():
    targets = sys.argv[1:]
    rows = read_corpus_manifest()
    if targets:
        rows = [r for r in rows if lecture_id_from_filename(r["filename"]) in targets]
    for row in rows:
        process_video(row)


if __name__ == "__main__":
    main()
