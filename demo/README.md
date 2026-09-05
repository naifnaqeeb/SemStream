# Phase 4.5 — course demo

Static browser page demonstrating content-aware tier switching. Tier decisions come from the
real Phase 4 agent, not a scripted animation.

## Running it

The page fetches `demo_manifest.json`, so it needs to be served over HTTP (`file://` blocks
the fetch):

```
cd demo
python -m http.server 8000
```

Then open `http://localhost:8000/index.html`. Press **Play**, then drag the bandwidth slider.

## What to look for

Dragging the slider down walks the agent through all four tiers and back up:

| Tier | Shown | Rung bitrate (this lecture) |
|---|---|---|
| 0 | full video + audio | 500 / 900 / 1500 kbps |
| 1 | slide image + audio | 79.55 kbps |
| 2 | slide image + captions | 13.35 kbps |
| 3 | rolling text summary | 0.04 kbps |

The HUD shows the current bandwidth, the agent's selected tier and quality index, the rung
bitrate, the upcoming segment's content label, and a simulated buffer.

Switching is not instantaneous by design: the agent enforces a 3-segment (12s) minimum dwell
before any switch, so the tier changes a beat after the slider moves. That lag is the real
hysteresis behaviour from `agent/hysteresis.py`, not sluggishness in the page.

## How the agent logic gets here

`agent/state_machine.py`, `agent/hysteresis.py` and `agent/bandwidth_source.py` are Python;
this page is static JS. `agent.js` is a deliberate port of those three files, and
`equivalence_test.py` mechanically checks the two implementations never disagree:

```
python demo/equivalence_test.py
```

It runs both the Python and JS agents over identical input sequences — sustained collapse and
recovery, label flipping every segment, exact safety-factor boundary bandwidths, degenerate
one- and two-rung ladders, unknown labels, and long random walks — and fails if any single
decision differs. Currently 34 cases / 3730 decisions, all matching.

Bandwidth reaches the agent only through `UIBandwidthSource.getBandwidthEstimate()`, mirroring
`agent/bandwidth_source.py` and the interface rule in `CLAUDE.md`.

## Rebuilding the assets

`assets/` and `demo_manifest.json` are generated from Phase 1/2 outputs:

```
python demo/build_assets.py
```

It cuts a 5-minute window (segments 303–377 of `mit_6_0002_comp_thinking_lec04`, chosen because
all three content labels are well represented there: 39 talking_head, 20 demo, 16 slides_static),
re-encodes one Tier 0 rung, and windows the audio, slides, captions and summaries to match.

## Licensing

The bundled excerpt is from *MIT 6.0002 Introduction to Computational Thinking and Data Science,
Fall 2016* (Prof. John Guttag, MIT OpenCourseWare), licensed CC BY-NC-SA 4.0 — redistributable
with attribution for non-commercial use, which is why this lecture was chosen for the demo
rather than one of the corpus's NPTEL lectures (those are all-rights-reserved and stay local;
see `docs/design_notes.md`).
