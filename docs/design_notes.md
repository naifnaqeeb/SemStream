# SemStream — Design Notes

## Phase 0 — corpus licensing (2026-08-29)

6 of the 9 corpus videos are NPTEL content. NPTEL's own terms page
(`onlinecourses-archive.nptel.ac.in/modules/nptel/assets/html/terms.html`, saved verbatim as
`corpus/nptel_terms_of_use_raw.html`) asserts full copyright, all rights reserved, with no
Creative Commons grant anywhere in the document. This is used under non-commercial
academic/research use (BITE314L coursework, non-commercial arXiv preprint), not under an open
licence — the older claim that NPTEL is CC BY-SA (2012/2014) is not reflected in its current
terms and should not be relied on. Full reasoning and the exact quoted clause:
`corpus/LICENCE_NOTES.md`.

Consequence for anything leaving this machine: the raw corpus (`corpus/*.mp4`) stays local and
is never pushed to a public repo or included as redistributable material in any submission.
Only derived results — numbers, tables, the demo running against a couple of clips — go
anywhere public. The remaining 3 videos are MIT OpenCourseWare, CC BY-NC-SA 4.0, which is
solid and separately verified, but the same "nothing public goes beyond derived results" rule
is easiest to apply uniformly across the whole corpus rather than tracking two different rules
per video.

## Phase 0 — corpus resolution and demo-category videos (2026-08-29)

Resolution: `yt-dlp` was pinned at 2025.12.08 and 403'd on adaptive-stream formats for 8 of 9
videos; updating to 2026.08.19 resolved this outright (no client-spoofing needed). Re-verified
per-video true source cap via `-F` rather than assuming a uniform 1080p ceiling — 7 of 9 videos
cap below 1080p (as low as 320x240 for two 2008-era NPTEL uploads), so those videos' Tier 0
rung ladders in Phase 1 will be truncated to their real source resolution rather than inventing
an upscaled top rung. Full per-video table in `corpus/manifest.csv`.

Demo-category content match: manual `demo` tags for MIT 6.0001 and 6.0002 were assigned from
course reputation, not verified footage. A dense scan (16 frames across the full runtime, one
every ~180s) of both Lecture 1s found zero code-editor footage in either — both are entirely
talking-head/slide for their first lecture, with code shown only as static text on slides.
Swapped to MIT 6.0001 Lecture 2 ("Branching and Iteration") and MIT 6.0002 Lecture 4
("Stochastic Thinking"), each confirmed by the same scan method to contain genuine live
IDE/shell footage. `nptel_dsa_iitd_lec01` was also found mistagged during spot-check (majority
slide-driven, not chalk-talk as originally labelled) but was kept rather than swapped, since a
mixed-content video is a more realistic test case for the Phase 2 classifier than a
single-register one.

## Phase 1 — Tier 0 rung ladder per source cap (2026-08-29)

Standard rung ladder is `{1080p:1500kbps, 720p:900kbps, 480p:700kbps, 360p:500kbps,
240p:300kbps}` (extending the 1080/720/360 example in `CLAUDE.md` with 480p and 240p rungs so
capped sources still get a meaningful ladder rather than one rung). For each video, the ladder
is the top 3 standard rungs at or below that video's real source resolution cap (`-F`-verified
in Phase 0): full-res sources get `[1080p,720p,360p]`, matching the `CLAUDE.md` example exactly;
480p-capped sources get `[480p,360p,240p]`; the 720p source gets `[720p,480p,360p]`; the two
240p-capped sources get a single `[240p]` rung, since there is nothing genuine to put below it.
Bitrate figures are ffmpeg encode targets, not reported measurements — actual segment sizes in
the manifest are always read from the real encoded files via `ffprobe`/`stat`, never computed
from bitrate x duration.

Segment duration is 4.0s, made identical to the Phase 2 classifier grid rather than merely
mapped to it — simplest choice that satisfies the exact-mapping requirement in `CLAUDE.md`
with no index arithmetic needed later.

**ffmpeg segment-muxer bug.** `-f segment -segment_time 4` (and the equivalent explicit
`-segment_times "4,8,12,..."`) silently drops the first entry in the cut-point list as an
internal priming value, so the real first cut only takes effect at the second list entry —
the first output segment comes out roughly double length regardless of whether cuts are driven
by `-segment_time` or explicit `-segment_times`, and regardless of keyframe placement (verified
keyframes DO land exactly on the requested timestamps; the muxer's cut logic is what's off).
Confirmed reproducible with a minimal test clip before rewriting `encode.py`. Fix: prepend a
dummy near-zero cut point (`"0.001,4,8,12,..."`) to absorb the off-by-one. `encode.py` also
does the rung encode and the segmentation as two separate passes (encode once with forced
keyframes, then stream-copy-segment the result) rather than one combined pass, since combining
them made this bug harder to isolate from keyframe-placement timing and the two-pass form is
easier to verify independently.

