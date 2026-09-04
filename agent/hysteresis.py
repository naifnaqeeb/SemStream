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

    def decide(self, bitrates_kbps, bandwidth_kbps):
        down_candidate = affordable_index(bitrates_kbps, bandwidth_kbps, self.down_safety_factor)
        up_candidate = affordable_index(bitrates_kbps, bandwidth_kbps, self.up_safety_factor)

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
