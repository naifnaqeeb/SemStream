# IMPLEMENTATION_PLAN.md — SemStream Build Plan

Read `CLAUDE.md` first for project identity, hard constraints, conventions, and shared schemas.
This file is the phase-by-phase build plan. Update the checklist at the top as phases complete —
this file is meant to be a living record of progress, not a static prompt.

**Do not reorder phases.** Phases 0–4 plus the course demo (4.5) are the actual critical path and
are individually cheap. Phase 5 (the real DASH prototype) is expensive and fragile plumbing that
must come after Phase 3 has already produced a quantitative result, so that if time runs out, a
complete result still exists. Do not begin Phase 5 before Phase 3's check is satisfied.

## Progress checklist

Current canonical progress summary: `docs/interim_findings.md`. Read that first for what has
been built and measured; `docs/design_notes.md` holds the per-decision reasoning behind it.

- [x] Phase 0 — Corpus collection
- [x] Phase 1 — Semantic tier generation
- [x] Phase 2 — Content classifier
- [x] Phase 3 — Simulation harness
- [x] Phase 4 — Switching agent
- [x] Phase 4.5 — Course demo
- [ ] Phase 5 — Real DASH prototype — **declined for now, not abandoned.** Course requirement is
      already satisfied by Phases 0–4.5. Do not start unless explicitly requested.
- [ ] Phase 6 — Evaluation — **split:**
  - [x] System metrics — substantially delivered by Phase 3's results table
        (`data/results/phase3_results.csv`, 135 runs; written up in `docs/interim_findings.md`).
  - [ ] Optional ablation: rules-based vs VLM classifier — **identified, explicitly not built.**
        Would quantify how much of the agent's headroom is lost to the 51.5% demo-recall ceiling
        rather than to the policy itself. Reasoning in `docs/interim_findings.md` §10.
  - [ ] Comprehension study — **not started, held.** Awaiting confirmation of Review 2 / Review 3
        dates before any tooling is built; participant recruitment and informal instructor
        clearance have a longer lead time than any phase so far.
- [ ] Phase 7 — Paper

---

## Phase 0 — Corpus collection

**Goal.** 8–12 lecture videos, deliberately mixed across three content types: talking-head-heavy
theory lectures, slide-heavy lectures, and demonstration/code-heavy screencasts. Source from
NPTEL or MIT OpenCourseWare for licence safety. Use `yt-dlp`.

**Tasks.**
1. Confirm `yt-dlp` is available in the environment.
2. Propose a candidate list of 8–12 lectures covering all three content-type categories, and wait
   for confirmation before downloading.
3. Download to `corpus/`.
4. Build `corpus/manifest.csv` listing, per video: filename, source URL, licence, approximate
   duration, and a manual content-type tag (rough sanity check only, not classifier ground truth).

**Check before proceeding.** Videos play, durations are known, licence is confirmed permissive
for academic use, and the content-type mix is not accidentally skewed to one category (at least
3 videos per category).

---

## Phase 1 — Semantic tier generation

**Goal.** For every corpus video, produce all four tiers and a manifest conforming to the schema
in `CLAUDE.md`.

**Tasks, in order.**
1. `pipeline/encode.py` — FFmpeg re-encode to the three Tier 0 rungs. Segment sizes in the
   manifest must be measured from the real encoded output, not estimated from bitrate × duration.
2. `pipeline/slides.py` — PySceneDetect to find slide-change boundaries; extract one
   representative frame per detected slide as a JPEG.
3. `pipeline/transcribe.py` — faster-whisper for word-level timestamped transcription. Produce
   Tier 2 WebVTT captions from this output directly.
4. `pipeline/summarise.py` — Ollama with a local model (confirm which model is actually available
   before assuming one) to produce rolling per-minute summaries for Tier 3 from the transcript.
5. `pipeline/manifest.py` — assembles all of the above into `data/manifests/<lecture_id>/manifest.json`.