**Tier 1 audio truncation.** Raw ADTS `.aac` output from `ffmpeg -c:a aac` silently truncated
one source's audio by ~130s out of 1680s (measured, not a rounding artefact — confirmed against
the source stream's own ffprobe duration). Wrapping the same encode in an `.m4a` (AAC-in-MP4)
container instead fixed it exactly, so Tier 1 audio is `.m4a`, not `.aac` as originally written
in `CLAUDE.md`'s schema example (now updated there and flagged).

**Slide-detection calibration.** A single global `ContentDetector(threshold=27, min_scene_len=3s)`
badly misfit the corpus's style range: a chalk-heavy MIT lecture produced 138 "slides" in 44
minutes (chalk/hand motion misread as cuts), while a code-editor NPTEL lecture collapsed to 2
slides across 27 minutes (gradual on-screen text changes have no hard-cut signature at all;
confirmed with `AdaptiveDetector` and thresholds down to 4, still only 2-6 scenes — a genuine
detector-suitability mismatch, not a threshold problem). Fix, both provisional pending eyeball
validation: `min_scene_len` raised to 20s (tames motion-noise over-triggering; does not fully
solve it — a chalk lecture will still read as slightly more "slide-dense" than a true slide deck),
and any detected span over `MAX_SLIDE_SECONDS` (180s) is split into equal sub-windows so Tier 1
still refreshes periodically through content a cut-detector cannot see. Full corpus re-run after
the fix: 10-62 slides per lecture, all in a plausible range by eye. Perfect slide segmentation
across chalk / whiteboard / code-editor / slide-deck styles is a harder problem than Phase 1
needs to solve outright; this is a bounded, documented compromise, not a claimed solution.

**Post-fix spot-check found the compromise still has real accuracy gaps (2026-08-30).** Manually
compared recorded slide images against fresh frames at their window's start/mid/end, on one
240p and one 1080p lecture:

- `nptel_computer_networks_lec01` slide_005 (191.6-359.1s): the window actually spans two real
  slides ("Introduction" then "Uses of Computer Network"); only the second is recorded, so the
  first ~100s of the window shows the wrong image. Confirms the 240p detection problem is not
  just under-counting (the fallback-split symptom above) but genuinely serving wrong content.
- Quantified across both 240p lectures: 14/46 (`computer_networks`) and 6/44 (`dsa_iitd`) slide
  entries are `MAX_SLIDE_SECONDS` fallback-split duplicates rather than genuine detections
  (30.4% and 13.6%) - the detector is failing on these sources more often than the raw slide
  count alone would suggest.
- `mit_6_0002_comp_thinking_lec04` slide_010 (616.3-727.5s, full 1080p source): spans THREE
  distinct visual states (talking-head, then a code slide, then a different text slide); only
  the middle one is recorded. Not a resolution problem - the `min_scene_len=20s` floor added
  to tame chalk-motion over-triggering also suppresses genuine fast transitions on lectures
  that switch content type quickly, even at full source quality.

Net: the Phase 1 slide-detection compromise trades one failure mode for another rather than
solving slide segmentation. Left as a known, documented Tier 1/2 delivery-quality limitation -
does not block Phase 2, since the content classifier reads frame-diff/OCR/face-detection
directly off the source video's 4s grid, independent of this Tier 1 slide extraction. Worth a
proper fix later (per-video-style detection, or a hybrid periodic+cut-triggered approach)
rather than further threshold tuning, which has now visibly hit diminishing returns.

## Phase 2 — content classifier (2026-08-30)

