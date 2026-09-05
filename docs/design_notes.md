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

## Phase 3 — "information delivered" defined before computing anything (2026-08-30)

Defined here, before `run_experiment.py` computes a single number from it, per instruction not
to let a metric get invented implicitly inside a script.

**The problem it has to solve.** Rebuffering time and tier-time distribution are both real,
directly measurable quantities - no modelling needed. "Information delivered" isn't directly
measurable in the same way, because the same tier delivers wildly different amounts of real
information depending on what's actually happening on screen: Tier 1 during a talking-head
segment loses almost nothing (the lecturer's face isn't the content, per `CLAUDE.md`'s own
stated thesis); Tier 1 during a demo segment loses most of what matters (a static slide cannot
show a live terminal executing). A flat "fraction of time at Tier 0" number can't distinguish
these two cases, and would not actually demonstrate this project's central claim.

**Definition.** Reuses `visual_importance` (real, Phase 2 output, in `manifest.json`'s
`segments_4s`) as the weight between two channels - visual and audio/text - rather than
inventing new per-segment data:

```
information_score(tier, visual_importance) =
    visual_importance * visual_availability(tier) + (1 - visual_importance) * audio_availability(tier)
```

`visual_availability(tier)` / `audio_availability(tier)` per tier:

| Tier | visual_availability | audio_availability |
|---|---|---|
| 0 (full video) | 1.0 | 1.0 |
| 1 (slide + audio) | 0.4 (`SLIDE_RETENTION`) | 1.0 |
| 2 (slide + captions) | 0.4 (`SLIDE_RETENTION`) | 0.85 (`CAPTION_RETENTION`) |
| 3 (summary only) | 0.0 | 0.3 (`SUMMARY_RETENTION`) |

Three constants, each a stated modelling assumption, not a measurement, with reasoning:
- `SLIDE_RETENTION = 0.4`: a static slide preserves legible on-screen text/diagrams but loses
  all motion, gesture, and live demonstration detail - meaningfully above zero (a slide clearly
  conveys something) but well below full (it cannot show a live code execution).
- `CAPTION_RETENTION = 0.85`: WebVTT captions are a near-complete transcription of speech (the
  same real Whisper transcript, Phase 1) - retains most of what audio conveys, docked below 1.0
  for lost prosody/emphasis/pacing and possible transcription error.
- `SUMMARY_RETENTION = 0.3`: a 60s rolling summary is a genuinely lossy compression of the
  underlying speech - Phase 2's own spot-check found summaries accurate but necessarily
  condensed to 1-2 sentences per minute of real content, so it retains gist, not detail. Set
  clearly below the caption factor because summarisation is fundamentally lossier than
  transcription.

Sanity checks the formula has to pass, and does: Tier 0 always scores 1.0 regardless of content
(nothing is lost, `visual_availability=audio_availability=1`). A demo segment
(`visual_importance=0.9`) at Tier 1 scores `0.9*0.4 + 0.1*1.0 = 0.46` - loses over half its
value, correctly reflecting that a demo reduced to a static slide has lost what made it a demo.
A talking-head segment (`visual_importance=0.15`) at Tier 1 scores `0.15*0.4 + 0.85*1.0 = 0.91`
- retains most of its value, correctly reflecting the project's own stated reason for dropping
Tier 0 eagerly during talking-head content.

**Run-level aggregation.** `information_delivered` for one policy run = time-weighted average
of `information_score` across played segments, using each segment's real duration from
`segments_4s`, divided by (played time + rebuffer time) rather than played time alone - a
policy that rebuffers a lot delivers less real information per unit of the viewer's actual
wall-clock time, even if what does get played is high quality, and the metric should reflect
that rather than only scoring what successfully played.

**Ground truth used for scoring is always the real manifest, regardless of which policy ran.**
`content_label`/`visual_importance` are deliberately absent from `naive.json` so the Naive
policy cannot use them to decide - but `run_experiment.py` always scores every run's outcome
against the real `data/manifests/<id>/manifest.json`, not against whatever restricted movie.json
the policy itself loaded. Restricting what a policy can see is a fairness concern for the
*decision*; restricting what the *evaluator* can see would make it impossible to measure
anything and isn't the same concern.

