# SemStream: interim findings (Phases 0 to 4.5)

Status note for Review 2. Covers everything built and measured so far: corpus, tier generation,
content classifier, simulation harness, switching agent, and the course demo. Phase 5 (real DASH
prototype) is deliberately not started. Phase 6 (evaluation) is split and on hold pending review
scheduling.

Every number in this document comes from an actual run against actual data. Where something has
not been measured, it says so. Modelling assumptions are labelled as assumptions, not results.

---

## 1. What the system does

Adaptive bitrate streaming degrades a lecture by lowering pixel quality within one video
representation. Below the lowest bitrate rung, the only remaining behaviours are rebuffering or
session failure, which is a loss of access to instruction rather than a loss of visual polish.

SemStream degrades **modality** instead. Each lecture is decomposed offline into four
representations of the same content, and a switching agent selects between them per segment
using estimated bandwidth and a content label for the upcoming segment.

| Tier | Representation | Measured bitrate range across the corpus |
|---|---|---|
| 0 | Full video, standard quality rungs | 300 to 1500 kbps |
| 1 | Slide images + audio | 67 to 87 kbps |
| 2 | Slide images + timed captions | 1.6 to 21.6 kbps |
| 3 | Rolling timestamped text summary | ~0.04 kbps |

Nothing is reconstructed. A slide image is a real extracted frame, a caption is a real
transcription, a summary is generated from that real transcript. No generative model
resynthesises a face, a video frame, or audio. This is the distinction from 2026 systems that
substitute modality by reconstructing an approximation of the original signal.

---

## 2. Corpus (Phase 0)

Nine lectures, 6.47 hours, 5831 four-second segments. Three content categories with three
lectures each: talking-head-heavy, slide-heavy, and demonstration/code-heavy.

Two findings worth carrying into the report:

**Source resolution is not uniform, and the tier ladder respects that.** Only two of nine
sources are genuinely 1080p. Seven cap lower, two of them at 240p. Rather than upscale to a
nominal 1080p rung, each lecture's Tier 0 ladder is truncated to what its source actually
supports, so no reported segment size describes an invented quality level. The two 240p lectures
have a single Tier 0 rung.

**Licensing is not uniform either.** Six of nine lectures are NPTEL. NPTEL's own terms page
asserts copyright with all rights reserved and contains no Creative Commons grant, contrary to
the commonly repeated claim that NPTEL is CC BY-SA. The three MIT OpenCourseWare lectures are
CC BY-NC-SA 4.0. Consequence: the raw corpus stays local and is never redistributed. Only
derived results leave the machine. This directly determined which lecture the demo could bundle
(see section 8).

A methodological note that generalises: the initial candidate list was assembled from course
reputation, and two of the three demonstration-category lectures turned out, on frame-by-frame
inspection of their entire runtime, to contain no live coding at all. They were replaced with
later lectures from the same courses that verifiably do. Category assignment by reputation is
not reliable and was replaced with verification.

---

## 3. Tier generation (Phase 1)

All four tiers generated for all nine lectures, with every Tier 0 segment size measured from the
real encoded file rather than estimated from bitrate multiplied by duration.

Three defects were found and fixed during this phase, each of which would have silently
corrupted downstream data:

1. **ffmpeg's segment muxer drops the first cut point** in a `-segment_times` list, treating it
   as an internal priming value. Every Tier 0 rung's first segment came out roughly double
   length. Fixed by prepending a dummy near-zero cut point.
2. **Raw ADTS `.aac` audio output silently truncated** one source by about 130 seconds out of
   1680. Wrapping the identical encode in an `.m4a` container preserved the full duration.
   Tier 1 audio is therefore `.m4a`, a documented deviation from the original schema.
3. **A single global slide-detection threshold badly misfit the corpus.** A chalk-heavy lecture
   produced 138 "slides" in 44 minutes from hand and chalk motion, while a code-editor lecture
   collapsed to 2 slides across 27 minutes because gradual on-screen text changes have no
   hard-cut signature at all. Mitigated by raising the minimum scene length and splitting any
   detected span longer than 180 seconds.

**Known remaining limitation.** The slide-detection mitigation trades one failure mode for
another rather than solving slide segmentation. Verified by direct inspection: on one 240p
lecture a single detected "slide" window spans two genuinely different slides, so the stored
image is wrong for roughly the first 100 seconds of its own window; on a 1080p lecture another
window spans three distinct visual states. This affects Tier 1 and Tier 2 delivery quality. It
does not affect any result in this document, because the content classifier reads the source
video directly rather than the extracted slides.

---

## 4. Content classifier (Phase 2)