**OCR tool.** Nothing was installed (checked per the plan's own instruction, not assumed) - no
`pytesseract`, no `tesseract` binary, no `easyocr`. Installed Tesseract 5.4.0 via winget plus
the `pytesseract` wrapper. `opencv-python` 5.0.0 also turned out to have dropped the classic
`cv2.CascadeClassifier` Haar-cascade binding entirely (no bundled XML files either); replaced
with `cv2.FaceDetectorYN` (YuNet), a modern DNN face detector, using the standard OpenCV Zoo
ONNX model (`classifier/models/face_detection_yunet_2023mar.onnx`, ~230KB, small enough to keep
in the repo). Neither of these was assumable from the plan text; both confirmed empirically
before writing `features.py`.

**Rules went through two real revisions, not just threshold tweaks, driven by actual feature
distributions rather than guessing:**

1. First version used frame_diff (motion) as part of the demo signal. Wrong: chalk-writing
   motion gives talking-head lectures a chronically elevated frame_diff (median 0.038-0.093
   across two chalk lectures) - well above the threshold - while the one lecture already
   verified (Phase 0/1 spot-checks) to contain genuine live coding has near-zero motion (median
   0.0001, mostly a static annotated code screen). Motion doesn't mean "demo" here; it means
   "chalk". Result: chalk lectures came back 33-40% "demo" (wrong), and the verified demo video
   came back 98.5% "slides_static", 1.5% "demo" (also wrong, and the more serious failure since
   it's the one lecture with an independently confirmed ground truth).
2. Second version dropped frame_diff and used face-presence as the primary discriminator
   instead (text+face -> slides_static, text+no-face -> demo). Fixed both problems above, but
   broke two different lectures: `nptel_dsa_iitd_lec01` and `nptel_computer_networks_lec01` are
   confirmed (direct frame spot-check, Phase 0/1) to be prose slide-deck lectures with no
   picture-in-picture instructor overlay - so their slides are face-absent AND text-dominant,
   identical on paper to the verified demo video's profile. Both came back with 0%
   `slides_static` and roughly 57% "demo". ocr_text_density magnitude doesn't separate this
   either: checked real distributions and a prose bullet-point slide covers almost exactly the
   same fraction of the frame with recognisable text (~0.09-0.17 density) as a code screen.
3. Third version (current): added `code_marker_count` to `features.py` - a count of Python
   syntax substrings (`def `, `for `, `==`, `elif`, `self.`, etc.) found in the OCR pass's
   already-recognised text, at no extra Tesseract cost since the text was already being read
   and discarded. `classify_segment` now requires `code_marker_count >= 2` (not just 1, to
   resist single-token OCR noise) alongside text-dominance and face-absence to call something
   `demo`. Verified on the two confirmed prose-slide lectures plus the verified demo lecture
   before committing to a full re-run: 0% false-positive rate on both prose lectures at this
   threshold, versus 24.5% of the demo lecture's segments correctly flagged. The known
   trade-off: roughly 3/4 of the verified demo lecture's true demo segments still fall through
   to `slides_static` rather than `demo` (OCR at 640px width evidently doesn't always resolve
   short code fragments accurately/completely enough to hit two markers). This is a precision-
   over-recall choice, made deliberately: mislabelling demo as `talking_head` would be worse
   for the switching agent (which drops Tier 0 eagerly on `talking_head`) than mislabelling it
   as `slides_static`, and the rules structurally cannot produce that worse error.

`visual_importance` is a constant per label (`demo=0.9`, `slides_static=0.5`,
`talking_head=0.15`), directly reflecting `CLAUDE.md`'s own stated reasoning for why the
switching agent should treat these three categories differently - not derived from the
features, since there's no measured relationship to derive it from yet.

All of the above is provisional pending the plan's own required by-eye spot check (see the next
entry once that check is done) and is explicitly not a validated classifier - it is a first
pass built and revised against real evidence rather than assumption, which is what Phase 2's own
check criterion asks for at this stage.

**By-eye spot check (2026-08-30), per the plan's Phase 2 check.** 9 segments across 4 lectures
and all 3 labels, picked from spread-out timestamps (not just the first match). 7/9 correct or
defensible on first pass. 2/9 wrong: `nptel_dsa_iitd_lec01` segment 310 and
`mit_6_0002_comp_thinking_lec04` segment 396 were both dense-text slides with no face anywhere
in frame, but labelled `talking_head`. Root cause, confirmed from the code, not guessed: the
`else` branch fell straight to `talking_head` whenever OCR wasn't confidently text-dominant,
without ever checking whether a face had actually been detected - meaning any slide OCR failed
to read (dense maths, small subscripts) silently became "talking_head" by default. Fixed by
adding an explicit `face_present` check to that branch.

Re-checking the fix exposed a second-order problem: defaulting the remaining "no face, no
confident text" case straight to `slides_static` fixed the two wrong segments but wrongly
pulled `nptel_theory_of_computation_lec01` (verified 100% chalk/talking-head content, Phase 0)
down to 51.5% `slides_static`, because a lecturer briefly turned from the camera (face
undetected) is indistinguishable on these features from a genuinely illegible slide. Re-admitted
`frame_diff` as a narrow tie-breaker for this specific ambiguous bucket only (not as a demo
signal, which is the failure mode it caused earlier) - near-zero motion stays `slides_static`,
elevated motion (an active, off-camera-face lecturer) becomes `talking_head`. This is grounded
in the same real dsa_iitd example (frame_diff 0.0048, correctly low) and confirmed by re-running
the full corpus: theory_of_computation moved to 74.1% `talking_head` / 25.9% `slides_static`,
matching its known category far better.

Re-verified: the two originally-wrong segments now label correctly (checked directly against
the corrected manifest, not just re-reasoned). Also worth recording honestly: one of the two
"wrong" segments in the first pass (`mit_6_0002` segment 396) turned out, on closer inspection,
to have `face_count=1` in the exact frame the classifier sampled - my manual spot-check had
seeked to a slightly different timestamp within the same 4s window via `ffmpeg -ss` and was
looking at different content than what `features.py` actually evaluated. Only the
`dsa_iitd` instance was a confirmed bug from the feature data itself; the fix was applied
anyway since the `mit_6042j`/`nptel_theory_of_computation` aggregate evidence independently
justified it.

A 4-segment follow-up spot check across two more lectures (`mit_6042j_math_for_cs_lec01`,
`nptel_computer_networks_lec01`, `mit_6_0001_intro_python_lec02`) after the fix found no new
regressions - 4/4 correct or within the already-documented chalk text-density ambiguity (two
visually similar chalk-board frames from the same lecture can land on either side of the OCR
threshold depending on how much has been written by that point; noted, not fixed, since no
feature currently available distinguishes "sparse fresh chalk" from "a slide with little text"
in a principled way).

**Net assessment.** This is a genuinely revised, evidence-driven first pass, not a rubber-
stamped default. Known remaining limitations, all documented rather than hidden: (1) demo
recall is intentionally low (~1/4 of a verified demo lecture's true demo segments) in exchange
for near-zero false positives on prose slides; (2) the chalk-vs-slide boundary is soft where
OCR density is the only signal and a lecture's chalk text accumulates gradually; (3) all
thresholds (`OCR_HIGH=0.05`, `CODE_MARKER_MIN=2`, `AMBIGUOUS_FRAME_DIFF=0.02`) are calibrated
against this specific 9-video corpus's feature distributions, not against ground truth labels,
and should be revisited if the corpus grows or changes composition.

**Face detection model provenance (2026-08-30).** `classifier/models/face_detection_yunet_2023mar.onnx`
is the standard OpenCV Zoo YuNet model, fetched from
`https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx`.
Licensed MIT (per `https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/LICENSE`),
permissive, redistribution allowed - no restriction on keeping it committed in this repo.

**Demo recall/precision, measured properly (2026-08-30), superseding the earlier "~25%
recall / near-zero false positives" claim.** That earlier figure was not a measured recall at
all - it was `code_marker_count>=2` hit-rate against every segment of one video, i.e. treating
the whole video as ground-truth "demo," which conflates "a lecture that contains demo content"
with "a segment that is demo content." Flagged when asked to justify it, and replaced with an
actual measurement:

Method: densely sampled (15-25s intervals) the demo-containing windows of the three lectures
with real code content (`nptel_python_dsa_mukund_lec01`, `mit_6_0001_intro_python_lec02`,
`mit_6_0002_comp_thinking_lec04`), identified from a coarser first pass. 79 segments judged by
eye against a fixed rule (demo = a real multi-line code block or an actual terminal/IDE screen
is the frame's primary content; not-demo = prose bullets, an English-language description of an
algorithm, talking-head, or an abstract placeholder template like `<variable>`/`<condition>`
with no concrete syntax) - deliberately including both classes, not just segments the
classifier already called demo, so recall isn't measured against its own answer. Each
timestamp's exact segment index was then looked up against the real `manifest.json` label.

Result: **33 true demo segments in the sample, 17 caught -> 51.5% recall. 20 classifier-demo
calls in the sample, 17 correct -> 85.0% precision.** Both figures are measured on a sample
deliberately concentrated on demo-relevant windows, not a random/representative slice of the
corpus - that was the brief, and it means these numbers describe classifier behaviour where
demo content actually is, not overall corpus-wide accuracy.

This corrects the earlier claim in both directions: recall is higher than the "~25%"
impression suggested, but "near-zero false positives" was also an overstatement - that was
only true for the two pure prose-slide lectures with zero code content anywhere in them. On
lectures that do contain real code, there is a genuine ~15% false-positive rate (3/20 in this
sample), concentrated at demo/talking-head boundary transitions - e.g. a professor momentarily
at a laptop with code partly visible on a background screen, or a slide sandwiched between two
code slides that still contains algorithmic pseudocode. Full false-positive/false-negative list
retained in this session's working notes; the pattern is boundary ambiguity, not a systematic
directional bias.

**Consequence for Phase 3, written down now rather than left as an implicit assumption.** The
switching agent's demo-preservation behaviour in simulation is bounded by the classifier's
actual demo recall (51.5% measured above), not by true demo content. Concretely: Phase 3's
results will show the agent correctly holding Tier 0 for roughly half of a lecture's genuine
demo segments - the half the classifier actually labelled `demo` - and treating the other half
as whatever the classifier mislabelled them as (mostly `talking_head` or `slides_static` per
the false-negative list above), meaning the agent will drop tier on that content the same way
it would for genuinely non-demo content. This is not a Phase 3 bug if it shows up in the
results; it is the expected, already-measured consequence of Phase 2's classifier ceiling, and
must be stated as such in any eventual write-up rather than presented as if the agent were
reacting to ground-truth content labels.

## Phase 3 — trace sourcing: FCC dropped, Norway HSDPA + Belgium 4G/LTE used instead (2026-08-30)

`IMPLEMENTATION_PLAN.md` originally called for FCC broadband + Norway HSDPA + a custom trace.
FCC broadband was dropped after a real, documented sourcing problem, not skipped for
convenience: FCC's official host (`data.fcc.gov/.../data-raw-2016-jun.tar.gz`) now redirects
to a generic search page - the 2016 MBA raw release isn't there any more. Every third-party
"FCC" mirror checked (`confiwent/Real-world-bandwidth-traces`, both its `fcc_ori/` and
`fcc_and_hsdpa/` folders) turned out, on actual file-content inspection rather than folder-name
trust, to contain the same Oslo bus HSDPA log files mislabeled as FCC. Pensieve's and
park-project's own loaders both point to long-dead Dropbox links for their pre-processed FCC
set. archive.org has a genuine Wayback snapshot of the original raw FCC tar.gz, but it is the
*raw* per-household release, not pre-processed into throughput time series - substantial
parsing work with unknown scope, disproportionate to take on speculatively. Rather than
mislabel data (the exact mistake found in the third-party mirrors) or fabricate a
"broadband-shaped" synthetic trace and call it FCC, this was raised as a real blocker and the
user chose: keep two genuine, verified datasets and drop the FCC label rather than mislabel.

**Norway HSDPA** (kept, as originally planned): `confiwent/Real-world-bandwidth-traces`,
`cooked_3gp/norway_*` files. Verified genuine by reading actual file content (not just trusting
the repo) - throughput values sit in the expected HSDPA range, filenames and categories (bus,
car, ferry, metro, train, tram) match the authentic Riiser et al. "Commute path bandwidth
traces from 3G networks" dataset structure. 12 files fetched across all 6 categories, 2 each.

**Belgium 4G/LTE** (replaces FCC as the second real dataset): Ghent University
(`users.ugent.be/~jvdrhoof/dataset-4g/logs/logs_all.zip`), the same "bonus" dataset Pensieve's
own `traces/README.md` documents alongside FCC and Norway - live host, confirmed 200 OK,
392KB. 40 real log files (bicycle/bus/car/etc mobility logs), each row genuine
`[unix_ts_ms, elapsed_ms, latitude, longitude, bytes_received, duration_ms]` - real GPS-tagged
mobile throughput measurements, not a derivative or a re-labelling of something else.

**Trace format conversion, both real datasets.** Sabre's `network.json` wants
`{duration_ms, bandwidth_kbps, latency_ms}` entries. Norway's `[timestamp_sec, throughput_mbps]`
samples convert to one entry per consecutive pair: `duration_ms` = real gap between samples,
`bandwidth_kbps` = the earlier sample's throughput held constant across that gap (standard
practice for piecewise-constant throughput traces). Belgium's rows already carry a real
`duration_ms` directly; `bandwidth_kbps` is computed from the row's own real `bytes_received`
and `duration_ms` (`bytes*8/duration_ms`), not estimated. Neither trace format carries a
latency column, so a fixed representative value is used per set and stated as an assumption,
not measured data: 150ms for Norway (typical HSDPA/3G RTT), 60ms for Belgium (typical LTE RTT).

**Custom "campus WiFi collapse" trace, as required by the plan.** Deliberately synthetic and
never presented as measured data - unlike the two real sets above, this one is *supposed* to
be constructed. 61 entries, 4000ms steps (aligned to the project's own 4s segment grid, not a
Sabre requirement, just tidy), fixed RNG seed 20260830 for reproducibility. Five phases: stable
good WiFi (~8000kbps, 20ms latency, 15 steps) -> congestion ramp-up (bandwidth falling
8000->300kbps while latency climbs 20->250ms *ahead of* the bandwidth drop, matching real
congestion behaviour where buffers fill and RTT rises before throughput visibly collapses, 8
steps) -> collapsed/overloaded AP (~300kbps, ~275ms latency, noisy, 15 steps) -> recovery ramp
(300->7500kbps, latency back down to 25ms, 15 steps) -> stable again (8 steps). Models a
lecture-hall AP overloaded when a class lets out and floods it with devices, then clearing.
Verified functional, not just schema-valid: ran through Sabre's built-in BOLA against the
Tier-0-only baseline movie and produced a nonzero "total reaction time" (285.39, vs 0.0 for
both real traces run against the same movie in the same session) - confirms the trace actually
forces adaptive bitrate switching, not just a well-formed but inert file.

## Phase 3 — Naive policy: hysteresis, thresholds, buffer-blindness (2026-08-30)

**Why Naive needs hysteresis at all.** Caught before writing any code: pure per-segment
threshold-switching with zero hysteresis would oscillate on any trace with realistic jitter,
making Naive look artificially worse than Ours for reasons that have nothing to do with
content-awareness - that would demonstrate hysteresis helps, not that content-awareness helps,
which isn't the comparison Phase 3 exists to isolate. Naive gets the same class of
hysteresis/dwell mechanism Ours will get in Phase 4.

**Shared module, not a duplicate.** Written as `agent/hysteresis.py` now, ahead of Phase 4
formally starting, rather than as a standalone copy inside the Naive policy file. This is a
narrow, generic, self-contained utility (margins + dwell time only) - not `state_machine.py` or
`bandwidth_source.py`, so it doesn't chain Phase 4's actual work into Phase 3. Reusing one file
avoids the exact two-independent-readings-that-can-diverge risk already flagged once this
session for Sabre's manifest loader; the alternative (a deliberately identical standalone copy
now) would have created two files to keep in sync by hand. Phase 4's Ours policy will construct
its own `HysteresisController` instance with its own constants - the class takes
`min_dwell_segments`/`up_safety_factor`/`down_safety_factor` as constructor arguments, so Naive
and Ours share the mechanism but not the numbers, per instruction.