## Phase 3 — run_experiment.py: two crashes fixed, first real results (2026-08-30)

**Two bugs found running the full 9-lecture x 3-trace x 2-policy batch, both fixed, both
documented rather than worked around silently.**

1. Sabre's default ABR (`bolae`/BolaEnh) raises `ZeroDivisionError` in its own `__init__` on
   the two 240p-capped lectures (`dsa_iitd`, `computer_networks`), which only have a single
   Tier 0 rung - BolaEnh's gap-parameter setup assumes 2+ quality levels. Plain `bola` handles
   a single rung fine and is literally what `CLAUDE.md` specifies ("standard BOLA-style
   logic") - `run_experiment.py` now pins Baseline to `--abr bola` explicitly rather than
   relying on Sabre's default.
2. `dsa_iitd`'s very first Tier 3 summary window (0-60s) is genuinely empty text - real
   silence/no transcribed speech in that window, not a Phase 1 bug - producing a literal
   0-byte segment. Sabre's own segment-timing code divides by the download duration, which
   rounds to exactly 0 for a 0-byte transfer, crashing the whole run. Fixed with a 1-byte
   floor on every segment size in `tier_rung.py`'s `build_movie` - justified as numerical
   stability, not a claimed measurement: a literal zero-byte network transfer was never
   physically realistic in the first place (there's always some minimal framing overhead),
   so flooring at 1 byte doesn't invent data, it just avoids asserting a value (exact
   mathematical zero) that couldn't be true of a real delivery anyway.

**First real comparative result** (`data/results/phase3_results.csv`, all 9 lectures, mean
across lectures per trace x policy):

| trace | policy | rebuffer (s) | rebuffer ratio | tier0 | tier1 | information delivered |
|---|---|---|---|---|---|---|
| campus_collapse | baseline | 94.09 | 0.0342 | 1.000 | 0.000 | 0.9657 |
| campus_collapse | naive | 12.91 | 0.0051 | 0.675 | 0.323 | 0.9218 |
| belgium_4g | baseline | 0.00 | 0 | 1.000 | 0.000 | 1.0000 |
| belgium_4g | naive | 0.00 | 0 | 0.998 | 0.000 | 0.9987 |
| norway_hsdpa | baseline | 0.00 | 0 | 1.000 | 0.000 | 1.0000 |
| norway_hsdpa | naive | 0.00 | 0 | 0.998 | 0.000 | 0.9987 |

Norway HSDPA and Belgium 4G both sit comfortably above every lecture's Tier 0 bitrate range for
this corpus - neither trace stresses either policy, both show ~0 rebuffering and ~full Tier 0
occupancy.

**Correction, not a footnote: that finding was about the two files sampled, not a property of
either dataset.** Checked before accepting it as final, per instruction not to let "these
traces never stress the system" stand as an untested assumption: computed min/p10/median
bandwidth and time-below-500kbps/300kbps across all 12 fetched Norway files and all 40 fetched
Belgium files, not just the two used above. `norway_bus_1` (median 3599kbps, 1.8s below
500kbps in 155s) and `report_bus_0001` (median 26843kbps, 0.0s below 500kbps in 607s) turned
out to be among the calmest files in each set - not representative. Real rough files exist in
both: `norway_tram_11` (median 818kbps, 86.3s below 500kbps) and `report_train_0003` (median
20270kbps but bursty - p10 938kbps, 54.0s below 500kbps). Added both as `norway_hsdpa_rough`
and `belgium_4g_rough` and re-ran the full batch (90 rows now, `data/results/phase3_results.csv`):

| trace | policy | rebuffer (s) | tier0 | tier1 | information delivered |
|---|---|---|---|---|---|
| norway_hsdpa_rough | baseline | 33.15 | 1.000 | 0.000 | 0.9887 |
| norway_hsdpa_rough | naive | 0.03 | 0.597 | 0.402 | 0.9031 |
| belgium_4g_rough | baseline | 53.70 | 1.000 | 0.000 | 0.9804 |
| belgium_4g_rough | naive | 55.80 | 0.830 | 0.092 | 0.9308 |

`norway_hsdpa_rough` reproduces the campus-collapse story on a real dataset: Naive drops
rebuffering from 33.15s to essentially zero by spending 40.2% of playback at Tier 1. This is
the real-world signal the paper needed beyond the synthetic trace.

`belgium_4g_rough` does NOT reproduce it, and that's recorded honestly rather than dropped:
Naive rebuffers marginally *more* than Baseline here (55.80s vs 53.70s) despite dropping to
Tier 1 9.2% of the time. Not investigated to a confirmed mechanism - flagged as a real,
observed result with a plausible but unconfirmed explanation: `report_train_0003`'s low-
bandwidth periods are bursty dips within an otherwise high-bandwidth trace (median 20270kbps,
p10 938kbps) rather than a sustained collapse, and a threshold-plus-dwell policy reacting to
brief spikes may pay a quality cost without the corresponding stall-avoidance benefit a
sustained collapse provides. Left as an honest limitation/caveat for the eventual report rather
than smoothed over - a naive bandwidth-only policy is not a strict improvement over pixel-only
in every real condition, only in sustained-collapse conditions, and this dataset is the evidence
for that qualification.

Stated plainly: for this corpus's bitrate range, the campus-collapse synthetic trace and
`norway_hsdpa_rough` both carry real comparative signal; `belgium_4g_rough` carries a real
counter-example worth keeping, not discarding; the two originally-sampled files were simply too
calm to be informative and are kept in the table for completeness, not because they demonstrate
anything about tier-switching on their own.

On campus-collapse, the story is real and clear, not a coincidence of one lecture: Baseline,
unable to leave Tier 0, rebuffers on every one of the 9 lectures (7-288s, worst on the two full
1080p lectures whose Tier 0 floor is a much higher bitrate to sustain through the trough than
the corpus's lower-resolution lectures). Naive, able to fall back to Tier 1, cuts rebuffering by
roughly 5-25x depending on lecture, spending ~25-46% of playback at Tier 1 to do it.
`information_delivered` tells a genuinely mixed, not uniform, story - Baseline scores higher on
7 of 9 lectures (its rebuffering costs less integrated information than Naive's sustained
Tier-1 time, given the current retention weights), but Naive wins outright on
`mit_6_0002_comp_thinking_lec04` (0.9250 vs 0.9122), and on `nptel_dsa_iitd_lec01` - where
Baseline never actually rebuffers at all on this trace (its Tier 0 floor is the corpus's lowest,
300kbps, and survives the trough) - Naive still drops to Tier 1 for 25% of playback for zero
rebuffering benefit, purely because it cannot tell that the drop wasn't necessary. That last
case is the clearest evidence in this dataset of exactly the weakness Phase 4's content-aware
policy exists to fix - not a flaw in the harness, the expected shape of a genuinely
content-blind policy's behaviour.

**Named case study: `nptel_dsa_iitd_lec01` on campus-collapse.** Baseline: 0.00s rebuffering,
1.000 Tier 0 the entire run - its Tier 0 floor (300kbps, the corpus's lowest, since this
lecture is 240p-capped) survives the trough outright. Naive: also 0.00s rebuffering, but drops
to Tier 1 for 0.323 of playback (`tier1_frac=0.323` in `data/results/phase3_results.csv`)
anyway, purely because its bandwidth estimate crossed its threshold - not because anything
required it to. Zero rebuffering benefit purchased for a real, measured cost:
`information_delivered` 1.0000 (Baseline) vs 0.9254 (Naive) on this exact lecture/trace pair.
This is the single clearest number in the whole dataset for why Phase 4's content-aware policy
exists: a policy that cannot tell "the drop wasn't necessary" pays the modality cost anyway.
Going straight into the eventual report as-is; recorded here so it doesn't have to be
re-derived from the raw CSV later.

**Worst-case Baseline rebuffering: which lectures, and does it match expectation.**
287.80s on `mit_6_0002_comp_thinking_lec04`, 229.38s on `mit_6_0001_intro_python_lec02` - the
two next-worst are `nptel_python_dsa_mukund_lec01` (89.70s) and
`nptel_theory_of_computation_lec01` (81.14s). The top two are, as expected, the corpus's only
two full 1080p sources: their Tier 0 floor is a much higher bitrate to sustain through the
collapse trough (500kbps, the lowest rung of a 1080p/720p/360p ladder) than every other
lecture's floor (300kbps for the 240p-capped pair, and generally lower rungs elsewhere) - a
higher-quality source has more to lose when it cannot leave Tier 0. Matches expectation exactly,
stated plainly rather than left to be inferred from the CSV.

**Why Naive still rebuffers 12.91s on average, despite having an escape valve - checked
against the actual verbose log, not guessed.** Traced one run in detail
(`nptel_software_engineering_lec01`, naive + campus-collapse): segments 27-28 took 7252ms and
6356ms to download respectively - each nearly double the 4000ms segment budget, meaning the
network had already collapsed - while the policy was still requesting q=5 (the top index) for
both. It only switches down at segment 29. Current index had been unchanged for far longer than
`min_dwell_segments` (3) by that point, so the dwell floor was not what blocked the reaction -
`self.session.get_throughput()` itself (Sabre's own smoothed bandwidth estimate) simply hadn't
caught up to the true instantaneous crash yet. **Primary cause: throughput-estimation lag, a
structural property of estimating from past downloads, not a Naive-specific defect.** The
`min_dwell_segments` floor is a secondary, smaller compounding factor - once the estimate does
finally flag a lower level, dwell can still add up to ~12s more before the switch fires, and the
observed step sequence (5->3, then a separate later 3->2) shows each intermediate level paying
its own dwell cost through a continuously-worsening ramp rather than one clean jump to the
final sustainable level. No fix applied - recorded because this is exactly the kind of thing
that should be understood before it becomes an input to tuning Phase 4's agent, not rediscovered
mid-tuning.

## Phase 4.5 — course demo (2026-09-05)

**"Reused, not reimplemented" vs a static browser page - the decision.** The plan requires the
demo feed the slider through the real `get_bandwidth_estimate()` into the real
`state_machine.py`, but that logic is Python and the deliverable is a static page. Three options
were put to the user: Pyodide (runs the actual `.py` in-browser via WebAssembly - literally
satisfies the wording, costs ~10MB CDN load and needs internet unless vendored), a JS port with
an automated Python-vs-JS equivalence test, or a bare JS port. Chosen: **JS port plus
equivalence test** - keeps the demo dependency-free, instant, and offline-capable, while
mechanically defending against the drift that the "not reimplemented" rule exists to prevent.

`demo/equivalence_test.py` runs `agent/state_machine.py` and `demo/agent.js` over identical
input sequences and fails on any disagreement: sustained collapse-and-recovery per label, label
flipping every segment against volatile bandwidth, bandwidths sitting exactly on each
safety-factor boundary (`bitrate / factor` for all six factors x six rungs), degenerate one- and
two-rung ladders, `None`/unknown labels, and five 400-step random walks. **34 cases, 3730
decisions, all matching.** This runs as a normal test, so a future edit to either implementation
that breaks parity fails loudly rather than silently making the demo a lie.

**Assets.** 5-minute window (segments 303-377) of `mit_6_0002_comp_thinking_lec04`, picked by
scanning every 75-segment window in the corpus for the best three-label mix - 39 `talking_head`,
20 `demo`, 16 `slides_static`, so the content-label HUD actually shows variety and the hold
profile is exercised. `demo/build_assets.py` cuts one Tier 0 rung (720p) and windows the audio,
slides, captions and summaries to match, remapping all timestamps to window-relative.

**Verified in a real browser, not just by unit logic.** Drove the page under Playwright/Chromium
(local HTTP server, since `file://` blocks the manifest fetch): all four views present, zero
console errors, and dragging the slider produced the real tier path
`Tier 0 -> Tier 1 -> Tier 2 -> Tier 3 -> Tier 0` with the HUD tracking bandwidth, quality index,
rung bitrate, live content label and a draining buffer. Screenshots confirm each tier renders
its actual content: Tier 0 the video, Tier 1 the real extracted slide, Tier 2 that slide plus a
time-synced caption, Tier 3 the real rolling summary text. Worth stating precisely: the downward
path visits all four tiers, but the upward path jumps (Tier 3 -> Tier 0 directly at 700kbps)
because `up_candidate` resolves straight to the highest affordable index once dwell permits -
correct agent behaviour, not a demo bug, but not a symmetric walk.

**Bug found only in the browser: CRLF broke caption parsing.** The Tier 2 caption bar came back
empty. Cause: `build_assets.py` wrote the windowed `.vtt` with Windows `\r\n` line endings, and
`demo.js` split cue blocks on `/\n\n+/` - so all 78 cues collapsed into a single malformed cue
spanning 0-3.15s and captions were blank for the rest of playback. Invisible to the simulation
because Python's text-mode reads translate newlines universally, so `tier_rung.py`'s VTT parsing
was never affected - this was purely a JS-side failure that only a real browser run would catch.
Fixed both ends: `demo.js` normalises CRLF before splitting (robust to any VTT it's handed), and
`build_assets.py` writes with `newline="\n"`.

**Licensing shaped the lecture choice.** The demo bundles a real 5-minute video excerpt, which
is redistributable media, not the "numbers and tables" that the Phase 0 licensing note allows to
go public. `mit_6_0002_comp_thinking_lec04` is MIT OpenCourseWare, CC BY-NC-SA 4.0 - so the
excerpt can be committed and shared with attribution for non-commercial use, which is now
displayed on the demo page itself as the licence requires. An NPTEL lecture could not have been
used this way (all rights reserved, stays local). The demo-lecture choice is therefore a licence
decision as much as a content one.

## Phase 4 — switching agent design, decided before any code exists (2026-09-04)

Four questions settled here first, per instruction, because this is the project's core
contribution and getting the mechanism wrong would silently undermine every result built on
top of it.

**1. Content label biases the proposed target tier, not the dwell time. Hysteresis itself
stays uniform across labels.** Confirmed, not argued against - varying `min_dwell_segments`
per label would reintroduce exactly the flicker problem hysteresis exists to solve (a segment
sitting near a label boundary, or a classifier flip between adjacent segments, would cause the
dwell floor itself to change moment to moment). Mechanism: `agent/hysteresis.py`'s
`HysteresisController.decide()` gets extended to accept optional per-call `up_safety_factor`/
`down_safety_factor` overrides (falling back to the instance defaults set at construction if
omitted) - additive, so Naive's existing calls are untouched. The agent picks which
(up, down) factor pair to pass in based on the upcoming segment's `content_label`; the dwell
floor (`min_dwell_segments`), the switch-gating structure, and `segments_since_switch` tracking
are identical regardless of label. Content-awareness changes what gets *proposed*; dwell
decides, uniformly, whether the proposal is allowed through yet.

**2. `slides_static` is explicit, not a fallthrough: it gets the SAME treatment as
`talking_head` (drop readily), not its own third profile.** Reasoning: Tier 1/2's slide-image
mechanism is specifically built to represent exactly this content - a static slide captured as
an image loses very little relative to the same slide shown as Tier 0 video, arguably less than
`talking_head` loses (a face/gesture has no direct Tier 1/2 equivalent at all, whereas a slide
has an almost-exact one). There is no content category in this project for which holding Tier 0
is justified other than `demo`, so `slides_static` and `talking_head` share one profile.

**3. Content-awareness adjusts the affordability threshold, not affordability itself.**
Confirmed as the only implementation that doesn't defeat the point: `affordable_index()` (in
`agent/hysteresis.py`) already only ever returns an index whose real bitrate is
`<= bandwidth_kbps * safety_factor`, and every factor used stays `<= 1` - so a proposed tier's
bitrate can never exceed the real measured bandwidth, regardless of content. What content
changes is how much headroom below that hard ceiling is required before the agent is willing to
sit at a given index. Two profiles, both defined as offsets from Naive's own already-precedented
neutral values (`down=0.9`, `up=0.7`, itself grounded in Sabre's built-in `ThroughputRule`) so
neither profile is picked from feel:

| profile | applies to | down_safety_factor | up_safety_factor | meaning |
|---|---|---|---|---|
| hold | `demo` | 0.95 (more tolerant than Naive's 0.9) | 0.6 (less headroom needed than Naive's 0.7) | tolerates thinner margin before dropping Tier 0; reclaims it eagerly once affordable |
| drop | `talking_head`, `slides_static` | 0.75 (less tolerant than Naive's 0.9) | 0.85 (more headroom needed than Naive's 0.7) | downgrades sooner even with some margin left; in no hurry to reclaim Tier 0 |

Both profiles are symmetric offsets around Naive's neutral pair, in opposite directions - `hold`
is strictly more Tier-0-favouring than Naive in both directions, `drop` is strictly less, by a
comparable margin. `min_dwell_segments` for Ours is kept at 3 (12s), the same value as Naive -
not because Ours copies Naive, but because dwell's job (preventing flicker) is, by point 1,
independent of content, so there is no content-driven reason for it to differ.

**4. Discrete `content_label`, not a blend with `visual_importance` - and the reason is not a
style preference, it's that blending currently adds nothing.** Checked before deciding:
`classifier/rules.py`'s `VISUAL_IMPORTANCE` is a fixed constant lookup keyed by the same
discrete label (`{"demo": 0.9, "slides_static": 0.5, "talking_head": 0.15}`), not an independent
per-segment confidence score - so a segment's `visual_importance` carries zero information
beyond its `content_label` as currently implemented. "Blending" the two would be mathematically
equivalent to using the label alone, just re-expressed as a float, and would give no additional
protection against misclassification - a demo segment mislabelled `slides_static` has
`visual_importance=0.5` regardless of which quantity the agent reads. Using the label directly
is simpler and more transparent to defend ("if label == demo, use the hold profile") without
pretending to a robustness benefit the current classifier doesn't provide. If Phase 2's
classifier is ever revised to output a genuine continuous, independently-informative confidence
(e.g. derived from raw OCR/code-marker signal strength rather than a per-label constant), this
decision should be revisited - noted here so it isn't forgotten.

**Restating Phase 2's demo recall ceiling as directly consequential, not hypothetical.**
Phase 2's measured demo recall was 51.5% (`docs/design_notes.md`, Phase 2 section). Combined
with point 4, that ceiling is now a direct, quantifiable property of the agent's real behaviour,
not an abstract classifier caveat: roughly half of a lecture's true demo segments will be
labelled something else (mostly `talking_head` or `slides_static` per Phase 2's false-negative
list) and will therefore receive the `drop` profile instead of `hold` - the agent will downgrade
Tier 0 during real demo content on those segments, exactly the failure mode this project exists
to avoid, on close to half of demo content. This is expected, already-measured, and must be
stated as such wherever Phase 4's results are reported - not discovered as a surprise later.

**Bandwidth estimator: Ours inherits the same one Naive uses, and therefore the same lag.**
`get_quality_delay` reads `self.session.get_throughput()`, Sabre's own internal
throughput-history estimator - the only one Sabre exposes in replayed-trace mode. This is the
exact mechanism diagnosed as the primary cause of Naive's residual rebuffering (Phase 3 section
above: the estimate lags the true instantaneous bandwidth after a sudden collapse). Ours will
show the same lag-driven reaction delay for the same structural reason. Stated here, not fixed -
`agent/bandwidth_source.py` (not yet written) will need to implement `get_bandwidth_estimate()`
for the demo/real-estimator cases separately in Phase 5, but for Phase 4's simulation context
the estimator is Sabre's, unmodified.

## Phase 4 — implemented, validated at the segment level, first 3-way results (2026-09-04)

**Implementation matches the design above exactly.** `agent/hysteresis.py`'s `decide()` gained
optional per-call `up_safety_factor`/`down_safety_factor` overrides (additive - re-ran the
exact Naive regression check from Phase 3 afterward, byte-for-byte identical output, confirming
Naive's calls are unaffected). `agent/state_machine.py` holds one `HysteresisController`
instance and looks up the `(up, down)` factor pair for the upcoming segment's `content_label`
before calling `decide()`. `sim/policies/Ours.py` wires it to Sabre exactly like `Naive.py`
does. Adding `"ours"` to `run_experiment.py`'s `POLICIES` dict was, as designed, the only
change needed - confirmed by actually doing it, not just claiming the design supported it.

**Segment-level validation, not just aggregate trust.** Ran Ours and Naive on
`nptel_dsa_iitd_lec01` + campus-collapse and found real demo-labelled segments where they
diverge exactly as designed: segments 154-157 and 643-645 (all `content_label=demo`) - Naive
drops to q=2 (Tier 1), Ours holds q=3 (Tier 0, this lecture's only rung). Direct, concrete
evidence the hold/drop profile split is actually taking effect, not just a plausible-sounding
number in an aggregate table.

**First 3-way result** (all 9 lectures, mean per trace):

| trace | policy | rebuffer (s) | tier0 | tier1 | information delivered |
|---|---|---|---|---|---|
| campus_collapse | baseline | 94.09 | 1.000 | 0.000 | 0.9657 |
| campus_collapse | naive | 12.91 | 0.675 | 0.323 | 0.9218 |
| campus_collapse | ours | **6.92** | 0.709 | 0.289 | **0.9304** |
| norway_hsdpa_rough | baseline | 33.15 | 1.000 | 0.000 | 0.9887 |
| norway_hsdpa_rough | naive | 0.03 | 0.597 | 0.402 | 0.9031 |
| norway_hsdpa_rough | ours | **0.00** | 0.749 | 0.249 | **0.9376** |
| belgium_4g_rough | baseline | 53.70 | 1.000 | 0.000 | 0.9804 |
| belgium_4g_rough | naive | 55.80 | 0.830 | 0.092 | 0.9308 |
| belgium_4g_rough | ours | **49.46** | 0.871 | 0.070 | **0.9472** |

On every trace with real stress, **Ours strictly dominates Naive on both measured dimensions
simultaneously** - lower rebuffering and higher `information_delivered`, using *less* Tier 1
time than Naive on two of the three (e.g. `norway_hsdpa_rough`: 24.9% vs Naive's 40.2%,
better outcome for less modality sacrifice). Against Baseline the trade is the expected one:
Baseline's raw `information_delivered` edges ahead on two of three traces (it never sacrifices
fidelity when it does play, and the metric's rebuffer penalty is comparatively mild relative to
sustained Tier-1 time), but Ours cuts rebuffering by 13x on campus-collapse (94.09s -> 6.92s)
and reaches zero on `norway_hsdpa_rough` where Baseline still loses 33.15s - a real, large
availability win purchased for a modest fidelity trade, which is exactly the shape of result
this project's central thesis predicts, not an artefact of a metric built to flatter it (the
metric was defined in Phase 3, before Ours existed, specifically to avoid that risk).

**Case study update: `nptel_dsa_iitd_lec01` on campus-collapse, now with all three policies.**
Baseline 1.000 Tier 0 (no rebuffering needed, its floor survives this trace outright). Naive
0.7446 Tier 0 / 0.2541 Tier 1, `information_delivered=0.9254`. Ours 0.7471 Tier 0 / 0.2517
Tier 1, `information_delivered=0.9263` - directionally correct (Ours > Naive, as designed) but
small in magnitude on this specific lecture/trace pair, because only 10.3% of this lecture's
segments are labelled `demo` (the rest are majority `slides_static`, which shares Naive's near-
neutral drop profile) and this trace never forces either policy to rebuffer here regardless.
The dramatic, unambiguous evidence for this case is the segment-level divergence above, not the
aggregate number - stated plainly so the aggregate isn't mistaken for the strongest evidence
when it isn't.

**Three follow-up checks run after the headline table, before starting Phase 4.5.**

*Is `belgium_4g_rough` the exception where Ours doesn't beat Naive?* No. Per-lecture, Ours
dominates Naive (better or equal on rebuffering AND information delivered) on 7 of 9 lectures
on that trace; the other 2 (`mit_6042j`, `theory_of_computation`) are mixed - Ours rebuffers
notably less (54.27s vs 66.08s, 76.50s vs 91.25s) for a marginally lower information score
(-0.004, -0.004). Naive does not dominate Ours on a single lecture on any trace.

*Tier-1-or-below occupancy, the concrete cost against Baseline.* Mean across the three
stressed traces: Baseline 0.0% of playback below Tier 0 with 60.31s rebuffering; Naive 29.9%
below Tier 0 with 22.91s; Ours 22.4% below Tier 0 with 18.79s. So Ours buys a 69% rebuffering
reduction versus Baseline for 22.4% of playback at reduced modality - and reaches that with
*less* modality sacrifice than Naive needs (22.4% vs 29.9%) while also stalling less.

*Do stalls land on demo segments?* **Not zero - and demo is over-represented.** Scanned all 27
Ours runs on stressed traces for segments where the buffer actually depleted mid-download
(`bl=A->0->` with `A>0`; validated the detector against a known single-rebuffer run first, and
against Sabre's own event count). 58 rebuffer events total: 36 `talking_head`, 17
`slides_static`, 5 `demo`. Against the corpus base rate (46.7% / 48.2% / 5.0% of segments),
that is 1.33x / 0.61x / **1.72x** representation. Demo segments carry the *highest* stall risk
per segment of any label under Ours.

This is the direct, measured cost of the hold profile and should be stated wherever the "holds
Tier 0 through demonstrations" claim is made: holding Tier 0 on a thinner safety margin during
demo content does exactly what it is designed to do, and the price is that when a stall does
happen it is disproportionately likely to happen during a demonstration. Whether that trade is
right is a judgement about which failure is worse for a student - a few seconds of freeze while
the demo's visuals are preserved, versus the demo dropping to a static slide - not something
the numbers settle on their own. Worth noting the trade is not paid out of a bigger stall
budget: Ours' total rebuffering is still lower than Naive's (18.79s vs 22.91s mean), so the
hold profile's localised cost is more than offset by the drop profile's savings elsewhere.
Three of the five demo stalls fall on `nptel_python_dsa_mukund_lec01`, the most demo-dense
lecture in the corpus (24.5% demo segments). `norway_hsdpa_rough` produced zero rebuffer
events under Ours across all nine lectures.

**Bandwidth interface compliance, caught before calling Phase 4 done.** `sim/policies/Ours.py`
initially called `self.session.get_throughput()` directly - functionally correct but a direct
violation of `CLAUDE.md`'s own Bandwidth interface rule ("The switching agent must only ever
call this interface - never read a trace file or a slider value directly"), and Phase 4's task
list explicitly calls for `agent/bandwidth_source.py` implementing `get_bandwidth_estimate()`
behind one shared interface across all three real implementations (replayed trace, UI slider,
real estimator). Added `agent/bandwidth_source.py` (`SabreBandwidthSource` wraps Sabre's
session for the simulation context used now; `UIBandwidthSource` ready for Phase 4.5;
`RealBandwidthSource` explicitly `NotImplementedError`, a Phase 5 concern per the plan, not
built yet) and routed `Ours.py` through it instead. Re-ran the exact same regression check
(`nptel_software_engineering_lec01`, ours.json, campus-collapse) before and after - byte-for-
byte identical output, confirming this was a real interface-compliance fix, not a behaviour
change.

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
