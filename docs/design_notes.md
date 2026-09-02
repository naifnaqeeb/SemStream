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

**Word-timestamp cold-start artefact.** `faster-whisper` (model `small`, `word_timestamps=True`)
places a large spurious gap after the very first transcribed word of a lecture (observed: word 1
ends at 0.84s, word 2 starts at 17.38s, though both are spoken back-to-back) — a known model
warm-up quirk, confirmed isolated to word 1 of ~176 segments on the test video, not a recurring
pattern. Left as-is: it does not affect the segment-level Tier 2 VTT captions (unaffected, spot
-checked coherent), and Tier 3 summarisation aggregates text by time window rather than reading
individual word timestamps, so it has no downstream consequence. Not worth engineering around
for a single-word edge case.
