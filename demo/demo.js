// Drives the demo page. All tier decisions come from ContentAwareStateMachine in
// agent.js (the verified-equivalent port of agent/state_machine.py); nothing here
// decides a tier. Bandwidth reaches the agent only through UIBandwidthSource's
// getBandwidthEstimate(), matching CLAUDE.md's bandwidth-interface rule.

// Media whose currentTime is further than this from the master clock is
// re-seeked. Large scrubs exceed it immediately, which is what forces the
// explicit re-sync rather than leaving media stalled while the clock runs on.
const SYNC_TOLERANCE_S = 0.35;

const el = (id) => document.getElementById(id);

const state = {
  manifest: null,
  machine: new ContentAwareStateMachine(),
  bandwidth: new UIBandwidthSource(1500),
  time: 0,
  playing: false,
  quality: null,
  tier: null,
  segment: -1,
  seeking: false,
  lastFrame: null,
};

function fmt(t) {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function segmentAt(t) {
  const i = Math.floor(t / state.manifest.segment_duration);
  return Math.max(0, Math.min(i, state.manifest.segments.length - 1));
}

// Phase 1's detector also fires on lecturer motion, so some extracted "slides"
// are frozen photos of the lecturer rather than slides. During those stretches
// the honest Tier 1/2 view is the last real slide, which is still the current
// slide as far as the lecture is concerned, and costs no extra bytes. Falls
// back to the raw slide only if no genuine one has appeared yet.
function slideAt(t) {
  const slides = state.manifest.slides;
  let current = null;
  for (let i = slides.length - 1; i >= 0; i--) {
    if (t >= slides[i].start) { current = slides[i]; break; }
  }
  if (current === null) return slides[0];
  if (current.genuine) return current;
  for (let i = slides.indexOf(current); i >= 0; i--) {
    if (slides[i].genuine) return slides[i];
  }
  return current;
}

function summaryAt(t) {
  const s = state.manifest.summaries;
  for (let i = s.length - 1; i >= 0; i--) {
    if (t >= s[i].start) return s[i];
  }
  return s[0];
}

let cues = [];
function captionAt(t) {
  for (let i = cues.length - 1; i >= 0; i--) {
    if (t >= cues[i].start && t <= cues[i].end) return cues[i].text;
  }
  return "";
}


function totalDuration() {
  return state.manifest.segments.length * state.manifest.segment_duration;
}

// Single source of truth for playback position. Both the scrub bar and normal
// playback write here, then media follows - never the other way round, so a
// seek cannot end up fighting the clock.
function seekTo(t) {
  state.time = Math.max(0, Math.min(t, totalDuration()));
  resyncMedia(true);
  const seg = segmentAt(state.time);
  state.segment = seg;
  decideForSegment(seg);
}

// force=true is used after a scrub, where currentTime may be far from the clock
// and the element needs an explicit seek rather than drift correction.
function resyncMedia(force) {
  const video = el("video");
  const audio = state.audio;
  for (const m of [video, audio]) {
    if (!m) continue;
    if (force || Math.abs(m.currentTime - state.time) > SYNC_TOLERANCE_S) {
      try { m.currentTime = state.time; } catch (e) { /* not seekable yet */ }
    }
  }
}

function applyTier(tier, t) {
  for (let i = 0; i <= 3; i++) {
    el("view" + i).classList.toggle("active", i === tier);
    el("row" + i).classList.toggle("on", i === tier);
  }
  const video = el("video");
  const audio = state.audio;

  if (tier === 0) {
    if (Math.abs(video.currentTime - t) > SYNC_TOLERANCE_S) video.currentTime = t;
    video.muted = false;
    if (state.playing) video.play().catch(() => {});
    else video.pause();
    audio.pause();
  } else if (tier === 1) {
    video.pause();
    el("slide1").src = slideAt(t).image;
    if (Math.abs(audio.currentTime - t) > SYNC_TOLERANCE_S) audio.currentTime = t;
    if (state.playing) audio.play().catch(() => {});
    else audio.pause();
  } else {
    video.pause();
    audio.pause();
    if (tier === 2) {
      el("slide2").src = slideAt(t).image;
      el("capbar").textContent = captionAt(t);
    } else {
      const s = summaryAt(t);
      el("sumstamp").textContent = `${fmt(s.start)} – ${fmt(s.end)}`;
      el("sumtext").textContent = s.text || "(no speech transcribed in this window)";
    }
  }
}

function renderHud() {
  const m = state.manifest;
  const seg = m.segments[state.segment] || m.segments[0];
  el("bwnum").textContent = Math.round(state.bandwidth.getBandwidthEstimate());
  el("tierv").textContent = state.tier === null ? "—" : "Tier " + state.tier;
  el("qv").textContent = state.quality === null ? "—" : state.quality;
  el("brv").textContent = state.quality === null ? "—"
    : m.bitrates_kbps[state.quality] + " kbps";
  el("lblv").innerHTML = `<span class="label ${seg.content_label}">${seg.content_label}</span>`;
  el("clock").textContent = `${fmt(state.time)} / ${fmt(totalDuration())}`;
  if (!state.seeking) el("seek").value = String(state.time);
}

// One agent decision per segment boundary, using the upcoming segment's label -
// same cadence and same input as the Sabre simulation.
function decideForSegment(index) {
  const m = state.manifest;
  const label = m.segments[index].content_label;
  const q = state.machine.nextQuality(m.bitrates_kbps, state.bandwidth.getBandwidthEstimate(), label);
  state.quality = q;
  state.tier = m.tiers[q];
}

function frame(ts) {
  requestAnimationFrame(frame);
  if (state.lastFrame === null) state.lastFrame = ts;
  const dt = Math.min(0.25, (ts - state.lastFrame) / 1000);
  state.lastFrame = ts;
  if (!state.manifest) return;

  const total = totalDuration();

  if (state.playing && !state.seeking) {
    state.time += dt;
    if (state.time >= total) {
      state.time = total;
      state.playing = false;
      el("playpause").textContent = "Play";
    }
  }

  const seg = segmentAt(state.time);
  if (seg !== state.segment) {
    state.segment = seg;
    decideForSegment(seg);
  }
  applyTier(state.tier, state.time);
  renderHud();
}

function init() {
  // Manifest and caption cues arrive as a plain <script> (demo_manifest.js) rather
  // than fetch(), so the page works when opened directly from disk. fetch() is
  // blocked on file:// by CORS, which would leave a review-room double-click with
  // a dead page and no obvious cause.
  state.manifest = window.DEMO_MANIFEST;
  cues = state.manifest.captions;

  el("video").src = state.manifest.tier0_video;
  state.audio = new Audio(state.manifest.tier1_audio);
  state.audio.preload = "auto";

  const w = state.manifest.source_window;
  el("assetnote").textContent =
    `${state.manifest.lecture_id} · source ${fmt(w.start_seconds)}–${fmt(w.end_seconds)}`;

  state.segment = 0;
  decideForSegment(0);

  const seek = el("seek");
  seek.max = String(totalDuration());
  // Scrubbing pauses clock advance so the thumb does not fight the playhead,
  // then seekTo() re-seeks both media elements explicitly on release. The agent
  // is deliberately NOT reset: it carries its tier and dwell state across the
  // jump, which is the realistic behaviour for a player that seeked.
  seek.addEventListener("input", (e) => {
    state.seeking = true;
    state.time = parseFloat(e.target.value);
    renderHud();
  });
  const endSeek = (e) => {
    if (!state.seeking) return;
    state.seeking = false;
    seekTo(parseFloat(e.target.value));
  };
  seek.addEventListener("change", endSeek);
  seek.addEventListener("pointerup", endSeek);

  el("bw").addEventListener("input", (e) => {
    state.bandwidth.setBandwidthKbps(parseFloat(e.target.value));
    renderHud();
  });
  el("playpause").addEventListener("click", () => {
    state.playing = !state.playing;
    el("playpause").textContent = state.playing ? "Pause" : "Play";
  });

  // Presentation scale is the default on every load, deliberately not persisted:
  // the failure mode worth avoiding is walking into a review with a laptop-scale
  // HUD because that was the last mode used at a desk.
  el("modetoggle").addEventListener("click", () => {
    const laptop = document.body.classList.toggle("laptop");
    el("modetoggle").textContent = laptop ? "Presentation scale" : "Laptop scale";
  });

  requestAnimationFrame(frame);
}

init();
