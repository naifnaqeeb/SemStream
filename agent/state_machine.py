from agent.hysteresis import HysteresisController

# Both profiles are symmetric offsets from Naive's own neutral pair
# (down=0.9, up=0.7, itself grounded in Sabre's built-in ThroughputRule) - not
# picked from feel. Reasoning for both profiles, and for why slides_static
# shares talking_head's profile rather than getting its own, is in
# docs/design_notes.md (Phase 4 design section).
FACTOR_PROFILES = {
    "demo": {"down_safety_factor": 0.95, "up_safety_factor": 0.6},
    "talking_head": {"down_safety_factor": 0.75, "up_safety_factor": 0.85},
    "slides_static": {"down_safety_factor": 0.75, "up_safety_factor": 0.85},
}

MIN_DWELL_SEGMENTS = 3
NEUTRAL_DOWN_SAFETY_FACTOR = 0.9
NEUTRAL_UP_SAFETY_FACTOR = 0.7


class ContentAwareStateMachine:
    def __init__(self):
        self.hysteresis = HysteresisController(
            min_dwell_segments=MIN_DWELL_SEGMENTS,
            down_safety_factor=NEUTRAL_DOWN_SAFETY_FACTOR,
            up_safety_factor=NEUTRAL_UP_SAFETY_FACTOR,
        )

    def next_quality(self, bitrates_kbps, bandwidth_kbps, content_label):
        profile = FACTOR_PROFILES.get(content_label)
        if profile is None:
            return self.hysteresis.decide(bitrates_kbps, bandwidth_kbps)
        return self.hysteresis.decide(
            bitrates_kbps,
            bandwidth_kbps,
            up_safety_factor=profile["up_safety_factor"],
            down_safety_factor=profile["down_safety_factor"],
        )