**Mechanism.** Two safety factors, not one, giving real asymmetry: `down_safety_factor` (0.9)
sets the level Naive drops to when the current index becomes unaffordable even under a lenient
read of throughput; `up_safety_factor` (0.7, stricter - needs throughput >= bitrate/0.7 ~= 1.43x
before upgrading, versus just >= bitrate/0.9 ~= 1.11x to avoid dropping) sets how much headroom
is required before climbing back up. Asymmetric margins (harder to go up than to come down) are
standard anti-flicker practice - the point is to stop a policy from immediately re-climbing
right after a legitimate downgrade on the next segment's noisy estimate. On top of the margins,
a hard `min_dwell_segments` (3 segments = 12s) blocks ANY switch, up or down, until that many
segments have passed since the last one - the margins alone reduce flicker probability, the
dwell floor removes it structurally.

**Numbers grounded in precedent, not feel - answering "did you tune the baseline to lose"
before it's asked.** `down_safety_factor = 0.9` is not invented: it is Sabre's own built-in
`ThroughputRule.safety_factor`, read directly from `sim/src/sabre.py` (used identically there
for exactly the same purpose - safety margin when deciding if current throughput can sustain a
rung). `up_safety_factor = 0.7` is the one genuinely chosen constant, set to give real
asymmetry against the 0.9 down factor rather than picked independently. `min_dwell_segments = 3`
(12s) is short enough that the campus-collapse trace's ~32s ramp phases (8 x 4s steps) still
produce visible multi-step adaptation rather than one instant jump, long enough to filter
single-segment jitter - chosen by looking at that trace's own timing, not a round number picked
by feel. **Bandwidth thresholds are not a separate invented lookup table at all**: Naive walks
the real per-lecture `bitrates_kbps` ladder that `tier_rung.py` already computed from real
measured tier/rung bitrates for whichever lecture is running - so the "threshold" between, say,
Tier 1 and Tier 0's lowest rung genuinely is that lecture's own real Tier 1 bitrate and real
Tier 0 lowest-rung bitrate, self-calibrating per lecture rather than one universal number that
might not fit every lecture's actual encode. Naive's own constants live in `sim/policies/Naive.py`,
independent of whatever Ours ends up using in Phase 4.