Rules-based, three features per segment: frame-difference magnitude, OCR text density, and face
count. Labels every segment `talking_head`, `slides_static`, or `demo`, plus a
`visual_importance` score.

Corpus label distribution: 2725 `talking_head` (46.7%), 2813 `slides_static` (48.2%), 293 `demo`
(5.0%).

The rules went through two evidence-driven revisions, both prompted by measured failure rather
than intuition:

- Motion was initially treated as a demo signal. It is not. Chalk writing gives talking-head
  lectures a chronically elevated frame-difference (median 0.038 to 0.093), well above the
  threshold, while the one lecture independently verified to contain live coding is nearly
  static (median 0.0001) because its code sits on a fixed annotated screen. Motion was removed
  from the label decision entirely.
- Face presence alone then misclassified prose slide decks as demos, because a slide deck with
  no picture-in-picture instructor is, on those features, indistinguishable from a code screen.
  OCR text density does not separate them either (both cover 0.09 to 0.17 of the frame with
  recognisable text). Resolved by counting programming-syntax tokens in the text the OCR pass
  already produced.

**Measured performance, and the ceiling it imposes.** Against 79 segments hand-labelled from
densely sampled frames concentrated on the demo-relevant windows of the three code-bearing
lectures: **51.5% recall (17 of 33 true demo segments) and 85.0% precision (17 of 20 demo
calls)**. These are measured on a sample deliberately concentrated where demo content is, not a
random slice, so they describe behaviour where it matters rather than corpus-wide accuracy.

This is consequential rather than academic. The switching agent consumes the discrete label, so
roughly half of true demo content is labelled something else and receives the eager-drop
profile instead of the hold profile. Any claim that the system "holds Tier 0 through
demonstrations" is bounded by that 51.5%, and should be stated that way.

All thresholds are provisional, calibrated against this corpus's feature distributions rather
than validated against ground truth.

---

## 5. Simulation harness (Phase 3)

Built on `UMass-LIDS/sabre`. Sabre represents a rung as a single index into a flat bitrate list
and assumes every quality index at a given segment covers the same slice of playback time.
Tier 0's rungs satisfy that. Tiers 1 to 3 do not, since a slide can hold for 40 seconds and a
summary window is 60.

**Resampling.** Rather than concatenating each tier's native structure, Tiers 1 to 3 are
resampled onto Tier 0's 4-second grid. For each segment, a tier's cost is the new bytes needed
to get through that slice: near zero mid-slide, a real spike where a new slide, caption cue or
summary window actually arrives. Audio is charged proportionally to elapsed time. Every figure
is a real file size or a real UTF-8 byte length.

**Policy isolation is structural, not conventional.** Sabre loads one manifest per process,
before any policy exists, so a policy asked politely not to read a field is one careless edit
away from reading it. Three manifest files are generated per lecture instead: the pixel-only
baseline gets a Tier-0-only manifest and literally cannot select a lower tier; the content-blind
policy gets all tiers but no `content_label` field anywhere in the file; only the content-aware
policy gets labels.

**Traces.** The plan called for FCC broadband. FCC's raw 2016 release is no longer hosted at its
documented URL, and every third-party mirror inspected contained Oslo HSDPA files mislabelled as
FCC, verified by reading file contents rather than trusting folder names. Rather than mislabel
data or synthesise a "broadband-shaped" trace, FCC was dropped and replaced with a second
genuine dataset. Final set: Norway HSDPA (Oslo commute traces), Belgium 4G/LTE (Ghent
University), and one synthetic campus-WiFi-collapse trace built to model a lecture-hall access
point overloaded when a class lets out.

A second sampling lesson: the first Norway and Belgium files chosen turned out to be among the
calmest in each dataset, which briefly suggested the real traces could not stress the system at
all. Checking bandwidth statistics across all 12 Norway and all 40 Belgium files found genuinely
rough ones, which were added. The conclusion changed once the sampling was checked.

**"Information delivered", defined before it was computed.** Rebuffering and tier occupancy are
directly measurable. Information delivered is not, because the same tier costs very different
amounts depending on content: Tier 1 during a talking-head passage loses almost nothing, while
Tier 1 during a demonstration loses most of what matters. The metric weights two channels by the
segment's `visual_importance`:

```
information_score(tier, v) = v * visual_availability(tier) + (1 - v) * audio_availability(tier)
```

with `visual_availability` of 1.0 / 0.4 / 0.4 / 0.0 and `audio_availability` of 1.0 / 1.0 / 0.85
/ 0.3 for Tiers 0 to 3. The three retention constants are stated modelling assumptions, not
measurements. Run-level score is the time-weighted average across played segments divided by
playback time plus rebuffering time, so stalls dilute it. Tier 0 always scores 1.0, a demo
segment at Tier 1 scores 0.46, and a talking-head segment at Tier 1 scores 0.91.

