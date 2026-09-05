// Port of agent/hysteresis.py + agent/state_machine.py + agent/bandwidth_source.py.
// Kept structurally line-for-line with the Python so divergence is easy to spot by eye;
// divergence is also checked mechanically by demo/equivalence_test.py, which runs both
// implementations over the same input sequences and fails if any decision differs.

function affordableIndex(bitratesKbps, bandwidthKbps, safetyFactor) {
  let index = 0;
  for (let i = 0; i < bitratesKbps.length; i++) {
    if (bitratesKbps[i] <= bandwidthKbps * safetyFactor) {
      index = i;
    }
  }
  return index;
}

class HysteresisController {
  constructor(minDwellSegments, upSafetyFactor, downSafetyFactor) {
    this.minDwellSegments = minDwellSegments;
    this.upSafetyFactor = upSafetyFactor;
    this.downSafetyFactor = downSafetyFactor;
    this.currentIndex = null;
    this.segmentsSinceSwitch = 0;
  }

  decide(bitratesKbps, bandwidthKbps, upSafetyFactor, downSafetyFactor) {
    const upFactor = upSafetyFactor === undefined || upSafetyFactor === null
      ? this.upSafetyFactor : upSafetyFactor;
    const downFactor = downSafetyFactor === undefined || downSafetyFactor === null
      ? this.downSafetyFactor : downSafetyFactor;

    const downCandidate = affordableIndex(bitratesKbps, bandwidthKbps, downFactor);
    const upCandidate = affordableIndex(bitratesKbps, bandwidthKbps, upFactor);

    if (this.currentIndex === null) {
      this.currentIndex = downCandidate;
      this.segmentsSinceSwitch = 0;
      return this.currentIndex;
    }

    let desired;
    if (downCandidate < this.currentIndex) {
      desired = downCandidate;
    } else if (upCandidate > this.currentIndex) {
      desired = upCandidate;
    } else {
      desired = this.currentIndex;
    }

    this.segmentsSinceSwitch += 1;
    if (desired !== this.currentIndex && this.segmentsSinceSwitch >= this.minDwellSegments) {
      this.currentIndex = desired;
      this.segmentsSinceSwitch = 0;
    }
    return this.currentIndex;
  }
}

const FACTOR_PROFILES = {
  demo: { downSafetyFactor: 0.95, upSafetyFactor: 0.6 },
  talking_head: { downSafetyFactor: 0.75, upSafetyFactor: 0.85 },
  slides_static: { downSafetyFactor: 0.75, upSafetyFactor: 0.85 },
};

const MIN_DWELL_SEGMENTS = 3;
const NEUTRAL_DOWN_SAFETY_FACTOR = 0.9;
const NEUTRAL_UP_SAFETY_FACTOR = 0.7;

class ContentAwareStateMachine {
  constructor() {
    this.hysteresis = new HysteresisController(
      MIN_DWELL_SEGMENTS, NEUTRAL_UP_SAFETY_FACTOR, NEUTRAL_DOWN_SAFETY_FACTOR);
  }

  nextQuality(bitratesKbps, bandwidthKbps, contentLabel) {
    const profile = FACTOR_PROFILES[contentLabel];
    if (profile === undefined) {
      return this.hysteresis.decide(bitratesKbps, bandwidthKbps);
    }
    return this.hysteresis.decide(
      bitratesKbps, bandwidthKbps, profile.upSafetyFactor, profile.downSafetyFactor);
  }
}

class UIBandwidthSource {
  constructor(initialKbps) {
    this.valueKbps = initialKbps === undefined ? 1000.0 : initialKbps;
  }
  setBandwidthKbps(valueKbps) {
    this.valueKbps = valueKbps;
  }
  getBandwidthEstimate() {
    return this.valueKbps;
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    affordableIndex, HysteresisController, ContentAwareStateMachine, UIBandwidthSource,
    FACTOR_PROFILES, MIN_DWELL_SEGMENTS,
    NEUTRAL_DOWN_SAFETY_FACTOR, NEUTRAL_UP_SAFETY_FACTOR,
  };
}
