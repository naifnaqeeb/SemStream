# CLAUDE.md — SemStream Project Context

This file is read at the start of every session. It holds what must not drift between sessions:
what the project is, the constraints that protect its research contribution, working conventions,
and the data schemas shared across phases. For what to build and in what order, see
`IMPLEMENTATION_PLAN.md` in this same directory — read that too, and check its phase-completion
notes before starting work, so you know which phase is current.

---

## What this project is

SemStream is a lecture video delivery system. Course project for BITE314L Multimedia Systems,
VIT Vellore, with a secondary goal of a conference submission. Being built solo (may become a
team of up to three; treat as solo unless told otherwise).

**The problem.** Adaptive bitrate streaming degrades a lecture by lowering pixel quality within a
single video representation. Below the lowest bitrate rung, the only remaining behaviour is
rebuffering or session failure — a loss of access to instruction, not just to visual quality.

**The idea.** Degrade modality instead of pixel fidelity. A lecture is decomposed into four
representations of the same content, generated automatically and offline:

| Tier | Representation | Approx. bitrate |
|---|---|---|
| 0 | Full video, standard quality rungs (1080p/720p/360p) | 500–1500 kbps |
| 1 | Slide images (one per slide change) + audio | 40–70 kbps |
| 2 | Slide images + timed captions (WebVTT), no audio | 5–10 kbps |
| 3 | Rolling timestamped text summary, no imagery | ~1 kbps |

A switching agent selects a tier from estimated bandwidth, buffer occupancy, current tier, and a
content label for the upcoming segment (`talking_head` / `slides_static` / `demo`). It holds
Tier 0 through demonstrations, where the visual channel carries information nothing else does,
and drops eagerly during talking-head passages, where it does not.

---

## Hard constraints — these define the research contribution, do not compromise on them

1. **No reconstruction, ever.** Tiers 1–3 are generated directly (a slide image is a slide image,
   a caption is a caption). No generative model resynthesises a face, a video frame, or audio.
   This is the single distinction between SemStream and the closest competing 2026 systems, which
   substitute modality by reconstructing an approximation of the original signal. If a task
   starts to resemble reconstruction, stop and flag it rather than proceeding.
2. **Content-aware, not bandwidth-only.** Tier selection must consult the content classifier's
   label, not bandwidth thresholds alone. Bandwidth-only switching is the "naive" baseline this
   project is compared against, not the thing being built.
3. **Standard delivery.** Integrates with MPEG-DASH, not a bespoke transport.
4. **No LLM on the switching decision path.** Language models are used only offline, during tier
   generation (Phase 1). The per-segment switching decision (Phase 4 onward) must be low-latency
   rules or a trained lightweight policy — never an LLM call at decision time. State this
   constraint back if a task ever touches the switching agent.
5. **Evaluation includes comprehension**, not perceptual quality alone. This is being built for
   in Phase 6; don't let earlier phases produce metrics framed as if perceptual quality were the
   end goal.

---

## Working conventions

- **No comments in code.** Standing preference. Code should read clearly through naming and
  structure. If something needs explaining, explain it in the chat response or in
  `docs/design_notes.md`, not inline in the file.
- **British English** in documentation, docstrings, and commit messages. No em dashes in prose.
- **No fabricated metrics or invented numbers, ever.** Every reported number must come from an
  actual run against actual data. If something has not been measured yet, say "not yet run"
  rather than estimating and presenting it as measured.
- **Explain design decisions as they happen.** Every non-trivial choice — a data structure, a
  threshold, an algorithm or library choice over an alternative — gets a sentence of reasoning in
  the response, and a short entry in `docs/design_notes.md` (decision, alternatives considered,
  reason chosen). This project will be defended in a viva where the design has to be re-derived
  from memory, not just demonstrated; do not let decisions get made silently.
- **State assumptions rather than stalling or guessing wrongly.** If a value or choice isn't
  specified anywhere in this file or the implementation plan, state the assumption being made and
  proceed.
- **Check in at phase boundaries.** After a phase's deliverables and check are done, stop and
  report what was built, what was verified, and what remains uncertain, before starting the next
  phase. Do not chain multiple phases together in one uninterrupted run.
- **Out of scope unless explicitly requested:** reinforcement-learning switching policy,
  VLM-based content classifier, live (rather than recorded) lecture handling. These are
  documented stretch goals, not defaults — do not start building toward them unprompted.