Defined and committed before the content-aware policy existed, specifically so the metric could
not be shaped to flatter it.

---

## 6. Results

135 runs: 9 lectures x 5 traces x 3 policies. Means across lectures.

| Trace | Policy | Rebuffering | Tier 0 | Below Tier 0 | Information delivered |
|---|---|---|---|---|---|
| campus_collapse | baseline | 94.09 s | 1.000 | 0.0% | 0.9657 |
| campus_collapse | naive | 12.91 s | 0.675 | 32.5% | 0.9218 |
| campus_collapse | **ours** | **6.92 s** | 0.709 | 29.1% | **0.9304** |
| norway_hsdpa_rough | baseline | 33.15 s | 1.000 | 0.0% | 0.9887 |
| norway_hsdpa_rough | naive | 0.03 s | 0.597 | 40.3% | 0.9031 |
| norway_hsdpa_rough | **ours** | **0.00 s** | 0.749 | 25.1% | **0.9376** |
| belgium_4g_rough | baseline | 53.70 s | 1.000 | 0.0% | 0.9804 |
| belgium_4g_rough | naive | 55.80 s | 0.830 | 17.0% | 0.9308 |
| belgium_4g_rough | **ours** | **49.46 s** | 0.871 | 12.9% | **0.9472** |
| norway_hsdpa (calm) | all three | 0.00 s | ~1.000 | ~0.2% | ~0.999 |
| belgium_4g (calm) | all three | 0.00 s | ~1.000 | ~0.2% | ~0.999 |

**The core result.** On every trace that applies real stress, the content-aware agent strictly
dominates the content-blind one on both measured dimensions at once: less rebuffering *and*
higher information delivered. On two of the three it achieves this while spending *less* time
below Tier 0 than the content-blind policy needs, which is the point. Knowing which segments can
afford to be degraded means fewer segments have to be.

Aggregated across the three stressed traces: baseline 0.0% below Tier 0 with 60.31 s
rebuffering, naive 29.9% with 22.91 s, **ours 22.4% with 18.79 s**. Against the pixel-only
baseline, the agent buys a 69% reduction in rebuffering for 22.4% of playback at reduced
modality.

**A real counter-example, kept rather than discarded.** On `belgium_4g_rough` the content-blind
policy rebuffers slightly *more* than the pixel-only baseline (55.80 s against 53.70 s) despite
dropping tier 17% of the time. That trace's low-bandwidth periods are short bursty dips inside
an otherwise fast connection rather than a sustained collapse, and a threshold-plus-dwell policy
reacting to brief dips pays a quality cost without buying the stall-avoidance a sustained
collapse would provide. A naive bandwidth-only fallback is therefore not a strict improvement
over pixel-only ABR in all real conditions, only in sustained-collapse conditions. The
content-aware agent still beats both on that trace.

**Where the calm traces sit.** Two of the five traces never stress any policy at this corpus's
bitrate range. They are reported for completeness and to show the harness behaves sanely under
easy conditions, not as evidence about tier switching.

---

## 7. Two findings that carry the argument

### 7.1 Case study: `nptel_dsa_iitd_lec01` on campus-collapse

This lecture's Tier 0 floor is the corpus's lowest, 300 kbps, because the source is 240p-capped.
It survives the collapse trough outright, so the pixel-only baseline never rebuffers at all on
this trace: **0.00 s rebuffering, 100% Tier 0, information delivered 1.0000**.

The content-blind policy, unable to tell that no drop was necessary, still drops to Tier 1 for
**32.3% of playback**, for **zero rebuffering benefit**, at a measured cost of information
delivered falling to **0.9254**.

This is the clearest single number in the dataset for why content-awareness is the contribution
rather than modality-switching alone. Bandwidth-only switching pays the modality cost whenever
its threshold is crossed, regardless of whether anything was actually at risk.

### 7.2 The cost of holding Tier 0 through demonstrations

The agent protects demo content by tolerating a thinner safety margin before downgrading. That
protection is not free, and the cost lands precisely where the protection is applied.

Scanning all 27 content-aware runs on stressed traces for segments where the buffer actually
depleted mid-download gives **58 rebuffer events: 36 `talking_head`, 17 `slides_static`, 5
`demo`**. Against the corpus base rates of 46.7% / 48.2% / 5.0%, that is 1.33x / 0.61x / **1.72x
representation**. Demo segments carry the highest per-segment stall risk of any label under this
agent.

