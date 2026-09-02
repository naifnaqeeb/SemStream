import csv
import json
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"
MANIFEST_CSV = CORPUS_DIR / "manifest.csv"
OUTPUT_ROOT = REPO_ROOT / "data" / "manifests"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.1:8b"
WINDOW_SECONDS = 60.0

PROMPT_TEMPLATE = """You are producing a rolling text summary of a recorded lecture for a student \
whose connection cannot support video or audio, only short text updates. \
Summarise ONLY the new material below in 1-2 plain sentences, in British English, present tense. \
Do not repeat what was already covered. Do not add commentary, headers, or bullet points.

What was already covered (for context only, do not repeat it): {prior_summary}

New transcript material (last {window_seconds:.0f} seconds):
{window_text}

One or two sentence summary of the new material:"""


def lecture_id_from_filename(filename):
    return Path(filename).stem


def read_corpus_manifest():
    with open(MANIFEST_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def group_into_windows(segments, duration):
    windows = []
    start = 0.0
    while start < duration:
        end = min(start + WINDOW_SECONDS, duration)
        text = " ".join(s["text"] for s in segments if s["start"] < end and s["end"] > start).strip()
        windows.append({"start": round(start, 3), "end": round(end, 3), "text": text})
        start = end
    return windows


def call_ollama(prompt):
    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL_NAME, "prompt": prompt, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["response"].strip()


def summarise_windows(windows):
    summaries = []
    prior_summary = "(nothing yet, this is the start of the lecture)"
    for window in windows:
        if not window["text"]:
            summaries.append({"start": window["start"], "end": window["end"], "text": ""})
            continue
        prompt = PROMPT_TEMPLATE.format(
            prior_summary=prior_summary,
            window_seconds=WINDOW_SECONDS,
            window_text=window["text"],
        )
        summary_text = call_ollama(prompt)
        summaries.append({"start": window["start"], "end": window["end"], "text": summary_text})
        prior_summary = summary_text
    return summaries


def process_video(row):
    lecture_id = lecture_id_from_filename(row["filename"])
    out_dir = OUTPUT_ROOT / lecture_id
    transcript_path = out_dir / "transcript.json"
    if not transcript_path.exists():
        print(f"[{lecture_id}] skipped, no transcript.json (run transcribe.py first)", flush=True)
        return None

    with open(transcript_path, encoding="utf-8") as f:
        transcript = json.load(f)

    duration = transcript["segments"][-1]["end"] if transcript["segments"] else 0.0
    windows = group_into_windows(transcript["segments"], duration)
    summaries = summarise_windows(windows)
    for s in summaries:
        print(f"[{lecture_id}] {s['start']:.0f}-{s['end']:.0f}s: {s['text'][:80]}", flush=True)

    tier3_dir = out_dir / "tier3"
    tier3_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "lecture_id": lecture_id,
        "model": MODEL_NAME,
        "window_seconds": WINDOW_SECONDS,
        "summaries": summaries,
    }
    with open(out_dir / "tier3_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"[{lecture_id}] {len(summaries)} summaries generated", flush=True)
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
