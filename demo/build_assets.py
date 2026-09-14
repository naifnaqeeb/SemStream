import json
import re
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = Path(__file__).resolve().parent
ASSETS_DIR = DEMO_DIR / "assets"

# mit_6_0001 is the only MIT OCW lecture in the corpus with substantial genuine
# slide content (43% slides_static + 8% demo); the other two are talking-head
# dominant, and the NPTEL lectures that are slide-rich are all rights reserved
# and cannot be shipped. Window 479 scored best for the combination of genuine
# slides (8 of 10) and a three-way label mix (28 demo / 30 talking / 17 slides).
LECTURE_ID = "mit_6_0001_intro_python_lec02"
START_SEGMENT = 479
N_SEGMENTS = 75
SEGMENT_DURATION = 4.0
TIER0_RUNG = "720p"

VTT_TIMESTAMP = re.compile(r"(\d+):(\d+):(\d+\.\d+)\s*-->\s*(\d+):(\d+):(\d+\.\d+)")


def vtt_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def parse_vtt(path):
    cues = []
    for block in path.read_text(encoding="utf-8").split("\n\n"):
        match = VTT_TIMESTAMP.search(block)
        if not match:
            continue
        start = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
        end = int(match.group(4)) * 3600 + int(match.group(5)) * 60 + float(match.group(6))
        text = block.split("\n", 1)[1].strip() if "\n" in block else ""
        text = "\n".join(line for line in text.split("\n") if not VTT_TIMESTAMP.search(line))
        cues.append({"start": start, "end": end, "text": text.strip()})
    return cues


def main():
    lecture_dir = REPO_ROOT / "data" / "manifests" / LECTURE_ID
    manifest = json.loads((lecture_dir / "manifest.json").read_text(encoding="utf-8"))
    ours = json.loads((REPO_ROOT / "sim" / "movies" / LECTURE_ID / "ours.json").read_text(encoding="utf-8"))

    window_start = START_SEGMENT * SEGMENT_DURATION
    window_end = window_start + N_SEGMENTS * SEGMENT_DURATION

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    (ASSETS_DIR / "slides").mkdir(exist_ok=True)

    source_video = REPO_ROOT / manifest["source_video"]
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(window_start), "-t", str(window_end - window_start),
        "-i", str(source_video), "-vf", "scale=-2:720",
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", "900k",
        "-c:a", "aac", "-b:a", "96k",
        str(ASSETS_DIR / "tier0.mp4"),
    ], check=True, capture_output=True, text=True)

    subprocess.run([
        "ffmpeg", "-y", "-ss", str(window_start), "-t", str(window_end - window_start),
        "-i", str(lecture_dir / "tier1" / manifest["tiers"]["1"]["audio_file"]),
        "-c:a", "aac", "-b:a", "64k",
        str(ASSETS_DIR / "tier1_audio.m4a"),
    ], check=True, capture_output=True, text=True)

    # Phase 1's slide detector fires on lecturer/camera motion as well as real
    # slide changes, so on a talking-head passage the "slide" it extracted is a
    # frozen photo of the lecturer. Tag each one using Phase 2's label for the
    # segment the frame was taken from; the page holds the last genuine slide
    # through talking-head stretches rather than showing the lecturer frame.
    all_segments = manifest["segments_4s"]

    def is_genuine_slide(slide):
        midpoint = (max(slide["start"], window_start) + min(slide["end"], window_end)) / 2
        index = int(midpoint // SEGMENT_DURATION)
        if index < 0 or index >= len(all_segments):
            return False
        return all_segments[index]["content_label"] in ("slides_static", "demo")

    slides = []
    for slide in manifest["tiers"]["1"]["slides"]:
        if slide["end"] <= window_start or slide["start"] >= window_end:
            continue
        src = lecture_dir / "tier1" / "slides" / slide["image"]
        shutil.copy(src, ASSETS_DIR / "slides" / slide["image"])
        slides.append({
            "genuine": is_genuine_slide(slide),
            "start": max(0.0, round(slide["start"] - window_start, 3)),
            "end": round(min(slide["end"], window_end) - window_start, 3),
            "image": f"assets/slides/{slide['image']}",
        })

    cues = [c for c in parse_vtt(lecture_dir / "tier2" / manifest["tiers"]["2"]["captions_file"])
            if c["end"] > window_start and c["start"] < window_end]
    windowed_cues = [{
        "start": round(max(0.0, c["start"] - window_start), 3),
        "end": round(min(c["end"], window_end) - window_start, 3),
        "text": c["text"],
    } for c in cues]

    vtt_lines = ["WEBVTT", ""]
    for c in windowed_cues:
        vtt_lines.append(f"{vtt_time(c['start'])} --> {vtt_time(c['end'])}")
        vtt_lines.append(c["text"])
        vtt_lines.append("")
    (ASSETS_DIR / "tier2_captions.vtt").write_text(
        "\n".join(vtt_lines), encoding="utf-8", newline="\n")

    summaries = []
    for s in manifest["tiers"]["3"]["summaries"]:
        if s["end"] <= window_start or s["start"] >= window_end:
            continue
        summaries.append({
            "start": max(0.0, round(s["start"] - window_start, 3)),
            "end": round(min(s["end"], window_end) - window_start, 3),
            "text": s["text"],
        })

    segments = []
    for i in range(N_SEGMENTS):
        src = manifest["segments_4s"][START_SEGMENT + i]
        segments.append({
            "index": i,
            "start": round(i * SEGMENT_DURATION, 3),
            "end": round((i + 1) * SEGMENT_DURATION, 3),
            "content_label": src["content_label"],
            "visual_importance": src["visual_importance"],
        })

    demo_manifest = {
        "lecture_id": LECTURE_ID,
        "source_window": {"start_segment": START_SEGMENT, "n_segments": N_SEGMENTS,
                          "start_seconds": window_start, "end_seconds": window_end},
        "segment_duration": SEGMENT_DURATION,
        "bitrates_kbps": ours["bitrates_kbps"],
        "tiers": ours["tiers"],
        "tier0_rung": TIER0_RUNG,
        "segments": segments,
        "slides": slides,
        "summaries": summaries,
        "captions_file": "assets/tier2_captions.vtt",
        "captions": windowed_cues,
        "tier0_video": "assets/tier0.mp4",
        "tier1_audio": "assets/tier1_audio.m4a",
    }
    (DEMO_DIR / "demo_manifest.json").write_text(json.dumps(demo_manifest, indent=2), encoding="utf-8")

    # The page loads this rather than fetching the .json: fetch() is blocked on
    # file://, so a double-clicked index.html would otherwise dead-end. Generated
    # from the same dict, so the two cannot drift.
    (DEMO_DIR / "demo_manifest.js").write_text(
        "window.DEMO_MANIFEST = " + json.dumps(demo_manifest, indent=2) + ";\n",
        encoding="utf-8", newline="\n")

    print(f"window: segments {START_SEGMENT}-{START_SEGMENT + N_SEGMENTS - 1} "
          f"({window_start:.0f}-{window_end:.0f}s)", flush=True)
    print(f"slides={len(slides)} cues={len(cues)} summaries={len(summaries)} segments={len(segments)}", flush=True)
    print(f"bitrates_kbps={demo_manifest['bitrates_kbps']} tiers={demo_manifest['tiers']}", flush=True)


if __name__ == "__main__":
    main()
