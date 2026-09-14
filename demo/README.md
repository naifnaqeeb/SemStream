# Phase 4.5 — course demo

Static browser page demonstrating content-aware tier switching. Tier decisions come from the
real Phase 4 agent, not a scripted animation.

## Running it

Double-click `index.html`. No server, no install, no build step. Press **Play**, then drag the
bandwidth slider.

Everything the page needs is loaded via plain `<script>`/`<video>`/`<img>` tags and relative
paths, so it works opened straight from disk over `file://`, including from a USB stick or a
copied folder. There are no `fetch()` calls: `fetch()` is blocked on `file://` by CORS, which
would leave a double-clicked page dead with no visible cause. The manifest and caption cues are
therefore emitted as `demo_manifest.js` (a `window.DEMO_MANIFEST = {...}` assignment) rather
than fetched as JSON.

Verified by copying `demo/` to a clean directory outside the project and opening it directly:
no console errors, all four tiers reachable, video and slides load, captions track playback.

## Presentation vs laptop scale

The page opens in **presentation scale** every time, deliberately not remembered between
loads: the failure worth avoiding is walking into a review with a laptop-scale HUD because
that was the last mode used at a desk. The button top-right switches to laptop scale for
close-up work.

Presentation scale puts the three readouts a panel must be able to read across a full-width
strip under the video, sized in `vh` so they adapt to whatever the projector actually runs at
rather than assuming 1080p. On a 2.5 m wide projected image they stay legible to roughly
12-14 m, at both 1080p and 768p. It also constrains the whole page to exactly one viewport
height, since nobody scrolls a projected page.

The content label is colour-coded as well as enlarged, so a change registers as a colour
before it has to be read: **demo = red**, **talking_head = blue**, **slides_static = amber**.
That readout matters most, since it is what makes this content-aware rather than bandwidth-only.

## What to look for

Dragging the slider down walks the agent through all four tiers and back up:

| Tier | Shown | Rung bitrate (this lecture) |
|---|---|---|
| 0 | full video + audio | 500 / 900 / 1500 kbps |
| 1 | slide image + audio | 87.19 kbps |
| 2 | slide image + captions | 21.56 kbps |
| 3 | rolling text summary | 0.04 kbps |

On talking-head stretches Tiers 1 and 2 hold the **last genuine slide** rather than switching to
a frozen frame of the lecturer. Phase 1's detector fires on lecturer motion as well as real
slide changes, so some extracted "slides" are just photos of the lecturer; `build_assets.py`
tags each one using Phase 2's content label and the page skips back to the last real slide.

The HUD shows the current bandwidth, the agent's selected tier and quality index, the rung
bitrate, and the upcoming segment's content label.

There is deliberately no buffer readout: the agent is buffer-blind (bandwidth plus content
label only), so showing a buffer figure would imply an input the switching decision does not
consult. See `docs/design_notes.md` for why, including how that diverges from the Phase 4 plan
spec.

Playback has its own play/pause and scrub bar. These are custom rather than the browser's
native video controls, because `state.time` is the master clock that the media follows: native
controls would fight it, and would render too small to use at presentation scale. Seeking does
**not** reset the agent, so it carries its tier and dwell state across the jump.

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

It cuts a 5-minute window (segments 479–553 of `mit_6_0001_intro_python_lec02`), re-encodes one
Tier 0 rung, and windows the audio, slides, captions and summaries to match. That lecture is the
only MIT OCW one in the corpus with substantial genuine slide content, and the window was picked
by scanning for the best mix of real slides and label variety: 8 of 10 slides genuine, 28 demo /
30 talking_head / 17 slides_static.

## Licensing

The bundled excerpt is from *MIT 6.0001 Introduction to Computer Science and Programming in
Python, Fall 2016* (MIT OpenCourseWare), licensed CC BY-NC-SA 4.0 — redistributable
with attribution for non-commercial use, which is why this lecture was chosen for the demo
rather than one of the corpus's NPTEL lectures (those are all-rights-reserved and stay local;
see `docs/design_notes.md`). Only 3 of the 9 corpus lectures are redistributable, which is also
why the demo ships a single lecture rather than a switcher.
