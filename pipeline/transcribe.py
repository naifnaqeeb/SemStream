import csv
import json
import sys
from pathlib import Path

from faster_whisper import WhisperModel

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"
MANIFEST_CSV = CORPUS_DIR / "manifest.csv"
OUTPUT_ROOT = REPO_ROOT / "data" / "manifests"

MODEL_SIZE = "small"

_model = None


def get_model():
    global _model
    if _model is None:
        _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def lecture_id_from_filename(filename):
    return Path(filename).stem


def read_corpus_manifest():
    with open(MANIFEST_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def format_vtt_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def write_vtt(segments, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for seg in segments:
            f.write(f"{format_vtt_timestamp(seg['start'])} --> {format_vtt_timestamp(seg['end'])}\n")
            f.write(f"{seg['text'].strip()}\n\n")


def process_video(row):
    lecture_id = lecture_id_from_filename(row["filename"])
    source_path = CORPUS_DIR / row["filename"]
    out_dir = OUTPUT_ROOT / lecture_id
    tier2_dir = out_dir / "tier2"
    tier2_dir.mkdir(parents=True, exist_ok=True)

    model = get_model()
    segments_iter, info = model.transcribe(str(source_path), word_timestamps=True, vad_filter=True)

    segments = []
    for seg in segments_iter:
        words = [
            {"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
            for w in (seg.words or [])
        ]
        segments.append({
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
            "words": words,
        })
        print(f"[{lecture_id}] {seg.start:.0f}s: {seg.text.strip()[:60]}", flush=True)

    write_vtt(segments, tier2_dir / "tier2_captions.vtt")

    with open(out_dir / "transcript.json", "w", encoding="utf-8") as f:
        json.dump({"lecture_id": lecture_id, "language": info.language, "segments": segments}, f, indent=2)

    print(f"[{lecture_id}] {len(segments)} segments transcribed", flush=True)
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