**Check before proceeding.** Manifests exist for every corpus video. Every Tier 0 segment size is
a real measured file size. Slide count is sane by eye against the slide-heavy videos. Tier 3
summaries read as coherent English when spot-checked against the source video.

---

## Phase 2 — Content classifier

**Goal.** Populate `content_label` and `visual_importance` for every 4-second segment in every
manifest. Rules-based only — the VLM-based alternative is an optional later ablation, not part
of this phase.

**Tasks.**
1. `classifier/features.py` — per-segment frame-difference magnitude, OCR text density (check
   what OCR library is actually available before assuming Tesseract), and face-detection
   presence/count via OpenCV.
2. `classifier/rules.py` — thresholding scheme mapping the three features to one of
   `talking_head` / `slides_static` / `demo`. Document the thresholds chosen and why in
   `docs/design_notes.md`, and flag them as provisional pending validation.
3. `classifier/label_segments.py` — runs the above over every manifest, writing labels into
   `segments_4s`.

**Check before proceeding.** For a handful of manually spot-checked segments across different
videos, the assigned label matches what a human would say looking at the frame. Report the
informal accuracy honestly as a spot check, not a rigorous evaluation.

---

## Phase 3 — Simulation harness (Sabre extension)

**This produces the core quantitative results of the project. Get this right.**

**Goal.** Fork `UMass-LIDS/sabre`. Before modifying anything, read its existing buffer model and
rung-selection interface and report back how it currently represents a rung, before changing
code. Then extend it so a selectable rung is `(tier, bitrate)` per the schema in `CLAUDE.md`,
using real segment sizes from the Phase 1 manifests.

**Tasks.**
1. Clone Sabre into `sim/`. Get it running unmodified on its own example trace first — confirm
   this works before touching anything.
2. `sim/tier_rung.py` — extends Sabre's rung abstraction to include tier alongside bitrate.
3. `sim/trace_loader.py` — loads bandwidth traces: FCC broadband, Norway HSDPA, and at least one
   custom "campus WiFi collapse" trace (document how it was constructed).
4. Implement three selectable policies over the same interface:
   - Baseline: buffer-based ABR, pixel-only (Tier 0 rungs only, standard BOLA-style logic).
   - Naive: content-blind modality switching on bandwidth thresholds only (represents commercial
     fallbacks such as audio-only mode).
   - Ours: the content-aware agent (built jointly with Phase 4).