**Buffer-blind, deliberately, not by default.** Naive reads `self.session.get_throughput()`
only - it never calls `get_buffer_level()`. Three reasons, not one: (1) `CLAUDE.md`'s own
definition of this baseline is explicit - "content-blind modality switching on **bandwidth
thresholds only**"; buffer-awareness isn't part of what's being represented. (2) Buffer-based
reasoning is what the pixel-only Baseline (built-in Sabre BOLA) already represents - giving
Naive buffer-awareness too would blur the one dimension each baseline is supposed to isolate.
(3) Real commercial fallback behaviour (a video call degrading to audio-only under a bad
connection) is legitimately modelled as reacting to measured network conditions, not local
buffer occupancy - that's what "represents commercial fallbacks" in `CLAUDE.md` is pointing at.

**Verified functional, not just "it ran".** `sim/policies/Naive.py` against
`movies/nptel_software_engineering_lec01/naive.json` and the campus-collapse trace: holds the
top index (q=5) through the whole stable-bandwidth phase, steps down 5->3->2 with the dwell
floor visibly respected (no single-segment reversals) through the collapse, holds the floor for
the full low-bandwidth trough, steps back up 2->3->4->5 on recovery - checked across the full
421-segment run (the trace loops, ~7 collapse/recovery cycles fit in one lecture's length), zero
single-segment oscillation anywhere. 1 rebuffer event total (3.09s, 0.18% ratio) - present
because the trace genuinely does collapse hard, not because the policy flails.

## Phase 3 — Sabre rung model: resampling Tiers 1-3, and the pixel-only baseline (2026-08-30)

**Read before writing any code, per the plan.** Sabre represents a rung as a single integer
index into a flat `bitrates_kbps` list; `segment_sizes_bits[segment_index][quality_index]`
gives the real bytes for that segment at that quality. Its buffer model
(`get_buffer_level()`) assumes every quality index at a given segment index covers the *same*
slice of playback time - that's what makes "download this segment at this quality" a
well-formed question. Confirmed by running the unmodified example (`example/movie.json` +
`example/network.json`, default BOLA): 0 rebuffering, 199 chunks played, output sane.

**Why naive concatenation was wrong (caught before writing `tier_rung.py`, not after).** Tier
0's rungs satisfy Sabre's same-time-slice assumption (each is the same 4s segment at different
fidelity). Tiers 1-3 don't: a slide can hold for 40s+, a Tier 3 summary window is 60s. Simply
appending each tier's own native segment list as extra quality indices would let a single
segment index mean a wildly different amount of real playback time depending which quality was
selected - breaking the buffer model at the root, not just producing a slightly-off number.

**Fix: resample Tiers 1-3 onto Tier 0's 4.0s grid** (the same grid as `segments_4s`, already
exactly aligned by Phase 1 design). For segment index `i`, each tier's byte cost is "how many
*new* bytes are needed to get through this 4s slice" - near-zero mid-slide/mid-summary, a real
spike exactly where new content arrives. Every number is a real measured file size, not an
average or an estimate:

