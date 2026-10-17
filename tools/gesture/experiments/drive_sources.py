"""Round 12, thread `drive` — freeze recorded kinematics as DRIVER signals.

A driver is a time series, not a line: it never draws its own shape. This
script reads the local corpora and writes compact library entries of the new
kind `drive_signal` (library/drive_signal/drive_<name>/: entry.json +
series.npz with `t` seconds and one float32 array per channel). The kit
modulators in gesture/kit/modulators_drive.py resample a window of a driver
onto a mark's arc length and map it to ink channels.

    .local/gesture/.venv/bin/python tools/gesture/experiments/drive_sources.py [--overwrite]

Sources (all read in place, nothing downloaded):
- mosquito: tethered mosquito flight in a closed-loop flight simulator
  (zenodo 5017751, `mos_vision.h5`, pandas fixed-format store read with the
  Homebrew `h5dump` because the research venv has no h5py). wbad = left−right
  wingbeat amplitude (the steering command), wbas = left+right (effort),
  case = the visual condition (30 s blocks). `hover_vision.h5`'s /df store
  is byte-identical to mos_vision's (same md5 of the dumped values), so only
  one fly is frozen.
- stork: LifeTrack White Stork Sicily, "Oduella" (5-min GPS, Jun–Dec 2015):
  height above ellipsoid (thermal climbs) and speed from successive fixes.
- tropicbird: white-tailed tropicbird 24202, one 10 h foraging trip at sea
  (1-min GPS): speed; sitting on the water reads as pauses.
- mosca: mosca-draw simulated fly walk `open_fru_s11` (connectome LIF model,
  courtship neurons driven): left/right motor pool rates → turn (L−R) and
  drive (L+R). Simulated, recorded as such.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d, median_filter

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "gesture"))

from gesture.kit import library as L  # noqa: E402

CORPUS = ROOT / ".local" / "gesture" / "corpus"
FLY = CORPUS / "earth" / "zenodo-5017751-fly" / "mos_vision.h5"
STORK = CORPUS / "animal" / "movebank-lifetrack-stork-sicily" / "stork-gps.csv"
TROPIC = CORPUS / "animal" / "movebank-tropicbird-santos2019" / "tropicbird-gps.csv"
MOSCA = Path("/Users/ianduclos/_SecondBrain/01_Projects/mosca-draw/out/k4_circulation/open_fru_s11.npz")
KIND = "drive_signal"
R_EARTH = 6371e3


def _h5dump(path: Path, dset: str, dtype: str, tmp: Path) -> np.ndarray:
    out = tmp / (dset.strip("/").replace("/", "_") + ".bin")
    subprocess.run(["h5dump", "-d", dset, "-b", "LE", "-o", str(out), str(path)], check=True,
                   stdout=subprocess.DEVNULL)
    return np.fromfile(out, dtype=dtype)


def _uniform(t, cols: dict, rate: float, sigma_s: float = 0.0):
    """Resample irregular samples onto a uniform grid (anti-aliased by a
    gaussian of sigma_s seconds on the source grid first)."""
    tg = np.arange(t[0], t[-1], 1.0 / rate)
    out = {}
    dts = float(np.median(np.diff(t)))
    for k, v in cols.items():
        x = gaussian_filter1d(v, sigma_s / dts) if sigma_s > 0 else v
        out[k] = np.interp(tg, t, x).astype(np.float32)
    return tg - tg[0], out


def fly(tmp: Path):
    a = _h5dump(FLY, "/df/block0_values", "<f8", tmp).reshape(-1, 27)
    t = _h5dump(FLY, "/df/axis1", "<i8", tmp) * 1e-9
    t = t - t[0]
    wbad, wbas, case = a[:, 25], a[:, 26], a[:, 2]
    ori = a[:, 11]
    dh = np.diff(ori)
    dh[np.abs(dh) > 50.0] = 0.0                 # the simulator resets the heading every 30 s trial: keep it continuous
    heading = np.r_[0.0, np.cumsum(dh)]
    tg, c = _uniform(t, {"steer": wbad, "effort": wbas, "heading": heading}, rate=40.0, sigma_s=0.008)
    c["trial"] = np.interp(tg, t, case).round().astype(np.float32)
    chans = {
        "steer": "left−right wingbeat amplitude (wbad): the fly's steering command, signed",
        "effort": "left+right wingbeat amplitude (wbas): flight effort; < 0.3 = wings stopped",
        "trial": "visual condition 0..3 (30 s blocks), categorical",
        "heading": "the fly's heading in the simulator, degrees, continuous (trial resets removed); some trials spin "
                   "at hundreds of degrees per second",
    }
    entry = {"id": "drive_mosquito", "kind": KIND, "label": "Mosquito in a flight simulator", "version": 1,
             "policy": "generative",
             "provenance": {"corpus": "earth/zenodo-5017751-fly", "file": "mos_vision.h5",
                            "columns": ["trajectory__wbad", "trajectory__wbas", "trajectory__case", "trajectory__pOri_x"],
                            "licence": "CC0", "recorded": True,
                            "research_file": "tools/gesture/experiments/drive_sources.py"},
             "rate_hz": 40.0, "duration_s": float(tg[-1]), "channels": chans,
             "notes": "Tethered mosquito, closed-loop visual flight simulator, 12.5 min at ~165 Hz resampled to "
                      "40 Hz (σ 8 ms). hover_vision.h5's /df store is byte-identical to this one, so only one "
                      "fly is frozen. A driver: never drawn as a shape."}
    return entry, tg, c


def _gps(rows, step_s: float):
    t = np.array([dt.datetime.fromisoformat(r["timestamp"]).timestamp() for r in rows])
    lon = np.array([float(r["location-long"]) for r in rows])
    lat = np.array([float(r["location-lat"]) for r in rows])
    o = np.argsort(t, kind="stable")
    t, lon, lat = t[o], lon[o], lat[o]
    keep = np.r_[True, np.diff(t) > 0]
    t, lon, lat = t[keep], lon[keep], lat[keep]
    x = np.radians(lon - lon.mean()) * np.cos(np.radians(lat.mean())) * R_EARTH
    y = np.radians(lat - lat.mean()) * R_EARTH
    tg = np.arange(t[0], t[-1], step_s)
    xg, yg = np.interp(tg, t, x), np.interp(tg, t, y)
    sp = np.r_[0.0, np.hypot(np.diff(xg), np.diff(yg)) / step_s]
    near = np.searchsorted(t, tg).clip(1, len(t) - 1)
    gap = np.minimum(np.abs(t[near] - tg), np.abs(t[near - 1] - tg)) > 4 * step_s
    return t, o, keep, tg, sp, gap


def stork():
    rows = [r for r in csv.DictReader(open(STORK)) if r["individual-local-identifier"].startswith("Oduella")
            and r["location-long"] and r["visible"] == "true"]
    t, o, keep, tg, sp, gap = _gps(rows, 300.0)
    h = np.array([float(r["height-above-ellipsoid"] or "nan") for r in rows])[o][keep]
    ok = np.isfinite(h)
    hg = np.interp(tg, t[ok], h[ok])
    hg = median_filter(hg, 3, mode="nearest")
    hg = np.clip(hg, np.percentile(hg, 0.5), np.percentile(hg, 99.7))     # GPS altitude spikes (one 5 km fix)
    sp = np.clip(median_filter(sp, 3, mode="nearest"), 0, np.percentile(sp, 99.8))
    tod = ((tg + 3600.0) % 86400.0) / 3600.0                                # local hour (UTC+1, CET; approx.)
    c = {"alt": hg.astype(np.float32), "speed": sp.astype(np.float32),
         "gap": gap.astype(np.float32), "hour": tod.astype(np.float32)}
    chans = {"alt": "height above ellipsoid, m (median-3, spikes clipped): thermal climbs",
             "speed": "ground speed from successive fixes, m/s (median-3)",
             "gap": "1 where no fix within 20 min (interpolated)",
             "hour": "approximate local hour of day (UTC+1)"}
    entry = {"id": "drive_stork", "kind": KIND, "label": "White stork 'Oduella', Sicily 2015", "version": 1,
             "policy": "generative",
             "provenance": {"corpus": "animal/movebank-lifetrack-stork-sicily", "file": "stork-gps.csv",
                            "individual": rows[0]["individual-local-identifier"], "licence": "CC0",
                            "recorded": True, "research_file": "tools/gesture/experiments/drive_sources.py"},
             "rate_hz": 1 / 300.0, "duration_s": float(tg[-1] - tg[0]), "channels": chans,
             "start_utc": dt.datetime.fromtimestamp(tg[0], dt.timezone.utc).isoformat(),
             "notes": "A juvenile that stayed in Sicily (no crossing): five months of days — night roosts, "
                      "morning thermals, foraging. 5-min fixes on a uniform grid. A driver: never drawn as a "
                      "shape (no lon/lat is stored)."}
    return entry, tg - tg[0], c


def tropicbird():
    rows = [r for r in csv.DictReader(open(TROPIC)) if r["individual-local-identifier"] == "24202"
            and r["location-long"]]
    t, o, keep, tg, sp, gap = _gps(rows, 60.0)
    c = {"speed": sp.astype(np.float32), "gap": gap.astype(np.float32)}
    entry = {"id": "drive_tropicbird", "kind": KIND, "label": "White-tailed tropicbird 24202, one trip",
             "version": 1, "policy": "generative",
             "provenance": {"corpus": "animal/movebank-tropicbird-santos2019", "file": "tropicbird-gps.csv",
                            "individual": "24202", "licence": "CC0", "recorded": True,
                            "research_file": "tools/gesture/experiments/drive_sources.py"},
             "rate_hz": 1 / 60.0, "duration_s": float(tg[-1] - tg[0]),
             "channels": {"speed": "speed from successive 1-min fixes, m/s (sitting on the water ≈ 0)",
                          "gap": "1 where no fix within 4 min"},
             "notes": "One 10 h foraging trip from Fernando de Noronha: flights broken by sitting on the water. "
                      "A driver: never drawn as a shape."}
    return entry, tg - tg[0], c


def mosca():
    d = np.load(MOSCA, allow_pickle=False)
    rates = d["rates"].astype(np.float64)                 # (300000, 2) at 0.1 ms over 30 s
    t = np.arange(len(rates)) * (30.0 / len(rates))
    tg, c = _uniform(t, {"L": rates[:, 0], "R": rates[:, 1]}, rate=200.0, sigma_s=0.004)
    c = {"turn": (c["L"] - c["R"]).astype(np.float32), "drive": (c["L"] + c["R"]).astype(np.float32)}
    entry = {"id": "drive_mosca", "kind": KIND, "label": "mosca-draw: simulated fly, courtship neurons driven",
             "version": 1, "policy": "generative",
             "provenance": {"project": "mosca-draw", "file": "out/k4_circulation/open_fru_s11.npz",
                            "recorded": False, "simulated": "connectome LIF model, differential-drive body",
                            "research_file": "tools/gesture/experiments/drive_sources.py"},
             "rate_hz": 200.0, "duration_s": float(tg[-1]),
             "channels": {"turn": "left − right motor pool rate, Hz (the walk's steering)",
                          "drive": "left + right motor pool rate, Hz (the walk's speed)"},
             "notes": "Simulated, not recorded: 30 s of motor-neuron rates from Ian's mosca-draw. A driver: "
                      "never drawn as a shape."}
    return entry, tg, c


def surrogate(fly_entry, t, cols, seed=5813):
    """A control, not a source: the mosquito's steering and heading RATE with
    their Fourier phases randomised (same power spectrum, same mean; the
    bursts — the intermittency — are destroyed), the heading re-integrated."""
    rng = np.random.default_rng(seed)

    def phase_rand(x):
        X = np.fft.rfft(x - x.mean())
        ph = rng.uniform(0, 2 * np.pi, len(X))
        ph[0] = 0.0
        return np.fft.irfft(np.abs(X) * np.exp(1j * ph), n=len(x)) + x.mean()

    dt = float(t[1] - t[0])
    rate = np.diff(cols["heading"]) / dt
    rs = phase_rand(rate)
    c = {"steer": phase_rand(cols["steer"]).astype(np.float32),
         "effort": phase_rand(cols["effort"]).astype(np.float32),
         "heading": np.r_[0.0, np.cumsum(rs * dt)].astype(np.float32)}
    entry = {"id": "drive_surrogate_mosquito", "kind": KIND, "label": "Control: mosquito, phases randomised",
             "version": 1, "policy": "generative",
             "provenance": {"derived_from": "drive_signal/drive_mosquito", "method": "Fourier phase randomisation",
                            "seed": seed, "recorded": False,
                            "research_file": "tools/gesture/experiments/drive_sources.py"},
             "rate_hz": fly_entry["rate_hz"], "duration_s": fly_entry["duration_s"],
             "channels": {k: f"{fly_entry['channels'][k]} — phase-randomised surrogate" for k in c},
             "notes": "A control for the honest test: same spectrum as the mosquito, no bursts. If a drawing "
                      "driven by this looks the same as one driven by the fly, the fly does not matter."}
    return entry, t, c


def save(entry, t, cols, overwrite):
    arrays = {"t": np.asarray(t, np.float64), **{k: np.asarray(v, np.float32) for k, v in cols.items()}}
    e = L.save(entry, {"series.npz": L.npz_bytes(arrays)}, overwrite=overwrite)
    print(f"{e['id']:18s} {len(t):7d} samples  {e['duration_s'] / 3600:8.2f} h  {e['size_bytes'] / 1024:7.1f} KB")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as td:
        fe, ft, fc = fly(Path(td))
    save(fe, ft, fc, a.overwrite)
    save(*surrogate(fe, ft, fc), a.overwrite)
    save(*stork(), a.overwrite)
    save(*tropicbird(), a.overwrite)
    save(*mosca(), a.overwrite)


if __name__ == "__main__":
    main()
