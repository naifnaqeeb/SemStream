import json
import random
import subprocess
import sys
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent
REPO_ROOT = DEMO_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from agent.state_machine import ContentAwareStateMachine

LABELS = ["demo", "talking_head", "slides_static"]

JS_DRIVER = """
const path = require("path");
const { ContentAwareStateMachine } = require(path.join(__dirname, "agent.js"));
const cases = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
const results = cases.map(function (c) {
  const sm = new ContentAwareStateMachine();
  return c.steps.map(function (s) {
    return sm.nextQuality(c.bitrates_kbps, s.bandwidth_kbps, s.content_label);
  });
});
process.stdout.write(JSON.stringify(results));
"""


def build_cases():
    rng = random.Random(20260905)
    cases = []

    real_ladder = [0.04, 13.35, 79.55, 500, 900, 1500]
    single_rung = [300.0]
    two_rung = [1.0, 300.0]

    # Sustained collapse then recovery, every label held constant.
    for label in LABELS:
        bandwidths = ([2000.0] * 10 + [1200.0] * 5 + [400.0] * 5
                      + [50.0] * 10 + [400.0] * 5 + [2000.0] * 10)
        cases.append({
            "bitrates_kbps": real_ladder,
            "steps": [{"bandwidth_kbps": b, "content_label": label} for b in bandwidths],
        })

    # Label flipping every segment against a volatile bandwidth trace.
    for _ in range(20):
        n = rng.randint(20, 120)
        steps = [{"bandwidth_kbps": rng.choice([0.0, 5.0, 50.0, 200.0, 480.0, 520.0,
                                                890.0, 910.0, 1490.0, 1510.0, 5000.0]),
                  "content_label": rng.choice(LABELS)} for _ in range(n)]
        cases.append({"bitrates_kbps": real_ladder, "steps": steps})

    # Exact-boundary bandwidths where safety factors decide the index.
    boundary = []
    for bitrate in real_ladder:
        for factor in (0.6, 0.7, 0.75, 0.85, 0.9, 0.95):
            boundary.append(bitrate / factor)
    for label in LABELS:
        cases.append({
            "bitrates_kbps": real_ladder,
            "steps": [{"bandwidth_kbps": b, "content_label": label} for b in boundary],
        })

    # Degenerate ladders and unknown/missing labels.
    for ladder in (single_rung, two_rung, real_ladder):
        cases.append({
            "bitrates_kbps": ladder,
            "steps": [{"bandwidth_kbps": b, "content_label": lbl}
                      for b in (0.0, 1.0, 299.0, 300.0, 301.0, 100000.0)
                      for lbl in LABELS + [None, "unlabelled"]],
        })

    # Long random walk, real ladder, to exercise dwell accounting over many switches.
    for seed_bump in range(5):
        walk = []
        bw = 1000.0
        for _ in range(400):
            bw = max(0.0, bw * rng.uniform(0.6, 1.6))
            walk.append({"bandwidth_kbps": bw, "content_label": rng.choice(LABELS)})
        cases.append({"bitrates_kbps": real_ladder, "steps": walk})

    return cases


def run_python(cases):
    results = []
    for case in cases:
        machine = ContentAwareStateMachine()
        results.append([
            machine.next_quality(case["bitrates_kbps"], step["bandwidth_kbps"], step["content_label"])
            for step in case["steps"]
        ])
    return results


def run_js(cases):
    cases_path = DEMO_DIR / "_equiv_cases.json"
    driver_path = DEMO_DIR / "_equiv_driver.js"
    cases_path.write_text(json.dumps(cases), encoding="utf-8")
    driver_path.write_text(JS_DRIVER, encoding="utf-8")
    try:
        out = subprocess.run(["node", str(driver_path), str(cases_path)],
                             capture_output=True, text=True, check=True)
        return json.loads(out.stdout)
    finally:
        cases_path.unlink(missing_ok=True)
        driver_path.unlink(missing_ok=True)


def main():
    cases = build_cases()
    py = run_python(cases)
    js = run_js(cases)

    total_steps = sum(len(c["steps"]) for c in cases)
    mismatches = []
    for case_i, (p, j) in enumerate(zip(py, js)):
        for step_i, (a, b) in enumerate(zip(p, j)):
            if a != b:
                mismatches.append((case_i, step_i, a, b, cases[case_i]["steps"][step_i]))

    print(f"cases: {len(cases)}   decisions compared: {total_steps}", flush=True)
    if mismatches:
        print(f"MISMATCHES: {len(mismatches)}", flush=True)
        for case_i, step_i, a, b, step in mismatches[:10]:
            print(f"  case {case_i} step {step_i}: python={a} js={b} input={step}", flush=True)
        sys.exit(1)
    print("PASS - python and js agents agree on every decision", flush=True)


if __name__ == "__main__":
    main()
