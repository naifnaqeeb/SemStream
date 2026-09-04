import json
import random
import urllib.request
import zipfile
from pathlib import Path

SIM_ROOT = Path(__file__).resolve().parent
RAW_DIR = SIM_ROOT / "traces" / "raw"
OUT_DIR = SIM_ROOT / "traces"

NORWAY_BASE_URL = "https://raw.githubusercontent.com/confiwent/Real-world-bandwidth-traces/master/cooked_3gp/"
NORWAY_FILES = [
    "norway_bus_1", "norway_bus_5",
    "norway_car_2", "norway_car_3",
    "norway_ferry_2", "norway_ferry_20",
    "norway_metro_2", "norway_metro_10",
    "norway_train_1", "norway_train_12",
    "norway_tram_10", "norway_tram_11",
]
# Not present in the throughput-only trace; documented assumption, not measured.
NORWAY_LATENCY_MS = 150

BELGIUM_ZIP_URL = "https://users.ugent.be/~jvdrhoof/dataset-4g/logs/logs_all.zip"
# Not present in the trace's own columns; documented assumption, not measured.
BELGIUM_LATENCY_MS = 60


def download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    urllib.request.urlretrieve(url, dest)


def fetch_norway_raw():
    out = RAW_DIR / "norway"
    for name in NORWAY_FILES:
        download(NORWAY_BASE_URL + name, out / name)
    return sorted(out.glob("norway_*"))


def fetch_belgium_raw():
    zip_path = RAW_DIR / "belgium" / "logs_all.zip"
    download(BELGIUM_ZIP_URL, zip_path)
    extract_dir = RAW_DIR / "belgium" / "logs"
    if not extract_dir.exists() or not any(extract_dir.iterdir()):
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
    return sorted(extract_dir.glob("report_*.log"))


def convert_norway_trace(path, latency_ms=NORWAY_LATENCY_MS):
    samples = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        t, mbps = float(parts[0]), float(parts[1])
        samples.append((t, mbps))
    samples.sort()

    entries = []
    for i in range(len(samples) - 1):
        t0, mbps0 = samples[i]
        t1, _ = samples[i + 1]
        duration_ms = round((t1 - t0) * 1000)
        if duration_ms <= 0:
            continue
        entries.append({
            "duration_ms": duration_ms,
            "bandwidth_kbps": round(mbps0 * 1000),
            "latency_ms": latency_ms,
        })
    return entries


def convert_belgium_trace(path, latency_ms=BELGIUM_LATENCY_MS):
    entries = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) != 6:
            continue
        _, _, _, _, byte_count, duration_ms = parts
        byte_count = int(byte_count)
        duration_ms = int(duration_ms)
        if duration_ms <= 0:
            continue
        bandwidth_kbps = round(byte_count * 8 / duration_ms)
        entries.append({
            "duration_ms": duration_ms,
            "bandwidth_kbps": bandwidth_kbps,
            "latency_ms": latency_ms,
        })
    return entries


def build_campus_wifi_collapse():
    # Synthetic trace, deliberately NOT presented as measured data. 4 phases in
    # 4000ms steps (aligned to the project's own segment grid, not a Sabre
    # requirement): stable good WiFi -> congestion ramp-up (bandwidth falling,
    # latency climbing ahead of it, matching real buffer-fill-then-drop
    # congestion behaviour) -> collapsed/overloaded AP -> recovery ramp back to
    # stable. Full reasoning and exact phase boundaries in docs/design_notes.md.
    # Fixed seed so the trace is reproducible, not re-randomised on every run.
    rng = random.Random(20260830)
    entries = []

    def add_phase(n_steps, bw_start, bw_end, lat_start, lat_end, noise_kbps, noise_ms):
        for i in range(n_steps):
            frac = i / max(1, n_steps - 1)
            bw = bw_start + (bw_end - bw_start) * frac
            lat = lat_start + (lat_end - lat_start) * frac
            bw += rng.uniform(-noise_kbps, noise_kbps)
            lat += rng.uniform(-noise_ms, noise_ms)
            entries.append({
                "duration_ms": 4000,
                "bandwidth_kbps": max(50, round(bw)),
                "latency_ms": max(10, round(lat)),
            })

    add_phase(15, 8000, 8000, 20, 20, 400, 5)
    add_phase(8, 8000, 300, 20, 250, 300, 20)
    add_phase(15, 300, 300, 250, 300, 100, 30)
    add_phase(15, 300, 7500, 300, 25, 300, 20)
    add_phase(8, 7500, 7500, 20, 20, 400, 5)

    return entries


def write_trace(entries, out_path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def build_all():
    norway_out = OUT_DIR / "norway_hsdpa"
    for path in fetch_norway_raw():
        entries = convert_norway_trace(path)
        write_trace(entries, norway_out / f"{path.name}.json")
    print(f"norway_hsdpa: {len(NORWAY_FILES)} traces written to {norway_out}", flush=True)

    belgium_out = OUT_DIR / "belgium_4g"
    belgium_files = fetch_belgium_raw()
    for path in belgium_files:
        entries = convert_belgium_trace(path)
        write_trace(entries, belgium_out / f"{path.stem}.json")
    print(f"belgium_4g: {len(belgium_files)} traces written to {belgium_out}", flush=True)

    custom_out = OUT_DIR / "custom"
    campus_entries = build_campus_wifi_collapse()
    write_trace(campus_entries, custom_out / "campus_wifi_collapse.json")
    print(f"custom: 1 trace written to {custom_out}", flush=True)


def list_traces():
    return sorted(OUT_DIR.glob("*/*.json"))


if __name__ == "__main__":
    build_all()
