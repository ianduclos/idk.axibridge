"""Regenerate the gesture kit's seed library from the local research outputs.

    .local/gesture/.venv/bin/python tools/gesture/build_library.py [--only hand,tempo,corpus]

Writes `tools/gesture/library/` (committed):

- hand/<id>/   the round-8 hands (matisse, hokusai, ingres from grammar_v7;
               shikasta, nastaliq, marden, lichtenberg, bubble from
               hybrid_hands) in tools/hand_drift/freeze.py's compact format
               made general: tables.npz (next-token kind, params, remaining
               length, position, source stroke, stroke lengths — integers at
               the research rounding) + sheet.json.gz (sheet-level data);
               previous-token columns and training strokes are derived on
               load. `library.encode_hand` asserts the decoded grammar equals
               the research JSON exactly.
- tempo/<id>/  the six dance tempo profiles (full research Timing, float64:
               lossless), from experiments/gesture_timing.take_timing.
- corpus/<id>/ an INDEX entry per folder in .local/gesture/corpus/ — counts,
               manifests, local path, policy. Scans never enter the library.

Policy: Arabic hands must pass calligraphy.require_generative AND not be in
script_syntax.EXCLUDE_GENERATIVE (the lead's wc-30 ruling); the calligraphy
and print corpora are measure-only (Qur'anic/devotional material inside),
with the calligraphy allow-list recorded as `generative_items`.

Needs `.local/gesture/` (this Mac). Re-running overwrites the seed entries
only; entries other agents added are left alone.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from gesture import calligraphy  # noqa: E402
from gesture.kit import library as L  # noqa: E402

V7 = ROOT / ".local/gesture/out/grammar_v7"
HYB = ROOT / ".local/gesture/out/hybrid_hands/grammars"
CORPUS = ROOT / ".local/gesture/corpus"
MAN = ROOT / "docs/research/gesture-corpus"
CREATED = "2026-10-17"

# id -> (research file, label, description, rights, corpus id)
HANDS = {
    "matisse": (V7 / "grammar_matisse.json", "Matisse", "Henri Matisse prints and drawings (SMK open data)",
                "matisse-smk.csv: public domain mark (SMK)", "matisse"),
    "hokusai": (V7 / "grammar_hokusai.json", "Hokusai", "Hokusai sketches (museum open-access scans)",
                "comparison-met.csv: Met Open Access (CC0)", "hokusai"),
    "ingres": (V7 / "grammar_ingres.json", "Ingres", "Ingres graphite drawings (museum open-access scans)",
               "comparison-met.csv: Met Open Access (CC0)", "ingres"),
    "shikasta": (HYB / "shikasta.json", "Shikasta (exercise)", "Shekasteh nasta'liq siyah mashq and a petition",
                 "calligraphy-harvest.csv: generative-allowed content types only", "calligraphy"),
    "nastaliq": (HYB / "nastaliq.json", "Nasta'liq (exercise)", "Nasta'liq calligraphic exercises / pen trials",
                 "calligraphy-harvest.csv: generative-allowed content types only", "calligraphy"),
    "marden": (HYB / "marden.json", "Marden", "Brice Marden drawings (MoMA open data images)",
               "artists-harvest.csv: (c) artist/estate, museum permits personal use; private research", "artists"),
    "lichtenberg": (HYB / "lichtenberg.json", "Lichtenberg", "One Lichtenberg figure, tiled 2x2",
                    "earth-physics-harvest.csv", "earth"),
    "bubble": (HYB / "bubble.json", "Bubble chamber", "One bubble-chamber print, tiled 2x2",
               "earth-physics-harvest.csv", "earth"),
}
ARABIC = ("shikasta", "nastaliq")

# id -> (experiments.gesture_timing.TAKES label, description)
TEMPOS = {
    "staccato": ("Staccato (Romero)", "E2-Create Stocos, Staccato take 1, right hand"),
    "fluidity": ("Fluidity (Romero)", "E2-Create Stocos, Fluidity take 1, right hand"),
    "levitation": ("Levitation (Romero)", "E2-Create Stocos, Levitation take 1, right hand"),
    "particles": ("Particles (Romero)", "E2-Create Stocos, Particles take 1, right hand"),
    "cmu_49_10": ("CMU 49_10 fold-in, curl", "CMU mocap subject 49 trial 10, right hand"),
    "cmu_55_mantis": ("CMU 55_13 praying mantis", "CMU mocap subject 55 trial 13, right hand"),
}

# corpus folder -> (manifest csv, row filter, docs, policy, notes)
CORPORA = {
    "matisse": ("matisse-smk.csv", None, None, "generative", "SMK prints/drawings; public domain mark."),
    "hokusai": ("comparison-met.csv", ("artist", "hokusai"), None, "generative", "Met Open Access (CC0) sketches."),
    "ingres": ("comparison-met.csv", ("artist", "ingres"), None, "generative", "Met Open Access (CC0) drawings."),
    "artists": ("artists-harvest.csv", None, "artists-line.md", "generative",
                "Marden, Cohen, Molnar, Nake, Noll, Henry, Kelly; Picasso line drawings (round 11); Oehlen works on "
                "paper (round 12, albert_oehlen/, manifest oehlen-works-on-paper.csv). Several in copyright: "
                "private research only, never published as training material."),
    "calligraphy": ("calligraphy-harvest.csv", None, "calligraphy-arabic.md", "measure-only",
                    "Contains Qur'anic and devotional sheets: the folder is measure-only. generative_items is the "
                    "allow-list (manifest content_type exercise/poetry/document, nothing to verify, minus "
                    "script_syntax.EXCLUDE_GENERATIVE). Never output legible Arabic; call outputs 'line studies "
                    "after the X hand'."),
    "print": ("print-harvest.csv", None, "typography.md", "measure-only",
              "Arabic print books, cassette covers and fonts; no row passes the generative gate (books may hold "
              "Qur'anic/devotional text). Fonts are shaped with neutral strings only (calligraphy.NEUTRAL_STRINGS)."),
    "dance": ("dance-harvest.csv", None, "dance-gesture.md", "generative",
              "Mocap (BVH/AMC): E2-Create Stocos (CC BY 4.0), CMU (free use), Motion Bank. Tempo entries come from "
              "here."),
    "earth": ("earth-physics-harvest.csv", None, "earth-physics-lines.md", "generative",
              "Bubble-chamber prints, Lichtenberg figures, rivers (GRWL), cloud-chamber tracks."),
    "animal": ("round11-harvest.csv", ("group", "animal"), "round11-harvest.md", "generative",
               "Movement tracks: LifeTrack white stork and tropicbird GPS (Movebank, CC0), GeoLife (zipped). "
               "Used as drivers (round 12), not as hands."),
}


def _commit() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                          text=True).stdout.strip()


def _excluded() -> frozenset:
    try:
        from gesture.script_syntax import EXCLUDE_GENERATIVE  # noqa: PLC0415
        return frozenset(EXCLUDE_GENERATIVE)
    except Exception:  # noqa: BLE001 — keep the ruling even if the module moves
        return frozenset({"wc-30"})


def build_hands(lib: L.Library, commit: str) -> None:
    meta_hyb = json.loads((HYB / "meta.json").read_text())
    excluded = _excluded()
    for key, (path, label, desc, rights, corpus) in HANDS.items():
        d = json.loads(path.read_text())
        arrays, sheet = L.encode_hand(d)        # asserts the exact round trip
        sheets = [Path(s).stem if "/" in s else s for s in d["meta"].get("sources", [])]
        prov = {"research_file": str(path.relative_to(ROOT)), "research_commit": commit, "description": desc,
                "rights": rights, "corpus": corpus, "training_sheets": sheets,
                "n_records": len(d["trans"]["nx"]), "n_strokes": len(d["strokes"]),
                "sigma_w": d["meta"].get("sigma_w"), "selection": d["meta"].get("selection", {})}
        notes = "Round-8 hand (results/hybrid_hands-2026-10-16.md); the Hand Drift bench's frozen copy is identical."
        if key in meta_hyb:
            prov["training"] = meta_hyb[key]
        if key in ARABIC:
            base = [s.split("#")[0] for s in sheets]
            calligraphy.require_generative(base)
            bad = sorted(set(base) & excluded)
            if bad:
                raise calligraphy.PolicyError(f"{key}: trained on lead-excluded sheets {bad}")
            prov["allow_list"] = ("every training sheet passes calligraphy.require_generative (manifest content "
                                  "type exercise/poetry/document, nothing to verify) and is not in "
                                  "script_syntax.EXCLUDE_GENERATIVE")
            prov["excluded_measure_only"] = meta_hyb.get(key, {}).get("excluded_measure_only", [])
            notes += " Line statistics only — outputs are line studies after the hand, never legible Arabic."
        entry = {"id": key, "kind": "hand", "label": label, "version": 1, "created": CREATED, "provenance": prov,
                 "policy": "generative", "notes": notes}
        lib.save(entry, {"tables.npz": L.npz_bytes(arrays), "sheet.json.gz": L.json_gz_bytes(sheet)},
                 overwrite=True)
        g = lib.load("hand", key)
        if not L.deep_equal(g.to_json(), d):
            raise AssertionError(f"{key}: library load differs from the research JSON")
        print(f"hand   {key:<14} {lib.entry('hand', key)['size_bytes'] / 1024:8.1f} KB")


def build_tempos(lib: L.Library, commit: str) -> None:
    from experiments import gesture_timing as E  # noqa: PLC0415
    rights = {}
    with open(MAN / "dance-harvest.csv", newline="") as f:
        for r in csv.DictReader(f):
            rights[r["file"]] = r["rights_note"]
    for key, (label, desc) in TEMPOS.items():
        tm = E.take_timing(label)
        arrays, sheet = L.encode_tempo(tm)
        rel, eff, t0, dur = E.TAKES[label]
        prov = {"source": f"dance/{rel}", "effector": eff, "window_s": [t0, float(t0 + tm.t[-1])],
                "fps": float(tm.fps), "frames": int(len(tm.t)), "pauses": tm.n_pauses(), "corpus": "dance",
                "rights": rights.get(f"dance/{rel}", ""), "description": desc,
                "made_by": "experiments/gesture_timing.take_timing → gesture_timing.timing_from_motion",
                "research_commit": commit}
        entry = {"id": key, "kind": "tempo", "label": label, "version": 1, "created": CREATED, "provenance": prov,
                 "policy": "generative",
                 "notes": "A dancer's timing over a window (speed, wrist angle, lateral residual, jerk, pauses); "
                          "time is the only axis. Loads as gesture_timing.Timing (results/gesture_timing-2026-10-16.md)."}
        lib.save(entry, {"profile.npz": L.npz_bytes(arrays), "sheet.json.gz": L.json_gz_bytes(sheet)},
                 overwrite=True)
        back = lib.load("tempo", key)
        for k in L.TEMPO_ARRAYS:
            if not (getattr(back, k) == getattr(tm, k)).all():
                raise AssertionError(f"{key}: tempo {k} differs after the round trip")
        print(f"tempo  {key:<14} {lib.entry('tempo', key)['size_bytes'] / 1024:8.1f} KB")


def _manifest_rows(name: str, flt) -> list[dict]:
    with open(MAN / name, newline="") as f:
        rows = list(csv.DictReader(f))
    if flt:
        rows = [r for r in rows if r.get(flt[0]) == flt[1]]
    return rows


def build_corpora(lib: L.Library, commit: str) -> None:
    excluded = _excluded()
    for folder in sorted(p for p in CORPUS.iterdir() if p.is_dir()):
        name = folder.name
        man, flt, doc, policy, notes = CORPORA.get(name, (None, None, None, "measure-only",
                                                         "Unindexed folder: measure-only until someone rules."))
        files = sorted(p for p in folder.rglob("*") if p.is_file() and not p.name.startswith("."))
        ext = Counter(p.suffix.lower() or "(none)" for p in files)
        subs = {}
        for p in files:
            rel = p.relative_to(folder)
            top = rel.parts[0] if len(rel.parts) > 1 else "."
            s = subs.setdefault(top, {"files": 0, "bytes": 0})
            s["files"] += 1
            s["bytes"] += p.stat().st_size
        counts = {"files": len(files), "bytes": sum(p.stat().st_size for p in files),
                  "by_extension": dict(sorted(ext.items())), "subfolders": dict(sorted(subs.items()))}
        prov = {"local_path": str(folder.relative_to(ROOT)), "indexed_commit": commit,
                "manifests": [], "docs": [f"docs/research/gesture-corpus/{doc}"] if doc else []}
        entry = {"id": name, "kind": "corpus", "label": f"{name} corpus (index)", "version": 1, "created": CREATED,
                 "provenance": prov, "policy": policy, "notes": notes, "counts": counts}
        if man:
            rows = _manifest_rows(man, flt)
            on_disk = 0
            for r in rows:
                f = r.get("file") or ""
                cand = [CORPUS / f, folder / f] if f else []
                on_disk += any(c.exists() and c.is_file() for c in cand)
            prov["manifests"].append({"file": f"docs/research/gesture-corpus/{man}", "rows": len(rows),
                                      "rows_on_disk": on_disk, "filter": list(flt) if flt else None})
        if name in ("calligraphy", "print"):
            m = calligraphy.load_manifest(name)
            items = {}
            for k, r in sorted(m.items()):
                gen = calligraphy.generative_allowed(r) and k not in excluded
                items[k] = {"content_type": r.get("content_type", ""), "generative": bool(gen),
                            "on_disk": bool(r.get("file")) and (CORPUS / r["file"]).exists()}
            entry["items"] = items
            entry["generative_items"] = sorted(k for k, v in items.items() if v["generative"])
            prov["policy_source"] = ("calligraphy.generative_allowed over the manifest content_type, minus "
                                     "script_syntax.EXCLUDE_GENERATIVE; docs/research/gesture-corpus/"
                                     "calligraphy-arabic.md 'Adopted policy'")
        lib.save(entry, {}, overwrite=True)
        print(f"corpus {name:<14} {policy:<13} {counts['files']:5d} files {counts['bytes'] / 2**20:8.1f} MB local")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="corpus,hand,tempo")
    ap.add_argument("--root", default=None, help="library root (default tools/gesture/library)")
    a = ap.parse_args()
    lib = L.Library(a.root)
    commit = _commit()
    todo = a.only.split(",")
    if "corpus" in todo:       # first: the hand policy re-check reads the corpus allow-list
        build_corpora(lib, commit)
    if "hand" in todo:
        build_hands(lib, commit)
    if "tempo" in todo:
        build_tempos(lib, commit)
    print(lib.table())


if __name__ == "__main__":
    main()