5. `sim/run_experiment.py` — runs all three policies against all traces and all manifests,
   producing a results table (rebuffering time, tier-time distribution, an "information
   delivered" measure per trace), written to `data/results/`.

**Check before proceeding.** A real table of numbers exists comparing all three policies across
all traces. This plus the Phase 4.5 demo is a complete, defensible course project on its own —
treat reaching this point as the project's floor, not merely a milestone.

---

## Phase 4 — Switching agent (overlaps with Phase 3)

**Goal.** A rules-based state machine, used inside the Phase 3 simulator as the "ours" policy,
reused unmodified later in the demo and any real prototype.

**Tasks.**
1. `agent/state_machine.py` — inputs: `get_bandwidth_estimate()`, current buffer level, current
   tier, content label of the upcoming segment. Output: next tier.
2. `agent/hysteresis.py` — margins preventing rapid oscillation, and a minimum dwell time per
   tier. Document the specific numbers chosen and the reasoning in `docs/design_notes.md`.
3. `agent/bandwidth_source.py` — implements `get_bandwidth_estimate()` three ways behind the one
   interface: replayed trace (Sabre), UI-controlled value (demo), stub for a real estimator
   (later prototype, not implemented yet).

**Restated constraint.** No LLM call anywhere in this phase's decision path. Reinforcement
learning is out of scope unless explicitly requested — if it is added later, it sits alongside
the rules-based agent as an alternative policy, not a replacement; the rules-based agent must
keep working regardless.

**Check before proceeding.** The agent runs inside the Phase 3 simulator and produces sane
tier-selection behaviour by eye against at least one trace with an obvious bandwidth collapse and
recovery.

---

## Phase 4.5 — Course demo

Build this immediately after Phase 4, before anything else. It is cheap, uses only Phase 1
outputs plus the Phase 4 agent, and is what gets marked in a course review — do not defer it.

**Goal.** A static browser page (`demo/`) that:
- Has a slider controlling a fake bandwidth value.
- Feeds that value through the real `get_bandwidth_estimate()` interface into the real
  `state_machine.py` logic (reused, not reimplemented).
- Swaps displayed content between video, slide+audio, slide+caption, and text-summary views
  based on the agent's tier decision.
- Shows a heads-up display: current fake bandwidth, buffer level (can be simulated for the
  demo), current tier, and content label of the current segment.

No DASH, no dash.js, no packaging needed here — Tier 0 can be a plain `<video>` element serving a
pre-encoded rung directly; Tiers 1–3 are images, an audio element, a VTT track, and text, swapped
via DOM manipulation.

**Check before proceeding.** Dragging the slider down visibly and correctly walks the demo down
through all four tiers and back up, using the actual agent logic, not a scripted animation.

---

## Phase 5 — Real DASH prototype (optional beyond the course deliverable)

**Do not start without an explicit go-ahead** — Phases 0–4.5 already satisfy the course
requirement.

**Goal, if approved.** Package Tier 0 with Shaka Packager or GPAC into real DASH segments and an
MPD, serve via nginx or a simple Python HTTP server, use dash.js for Tier 0 playback with custom
JS handling Tiers 1–3, and drive switching with the Phase 4 agent using dash.js's real bandwidth
estimate rather than the demo slider.

**Known hard part, flagged in advance.** Cross-tier timestamp synchronisation — keeping audio
playing continuously and in sync when video is dropped and later restored — is the hardest single
piece of this phase. Expect visual, browser-specific bugs that cannot be diagnosed from logs
alone; describe precisely what is observed and ask for confirmation of what is on screen rather
than guessing blind at CSS/DOM causes.

---

## Phase 6 — Evaluation

**Do not start before Phase 3 and Phase 4.5 are both solid.**

**Goal.** Two-pronged evaluation.
1. System metrics, substantially already produced by Phase 3 — extend with additional traces or
   ablations if needed (e.g. rules-based classifier vs. a VLM-based one, if that optional path
   was built).
2. Comprehension study: 15–25 student participants watch lecture excerpts under three conditions
   (pixel-ABR baseline / content-blind switching / the agent), then a short quiz and a subjective
   rating. Quiz questions may be drafted with LLM assistance but must be hand-verified — flag any
   question with an ambiguous correct answer rather than resolving it unilaterally.

**Note.** This phase requires human participants and informal institutional clearance. Building
the quiz-delivery and data-collection tooling is in scope here; running the actual study is not
something to execute autonomously.

---

## Phase 7 — Paper

Not a coding phase. Do not draft until asked. Structure: motivation → related work (modality
conversion required manual authoring; generative AI removes that barrier; we substitute rather
than reconstruct) → system → simulation results → prototype → user study.

---

## Standing instructions (apply across every phase — see also CLAUDE.md)

- State assumptions rather than stalling or guessing wrongly.
- No fabricated results, ever — say "not yet run" rather than inventing a plausible figure.
- Explain design decisions as they happen, and log them in `docs/design_notes.md`.
- Check in at phase boundaries: report what was built, what was verified, what remains uncertain,
  before starting the next phase.
- Flag scope creep immediately — reinforcement learning, VLM classification, live lecture
  handling, or any generative reconstruction of audio/video are out of scope unless explicitly
  requested.

## Immediate next step

Begin with Phase 0. Confirm `yt-dlp` is available, propose a candidate list of 8–12 NPTEL/MIT OCW
lectures covering the three content-type categories, and wait for confirmation before downloading.
