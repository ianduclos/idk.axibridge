"""Freeze the gesture kit for the synthesis bench (re-runnable; S4 of the build plan).

    .local/gesture/.venv/bin/python tools/synthesis/freeze.py [--no-fixtures]

A SEPARATE frozen copy of the kit (Ian, 2026-10-19: "studies are done, this
bench we might develop"): the synthesis bench is refrozen often, Gesture
Studies and its kept layers never move because of it. The hand library is
shared, because it is append-only and content-addressed.

Everything is read from the COMMITTED HEAD (`git archive HEAD`), never the
working tree. It writes:

1. `axibridge/sources/_synthesis/kit/` — every kit module the score executor,
   the relations, the writers, the devices and the Gesture Studies recipes
   (sealed layers) reach, found by following imports (lazy ones included) from
   `SEEDS`, plus the research modules they import under `kit/_research/`.
   Rewrites and the `calligraphy` stub are Gesture Studies' freeze's own
   (`tools/gesture_studies/freeze.py`); the one patch: the kit library's ROOT
   is Gesture Studies' frozen library. `kit/FROZEN.json` records the research
   commit, the library snapshot the bench resolves against by default, and the
   sha256 of every frozen file (a test checks nobody hand-edits them).

2. The library: Gesture Studies' `library/` (append-only). When the HEAD
   research library holds entries (or versions) that no frozen snapshot has,
   they are appended and a new snapshot written, WITHOUT moving Gesture
   Studies' `current` (its live previews stay as they are); the bench's
   snapshot is recorded in `kit/FROZEN.json`. A research withdrawal (an entry
   made measure-only) is global: the script stops and asks for a Gesture
   Studies refreeze first.

3. `tests/fixtures/synthesis/<case>.json` — parity fixtures: each case's
   score (written by the HEAD research writers, or literal) played by the HEAD
   research kit over the HEAD research library, summarised per ink. Before
   writing, the FROZEN copy (its writers too) must reproduce the very same
   score and summary under this interpreter. `tests/test_synthesis.py` replays
   them in the app venv.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/gesture_studies"))
import freeze as GS  # noqa: E402  — Gesture Studies' freeze: rewrites, stub, hashing, summaries

APP = ROOT / "axibridge/sources/_synthesis"
KIT_OUT = APP / "kit"
RES_OUT = KIT_OUT / "_research"
LIB = ROOT / "axibridge/sources/_gesture_studies/library"          # shared, append-only
FIXTURES = ROOT / "tests/fixtures/synthesis"

# where the import walk starts: Gesture Studies' modules (every study recipe works as a sealed layer)
# and the synthesis contract (executor, relations, writers, devices)
SEED_GLOBS = ("_synth", "_relations", "_writers", "_measure", "relations_*", "writers_*", "devices_*",
              "modulators_place")
LIBRARY_PATCHES = [
    ('ROOT = KIT.parents[1] / "library"             # tools/gesture/library',
     'ROOT = KIT.parents[1] / "_gesture_studies" / "library"   # app: Gesture Studies\' frozen library (shared,\n'
     '                                # append-only); read it through axibridge.sources._synthesis.frozen_library'),
]
_KIT_IMPORT = (re.compile(r"^\s*from \.(\w+) import", re.M), re.compile(r"^\s*from \. import ([\w ,]+)", re.M))
_RES_IMPORT = (re.compile(r"^\s*from \.\. import ([\w ,]+)", re.M), re.compile(r"^\s*from \.\.(\w+) import", re.M))
_RES_INNER = (re.compile(r"^\s*from (?:gesture)?\.(\w+) import", re.M),
              re.compile(r"^\s*from (?:gesture|\.) import ([\w ,]+)", re.M),
              re.compile(r"^\s*from gesture\.(\w+) import", re.M))


def _names(found: list[str]) -> list[str]:
    out = []
    for f in found:
        for part in f.split(","):
            w = part.strip().split(" as ")[0].strip()
            if w:
                out.append(w)
    return out


def module_sets(src_root: Path) -> tuple[list[str], list[str]]:
    """(kit modules, research modules) the synthesis bench needs, by following imports from the seeds."""
    kit = src_root / "tools/gesture/gesture/kit"
    res = src_root / "tools/gesture/gesture"
    todo = list(GS.KIT_MODULES) + ["__init__", "core", "library"]
    for g in SEED_GLOBS:
        todo += sorted(p.stem for p in kit.glob(f"{g}.py"))
    have: set[str] = set()
    rmods: set[str] = set(GS.RESEARCH_MODULES)
    while todo:
        m = todo.pop()
        if m in have or not (kit / f"{m}.py").exists():
            continue
        have.add(m)
        t = (kit / f"{m}.py").read_text()
        for rx in _KIT_IMPORT:
            todo += [n for n in _names(rx.findall(t)) if (kit / f"{n}.py").exists()]
        for rx in _RES_IMPORT:
            rmods |= {n for n in _names(rx.findall(t)) if (res / f"{n}.py").exists()}
    todo, rhave = sorted(rmods), set()
    while todo:
        m = todo.pop()
        if m in rhave or m == "calligraphy" or not (res / f"{m}.py").exists():
            continue
        rhave.add(m)
        t = (res / f"{m}.py").read_text()
        for rx in _RES_INNER:
            todo += [n for n in _names(rx.findall(t)) if (res / f"{n}.py").exists()]
    return sorted(have), sorted(rhave)


def freeze_code(src_root: Path, commit: str, snapshot: str) -> dict:
    kit_mods, res_mods = module_sets(src_root)
    if KIT_OUT.exists():
        shutil.rmtree(KIT_OUT)
    RES_OUT.mkdir(parents=True)
    files = {}

    def put(dst: Path, text: str, rel: str):
        dst.write_text(text)
        files[str(dst.relative_to(APP))] = {"research": rel, "sha256": hashlib.sha256(dst.read_bytes()).hexdigest()}

    ges = src_root / "tools/gesture/gesture"
    for name in kit_mods:
        rel = f"tools/gesture/gesture/kit/{name}.py"
        text = GS.rewrite_kit((ges / "kit" / f"{name}.py").read_text())
        if name == "library":
            for old, new in LIBRARY_PATCHES:
                if old not in text:
                    raise SystemExit(f"library.py patch target moved: {old!r}")
                text = text.replace(old, new)
        put(KIT_OUT / f"{name}.py", GS.header(commit, rel).replace("gesture_studies", "synthesis") + text, rel)
    put(RES_OUT / "__init__.py", GS.header(commit, "tools/gesture/gesture/").replace("gesture_studies", "synthesis")
        + '"""app: the research modules the frozen kit imports (`tools/gesture/gesture/`)."""\n',
        "tools/gesture/gesture/__init__.py")
    for name in res_mods:
        rel = f"tools/gesture/gesture/{name}.py"
        put(RES_OUT / f"{name}.py", GS.header(commit, rel).replace("gesture_studies", "synthesis")
            + GS.rewrite_research((ges / f"{name}.py").read_text()), rel)
    put(RES_OUT / "calligraphy.py", GS.header(commit, "tools/gesture/gesture/calligraphy.py").replace(
        "gesture_studies", "synthesis") + GS.CALLIGRAPHY_STUB, "tools/gesture/gesture/calligraphy.py (stub)")

    # what the frozen code could reach but cannot do in the app: reported, never silently present
    frozen = {*res_mods, "calligraphy"}
    dangling = []
    for f in sorted(KIT_OUT.rglob("*.py")):
        text = f.read_text()
        for mod in re.findall(r"^\s+from \.(\w+) import", text, re.M) + re.findall(r"^\s+from \. import (\w+)",
                                                                                     text, re.M):
            if f.parent == RES_OUT and mod not in frozen:
                dangling.append(f"{f.relative_to(APP)}: lazy import of unfrozen research module {mod!r}")
        for mod in re.findall(r"^\s+(?:from|import) (experiments|sklearn|skimage|fontTools|uharfbuzz)\b",
                              text, re.M):
            dangling.append(f"{f.relative_to(APP)}: lazy import of {mod!r} (not in the app)")
        if re.search(r"\.local/gesture|docs/research", text):
            dangling.append(f"{f.relative_to(APP)}: names a research data path (that code path cannot run in the app)")
    manifest = {"frozen_from": commit, "frozen": _dt.date.today().isoformat(), "library_snapshot": snapshot,
                "kit_modules": kit_mods, "research_modules": [*res_mods, "calligraphy (stub)"],
                "dangling_lazy_imports": sorted(set(dangling)), "files": files}
    (KIT_OUT / "FROZEN.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def ensure_library(src_root: Path, commit: str) -> dict:
    """The research library as a snapshot of Gesture Studies' frozen library (appending what is new,
    never moving its `current`). Returns {"snapshot", "added", "counts"}."""
    sys.path.insert(0, str(src_root / "tools/gesture"))
    from gesture.kit import library as L  # noqa: PLC0415 — the HEAD research library
    lib = L.Library(src_root / "tools/gesture/library")
    index = json.loads((LIB / "index.json").read_text())
    snapshot: dict[str, dict[str, str]] = {}
    added, newly_withdrawn = [], []
    for kind in (*GS.META_KINDS, *GS.GENERATIVE_KINDS, *GS.DATA_KINDS):
        snapshot[kind] = {}
        for eid in lib.ids(kind):
            entry = lib.entry(kind, eid)
            folder = lib.folder(kind, eid)
            if kind in GS.GENERATIVE_KINDS or kind in GS.DATA_KINDS:
                try:
                    lib.check(entry, "generate")
                    lib.load(kind, eid)
                except L.PolicyError:
                    if f"{kind}/{eid}" not in index.get("withdrawn", []):
                        newly_withdrawn.append(f"{kind}/{eid}")
                    continue
            h = GS._hash_entry(folder, entry)
            dst = LIB / kind / eid / h
            if not dst.exists():
                dst.mkdir(parents=True)
                for name in ["entry.json", *entry.get("files", {}).values()]:
                    (dst / name).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(folder / name, dst / name)
                added.append(f"{kind}/{eid}@{h}")
            snapshot[kind][eid] = h
    if newly_withdrawn:
        raise SystemExit(f"the research withdrew {newly_withdrawn} from generation: run "
                         "tools/gesture_studies/freeze.py first (a withdrawal is global)")
    sid = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()[:12]
    snap_path = LIB / "snapshots" / f"{sid}.json"
    if not snap_path.exists():
        snap_path.write_text(json.dumps({"id": sid, "frozen_from": commit, "frozen": _dt.date.today().isoformat(),
                                         "entries": snapshot, "by": "tools/synthesis/freeze.py"},
                                        indent=1, sort_keys=True) + "\n")
        index["history"].append(sid)                 # history only: Gesture Studies' `current` stays put
        (LIB / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    return {"snapshot": sid, "added": added, "counts": {k: len(v) for k, v in snapshot.items()}}


# ---------------------------------------------------------------------------
# parity fixtures
# ---------------------------------------------------------------------------

FRAME = [250.0, 175.0]


def _sealed_case(study_id: str) -> dict:
    d = json.loads((ROOT / "axibridge/sources/_gesture_studies/studies" / study_id / "study.json").read_text())
    composer = {k: v for k, v in d["recipe"].items() if k not in ("frame", "seed")}
    return {"version": 2, "frame": FRAME, "seed": 16001,
            "layers": [{"id": "A", "pen": "black", "part": {"voice": {"id": "hand", "hand": "marden"}}},
                       {"id": "S", "role": "sealed", "pen": "blue", "region": [125, 10, 115, 155],
                        "composer": composer}],
            "relations": [{"id": "X", "kind": "crossing", "src": "*", "dst": "*"}]}


def _base_case() -> dict:
    lines = [[[20.0 + 10 * i, 30.0], [40.0 + 10 * i, 150.0]] for i in range(12)]
    return {"version": 2, "frame": FRAME, "seed": 16002, "base": {"lines": lines},
            "layers": [{"id": "L0", "pen": "red", "part": {"voice": {"id": "hand", "hand": "matisse"}}},
                       {"id": "L1", "role": "listener", "pen": "blue",
                        "part": {"voice": {"id": "hand", "hand": "hokusai"}}}],
            "relations": [{"id": "X", "kind": "crossing", "src": "*", "dst": "*"},
                          {"id": "B", "kind": "crossing", "src": "base", "dst": "L1"}]}


# (name, how the score is made). "compose" cases run the writer on both sides and compare the scores too.
CASES = [
    ("listen-15102", {"compose": ["listen", 15102, {"balance": "one"}]}),
    ("listen-15105-speakers", {"compose": ["listen", 15105, {"balance": "speakers"}]}),
    ("ccolour-4545", {"compose": ["ccolour", 4545, {}]}),
    ("arch-15045", {"compose": ["arch", 15045, {}]}),
    ("recompose-15106", {"recompose": ["listen", 15106, {"balance": "one"}, "speaker", 15201]}),
    ("sealed-leaf_miner", {"score": "sealed:leaf_miner"}),
    ("base-lines", {"score": "base"}),
    ("listen-devices", {"compose": ["listen", 15103, {"balance": "one"}],
                        "devices": [{"id": "mdoc_staff", "place": "beside", "side": "bottom"},
                                    {"id": "meas_arcs", "place": "beside", "side": "bottom", "size": 50.0}]}),
]


def _make(case: dict, synth, writers, lib):
    if "compose" in case:
        w, seed, params = case["compose"]
        score = writers.compose(w, frame=FRAME, seed=seed, params=params, library=lib)
    elif "recompose" in case:
        w, seed, params, role, again = case["recompose"]
        s = writers.compose(w, frame=FRAME, seed=seed, params=params, library=lib)
        lock = next(L["id"] for L in s["layers"] if L["role"] == role)
        score = writers.recompose(synth.pin(s, [lock], library=lib), locked=[lock], seed=again, library=lib)
    elif case["score"] == "base":
        score = synth.validate(_base_case(), library=lib)
    else:
        score = synth.validate(_sealed_case(case["score"].split(":", 1)[1]), library=lib)
    if case.get("devices"):
        score = {**score, "devices": case["devices"]}
    return json.loads(json.dumps(score, default=float))


def parity_fixtures(src_root: Path, commit: str, snapshot: str) -> None:
    sys.path.insert(0, str(src_root / "tools/gesture"))
    import shapely  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    from gesture.kit import _synth as r_synth  # noqa: PLC0415
    from gesture.kit import _writers as r_writers  # noqa: PLC0415
    from gesture.kit import library as r_L  # noqa: PLC0415
    sys.path.insert(0, str(ROOT))
    from axibridge.sources._synthesis import frozen_library as FL  # noqa: PLC0415
    from axibridge.sources._synthesis.kit import _synth as f_synth  # noqa: PLC0415
    from axibridge.sources._synthesis.kit import _writers as f_writers  # noqa: PLC0415
    r_lib = r_L.Library(src_root / "tools/gesture/library")
    f_lib = FL.FrozenLibrary(snapshot)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, case in CASES:
        score = _make(case, r_synth, r_writers, r_lib)
        mine = _make(case, f_synth, f_writers, f_lib)
        if json.dumps(score, sort_keys=True) != json.dumps(mine, sort_keys=True):
            raise SystemExit(f"{name}: the frozen writers do not write the research writers' score")
        sheet = r_synth.run(score, library=r_lib, cache=False)
        out = {"case": name, "made": case, "research_commit": commit, "library": snapshot,
               "numpy": np.__version__, "geos": shapely.geos_version_string, "score": score, **GS._summary(sheet)}
        f_sheet = f_synth.run(mine, library=f_lib, cache=False)
        if GS._summary(f_sheet) != {k: out[k] for k in ("inks", "stride", "sample", "n_points")}:
            raise SystemExit(f"{name}: the frozen kit does not reproduce the research kit")
        (FIXTURES / f"{name}.json").write_text(json.dumps(out, separators=(",", ":")) + "\n")
        print(f"fixture {name:<24} {len(out['inks']):5d} inks {out['n_points']:7d} points "
              f"({sheet.meta['seconds']['marks'] + sheet.meta['seconds']['inks']:.1f} s)")


def main() -> None:
    commit = GS.git("rev-parse", "--short", "HEAD")
    with tempfile.TemporaryDirectory(prefix="synthesis-freeze-") as tmp:
        src_root = Path(tmp)
        GS.export_head(src_root)
        lib = ensure_library(src_root, commit)
        print(f"library snapshot {lib['snapshot']}: {lib['counts']}; appended {len(lib['added'])}")
        for a in lib["added"]:
            print("  added:", a)
        manifest = freeze_code(src_root, commit, lib["snapshot"])
        print(f"froze {len(manifest['files'])} files from {commit} "
              f"({len(manifest['kit_modules'])} kit, {len(manifest['research_modules'])} research)")
        for d in manifest["dangling_lazy_imports"]:
            print("  unreachable-in-app:", d)
        if "--no-fixtures" not in sys.argv:
            parity_fixtures(src_root, commit, lib["snapshot"])


if __name__ == "__main__":
    main()