Stated plainly, because it will be asked: holding Tier 0 on a thinner margin during
demonstrations does exactly what it is designed to do, and the price is that when a stall does
occur it is disproportionately likely to occur during a demonstration. Whether that trade is
correct is a judgement about which failure hurts a student more, a few seconds of freeze with
the demonstration's visuals intact, or the demonstration silently collapsing to a static slide.
The numbers do not settle it.

The trade is not funded by a larger stall budget. Total rebuffering under the content-aware
agent remains below the content-blind policy's (18.79 s against 22.91 s mean), so the hold
profile's localised cost is more than covered by the drop profile's savings elsewhere.

---

## 8. Course demo (Phase 4.5)

Static browser page. The bandwidth slider feeds the real agent through the same
`get_bandwidth_estimate()` interface the simulation uses, and the displayed content swaps
between video, slide plus audio, slide plus captions, and rolling text summary according to the
agent's decision.

The agent is Python and the page is static, so the browser runs a deliberate port, with
`demo/equivalence_test.py` running both implementations over identical input sequences and
failing on any disagreement. Coverage includes sustained collapse and recovery, label flipping
every segment, bandwidths sitting exactly on each safety-factor boundary, degenerate one- and
two-rung ladders, unknown labels, and long random walks: **34 cases, 3730 decisions, all
matching**. The port cannot drift silently.

Verified in Chromium under Playwright rather than by logic alone: all four views render real
content, no console errors, and the slider produces the tier path Tier 0 to 1 to 2 to 3 and back.
Recovery is a single jump rather than a gradual climb, which is correct: the agent applies an
asymmetric margin, descending deliberately because being caught overcommitted is expensive,
ascending directly to the highest sustainable rung because the only cost of climbing too eagerly
is coming back down.

The bundled excerpt is MIT 6.0002, CC BY-NC-SA 4.0, chosen because it is the licence that
permits redistributing a real video excerpt with attribution. An NPTEL lecture could not have
been used for this.

Building the demo early paid for itself immediately: it surfaced a caption bug invisible to the
simulation. The generated WebVTT carried Windows line endings, which defeated the browser's
block splitting and collapsed all 78 caption cues into one malformed cue, blanking Tier 2
captions after the first three seconds. Python's universal-newline reads had hidden this from
every prior test.

---

## 9. Consolidated limitations

Stated here in one place so they are not discovered piecemeal.

1. **Demo recall is 51.5%.** Roughly half of true demonstration content is not labelled as such
   and receives the eager-drop profile. Every claim about protecting demonstrations is bounded
   by this.
2. **Classifier thresholds are provisional**, calibrated against this corpus's feature
   distributions, not validated against ground truth labels.
3. **Slide segmentation is imperfect.** Verified cases exist where a stored slide image is wrong
   for part of its own window. Affects Tier 1 and Tier 2 quality, not the results here.
4. **`information_delivered` contains three modelling constants**, not measurements. Conclusions
   drawn from it are conditional on that weighting. It was defined before the agent existed.
5. **Most comparative signal comes from one synthetic trace and one real rough trace.** Two of
   five traces never stress the system.
6. **The switch-in cost of a mid-slide tier change is not modelled.** A policy switching into
   Tier 1 mid-slide is not charged for the slide image it would really need to fetch. This
   affects all three policies identically, so the comparison stays fair while all absolute
   numbers are slightly optimistic.
7. **Bandwidth estimation lag is inherited from Sabre** and is the primary cause of residual
   rebuffering under both switching policies. Confirmed from verbose logs: segments still being
   requested at top quality while already taking 6 to 7 seconds against a 4-second budget.
8. **No human comprehension data yet.** Everything above is system metrics. The claim that
   modality degradation preserves *understanding* rather than merely *bytes delivered* is not
   yet tested.

---

## 10. Status and next steps

Complete: Phases 0, 1, 2, 3, 4, 4.5. The simulation results plus the working demo constitute a
complete and defensible course project on their own.

Not started, deliberately:

- **Phase 5, real DASH prototype.** Declined for now. The course requirement is already
  satisfied, and this phase is expensive, fragile plumbing whose hardest part is cross-tier
  timestamp synchronisation.
- **Phase 6, evaluation.** Split. The system-metrics half is substantially delivered by the
  results above. One cheap optional ablation is available if wanted: comparing the current
  rules-based classifier against a VLM-based one on the same segments, which would directly
  address the 51.5% recall ceiling identified in section 4 and quantify how much of the
  agent's headroom is lost to classification rather than to policy. Flagged as an option, not
  built. The comprehension study half is on hold pending sequencing against the Review 2 and
  Review 3 dates, as participant recruitment and informal instructor clearance have a longer
  lead time than any phase so far.
- **Phase 7, paper.** Not started.
