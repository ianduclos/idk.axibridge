"""Freeze the gesture kit and its library into the app (re-runnable).

    .local/gesture/.venv/bin/python tools/gesture_studies/freeze.py

Everything is read from the COMMITTED HEAD (`git archive HEAD`), never from
the working tree, so files a research agent is editing right now cannot leak
into the app. It writes:

1. `axibridge/sources/_gesture_studies/kit/` — the kit modules the studies use
   (KIT_MODULES) and, under `kit/_research/`, the research modules they import
   (RESEARCH_MODULES). Copied verbatim except for import rewrites (the kit's
   `from .. import grammar` becomes `from ._research import grammar`) and the
   patches marked "app:" below. `calligraphy.py` is replaced by a stub holding
   only `PolicyError` (the research module needs PIL at import). Each file gets
   a header naming the research commit; `kit/FROZEN.json` records the commit,
   every file's research path and the sha256 of the frozen bytes (a test checks
   nobody hand-edits them).

2. `axibridge/sources/_gesture_studies/library/` — EVERY generative entry of
   the kinds the studies can pick (hand, tempo, dance_trail) plus the corpus
   index entries (metadata only: the policy gate re-checks hands learned from a
   measure-only corpus against its allow-list). Entries that fail the research
   policy gate (`Library.check(entry, "generate")`) are never frozen and never
   become options. Content-addressed and APPEND-ONLY:

       library/<kind>/<id>/<hash12>/entry.json + data files
       library/snapshots/<snapshot12>.json   {kind: {id: hash12}} of one freeze
       library/index.json                    current snapshot, history, withdrawn

   A refreeze adds new hash folders and a new snapshot and moves `current`;
   it never deletes or rewrites an old one, so a kept layer (which records the
   snapshot it was made with and the hash of every entry its controls name)
   resolves exactly as it did. Entries that disappear from the research
   library simply leave `current`; entries the research has since made
   measure-only are listed in `withdrawn` and refused even through an old
   snapshot.

3. `tests/fixtures/gesture_studies/<study>.json` — the parity fixture: each
   built-in kit study's recipe (a sampler study: the recipe its seed samples,
   recorded as `sampled`, after checking the frozen sampler picks the same one)
   run through the HEAD research kit with the HEAD
   research library (this interpreter), summarised per ink (point count,
   closed/filled, pen, end points, coordinate moments) plus a strided sample of
   the points, and the GEOS version. Before writing it the script runs the
   FROZEN copy under this same interpreter and requires an identical result (the
   freeze is faithful). `tests/test_gesture_studies.py` runs the recipe through
   the frozen copy in the app venv and compares.

New hands, tempos or dance trails learned in the research library appear in
every study's hand / tempo / dance controls after a rerun of this script and a
restart: the controls list whatever the current snapshot holds.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "axibridge/sources/_gesture_studies"
KIT_OUT = APP / "kit"
RES_OUT = KIT_OUT / "_research"
LIB_OUT = APP / "library"
STUDIES = APP / "studies"
FIXTURES = ROOT / "tests/fixtures/gesture_studies"

# kit modules (tools/gesture/gesture/kit/<name>.py) the built-in studies need
KIT_MODULES = ("__init__", "core", "library", "arrangers_base", "modulators_base", "renderers_base",
               "voices_base", "voices_machine", "voices_machine_diagram", "poly_sheets", "poly_converse",
               "voices_corpus",
               # Studies v2 (2026-10-17): measurement pairs, the chorus and the sampler (its sample
               # space reaches prosody, restatement and coils, so those come too)
               "measure_pairs", "prosody_voices", "prosody_modulators", "prosody_renderers",
               "prosody_arrangers", "dev_beads", "dev_chorus", "sampler")
# research modules (tools/gesture/gesture/<name>.py) they import, transitively
RESEARCH_MODULES = ("core", "curvature", "clothoid", "grammar", "hybrid", "regime", "penrender",
                    "regime_field", "gesture_timing", "broadnib")
GENERATIVE_KINDS = ("hand", "tempo", "dance_trail")   # kinds a study control can pick
META_KINDS = ("corpus",)                              # index entries the policy gate reads
SAMPLE_POINTS = 800                                   # strided parity sample per study

CALLIGRAPHY_STUB = '''"""app: the research `calligraphy` module reduced to the one name the kit
library imports. The full module needs PIL and reads the scans; the app only
needs the exception type, so `kit.library.PolicyError` stays a subclass of it
exactly as in the research."""


class PolicyError(RuntimeError):
    """Restricted (measure-only) material reached a generative path."""
'''


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def export_head(dest: Path) -> None:
    data = subprocess.run(["git", "archive", "HEAD", "tools/gesture/gesture", "tools/gesture/library"], cwd=ROOT,
                          capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dest, filter="data")


def header(commit: str, rel: str) -> str:
    return (f"# FROZEN from research commit {commit}: {rel}\n"
            "# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked \"app:\").\n")


def rewrite_kit(src: str) -> str:
    src = re.sub(r"^(\s*)from \.\. import ", r"\1from ._research import ", src, flags=re.M)
    src = re.sub(r"^(\s*)from \.\.([A-Za-z_]\w*) import ", r"\1from ._research.\2 import ", src, flags=re.M)
    src = re.sub(r"^(\s*)from gesture import ", r"\1from ._research import ", src, flags=re.M)
    return src


def rewrite_research(src: str) -> str:
    src = re.sub(r"^(\s*)from gesture import ", r"\1from . import ", src, flags=re.M)
    src = re.sub(r"^(\s*)from gesture\.([A-Za-z_]\w*) import ", r"\1from .\2 import ", src, flags=re.M)
    return src


LIBRARY_PATCHES = [
    ('ROOT = KIT.parents[1] / "library"             # tools/gesture/library',
     'ROOT = KIT.parent / "library"   # app: the frozen, content-addressed library; read it through\n'
     '                                # axibridge.sources._gesture_studies.frozen_library, never directly'),
]


def freeze_code(src_root: Path, commit: str) -> dict:
    if KIT_OUT.exists():
        shutil.rmtree(KIT_OUT)
    RES_OUT.mkdir(parents=True)
    files = {}

    def put(dst: Path, text: str, rel: str):
        dst.write_text(text)
        files[str(dst.relative_to(APP))] = {"research": rel,
                                            "sha256": hashlib.sha256(dst.read_bytes()).hexdigest()}

    ges = src_root / "tools/gesture/gesture"
    for name in KIT_MODULES:
        rel = f"tools/gesture/gesture/kit/{name}.py"
        text = rewrite_kit((ges / "kit" / f"{name}.py").read_text())
        if name == "library":
            for old, new in LIBRARY_PATCHES:
                if old not in text:
                    raise SystemExit(f"library.py patch target moved: {old!r}")
                text = text.replace(old, new)
        put(KIT_OUT / f"{name}.py", header(commit, rel) + text, rel)
    put(RES_OUT / "__init__.py", header(commit, "tools/gesture/gesture/") +
        '"""app: the research modules the frozen kit imports (`tools/gesture/gesture/`)."""\n',
        "tools/gesture/gesture/__init__.py")
    for name in RESEARCH_MODULES:
        rel = f"tools/gesture/gesture/{name}.py"
        put(RES_OUT / f"{name}.py", header(commit, rel) + rewrite_research((ges / f"{name}.py").read_text()), rel)
    put(RES_OUT / "calligraphy.py", header(commit, "tools/gesture/gesture/calligraphy.py") + CALLIGRAPHY_STUB,
        "tools/gesture/gesture/calligraphy.py (stub)")

    # imports the frozen code could reach that are NOT frozen: reported, never silently present
    frozen = {*RESEARCH_MODULES, "calligraphy"}
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
        # Pillow is a declared app dependency (pyproject), so penrender's pen-lift
        # coverage mask keeps the research's PIL raster: replacing it would break parity.
    manifest = {"frozen_from": commit, "frozen": _dt.date.today().isoformat(),
                "kit_modules": list(KIT_MODULES), "research_modules": [*RESEARCH_MODULES, "calligraphy (stub)"],
                "dangling_lazy_imports": sorted(set(dangling)), "files": files}
    (KIT_OUT / "FROZEN.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def _hash_entry(folder: Path, entry: dict) -> str:
    h = hashlib.sha256()
    names = ["entry.json", *sorted(entry.get("files", {}).values())]
    for name in names:
        h.update(name.encode() + b"\0" + (folder / name).read_bytes() + b"\0")
    return h.hexdigest()[:12]


def freeze_library(src_root: Path, commit: str) -> dict:
    sys.path.insert(0, str(src_root / "tools/gesture"))
    from gesture.kit import library as L  # noqa: PLC0415 — the HEAD research library
    lib = L.Library(src_root / "tools/gesture/library")
    LIB_OUT.mkdir(parents=True, exist_ok=True)
    (LIB_OUT / "snapshots").mkdir(exist_ok=True)
    index_path = LIB_OUT / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"history": [], "withdrawn": []}
    snapshot: dict[str, dict[str, str]] = {}
    skipped, withdrawn = [], set(index.get("withdrawn", []))
    for kind in (*META_KINDS, *GENERATIVE_KINDS):
        snapshot[kind] = {}
        for eid in lib.ids(kind):
            entry = lib.entry(kind, eid)
            folder = lib.folder(kind, eid)
            if kind in GENERATIVE_KINDS:
                try:
                    lib.check(entry, "generate")          # the research policy gate, incl. corpus allow-lists
                    lib.load(kind, eid)                     # and it decodes
                except L.PolicyError as e:
                    skipped.append(f"{kind}/{eid}: {e}")
                    withdrawn.add(f"{kind}/{eid}")
                    continue
                withdrawn.discard(f"{kind}/{eid}")
            h = _hash_entry(folder, entry)
            dst = LIB_OUT / kind / eid / h
            if not dst.exists():
                dst.mkdir(parents=True)
                for name in ["entry.json", *entry.get("files", {}).values()]:
                    (dst / name).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(folder / name, dst / name)
            snapshot[kind][eid] = h
    sid = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()[:12]
    snap_path = LIB_OUT / "snapshots" / f"{sid}.json"
    if not snap_path.exists():
        snap_path.write_text(json.dumps({"id": sid, "frozen_from": commit, "frozen": _dt.date.today().isoformat(),
                                         "entries": snapshot}, indent=1, sort_keys=True) + "\n")
    if sid not in index["history"]:
        index["history"].append(sid)
    index.update({"current": sid, "frozen_from": commit, "withdrawn": sorted(withdrawn),
                  "generative_kinds": list(GENERATIVE_KINDS)})
    index_path.write_text(json.dumps(index, indent=1) + "\n")
    return {"snapshot": sid, "skipped": skipped, "counts": {k: len(v) for k, v in snapshot.items()}}


def _summary(sheet) -> dict:
    inks = []
    pts = []
    for ink in sheet.inks:
        p = np.asarray(ink.points, float)
        pts.append(p)
        inks.append([len(p), bool(ink.closed), bool(ink.filled), float(ink.pen),
                     *[float(v) for v in p[0]], *[float(v) for v in p[-1]],
                     float(p[:, 0].sum()), float(p[:, 1].sum()),
                     float((p[:, 0] ** 2).sum()), float((p[:, 1] ** 2).sum())])
    allp = np.vstack(pts) if pts else np.zeros((0, 2))
    stride = max(1, len(allp) // SAMPLE_POINTS)
    return {"inks": inks, "stride": stride, "sample": allp[::stride].tolist(), "n_points": int(len(allp))}


def parity_fixtures(src_root: Path, commit: str) -> None:
    sys.path.insert(0, str(src_root / "tools/gesture"))
    from gesture import kit  # noqa: PLC0415
    from gesture.kit import library as L  # noqa: PLC0415
    lib = L.Library(src_root / "tools/gesture/library")
    import shapely  # noqa: PLC0415
    sys.path.insert(0, str(ROOT))
    from axibridge.sources._gesture_studies import frozen_library as frozen_lib  # noqa: PLC0415
    from axibridge.sources._gesture_studies.kit import core as frozen_kit  # noqa: PLC0415
    FIXTURES.mkdir(parents=True, exist_ok=True)
    from axibridge.sources._gesture_studies.kit import sampler as frozen_sampler  # noqa: PLC0415
    from gesture.kit import sampler as research_sampler  # noqa: PLC0415
    order = json.loads((STUDIES / "index.json").read_text())["order"]
    for sid in order:
        study = json.loads((STUDIES / sid / "study.json").read_text())
        sampled = None
        if study["engine"] == "sampler":
            # the seed picks a combination from the library's pools: the research
            # sampler over the HEAD research library and the frozen sampler over
            # the frozen library must pick the very same recipe
            r = study["recipe"]
            recipe = research_sampler.sample(int(r["seed"]), library=lib, frame=tuple(r["frame"]))
            mine_r = frozen_sampler.sample(int(r["seed"]), library=frozen_lib.FrozenLibrary(),
                                           frame=tuple(r["frame"]))
            if json.dumps(recipe, sort_keys=True) != json.dumps(mine_r, sort_keys=True):
                raise SystemExit(f"{sid}: the frozen sampler does not pick the research sampler's recipe")
            sampled = recipe
        elif study["engine"] != "kit":
            continue
        else:
            recipe = study["recipe"]
        sheet = kit.run(recipe, library=lib)
        out = {"study": sid, "version": study["version"], "research_commit": commit,
               "numpy": np.__version__, "geos": shapely.geos_version_string, **_summary(sheet)}
        if sampled is not None:
            out["sampled"] = sampled
        # the frozen copy, run by THIS interpreter, must reproduce the research exactly
        mine = frozen_kit.run(recipe, library=frozen_lib.FrozenLibrary())
        if _summary(mine) != {k: out[k] for k in ("inks", "stride", "sample", "n_points")}:
            raise SystemExit(f"{sid}: the frozen kit does not reproduce the research kit")
        (FIXTURES / f"{sid}.json").write_text(json.dumps(out, separators=(",", ":")) + "\n")
        print(f"fixture {sid:<22} {len(out['inks']):5d} inks {out['n_points']:7d} points "
              f"({sheet.meta['seconds']['marks'] + sheet.meta['seconds']['inks']:.1f} s)")


def main() -> None:
    commit = git("rev-parse", "--short", "HEAD")
    with tempfile.TemporaryDirectory(prefix="gesture-freeze-") as tmp:
        src_root = Path(tmp)
        export_head(src_root)
        manifest = freeze_code(src_root, commit)
        print(f"froze {len(manifest['files'])} files from {commit}")
        for d in manifest["dangling_lazy_imports"]:
            print("  unreachable-in-app:", d)
        lib = freeze_library(src_root, commit)
        print(f"library snapshot {lib['snapshot']}: {lib['counts']}")
        for s in lib["skipped"]:
            print("  not frozen (policy):", s)
        if "--no-fixtures" not in sys.argv:
            parity_fixtures(src_root, commit)
    size = sum(p.stat().st_size for p in LIB_OUT.rglob("*") if p.is_file())
    print(f"library on disk {size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
