import csv
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytesseract

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"
MANIFEST_CSV = CORPUS_DIR / "manifest.csv"
OUTPUT_ROOT = REPO_ROOT / "data" / "manifests"

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

SEGMENT_DURATION = 4.0
SAMPLE_INTERVAL = SEGMENT_DURATION / 2
FRAME_WIDTH = 640
OCR_CONFIDENCE_MIN = 30
CODE_MARKERS = [
    "def ", "for ", "while ", "return", "import ", "print(", "range(",
    "elif", "self.", "==", "!=", "append(", "class ", "except:", "try:",
]

FACE_MODEL_PATH = Path(__file__).resolve().parent / "models" / "face_detection_yunet_2023mar.onnx"
FACE_DETECTOR = cv2.FaceDetectorYN_create(str(FACE_MODEL_PATH), "", (FRAME_WIDTH, FRAME_WIDTH), score_threshold=0.7)


def lecture_id_from_filename(filename):
    return Path(filename).stem


def read_corpus_manifest():
    with open(MANIFEST_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def extract_sample_frames(source_path, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    for existing in out_dir.glob("frame_*.jpg"):
        existing.unlink()
    pattern = str(out_dir / "frame_%06d.jpg")
    cmd = [
        "ffmpeg", "-y", "-i", str(source_path),
        "-vf", f"fps=1/{SAMPLE_INTERVAL},scale={FRAME_WIDTH}:-2",
        "-q:v", "4", pattern,
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return sorted(out_dir.glob("frame_*.jpg"))


def frame_diff(gray_a, gray_b):
    diff = cv2.absdiff(gray_a, gray_b)
    return round(float(np.mean(diff)) / 255.0, 4)


def face_count(bgr_frame):
    height, width = bgr_frame.shape[:2]
    FACE_DETECTOR.setInputSize((width, height))
    _, faces = FACE_DETECTOR.detect(bgr_frame)
    return 0 if faces is None else int(len(faces))


def ocr_features(bgr_frame):
    data = pytesseract.image_to_data(bgr_frame, output_type=pytesseract.Output.DICT)
    frame_area = bgr_frame.shape[0] * bgr_frame.shape[1]
    text_area = 0
    words = []
    for i, conf in enumerate(data["conf"]):
        if int(conf) >= OCR_CONFIDENCE_MIN and data["text"][i].strip():
            text_area += data["width"][i] * data["height"][i]
            words.append(data["text"][i])
    density = round(min(text_area / frame_area, 1.0), 4)
    full_text = " ".join(words)
    code_marker_count = sum(1 for marker in CODE_MARKERS if marker in full_text)
    return density, code_marker_count


def process_video(row):
    lecture_id = lecture_id_from_filename(row["filename"])
    source_path = CORPUS_DIR / row["filename"]
    out_dir = OUTPUT_ROOT / lecture_id
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"[{lecture_id}] skipped, no manifest.json", flush=True)
        return None

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    n_segments = len(manifest["segments_4s"])

    frames_dir = out_dir / "_feature_frames"
    frame_paths = extract_sample_frames(source_path, frames_dir)

    segments = []
    for index in range(n_segments):
        a_idx, b_idx = 2 * index, 2 * index + 1
        if b_idx >= len(frame_paths):
            segments.append({
                "index": index, "frame_diff": 0.0, "face_count": 0,
                "ocr_text_density": 0.0, "code_marker_count": 0,
            })
            continue

        frame_a = cv2.imread(str(frame_paths[a_idx]))
        frame_b = cv2.imread(str(frame_paths[b_idx]))
        gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
        gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)
        density, code_marker_count = ocr_features(frame_b)

        segments.append({
            "index": index,
            "frame_diff": frame_diff(gray_a, gray_b),
            "face_count": face_count(frame_b),
            "ocr_text_density": density,
            "code_marker_count": code_marker_count,
        })
        if index % 100 == 0:
            print(f"[{lecture_id}] {index}/{n_segments} segments processed", flush=True)

    for f in frame_paths:
        f.unlink()
    frames_dir.rmdir()

    features_path = out_dir / "features.json"
    with open(features_path, "w", encoding="utf-8") as f:
        json.dump({"lecture_id": lecture_id, "segments": segments}, f, indent=2)
    print(f"[{lecture_id}] {len(segments)} segments, features.json written", flush=True)
    return segments


def main():
    targets = sys.argv[1:]
    rows = read_corpus_manifest()
    if targets:
        rows = [r for r in rows if lecture_id_from_filename(r["filename"]) in targets]
    for row in rows:
        process_video(row)


if __name__ == "__main__":
    main()
