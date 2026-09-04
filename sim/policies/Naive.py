import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import sabre
from agent.hysteresis import HysteresisController

# Bandwidth-thresholds-only, per CLAUDE.md's definition of the naive baseline:
# "content-blind modality switching on bandwidth thresholds only". Deliberately
# never reads buffer level - that is what the pixel-only Baseline (built-in
# Sabre BOLA) already represents, and real commercial fallbacks (e.g. a video
# call dropping to audio-only) react to measured network conditions, not local
# buffer occupancy. See docs/design_notes.md for the full reasoning and the
# hysteresis constants chosen below.
MIN_DWELL_SEGMENTS = 3
UP_SAFETY_FACTOR = 0.7
DOWN_SAFETY_FACTOR = 0.9


class Naive(sabre.Abr):
    def __init__(self, config):
        self.hysteresis = HysteresisController(
            min_dwell_segments=MIN_DWELL_SEGMENTS,
            up_safety_factor=UP_SAFETY_FACTOR,
            down_safety_factor=DOWN_SAFETY_FACTOR,
        )

    def get_quality_delay(self, segment_index):
        bitrates_kbps = self.session.manifest.bitrates
        bandwidth_kbps = self.session.get_throughput()
        quality = self.hysteresis.decide(bitrates_kbps, bandwidth_kbps)
        return (quality, 0)
