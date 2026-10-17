"""New voices learned from corpora (research round 9, thread voices_corpus, 2026-10-17).

    .local/gesture/.venv/bin/python tools/gesture/experiments/voices_corpus.py <stage> [...]

stages:
  extract  — early computer art (Noll, Nake, Cohen/AARON, Cohen 1969 meanders,
             Molnar, Desmond Paul Henry) through extract_hybrid; overlays written
  learn    — grammars: dance trails per movement quality and per CMU-55 animal
             mime, the computer-art groups, one trace fossil; saved as library
             `hand` entries (policy gate checked on load) and dance trails frozen
             as library `trail` entries (the `dance` voice reads them)
  measure  — distinctness (panel space, standard preprocessing) and coherence
             (self-consistency of each hand's own generated sheets)
  sheets   — result images through kit.run + kit.preview (recipe JSON beside each)
  all

Outputs: .local/gesture/out/voices_corpus/. Write-up:
tools/gesture/results/voices_corpus-2026-10-17.md.

Corpora give behaviours, never forms: the hands learn token statistics
(segment lengths, curvature, corners, joins), never a drawing's layout.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import grammar as gm  # noqa: E402
from gesture.core import Drawing  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/voices_corpus"
RES = HERE / "results"
CORPUS = ROOT / ".local/gesture/corpus"
JOBS = 2
COMMIT = "1245f20"

# ---------------------------------------------------------------------------
# early computer art: (artist dir, file stem, crop x0 y0 x1 y1, mode, extract kw)
# mode: "gray" luminance; "min" darkest channel (coloured lines on white); "inv" white-on-black
# ---------------------------------------------------------------------------
ART = {
    "noll_gq": ("a_michael_noll", "va-O1193785", (0.12, 0.04, 0.88, 0.83), "gray", {}),
    "nake_poly": ("frieder_nake", "va-O239558", (0.13, 0.08, 0.90, 0.86), "gray", {}),
    "aaron_1985": ("harold_cohen", "va-O239975", (0.02, 0.02, 0.98, 0.74), "gray", {}),
    "aaron_1987a": ("harold_cohen", "va-O499538", (0.04, 0.04, 0.96, 0.86), "gray", {}),
    "aaron_1987b": ("harold_cohen", "va-O499539", (0.04, 0.04, 0.96, 0.86), "gray", {}),
    "aaron_1989": ("harold_cohen", "va-O218310", (0.08, 0.12, 0.92, 0.90), "gray", {}),
    "meander_1969a": ("harold_cohen", "va-O499573", (0.10, 0.08, 0.90, 0.58), "min", {}),
    "meander_1969b": ("harold_cohen", "va-O499616", (0.08, 0.05, 0.92, 0.82), "min", {}),
    "molnar_letters": ("molnar_vera", "va-O216188", (0.05, 0.15, 0.95, 0.85), "min", {}),
    "henry_beach": ("desmond_paul_henry", "va-O499535", (0.05, 0.03, 0.95, 0.92), "gray",
                    {"method": "otsu", "paper_window_frac": 0.08, "spur_factor": 2.5,
                     "crop_to_plate": False, "drop_frames": False}),
    "henry_serpent": ("desmond_paul_henry", "va-O499534", (0.05, 0.03, 0.95, 0.85), "gray",
                      {"method": "otsu", "paper_window_frac": 0.08, "spur_factor": 2.5,
                       "crop_to_plate": False, "drop_frames": False}),
    "henry_untitled": ("desmond_paul_henry", "va-O499536", (0.05, 0.03, 0.95, 0.90), "inv",
                       {"method": "otsu", "paper_window_frac": 0.08, "spur_factor": 2.5,
                        "crop_to_plate": False, "drop_frames": False}),
}
EARTH = {
    "helminthoida": ("trace-helminthoida-carnero", (0.03, 0.03, 0.97, 0.97), "gray", {}),
    "nereites": ("trace-nereites-cymru", (0.03, 0.03, 0.97, 0.97), "gray", {}),
}


def _load_gray(path: Path, crop, mode: str, max_side: int = 2400) -> np.ndarray:
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(path) as im:
        im = im.convert("RGB")
        W, H = im.size
        x0, y0, x1, y1 = crop
        im = im.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))
        if max(im.size) > max_side:
            f = max_side / max(im.size)
            im = im.resize((int(im.size[0] * f), int(im.size[1] * f)), Image.Resampling.LANCZOS)
        a = np.asarray(im, dtype=np.float64) / 255.0
    if mode == "min":
        g = a.min(axis=2)
    else:
        g = a @ np.array([0.299, 0.587, 0.114])
    return 1.0 - g if mode == "inv" else g


def _extract_job(args):
    name, path, crop, mode, kw = args
    from gesture import extract_hybrid
    from gesture.extract import debug_overlay
    t = time.perf_counter()
    g = _load_gray(path, crop, mode)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            d = extract_hybrid.extract(g, source=name, **kw)
        except Exception as e:  # noqa: BLE001
            return {"name": name, "error": repr(e)}
    od = OUT / "extract"
    od.mkdir(parents=True, exist_ok=True)
    d.save(od / f"{name}.json")
    Image.fromarray(debug_overlay(g, d, max_side=1400)).save(od / f"{name}.jpg", quality=80)
    L = [s.length() for s in d.strokes]
    w = float(d.meta.get("line_width_px", 0) or 0)
    return {"name": name, "strokes": len(d.strokes), "w_px": round(w, 2),
            "med_len_w": round(float(np.median(L) / max(w, 1e-9)), 1) if L else 0,
            "secs": round(time.perf_counter() - t, 1)}


def stage_extract(a):
    jobs = [(n, CORPUS / "artists" / d / f"{f}.jpg", c, m, kw) for n, (d, f, c, m, kw) in ART.items()]
    for n, (d, c, m, kw) in EARTH.items():
        fs = sorted((CORPUS / "earth" / d).glob("*.jp*g"))
        if fs:
            jobs.append((n, fs[0], c, m, kw))
    if a.only:
        jobs = [j for j in jobs if j[0] in a.only.split(",")]
    rows = []
    with ProcessPoolExecutor(JOBS) as ex:
        for r in ex.map(_extract_job, jobs):
            print(r, flush=True)
            rows.append(r)
    p = OUT / "extract" / "summary.json"
    old = json.loads(p.read_text()) if p.exists() else []
    keep = {r["name"]: r for r in old}
    keep.update({r["name"]: r for r in rows})
    p.write_text(json.dumps(list(keep.values()), indent=1))


# ---------------------------------------------------------------------------
# stage: learn
# ---------------------------------------------------------------------------

# dance sources: id -> (file under corpus/dance, label, rights)
E2 = "E2-Create Stocos, CC BY 4.0 (dance-harvest.csv)"
CMU = "CMU Graphics Lab Motion Capture DB, free use (dance-harvest.csv)"
DANCE = {
    "dance_staccato": ("e2-stocos/Staccato_FullBody_Take1_proc.bvh", "Dance: Staccato", E2),
    "dance_levitation": ("e2-stocos/Levitation_FullBody_Take1_proc.bvh", "Dance: Levitation", E2),
    "dance_thrusting": ("e2-stocos/Thrusting_FullBody_Take1_proc.bvh", "Dance: Thrusting", E2),
    "dance_particles": ("e2-stocos/Particles_FullBody_Take1_proc.bvh", "Dance: Particles", E2),
    "dance_fluidity": ("e2-stocos/Fluidity_FullBody_Take1_proc.bvh", "Dance: Fluidity", E2),
    "mime_mantis": ("cmu-55/55_13.amc", "Mime: praying mantis (CMU 55_13)", CMU),
    "mime_penguin": ("cmu-55/55_18.amc", "Mime: penguin (CMU 55_18)", CMU),
    "mime_dragon": ("cmu-55/55_19.amc", "Mime: dragon (CMU 55_19)", CMU),
    "mime_roadrunner": ("cmu-55/55_15.amc", "Mime: roadrunner (CMU 55_15)", CMU),
    "mime_prairiedog": ("cmu-55/55_14.amc", "Mime: prairie dog (CMU 55_14)", CMU),
    "mime_monkey": ("cmu-55/55_08.amc", "Mime: monkey (CMU 55_08)", CMU),
}
DANCE_WIN, DANCE_MAX_WIN = 15.0, 6
VA = "V&A Collections API images (artists-harvest.csv); private research, statistics only, never published as training material"
ART_HANDS = {
    # id -> (extract names, tile nx×ny (1 = whole), label, description)
    "polygon_walk": (("noll_gq", "nake_poly"), 1, "Polygon walk (Noll, Nake)",
                     "Noll 'Gaussian-Quadratic' (1963) + Nake 'Random Polygons' (1965): straight runs and hard corners"),
    "aaron": (("aaron_1985", "aaron_1987a", "aaron_1987b"), 1, "AARON (Cohen)",
              "Harold Cohen's AARON line drawings, 1985 and 1987 (signature cropped)"),
    "meander69": (("meander_1969a", "meander_1969b"), 2, "Cohen meanders 1969",
                  "Harold Cohen 1969 untitled plotter meanders: right-angle routes, concentric squares"),
    "molnar_letters": (("molnar_letters",), 2, "Molnar 'Letters from my Mother'",
                       "Vera Molnar 'Letters from my Mother' (1988): rows of pseudo-script zigzag"),
    "henry_machine": (("henry_serpent", "henry_untitled"), 2, "Desmond Paul Henry machine",
                      "Desmond Paul Henry drawing-machine (bombsight) figures 1962/64, Otsu extraction"),
}


def dance_drawings(rel: str) -> tuple[list[Drawing], dict]:
    from gesture import dance as D
    m = D.load(CORPUS / "dance" / rel, 0, None, fps_out=60.0)
    dur = m.T / m.fps
    ds = []
    for k in range(min(int(dur // DANCE_WIN), DANCE_MAX_WIN)):
        d = D.trails(m.window(k * DANCE_WIN, (k + 1) * DANCE_WIN), view="front")
        if len(d.strokes) >= 3:
            ds.append(Drawing(d.strokes, source=f"{Path(rel).stem}@{int(k * DANCE_WIN)}s", size=d.size, meta=d.meta))
    return ds, {"duration_s": round(dur, 1), "windows_s": DANCE_WIN, "n_windows": len(ds)}


def art_drawings(names, tile: int) -> list[Drawing]:
    from gesture import hybrid as hy
    out = []
    for n in names:
        d = Drawing.load(OUT / "extract" / f"{n}.json")
        d = Drawing(d.strokes, source=n, size=d.size, meta=d.meta)
        out += hy.tile_drawing(d, tile, tile) if tile > 1 else [d]
    return out


def _learn_job(args):
    key, kind = args
    t = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if kind == "dance":
            ds, info = dance_drawings(DANCE[key][0])
        else:
            names, tile = ART_HANDS[key][:2]
            ds, info = art_drawings(names, tile), {"tile": tile, "extracts": list(names)}
        g = gm.learn(ds, name=key, min_len_w=12)
    (OUT / "grammars").mkdir(parents=True, exist_ok=True)
    g.save(OUT / "grammars" / f"{key}.json")
    (OUT / "train").mkdir(parents=True, exist_ok=True)
    for i, d in enumerate(ds):                       # training drawings, for the fidelity measure
        d.save(OUT / "train" / f"{key}__{i}.json")
    info.update({"sources": [d.source for d in ds], "strokes": len(g.strokes), "records": len(g.trans["nx"]),
                 "min_len_w": 12, "drawings": len(ds), "secs": round(time.perf_counter() - t, 1)})
    return key, kind, info


def save_hand(key: str, kind: str, info: dict, overwrite: bool = True):
    from gesture.kit import library as L
    d = json.loads((OUT / "grammars" / f"{key}.json").read_text())
    arrays, sheet = L.encode_hand(d)
    if kind == "dance":
        rel, label, rights = DANCE[key]
        corpus, desc = "dance", f"end-effector trails (hands, feet, head; front view) of {rel}, " \
                                f"{info['n_windows']} windows of {DANCE_WIN:.0f} s cut at whole-body stillness"
    else:
        names, tile, label, desc = ART_HANDS[key]
        corpus, rights = "artists", VA
    prov = {"research_file": str((OUT / "grammars" / f"{key}.json").relative_to(ROOT)), "research_commit": COMMIT,
            "description": desc, "rights": rights, "corpus": corpus, "training_sheets": info["sources"],
            "n_records": len(d["trans"]["nx"]), "n_strokes": len(d["strokes"]), "sigma_w": d["meta"].get("sigma_w"),
            "selection": d["meta"].get("selection", {}), "training": info,
            "experiment": "tools/gesture/experiments/voices_corpus.py learn"}
    entry = {"id": key, "kind": "hand", "label": label, "version": 1, "provenance": prov, "policy": "generative",
             "notes": "Round-9 voices_corpus hand (results/voices_corpus-2026-10-17.md). Token statistics only: "
                      "corpora give behaviours, never forms."}
    L.save(entry, {"tables.npz": L.npz_bytes(arrays), "sheet.json.gz": L.json_gz_bytes(sheet)}, overwrite=overwrite)
    g = L.load("hand", key)
    assert L.deep_equal(g.to_json(), d), key
    return L.entry("hand", key)["size_bytes"]


# dance trails frozen for the `dance` voice: (source id) -> (file, t0 s, seconds)
TRAILS = {
    "levitation": ("e2-stocos/Levitation_FullBody_Take1_proc.bvh", 30.0, 45.0, E2),
    "staccato": ("e2-stocos/Staccato_FullBody_Take1_proc.bvh", 30.0, 45.0, E2),
    "thrusting": ("e2-stocos/Thrusting_FullBody_Take1_proc.bvh", 20.0, 45.0, E2),
    "particles": ("e2-stocos/Particles_FullBody_Take1_proc.bvh", 30.0, 45.0, E2),
    "outofbalance": ("e2-stocos/OutOfBalance_FullBody_Take1_proc.bvh", 20.0, 45.0, E2),
    "mantis": ("cmu-55/55_13.amc", 20.0, 45.0, CMU),
    "penguin": ("cmu-55/55_18.amc", 0.0, 40.0, CMU),
    "dragon": ("cmu-55/55_19.amc", 5.0, 35.0, CMU),
    "hummingbird": ("cmu-55/55_05.amc", 0.0, 23.0, CMU),
}
TRAIL_FPS = 30.0


def save_trail(key: str, overwrite: bool = True) -> int:
    from gesture import dance as D
    from gesture.kit import library as L
    rel, t0, dur, rights = TRAILS[key]
    m = D.load(CORPUS / "dance" / rel, t0, t0 + dur, fps_out=TRAIL_FPS)
    B = D.view_basis(m, "front")
    H = m.height()
    arrays = {}
    from scipy.ndimage import gaussian_filter1d
    for name in D.EFFECTORS:
        p3 = m.pos[:, m.find(name)]
        p2 = gaussian_filter1d(p3 @ B, max(0.03 * m.fps, 0.5), axis=0, mode="nearest") / H
        v, a = D.kinematics(p3, m.fps, H)
        arrays[f"{name}_xy"] = p2.astype(np.float32)
        arrays[f"{name}_v"] = v.astype(np.float32)
        arrays[f"{name}_a"] = a.astype(np.float32)
    arrays["energy"] = D.energy(m).astype(np.float32)
    entry = {"id": key, "kind": "dance_trail", "label": f"Dance trail: {key}", "version": 1, "policy": "generative",
             "provenance": {"corpus": "dance", "file": f".local/gesture/corpus/dance/{rel}", "t0_s": t0,
                            "duration_s": round(m.T / m.fps, 3), "fps": float(m.fps), "view": "front",
                            "units": "body heights (median root-head x2); y down; speed in body heights/s",
                            "smoothing_s": 0.03, "rights": rights, "research_commit": COMMIT,
                            "effectors": list(D.EFFECTORS),
                            "experiment": "tools/gesture/experiments/voices_corpus.py learn"},
             "notes": "Frozen end-effector trails (the dance drawing itself) with per-frame speed/acceleration "
                      "and whole-body energy; read by the voices_corpus `dance` voice."}
    L.save(entry, {"trail.npz": L.npz_bytes(arrays)}, overwrite=overwrite)
    return L.entry("dance_trail", key)["size_bytes"]


KEEP_OUT = {"henry_machine"}


def stage_learn(a):
    jobs = [(k, "dance") for k in DANCE] + [(k, "art") for k in ART_HANDS]
    if a.only:
        jobs = [j for j in jobs if j[0] in a.only.split(",")]
    rows = {}
    if jobs:
        with ProcessPoolExecutor(JOBS) as ex:
            for key, kind, info in ex.map(_learn_job, jobs):
                # henry_machine is learned and measured but kept out of the library (a dud: nearest marden, loose)
                info["size_bytes"] = save_hand(key, kind, info) if key not in KEEP_OUT else 0
                rows[key] = info
                print(key, {k: v for k, v in info.items() if k != "sources"}, flush=True)
    p = OUT / "learn.json"
    old = json.loads(p.read_text()) if p.exists() else {}
    old.update(rows)
    p.write_text(json.dumps(old, indent=1))
    if not a.only or "trails" in a.only.split(","):
        for k in TRAILS:
            print("trail", k, save_trail(k), "bytes", flush=True)


# ---------------------------------------------------------------------------
# stage: measure — distinctness and coherence in panel space
# ---------------------------------------------------------------------------

SEED_HANDS = ("matisse", "hokusai", "ingres", "shikasta", "nastaliq", "marden", "lichtenberg", "bubble")
SIZE = (1000, 1200)
N_SHEETS = 6
HYB_REAL = ROOT / ".local/gesture/out/hybrid_hands/panel_real.json"


def new_hands() -> list[str]:
    p = OUT / "learn.json"
    return sorted(json.loads(p.read_text())) if p.exists() else []


def _features(d: Drawing) -> dict:
    from gesture import medium, panel
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if len(d.strokes) < 2:
            return {}
        f, _ = panel.features_with_info(d, sigma_min_w=medium.SIGMA_MIN_W)
    return f


def _gen_job(args):
    hand, i = args
    from gesture.kit import library as L
    g = L.load("hand", hand)                      # policy gate
    t = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            d = gm.generate_drawing(g, np.random.default_rng(9000 + i), SIZE)
        except Exception as e:  # noqa: BLE001
            return f"{hand}|gen{i}", None, repr(e)
    (OUT / "gen").mkdir(parents=True, exist_ok=True)
    d.save(OUT / "gen" / f"{hand}__{i}.json")
    return f"{hand}|gen{i}", _features(d), round(time.perf_counter() - t, 1)


def _train_job(path):
    d = Drawing.load(path)
    return path.stem.split("__")[0] + "|" + path.stem, _features(d)


def stage_measure(a):
    from gesture import hybrid as hy
    hands = list(SEED_HANDS) + new_hands()
    pf = OUT / "panel_gen.json"
    gen = json.loads(pf.read_text()) if pf.exists() else {}
    jobs = [(h, i) for h in hands for i in range(N_SHEETS) if f"{h}|gen{i}" not in gen]
    tf_ = OUT / "panel_train.json"
    train = json.loads(tf_.read_text()) if tf_.exists() else {}
    tjobs = [p for p in sorted((OUT / "train").glob("*.json")) if not any(k.endswith(p.stem) for k in train)]
    print(len(jobs), "sheets to generate,", len(tjobs), "training drawings to measure", flush=True)
    with ProcessPoolExecutor(JOBS) as ex:
        for k, f in ex.map(_train_job, tjobs):
            train[k] = f
        tf_.write_text(json.dumps(train))
        for n, (k, f, info) in enumerate(ex.map(_gen_job, jobs)):
            if f is None:
                print("FAIL", k, info, flush=True)
                continue
            gen[k] = f
            if n % 6 == 0:
                print(n, k, info, "s", flush=True)
                pf.write_text(json.dumps(gen))
    pf.write_text(json.dumps(gen))
    rep = measure_report(hands, gen, train, json.loads(HYB_REAL.read_text()), hy)
    (OUT / "measure.json").write_text(json.dumps(rep, indent=1))
    md = measure_table(rep)
    (OUT / "measure.md").write_text(md)
    print(md)


def measure_report(hands, gen, train, real, hy) -> dict:
    tf, names, rkeys, Zr = hy.projector(real)

    def Z(feats: dict):
        keys = [k for k in feats if feats[k]]
        X = np.array([[feats[k].get(n, np.nan) for n in names] for k in keys], float)
        return keys, tf(X)
    gk, Zg = Z(gen)
    grp = np.array([k.split("|")[0] for k in gk])
    hands = [h for h in hands if (grp == h).sum() >= 3]
    cen = {h: Zg[grp == h].mean(0) for h in hands}
    rad = {h: float(np.sqrt(np.mean(np.sum((Zg[grp == h] - cen[h]) ** 2, 1)))) for h in hands}
    med_rad = float(np.median(list(rad.values())))
    # training drawings: new hands from OUT/train, seed hands from the round-8 real panel
    tk, Zt = Z(train) if train else ([], np.zeros((0, Zg.shape[1])))
    tgrp = np.array([k.split("|")[0] for k in tk])
    rgrp = np.array([k.split("|")[0] for k in rkeys])
    out = {"names": len(names), "n_sheets": {h: int((grp == h).sum()) for h in hands}, "hands": {}}
    for h in hands:
        others = [o for o in hands if o != h]
        dist = {o: float(np.linalg.norm(cen[h] - cen[o]) / (0.5 * (rad[h] + rad[o]))) for o in others}
        near = min(dist, key=dist.get)
        seed_others = [o for o in others if o in SEED_HANDS]
        near_seed = min(seed_others, key=dist.get)
        m = (grp == h) | (grp == near)
        auc_near = hy.cv_auc(Zg[m], (grp[m] == h).astype(int))
        # self-recognition: leave-one-out nearest centroid among all hands
        hits = 0
        for z_i in np.flatnonzero(grp == h):
            c_h = (Zg[grp == h].sum(0) - Zg[z_i]) / max((grp == h).sum() - 1, 1)
            dd = {o: np.linalg.norm(Zg[z_i] - (c_h if o == h else cen[o])) for o in hands}
            hits += min(dd, key=dd.get) == h
        Ztr = Zt[tgrp == h] if h not in SEED_HANDS else Zr[rgrp == h]
        fid = None
        fid_dist = None
        if len(Ztr) >= 3:
            mm = np.vstack([Zg[grp == h], Ztr])
            yy = np.r_[np.ones((grp == h).sum()), np.zeros(len(Ztr))].astype(int)
            fid = hy.cv_auc(mm, yy)
            ctr = Ztr.mean(0)
            rtr = float(np.sqrt(np.mean(np.sum((Ztr - ctr) ** 2, 1))))
            fid_dist = float(np.linalg.norm(cen[h] - ctr) / (0.5 * (rad[h] + rtr)))
        out["hands"][h] = {
            "new": h not in SEED_HANDS, "nearest": near, "dist_nearest": round(dist[near], 3),
            "nearest_seed": near_seed, "dist_nearest_seed": round(dist[near_seed], 3),
            "auc_vs_nearest": round(auc_near, 3), "tightness": round(rad[h] / med_rad, 3),
            "self_recognition": round(hits / max((grp == h).sum(), 1), 3),
            "fidelity_auc": None if fid is None else round(fid, 3),
            "fidelity_dist": None if fid_dist is None else round(fid_dist, 3),
            "n_train": int(len(Ztr)), "dist": {o: round(v, 3) for o, v in sorted(dist.items())}}
    from sklearn.decomposition import PCA
    pca = PCA(2, random_state=0).fit(Zg)
    out["pca"] = {k: [round(float(v), 4) for v in pca.transform(Zg[i:i + 1])[0]] for i, k in enumerate(gk)}
    out["pca_train"] = {k: [round(float(v), 4) for v in pca.transform(Zt[i:i + 1])[0]] for i, k in enumerate(tk)}
    out["pca_var"] = [round(float(v), 3) for v in pca.explained_variance_ratio_]
    return out


def measure_table(rep: dict) -> str:
    rows = ["| # | hand | new | nearest (dist) | nearest seed hand (dist) | AUC vs nearest | tightness | "
            "self-recog | fidelity AUC / dist | n train |", "|---|---|---|---|---|---|---|---|---|---|"]
    H = rep["hands"]
    order = sorted(H, key=lambda h: (not H[h]["new"], -H[h]["dist_nearest_seed"]))
    for i, h in enumerate(order, 1):
        r = H[h]
        fa = "–" if r["fidelity_auc"] is None else f"{r['fidelity_auc']:.2f} / {r['fidelity_dist']:.2f}"
        rows.append(f"| {i} | {h} | {'yes' if r['new'] else ''} | {r['nearest']} ({r['dist_nearest']:.2f}) | "
                    f"{r['nearest_seed']} ({r['dist_nearest_seed']:.2f}) | {r['auc_vs_nearest']:.2f} | "
                    f"{r['tightness']:.2f} | {r['self_recognition']:.2f} | {fa} | {r['n_train']} |")
    return "\n".join(rows) + "\n"


# ---------------------------------------------------------------------------
# stage: limb — which pairing / extraction setting gives the hand farthest from
# every library hand while staying self-consistent? (variants are NOT saved to
# the library unless they win; grammars in OUT/limb)
# ---------------------------------------------------------------------------

LIMB = {
    # id -> (kind, sources, tile, min_len_w, effectors (dance only))
    "L_noll": ("art", ("noll_gq",), 2, 12, None),
    "L_nake": ("art", ("nake_poly",), 2, 12, None),
    "L_polygon_t2": ("art", ("noll_gq", "nake_poly"), 2, 12, None),
    "L_polygon_w40": ("art", ("noll_gq", "nake_poly"), 2, 40, None),
    "L_meander_w40": ("art", ("meander_1969a", "meander_1969b"), 2, 40, None),
    "L_aaron_w30": ("art", ("aaron_1985", "aaron_1987a", "aaron_1987b"), 1, 30, None),
    "L_staccato_hands": ("dance", "e2-stocos/Staccato_FullBody_Take1_proc.bvh", 0, 12, ("lhand", "rhand")),
    "L_roadrunner_feet": ("dance", "cmu-55/55_15.amc", 0, 12, ("lfoot", "rfoot")),
    "L_monkey_hands": ("dance", "cmu-55/55_08.amc", 0, 12, ("lhand", "rhand")),
    "L_levitation_head": ("dance", "e2-stocos/Levitation_FullBody_Take1_proc.bvh", 0, 12, ("head",)),
}


def _limb_learn(key):
    from gesture import dance as D
    kind, src, tile, mlw, eff = LIMB[key]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if kind == "art":
            ds = art_drawings(src, tile)
        else:
            m = D.load(CORPUS / "dance" / src, 0, None, fps_out=60.0)
            ds = []
            for k in range(min(int(m.T / m.fps // DANCE_WIN), 8)):
                d = D.trails(m.window(k * DANCE_WIN, (k + 1) * DANCE_WIN), eff, view="front")
                if len(d.strokes) >= 3:
                    ds.append(Drawing(d.strokes, source=f"{Path(src).stem}@{int(k * DANCE_WIN)}s", size=d.size,
                                      meta=d.meta))
        g = gm.learn(ds, name=key, min_len_w=mlw)
    (OUT / "limb").mkdir(parents=True, exist_ok=True)
    g.save(OUT / "limb" / f"{key}.json")
    feats = {f"{key}|train{i}": _features(d) for i, d in enumerate(ds)}
    gen = {}
    for i in range(N_SHEETS):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                d = gm.generate_drawing(g, np.random.default_rng(9000 + i), SIZE)
            except Exception:  # noqa: BLE001
                continue
        gen[f"{key}|gen{i}"] = _features(d)
    return key, feats, gen, {"drawings": len(ds), "strokes": len(g.strokes), "sources": [d.source for d in ds]}


def stage_limb(a):
    from gesture import hybrid as hy
    keys = [k for k in LIMB if not a.only or k in a.only.split(",")]
    gen = json.loads((OUT / "panel_gen.json").read_text())
    train = json.loads((OUT / "panel_train.json").read_text())
    info = {}
    with ProcessPoolExecutor(JOBS) as ex:
        for key, tf_, gf, inf in ex.map(_limb_learn, keys):
            train.update(tf_)
            gen.update(gf)
            info[key] = inf
            print(key, inf["drawings"], inf["strokes"], len(gf), flush=True)
    hands = list(SEED_HANDS) + new_hands() + keys
    rep = measure_report(hands, gen, train, json.loads(HYB_REAL.read_text()), hy)
    # distinctness vs the LIBRARY (seed + this round's saved hands), excluding the other limb variants
    lib = set(SEED_HANDS) | set(new_hands())
    for k in list(rep["hands"]):
        r = rep["hands"][k]
        cand = {o: v for o, v in r["dist"].items() if o in lib and o != k}
        o = min(cand, key=cand.get)
        r["nearest_library"], r["dist_nearest_library"] = o, cand[o]
        r["score"] = round(cand[o] / max(r["tightness"], 1e-9), 3)
    rep["limb_info"] = info
    (OUT / "limb.json").write_text(json.dumps(rep, indent=1))
    rows = ["| # | hand | nearest library hand (dist) | tightness | self-recog | fidelity AUC | score = dist / tightness |",
            "|---|---|---|---|---|---|---|"]
    H = rep["hands"]
    for i, k in enumerate(sorted(H, key=lambda h: -H[h]["score"]), 1):
        r = H[k]
        fa = "–" if r["fidelity_auc"] is None else f"{r['fidelity_auc']:.2f}"
        rows.append(f"| {i} | {k} | {r['nearest_library']} ({r['dist_nearest_library']:.2f}) | {r['tightness']:.2f} | "
                    f"{r['self_recognition']:.2f} | {fa} | {r['score']:.2f} |")
    md = "\n".join(rows) + "\n"
    (OUT / "limb.md").write_text(md)
    print(md)


# ---------------------------------------------------------------------------
# stage: sheets — every image from kit.run + kit.preview (recipe JSON beside it)
# ---------------------------------------------------------------------------

DANCE_HANDS = ("dance_staccato", "dance_levitation", "dance_thrusting", "dance_particles", "dance_fluidity",
               "mime_mantis", "mime_penguin", "mime_dragon", "mime_roadrunner", "mime_prairiedog", "mime_monkey")
ART_IDS = ("polygon_walk", "aaron", "meander69", "molnar_letters")  # henry_machine: dud, not kept in the library
TILE = [130, 100]


def _tile(name: str, recipe: dict, px: float = 4.0):
    from gesture import kit
    sheet = kit.run(recipe)
    kit.preview(sheet, OUT / "sheets" / f"{name}.jpg", px_per_mm=px, label=recipe["label"])
    return kit.render_image(sheet, px_per_mm=px, label=recipe["label"]), sheet


def _hand_tile(h: str, seed: int, length: float = 5.0, joins: str = "smooth", note: str = ""):
    return {"label": f"{h}{note}  (hand, {length:g} R, seed {seed}{', chain' if joins == 'chain' else ''})",
            "frame": TILE, "seed": seed, "voice": {"id": "hand", "hand": h, "length": length, "joins": joins},
            "renderer": {"id": "wire", "pen": 0.35}}


def _save(img, path: Path, max_kb: int = 950):
    img = img.convert("RGB")
    if max(img.size) > 2800:
        img.thumbnail((2800, 2800), Image.Resampling.LANCZOS)
    for q in (88, 82, 75, 68, 60, 52):
        img.save(path, quality=q)
        if path.stat().st_size <= max_kb * 1024:
            break
    print("wrote", path.relative_to(ROOT), f"{path.stat().st_size // 1024} KB", flush=True)


def sheet_set(name: str, recipes: list[tuple[str, dict]], cols: int, title: str, px: float = 4.0):
    from gesture import kit
    (OUT / "sheets").mkdir(parents=True, exist_ok=True)
    imgs = []
    for nm, r in recipes:
        t = time.perf_counter()
        try:
            im, _ = _tile(f"{name}__{nm}", r, px)
        except Exception as e:  # noqa: BLE001
            print("FAIL", nm, repr(e), flush=True)
            continue
        imgs.append(im)
        print(f"  {nm:<34} {time.perf_counter() - t:5.1f} s", flush=True)
    _save(kit.contact(imgs, cols, title=title), RES / f"voices_corpus-{name}.jpg")


def stage_sheets(a):
    only = set(a.only.split(",")) if a.only else None
    want = lambda k: only is None or k in only  # noqa: E731
    if want("hands-dance"):
        rs = [(h, _hand_tile(h, 7000)) for h in DANCE_HANDS] + [("matisse", _hand_tile("matisse", 7000, note=" [seed hand, reference]"))]
        sheet_set("hands-dance", rs, 4, "voices_corpus: hands learned from dance trails (E2 qualities, CMU-55 mimes), "
                  "each alone, one line, wire; last tile = matisse for reference")
    if want("hands-computer"):
        rs = []
        for h in ART_IDS:
            rs += [(f"{h}-a", _hand_tile(h, 7000)), (f"{h}-b", _hand_tile(h, 7001, joins="chain"))]
        rs += [("matisse", _hand_tile("matisse", 7000, note=" [seed]")), ("shikasta", _hand_tile("shikasta", 7000, note=" [seed]"))]
        sheet_set("hands-computer", rs, 4, "voices_corpus: hands learned from early computer art (Noll+Nake, AARON, "
                  "Cohen 1969, Molnar), each alone: smooth joins | chain joins; last two = seed hands")
    if want("dance-itself"):
        rs = []
        for tr in ("levitation", "staccato", "mantis", "penguin", "dragon", "outofbalance", "thrusting",
                   "particles", "hummingbird"):
            rs.append((tr, {"label": f"dance '{tr}' 15 s, all ends, own_tempo (self, one bead per pause), nib e", "frame": TILE,
                            "seed": 7000, "voice": {"id": "dance", "trail": tr, "seconds": 15.0},
                            "modulators": [{"id": "own_tempo"}], "renderer": {"id": "nib", "style": "e", "pen": 0.35}}))
        for tr in ("penguin", "staccato", "outofbalance"):
            rs.append((f"{tr}-dwell", {"label": f"dance '{tr}', own_tempo beads=DWELL (every still sample is mass)",
                                       "frame": TILE, "seed": 7000, "voice": {"id": "dance", "trail": tr, "seconds": 15.0},
                                       "modulators": [{"id": "own_tempo", "beads": "dwell", "mass_width": 4.0}],
                                       "renderer": {"id": "nib", "style": "e", "pen": 0.35}}))
        for tr in ("levitation", "staccato", "outofbalance"):
            rs.append((f"{tr}-abs", {"label": f"dance '{tr}', own_tempo ABSOLUTE norm (v_ref 1.5 bh/s): quality as weight",
                                     "frame": TILE, "seed": 7000, "voice": {"id": "dance", "trail": tr, "seconds": 15.0},
                                     "modulators": [{"id": "own_tempo", "norm": "absolute"}],
                                     "renderer": {"id": "nib", "style": "e", "pen": 0.35}}))
        sheet_set("dance-itself", rs, 3, "voices_corpus: the dance drawing itself (voice 'dance'), weighted by the "
                  "line's own clock (modulator own_tempo: stillness -> bead, speed -> wire)")
    if want("drifts"):
        D = [("matisse", "aaron", "polygon_walk", "smooth"), ("polygon_walk", "meander69", "molnar_letters", "chain"),
             ("dance_levitation", "mime_mantis", "shikasta", "smooth"), ("aaron", "mime_penguin", "lichtenberg", "smooth"),
             ("meander69", "hokusai", "mime_roadrunner", "chain"), ("mime_dragon", "polygon_walk", "aaron", "chain")]
        rs = [(f"{'-'.join(d[:3])}-{d[3]}",
               {"label": f"drift {' > '.join(d[:3])} ({d[3]} joins)", "frame": [180, 130], "seed": 7100 + i,
                "voice": {"id": "drift", "hands": list(d[:3]), "joins": d[3], "length": 7.0},
                "renderer": {"id": "wire", "pen": 0.35}}) for i, d in enumerate(D)]
        sheet_set("drifts", rs, 2, "voices_corpus: new hands in drifts with seed hands (one line each, wire)")
    if want("limb"):
        rs = []
        for h in ("polygon_walk", "mime_monkey_hands"):
            for sd in (7000, 7001, 7002):
                rs.append((f"{h}-{sd}", _hand_tile(h, sd, length=5.0, joins="chain" if sd == 7002 else "smooth")))
        rs += [("drift-poly-monkey-matisse", {"label": "drift polygon_walk > mime_monkey_hands > matisse (smooth)",
                                              "frame": TILE, "seed": 7400,
                                              "voice": {"id": "drift", "hands": ["polygon_walk", "mime_monkey_hands", "matisse"],
                                                        "length": 7.0}, "renderer": {"id": "wire", "pen": 0.35}}),
               ("drift-monkey-shikasta-poly", {"label": "drift mime_monkey_hands > shikasta > polygon_walk (chain)",
                                               "frame": TILE, "seed": 7401,
                                               "voice": {"id": "drift", "hands": ["mime_monkey_hands", "shikasta", "polygon_walk"],
                                                         "length": 7.0, "joins": "chain"}, "renderer": {"id": "wire", "pen": 0.35}})]
        sheet_set("limb", rs, 4, "voices_corpus limb: the two hands farthest from every library hand - polygon_walk "
                  "(Noll+Nake, coherent: tightness 0.33, self-recognition 1.00) and mime_monkey_hands (far: 2.61, loose) - "
                  "alone x3, then in drifts")
    if want("grid"):
        pairs = ["aaron", "matisse", "polygon_walk", "shikasta", "meander69", "lichtenberg", "mime_mantis",
                 "hokusai", "molnar_letters", "marden", "dance_staccato", "bubble"]
        rs = [("grid", {"label": "grid, one common scale: aaron | matisse | polygon_walk | shikasta / meander69 | "
                                 "lichtenberg | mime_mantis | hokusai / molnar_letters | marden | dance_staccato | bubble",
                        "frame": [267, 180], "seed": 7200, "arranger": {"id": "grid", "cols": 4, "gap": 4},
                        "parts": [{"voice": {"id": "hand", "hand": h, "length": 4.0}} for h in pairs],
                        "renderer": {"id": "wire", "pen": 0.35}}),
              ("polyphony", {"label": "one surface: mantis dance itself (own_tempo, nib e) x polygon_walk wire x "
                                      "aaron wire",
                             "frame": [267, 180], "seed": 7300,
                             "parts": [{"voice": {"id": "dance", "trail": "mantis", "seconds": 12.0},
                                        "modulators": [{"id": "own_tempo"}],
                                        "renderer": {"id": "nib", "style": "e", "pen": 0.35}},
                                       {"voice": {"id": "hand", "hand": "polygon_walk", "length": 4.0, "joins": "chain"},
                                        "renderer": {"id": "wire", "pen": 0.3}},
                                       {"voice": {"id": "hand", "hand": "aaron", "length": 5.0},
                                        "renderer": {"id": "wire", "pen": 0.3}}],
                             "renderer": {"id": "wire", "pen": 0.35}})]
        sheet_set("grid", rs, 1, "voices_corpus: new hands set among seed hands (grid 'each') and on one surface",
                  px=5.0)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("stage")
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    stages = {"extract": stage_extract, "learn": stage_learn, "measure": stage_measure, "sheets": stage_sheets, "limb": stage_limb}
    for s in (list(stages) if a.stage == "all" else a.stage.split(",")):
        t = time.time()
        stages[s](a)
        print(f"[{s}] {time.time() - t:.0f} s", flush=True)


if __name__ == "__main__":
    main()