- Tier 1 (audio + slides): `bytes[i] = audio_share[i] + slide_spike[i]`.
  `audio_share[i] = audio_total_bytes * (seg_i.end - seg_i.start) / duration_seconds` (audio is
  continuous, so its cost is proportional to real elapsed time) - `audio_total_bytes` read from
  the real `.m4a` file's own size, NOT derived from `manifest.json`'s `tiers.1.bitrate_kbps`,
  since that figure is audio+slides already blended together and can't be split back apart.
  `slide_spike[i]` = real byte size of `slide_NNN.jpg` for any slide whose `start` falls inside
  `[seg_i.start, seg_i.end)`, else 0.
- Tier 2 (slides + captions, no audio): `bytes[i] = caption_bytes[i] + slide_spike[i]`.
  `caption_bytes[i]` = summed real serialised byte size of whichever VTT cues have their `start`
  inside `[seg_i.start, seg_i.end)` - computed from real cue text/timestamps, not a per-second
  average of the whole `.vtt` file. `slide_spike[i]` shares the same slide list as Tier 1.
- Tier 3 (summaries only): `bytes[i]` = real UTF-8 byte length of the summary text for segments
  where a new 60s window begins, 0 elsewhere.

Nominal `bitrates_kbps` per tier (used by Sabre's built-in ABR algorithms for utility
calculations, e.g. BOLA's log-utility - confirmed from Sabre's source that this is separate
from and doesn't have to equal the real per-segment download size) stays the existing real
measured `tiers.N.bitrate_kbps` already in each lecture's `manifest.json`.

**Pixel-only baseline: restriction lives in `tier_rung.py`, not in policy code or
`run_experiment.py`.** Checked Sabre's actual loading path (`sabre.py` `main()`):
`manifest = load_json(args.movie)` then `SessionInfo.manifest = manifest` runs once per
process, from one file path, before any ABR policy object exists. There is no per-call
mechanism for a policy to see a restricted view of a shared manifest at runtime - whatever
manifest a process loaded IS the global truth for that run. That means "the baseline policy's
code just never selects a Tier 1-3 index" is an unenforced convention: a bug, or a lazy reuse
of a built-in Sabre ABR (Bola, ThroughputRule) as the pixel-only baseline, would silently have
Tier 1-3 available to it with nothing to catch it, quietly invalidating the whole point of the
comparison. `tier_rung.py` will therefore build two manifest JSON files per lecture - a full
one (all tiers, for Naive and Ours) and a Tier-0-only one (for Baseline) - and
`run_experiment.py` points each policy's Sabre invocation at the correct file. The baseline
becomes structurally incapable of touching Tier 1-3, because those bytes don't exist in the
file it loaded, not because its code happens to behave.

**Known conservative approximation: `slide_spike[i]` only charges a slide's bytes at its
natural start segment.** If the agent is in Tier 0 while a slide starts, then switches into
Tier 1/2 mid-slide, that slide has already "aired" at segment `i` with `slide_spike[i]`
charged there regardless of which tier was active - so the segment where the agent actually
switches in gets charged zero for a slide image it does, in reality, still need to fetch on
first arrival at Tier 1/2. This understates the real cost of switching exactly at the moments
switching matters most (a fresh tier-1/2 view mid-slide still needs that slide's image). Not
fixable with a static per-segment table alone, since the true cost depends on simulation
history (which segment a given policy run actually switched on) - out of scope for
`tier_rung.py`, which only has access to the manifest, not a policy's trajectory. Left as a
known approximation for Phase 3. It affects Baseline, Naive, and Ours identically (none of the
three get "switch-in credit" from this table), so the three-way comparison stays fair even
though all three policies' absolute numbers are slightly optimistic in the same direction.
Flagged as a candidate fix for Phase 4: the agent already holds state across per-segment calls,
and which slide is active at segment `i` is itself a static, precomputable fact (independent of
simulation history) even though *whether the agent just switched into a tier* is not - so the
agent can look up the active slide's real byte size from the manifest and add a one-time
corrective delay on its own switch-in segments, without needing any change to `tier_rung.py`'s
output.

**Naive manifest must not carry `content_label`, or "content-blind" isn't actually blind.**
Same structural-enforcement logic as the Baseline split: a Naive policy that is merely asked
nicely not to read `content_label` is one careless implementation away from quietly not being
content-blind. `tier_rung.py` will therefore produce three manifest views per lecture, not two:
a Tier-0-only view (Baseline), a full-tiers view with no `content_label` field anywhere in the
JSON (Naive), and a full-tiers view that does include per-segment `content_label` (Ours/Phase
4). Naive and Ours share identical bitrate/tier/segment-size data - the only difference is
whether the `content_label` key exists in the file at all - so the split costs no duplicated
resampling logic, only a second, smaller JSON write per lecture.

**`sabre.py` modified: `ManifestInfo` now carries `tiers` and `content_labels`.** Without this,
Sabre's own manifest loader silently dropped `tier_rung.py`'s extra JSON fields on load (its
`ManifestInfo` namedtuple only kept `segment_time`/`bitrates`/`utilities`/`segments`), which
would have left the Naive policy with no way to know which quality index belongs to which tier.
Considered having each policy class load `movie.json` a second time on its own instead, but
rejected that: two independent readings of the same file are two things that can quietly
diverge later, and `CLAUDE.md`'s shared-schema rule is explicit that phases must not develop
divergent readings of the same data. Fixed at the one canonical load path instead.

Exact diff, in `sim/src/sabre.py`:
```python
# before
ManifestInfo = namedtuple('ManifestInfo', 'segment_time bitrates utilities segments')
...
manifest = ManifestInfo(segment_time = manifest['segment_duration_ms'],
                        bitrates     = bitrates,
                        utilities    = utilities,
                        segments     = manifest['segment_sizes_bits'])

# after
ManifestInfo = namedtuple('ManifestInfo', 'segment_time bitrates utilities segments tiers content_labels')
...
manifest = ManifestInfo(segment_time   = manifest['segment_duration_ms'],
                        bitrates        = bitrates,
                        utilities       = utilities,
                        segments        = manifest['segment_sizes_bits'],
                        tiers           = manifest.get('tiers'),
                        content_labels  = manifest.get('content_labels'))
```
Both new fields use `dict.get()`, defaulting to `None` when a `movie.json` doesn't define them
- purely additive, no existing field touched. Verified genuinely additive, not just by reading
the diff: re-ran the exact Baseline smoke test from before the change
(`movies/nptel_software_engineering_lec01/baseline.json` through unmodified built-in BOLA) and
it came back byte-for-byte identical on every output line (698.905814 time-average bitrate,
1684.347126 play time, 421.086782 chunks, 0 rebuffering, 400.000000 bitrate change,
-449.267132 estimate). Also re-ran Sabre's own unmodified `example/movie.json` (no `tiers`/
`content_labels` keys at all) against `example/network.json` - identical to the very first
task-1 run (leq estimate count 110, estimate -234.281143, rampup 3.252272, reaction time
61.261360). A standard Sabre manifest still loads exactly as it did before this repo touched
Sabre at all.

**Word-timestamp cold-start artefact.** `faster-whisper` (model `small`, `word_timestamps=True`)
places a large spurious gap after the very first transcribed word of a lecture (observed: word 1
ends at 0.84s, word 2 starts at 17.38s, though both are spoken back-to-back) — a known model
warm-up quirk, confirmed isolated to word 1 of ~176 segments on the test video, not a recurring
pattern. Left as-is: it does not affect the segment-level Tier 2 VTT captions (unaffected, spot
-checked coherent), and Tier 3 summarisation aggregates text by time window rather than reading
individual word timestamps, so it has no downstream consequence. Not worth engineering around
for a single-word edge case.
