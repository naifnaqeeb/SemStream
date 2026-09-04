import csv
import json
import re
import subprocess
import sys
from pathlib import Path

SIM_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SIM_ROOT.parent
CORPUS_DIR = REPO_ROOT / "corpus"
MANIFEST_CSV = CORPUS_DIR / "manifest.csv"
MANIFESTS_ROOT = REPO_ROOT / "data" / "manifests"
RESULTS_DIR = REPO_ROOT / "data" / "results"
SABRE = SIM_ROOT / "src" / "sabre.py"

# norway_hsdpa/belgium_4g are the calmest files in each fetched set (checked
# against all 12/40 fetched files - median 3599/26843 kbps, <2s below 500kbps
# in either); norway_hsdpa_rough/belgium_4g_rough are the roughest real files
# found in the same sets (median 818/22061 kbps but with long low-bandwidth
# stretches - 86.3s/54.0s below 500kbps), added specifically so the real
# datasets carry comparative signal too, not just the synthetic collapse trace.
TRACES = {
    "norway_hsdpa": SIM_ROOT / "traces" / "norway_hsdpa" / "norway_bus_1.json",
    "norway_hsdpa_rough": SIM_ROOT / "traces" / "norway_hsdpa" / "norway_tram_11.json",
    "belgium_4g": SIM_ROOT / "traces" / "belgium_4g" / "report_bus_0001.json",
    "belgium_4g_rough": SIM_ROOT / "traces" / "belgium_4g" / "report_train_0003.json",
    "campus_collapse": SIM_ROOT / "traces" / "custom" / "campus_wifi_collapse.json",
}

# Adding "ours" here (movie "ours.json", abr "policies/Ours.py") is the only change
# needed once Phase 4's policy exists - everything downstream is policy-agnostic.
#
# Baseline is pinned to Sabre's built-in "bola" (not the default "bolae"/BolaEnh):
# CLAUDE.md specifies "standard BOLA-style logic" for this policy, and BolaEnh
# also crashes with ZeroDivisionError on the two 240p-capped lectures that only
# have a single Tier 0 rung (confirmed: BolaEnh's gap-parameter setup assumes
# 2+ quality levels; plain bola does not).
POLICIES = {
    "baseline": {"movie": "baseline.json", "abr": None, "builtin_abr": "bola"},
    "naive": {"movie": "naive.json", "abr": "policies/Naive.py", "builtin_abr": None},
    "ours": {"movie": "ours.json", "abr": "policies/Ours.py", "builtin_abr": None},
}

SEGMENT_LOG_RE = re.compile(r"^\[\d+-\d+\]\s+(\d+): q=(\d+)")
SUMMARY_RE = re.compile(r"^([a-zA-Z_ ]+?):\s+([-\d.]+)\s*$")

SLIDE_RETENTION = 0.4
CAPTION_RETENTION = 0.85
SUMMARY_RETENTION = 0.3


def lecture_id_from_filename(filename):
    return Path(filename).stem


def read_corpus_manifest():
    with open(MANIFEST_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def channel_availability(tier):
    if tier == 0:
        return (1.0, 1.0)
    if tier == 1:
        return (SLIDE_RETENTION, 1.0)
    if tier == 2:
        return (SLIDE_RETENTION, CAPTION_RETENTION)
    return (0.0, SUMMARY_RETENTION)


def information_score(tier, visual_importance):
    visual_avail, audio_avail = channel_availability(tier)
    return visual_importance * visual_avail + (1 - visual_importance) * audio_avail


def run_sabre(movie_path, trace_path, abr_relpath, builtin_abr):
    cmd = ["python", str(SABRE), "-m", str(movie_path), "-n", str(trace_path), "-v"]
    if abr_relpath:
        cmd += ["-a", str(SIM_ROOT / abr_relpath)]
    elif builtin_abr:
        cmd += ["-a", builtin_abr]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=SIM_ROOT, check=True)
    return result.stdout


def parse_quality_sequence(stdout):
    seq = {}
    for line in stdout.splitlines():
        match = SEGMENT_LOG_RE.match(line)
        if match:
            seq[int(match.group(1))] = int(match.group(2))
    return seq


def parse_summary(stdout):
    stats = {}
    for line in stdout.splitlines():
        match = SUMMARY_RE.match(line)
        if match:
            try:
                stats[match.group(1).strip()] = float(match.group(2))
            except ValueError:
                pass
    return stats


def evaluate_run(quality_seq, tiers_list, manifest):
    tier_time = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0}
    info_weighted_sum = 0.0
    played_time = 0.0
    for seg in manifest["segments_4s"]:
        quality = quality_seq.get(seg["index"])
        if quality is None:
            continue
        tier = tiers_list[quality]
        duration = seg["end"] - seg["start"]
        visual_importance = seg["visual_importance"]
        tier_time[tier] += duration
        info_weighted_sum += duration * information_score(tier, visual_importance)
        played_time += duration
    return tier_time, info_weighted_sum, played_time


def run_one(lecture_id, manifest, trace_name, trace_path, policy_name, policy_cfg):
    movie_path = SIM_ROOT / "movies" / lecture_id / policy_cfg["movie"]
    stdout = run_sabre(movie_path, trace_path, policy_cfg["abr"], policy_cfg.get("builtin_abr"))
    quality_seq = parse_quality_sequence(stdout)
    summary = parse_summary(stdout)
    tiers_list = json.loads(movie_path.read_text(encoding="utf-8"))["tiers"]

    tier_time, info_sum, played_time = evaluate_run(quality_seq, tiers_list, manifest)
    rebuffer_s = summary.get("total rebuffer", 0.0)
    total_time = played_time + rebuffer_s
    information_delivered = round(info_sum / total_time, 4) if total_time > 0 else 0.0

    row = {
        "lecture_id": lecture_id,
        "trace": trace_name,
        "policy": policy_name,
        "rebuffer_time_s": round(rebuffer_s, 3),
        "rebuffer_ratio": summary.get("rebuffer ratio", 0.0),
        "tier0_frac": round(tier_time[0] / played_time, 4) if played_time else 0.0,
        "tier1_frac": round(tier_time[1] / played_time, 4) if played_time else 0.0,
        "tier2_frac": round(tier_time[2] / played_time, 4) if played_time else 0.0,
        "tier3_frac": round(tier_time[3] / played_time, 4) if played_time else 0.0,
        "information_delivered": information_delivered,
    }
    return row


def main():
    targets = sys.argv[1:]
    rows_ = read_corpus_manifest()
    if targets:
        rows_ = [r for r in rows_ if lecture_id_from_filename(r["filename"]) in targets]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for row in rows_:
        lecture_id = lecture_id_from_filename(row["filename"])
        manifest_path = MANIFESTS_ROOT / lecture_id / "manifest.json"
        if not manifest_path.exists():
            print(f"[{lecture_id}] skipped, no manifest.json", flush=True)
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        for trace_name, trace_path in TRACES.items():
            for policy_name, policy_cfg in POLICIES.items():
                result = run_one(lecture_id, manifest, trace_name, trace_path, policy_name, policy_cfg)
                results.append(result)
                print(result, flush=True)

    out_path = RESULTS_DIR / "phase3_results.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"\n{len(results)} rows written to {out_path}", flush=True)


if __name__ == "__main__":
    main()
