class BandwidthSource:
    def get_bandwidth_estimate(self):
        raise NotImplementedError


class SabreBandwidthSource(BandwidthSource):
    def __init__(self, session):
        self.session = session

    def get_bandwidth_estimate(self):
        return self.session.get_throughput()


class UIBandwidthSource(BandwidthSource):
    def __init__(self, initial_kbps=1000.0):
        self.value_kbps = initial_kbps

    def set_bandwidth_kbps(self, value_kbps):
        self.value_kbps = value_kbps

    def get_bandwidth_estimate(self):
        return self.value_kbps


class RealBandwidthSource(BandwidthSource):
    # Phase 5 prototype, not implemented yet - see IMPLEMENTATION_PLAN.md.
    def get_bandwidth_estimate(self):
        raise NotImplementedError("real network estimator is a Phase 5 concern, not built yet")
