// Drives the demo page. All tier decisions come from ContentAwareStateMachine in
// agent.js (the verified-equivalent port of agent/state_machine.py); nothing here
// decides a tier. Bandwidth reaches the agent only through UIBandwidthSource's
// getBandwidthEstimate(), matching CLAUDE.md's bandwidth-interface rule.

const BUFFER_CAPACITY_S = 25;
const REBUFFER_RESUME_S = 2;

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
  buffer: BUFFER_CAPACITY_S,
  stalled: false,
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

function slideAt(t) {
  const slides = state.manifest.slides;
  for (let i = slides.length - 1; i >= 0; i--) {
    if (t >= slides[i].start) return slides[i];
  }
  return slides[0];
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

async function loadCaptions(url) {
  // Normalise CRLF first: VTT written on Windows arrives with \r\n, which would
  // otherwise defeat the blank-line block split and collapse every cue into one.
  const text = (await (await fetch(url)).text()).replace(/\r\n/g, "\n");
  const re = /(\d+):(\d+):([\d.]+)\s*-->\s*(\d+):(\d+):([\d.]+)/;
  cues = [];
  for (const block of text.split(/\n\n+/)) {
    const m = block.match(re);
    if (!m) continue;
    const start = +m[1] * 3600 + +m[2] * 60 + parseFloat(m[3]);
    const end = +m[4] * 3600 + +m[5] * 60 + parseFloat(m[6]);
    const body = block.split("\n").filter((l) => !re.test(l) && l.trim() !== "WEBVTT").join(" ").trim();
    cues.push({ start, end, text: body });
  }
}

// Simulated buffer: drains at 1x while playing, fills at (bandwidth / rung bitrate)x.
// Purely for the HUD and the stall indicator - the plan allows a simulated buffer here.
function updateBuffer(dt) {
  const bitrate = state.manifest.bitrates_kbps[state.quality];
  const bw = state.bandwidth.getBandwidthEstimate();
  const fillRate = bitrate > 0 ? bw / bitrate : 100;
  state.buffer += dt * (fillRate - 1);
  state.buffer = Math.max(0, Math.min(BUFFER_CAPACITY_S, state.buffer));

  if (!state.stalled && state.buffer <= 0) state.stalled = true;
  else if (state.stalled && state.buffer >= REBUFFER_RESUME_S) state.stalled = false;
}

function applyTier(tier, t) {
  for (let i = 0; i <= 3; i++) {
    el("view" + i).classList.toggle("active", i === tier);
    el("row" + i).classList.toggle("on", i === tier);
  }
  const video = el("video");
  const audio = state.audio;

  if (tier === 0) {
    if (Math.abs(video.currentTime - t) > 0.35) video.currentTime = t;
    video.muted = false;
    if (state.playing && !state.stalled) video.play().catch(() => {});
    else video.pause();
    audio.pause();
  } else if (tier === 1) {
    video.pause();
    el("slide1").src = slideAt(t).image;
    if (Math.abs(audio.currentTime - t) > 0.35) audio.currentTime = t;
    if (state.playing && !state.stalled) audio.play().catch(() => {});
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
  el("bufv").textContent = state.buffer.toFixed(1) + " s";
  el("bufbar").style.width = (100 * state.buffer / BUFFER_CAPACITY_S) + "%";
  el("stall").classList.toggle("on", state.stalled);
  el("clock").textContent = `${fmt(state.time)} / ${fmt(m.segments.length * m.segment_duration)}`;
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

  const total = state.manifest.segments.length * state.manifest.segment_duration;

  if (state.playing && !state.stalled) {
    state.time += dt;
    if (state.time >= total) {
      state.time = total;
      state.playing = false;
      el("playpause").textContent = "Play";
    }
  }
  if (state.playing) updateBuffer(dt);

  const seg = segmentAt(state.time);
  if (seg !== state.segment) {
    state.segment = seg;
    decideForSegment(seg);
  }
  applyTier(state.tier, state.time);
  renderHud();
}

async function init() {
  state.manifest = await (await fetch("demo_manifest.json")).json();
  await loadCaptions(state.manifest.captions_file);

  el("video").src = state.manifest.tier0_video;
  state.audio = new Audio(state.manifest.tier1_audio);
  state.audio.preload = "auto";

  const w = state.manifest.source_window;
  el("assetnote").textContent =
    `${state.manifest.lecture_id} · source ${fmt(w.start_seconds)}–${fmt(w.end_seconds)}`;

  state.segment = 0;
  decideForSegment(0);

  el("bw").addEventListener("input", (e) => {
    state.bandwidth.setBandwidthKbps(parseFloat(e.target.value));
    renderHud();
  });
  el("playpause").addEventListener("click", () => {
    state.playing = !state.playing;
    el("playpause").textContent = state.playing ? "Pause" : "Play";
  });

  requestAnimationFrame(frame);
}

init();
