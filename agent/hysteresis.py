def affordable_index(bitrates_kbps, bandwidth_kbps, safety_factor):
    index = 0
    for i, kbps in enumerate(bitrates_kbps):
        if kbps <= bandwidth_kbps * safety_factor:
            index = i
    return index


class HysteresisController:
    def __init__(self, min_dwell_segments, up_safety_factor, down_safety_factor):
        self.min_dwell_segments = min_dwell_segments
        self.up_safety_factor = up_safety_factor
        self.down_safety_factor = down_safety_factor
        self.current_index = None
        self.segments_since_switch = 0

    def decide(self, bitrates_kbps, bandwidth_kbps, up_safety_factor=None, down_safety_factor=None):
        # Per-call overrides let a caller bias which target tier gets proposed
        # (e.g. content-aware affordability margins) without touching the dwell
        # floor or the switch-gating logic below, which stay uniform regardless.
        up_factor = self.up_safety_factor if up_safety_factor is None else up_safety_factor
        down_factor = self.down_safety_factor if down_safety_factor is None else down_safety_factor
        down_candidate = affordable_index(bitrates_kbps, bandwidth_kbps, down_factor)
        up_candidate = affordable_index(bitrates_kbps, bandwidth_kbps, up_factor)

        if self.current_index is None:
            self.current_index = down_candidate
            self.segments_since_switch = 0
            return self.current_index

        if down_candidate < self.current_index:
            desired = down_candidate
        elif up_candidate > self.current_index:
            desired = up_candidate
        else:
            desired = self.current_index

        self.segments_since_switch += 1
        if desired != self.current_index and self.segments_since_switch >= self.min_dwell_segments:
            self.current_index = desired
            self.segments_since_switch = 0
        return self.current_index
