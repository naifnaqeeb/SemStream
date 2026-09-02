# Thresholds and rule structure are provisional, calibrated against real feature
# distributions from a handful of spot-checked lectures (see docs/design_notes.md
# for the numbers and the reasoning), not validated against ground truth labels.
#
# frame_diff is deliberately NOT used to decide the label: chalk-writing motion
# gives talking-head lectures a chronically elevated frame_diff (median 0.04-0.09
# across two chalk lectures), well above what the one verified demo video shows
# for its static annotated-code screens (median 0.0001). Motion is not a demo
# signal in this corpus.
#
# ocr_text_density alone cannot separate a printed slide (bullet-point prose)
# from a code/terminal screen either - both cover a similar fraction of the frame
# with recognisable text (~0.09-0.17 density across two confirmed slide lectures
# and the one confirmed demo lecture, no separation). code_marker_count (a count
# of Python-syntax substrings found in the same OCR pass's recognised text) is
# what actually distinguishes them.
#
# When neither confident OCR text nor a face is detected, frame_diff is used as
# a narrow tie-breaker only (not as a demo signal - see above): near-zero motion
# usually means a genuinely static slide OCR failed to read (confirmed by a real
# spot-checked example: frame_diff 0.0048, ocr_text_density 0.0479, just under
# threshold), while elevated motion with no detected face is usually an active
# lecturer whose face YuNet missed (side profile, writing, briefly out of frame)
# rather than an actual static slide.

OCR_HIGH = 0.05
CODE_MARKER_MIN = 2
AMBIGUOUS_FRAME_DIFF = 0.02

VISUAL_IMPORTANCE = {
    "demo": 0.9,
    "slides_static": 0.5,
    "talking_head": 0.15,
}


def classify_segment(frame_diff, face_count, ocr_text_density, code_marker_count):
    text_dominant = ocr_text_density >= OCR_HIGH
    face_present = face_count >= 1
    code_like = code_marker_count >= CODE_MARKER_MIN

    if text_dominant and code_like and not face_present:
        label = "demo"
    elif text_dominant:
        label = "slides_static"
    elif face_present:
        label = "talking_head"
    elif frame_diff >= AMBIGUOUS_FRAME_DIFF:
        label = "talking_head"
    else:
        label = "slides_static"

    return label, VISUAL_IMPORTANCE[label]