---

## Shared data schemas

These are used across multiple phases. Do not let any phase's code diverge from these without
updating this file and flagging the change.

### Tier manifest (one per lecture; produced in Phase 1, consumed by Phases 2–5)

Path: `data/manifests/<lecture_id>/manifest.json`

```json
{
  "lecture_id": "nptel_cs101_lec03",
  "duration_seconds": 2734.0,
  "source_video": "corpus/nptel_cs101_lec03.mp4",
  "tiers": {
    "0": {
      "rungs": [
        {"resolution": "1080p", "bitrate_kbps": 1500, "segments": [{"index": 0, "start": 0.0, "duration": 4.0, "size_bytes": 750000}]},
        {"resolution": "720p",  "bitrate_kbps": 900,  "segments": ["..."]},
        {"resolution": "360p",  "bitrate_kbps": 500,  "segments": ["..."]}
      ]
    },
    "1": {
      "bitrate_kbps": 55,
      "audio_file": "tier1_audio.m4a",
      "slides": [{"index": 0, "start": 0.0, "end": 42.3, "image": "slide_000.jpg"}]
    },
    "2": {
      "bitrate_kbps": 7,
      "captions_file": "tier2_captions.vtt",
      "slides": ["same slide list as tier 1"]
    },
    "3": {
      "bitrate_kbps": 1,
      "summaries": [{"start": 0.0, "end": 60.0, "text": "..."}]
    }
  },
  "segments_4s": [
    {"index": 0, "start": 0.0, "end": 4.0, "content_label": null, "visual_importance": null}
  ]
}
```

The 4-second classifier grid duration must be documented against whatever Tier 0 DASH segment
duration is chosen — they need not be identical, but the mapping between them must be exact.
Tier 0 segment duration is 4.0s, identical to the classifier grid (Phase 1 design choice).

Tier 1 audio is `.m4a` (AAC-in-MP4), not raw `.aac`. Raw ADTS output from `ffmpeg` was found in
Phase 1 to silently truncate on some source streams; the MP4 container's timestamp/edit-list
handling preserves the full duration. See `docs/design_notes.md`.

### Content label (written into `segments_4s` above, by Phase 2)

Exactly three labels: `talking_head`, `slides_static`, `demo`. Plus a `visual_importance` float
in [0, 1]. Do not add a fourth label without updating this file first — the agent's hysteresis
logic is written against exactly these three.

### Rung (used by the simulator, Phase 3, and the agent, Phase 4)

A rung is `(tier: int, bitrate_kbps: float, segment_size_bytes: int)`. The simulator and the
agent must share this representation exactly, so agent code written against the simulator runs
unmodified later against a real bandwidth estimate.

### Bandwidth interface (used from Phase 4 onward)

```python
def get_bandwidth_estimate() -> float:  # kbps
    ...
```

Implemented three ways behind this one signature: replayed trace (simulation), UI-controlled
value (demo), real estimator (later prototype). The switching agent must only ever call this
interface — never read a trace file or a slider value directly.

---

## Repository structure

```
semstream/
  corpus/                    # source lecture videos + metadata (gitignored, large files)
  pipeline/                  # Phase 1: tier generation
  classifier/                # Phase 2: content labelling
  sim/                       # Phase 3: Sabre extension
  agent/                     # Phase 4: switching policy
  demo/                      # course-review demo (static HTML/JS)
  prototype/                 # Phase 5: real DASH prototype (optional, confirm before starting)
  eval/                      # Phase 6: evaluation harness + quiz materials
  data/
    manifests/
    traces/
    results/
  docs/
    design_notes.md
  CLAUDE.md                  # this file
  IMPLEMENTATION_PLAN.md     # phase-by-phase build plan and progress
```

---

## Known competing/adjacent work (context, not to be replicated)

- MPEG-21 DIA / modality conversion literature (1999–2005) — required manual authoring of
  alternative modalities. This project automates that.
- Modern ABR research (Pensieve, BOLA, Sabre) — adapts bitrate only, never modality.
- 2026 systems (talking-head reconstruction for video conferencing, satellite semantic
  communication) — substitute modality via generative reconstruction. SemStream does not
  reconstruct anything; see Hard Constraints above.
