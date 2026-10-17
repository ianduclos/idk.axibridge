# FROZEN from research commit 31f7575: tools/gesture/gesture/kit/library.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""The gesture library: everything learned, saved with provenance — and the
single POLICY GATE.

Layout (committed, `tools/gesture/library/`): one folder per entry, so
parallel work adds entries without touching a shared index.

    library/<kind>/<id>/entry.json   id, kind, label, version, created,
                                     provenance, policy, notes, files
                                     {name: relative path}, size_bytes
    library/<kind>/<id>/<data>       npz / json.gz (compact, lossless)

Kinds seeded: `hand` (a learned line grammar — loads as a research
`grammar.Grammar`), `tempo` (a dance timing profile — loads as a research
`gesture_timing.Timing`), `corpus` (an INDEX of a local extraction under
`.local/gesture/corpus/`: counts, manifests, policy; the scans never enter the
library). New kinds: add folders, and register a loader with `@loader(kind)`
in your technique file if the data needs decoding (otherwise `load` returns
{"entry", "folder", "files"}).

Policy: `policy` is "generative" or "measure-only". `load(..., purpose=
"generate")` (the default, and what `ctx.use` asks) raises PolicyError for a
measure-only entry — Qur'anic and devotional calligraphy is measure-only,
and outputs never show legible Arabic. A measure-only corpus may carry
`generative_items` (an allow-list); asking with `items=` inside it passes.
Hands learned from a corpus (`provenance.corpus`) are re-checked against
that corpus entry's allow-list every time they are loaded for generation.
"""
from __future__ import annotations

import copy
import datetime as _dt
import gzip
import io
import json
import math
import os
import threading
from pathlib import Path
from typing import Callable

import numpy as np

from ._research.calligraphy import PolicyError as _CalligraphyPolicyError

KIT = Path(__file__).resolve().parent
ROOT = KIT.parent / "library"   # app: the frozen, content-addressed library; read it through
                                # axibridge.sources._gesture_studies.frozen_library, never directly
REPO = KIT.parents[3]
POLICIES = ("generative", "measure-only")
PURPOSES = ("generate", "measure")
REQUIRED = ("id", "kind", "label", "version", "created", "provenance", "policy", "notes", "files", "size_bytes")
NX = ("line", "arc", "clothoid", "corner")
P7 = 10_000_000          # research rounding round(v, 7)
P5 = 100_000             # u: round(v, 5)


class PolicyError(_CalligraphyPolicyError):
    """Measure-only material asked for generation (subclass of the research
    `calligraphy.PolicyError`, so either catch works)."""


class LibraryError(KeyError):
    """No such entry / malformed entry."""

    def __str__(self):
        return str(self.args[0]) if self.args else ""


# ---------------------------------------------------------------------------
# loaders per kind
# ---------------------------------------------------------------------------

_LOADERS: dict[str, Callable] = {}


def loader(kind: str):
    """Register `fn(entry: dict, folder: Path) -> object` as the decoder of
    `kind` (one per kind; put it in your technique file for a new kind)."""
    def deco(fn):
        old = _LOADERS.get(kind)
        if old is not None and f"{old.__module__}.{old.__qualname__}" != f"{fn.__module__}.{fn.__qualname__}":
            raise ValueError(f"a loader for kind {kind!r} already exists ({old.__module__})")
        _LOADERS[kind] = fn
        return fn
    return deco


# ---------------------------------------------------------------------------
# small io helpers (deterministic bytes: gzip mtime 0, sorted keys)
# ---------------------------------------------------------------------------

def json_gz_bytes(obj) -> bytes:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as f:
        f.write(raw)
    return buf.getvalue()


def read_json_gz(path) -> object:
    with gzip.open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def npz_bytes(arrays: dict) -> bytes:
    buf = io.BytesIO()
    np.savez_compressed(buf, **{k: arrays[k] for k in sorted(arrays)})
    return buf.getvalue()


def read_npz(path) -> dict:
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def deep_equal(a, b) -> bool:
    """Structural equality where numbers compare by value (0 == 0.0, the way
    JSON round trips them) and lists/tuples are interchangeable."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(deep_equal(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(deep_equal(x, y) for x, y in zip(a, b))
    num = (int, float, np.integer, np.floating)
    if isinstance(a, num) and isinstance(b, num) and not isinstance(a, bool) and not isinstance(b, bool):
        fa, fb = float(a), float(b)
        return fa == fb or (math.isnan(fa) and math.isnan(fb))
    return type(a) is type(b) and a == b


def _pack(values, scale: int) -> tuple[np.ndarray, int | None]:
    """Integers on the research rounding grid if every value sits on it
    (bit-exact round trip), else float64 (scale None)."""
    a = np.asarray(values, dtype=np.float64)
    if a.size and np.all(np.isfinite(a)) and np.max(np.abs(a)) < 9e11:
        q = np.round(a * scale).astype(np.int64)
        if np.array_equal(q / scale, a):
            return q, scale
    return a, None


def _unpack(a: np.ndarray, scale: int | None) -> np.ndarray:
    return np.asarray(a) / scale if scale else np.asarray(a, dtype=np.float64)


# ---------------------------------------------------------------------------
# hand codec (tools/hand_drift/freeze.py's compact format, made general)
# ---------------------------------------------------------------------------

def _derive_trans(nx: list, par: list, sid: list) -> dict:
    """The previous-token columns: a record's previous token is the record
    before it in the same source stroke (sid)."""
    p1, p2, f1, f2 = [], [], [], []
    for i in range(len(nx)):
        if i >= 1 and sid[i - 1] == sid[i]:
            p1.append(nx[i - 1])
            f1.append(list(par[i - 1]))
            if i >= 2 and sid[i - 2] == sid[i]:
                p2.append(nx[i - 2])
                f2.append(list(par[i - 2]))
            else:
                p2.append("START")
                f2.append([])
        else:
            p1.append("START")
            f1.append([])
            p2.append("START")
            f2.append([])
    return {"p1": p1, "p2": p2, "f1": f1, "f2": f2}


def _derive_strokes(nx: list, par: list, sid: list, n_strokes: int) -> list:
    """Training strokes = the even-sid records in order (odd sids are the
    reversal augmentation)."""
    rec: dict[int, list] = {}
    for k, row, s in zip(nx, par, sid):
        if s % 2 == 0:
            rec.setdefault(s // 2, []).append([k] + list(row))
    return [rec.get(i, []) for i in range(n_strokes)]


def encode_hand(g: dict) -> tuple[dict, dict]:
    """A research grammar's JSON (Grammar.to_json()) → (arrays for
    tables.npz, sheet dict for sheet.json.gz). Lossless: `decode_hand`
    reproduces `g` exactly (checked here; raises AssertionError if not)."""
    T = g["trans"]
    n = len(T["nx"])
    if any(k not in NX for k in T["nx"]):
        raise AssertionError("unknown token kind in trans.nx")
    par = np.zeros((n, 3), np.float64)
    for i, (k, row) in enumerate(zip(T["nx"], T["par"])):
        if len(row) != (1 if k == "corner" else 3):
            raise AssertionError(f"record {i}: param count")
        par[i, :len(row)] = row
    arrays, enc = {"nx": np.array([NX.index(k) for k in T["nx"]], np.int8),
                   "sid": np.asarray(T["sid"], np.int32)}, {}
    for name, vals, sc in (("par", par, P7), ("rem", T["rem"], P7), ("u", T["u"], P5),
                           ("stroke_lengths", g["stroke_lengths"], P7)):
        arrays[name], enc[name] = _pack(vals, sc)
    if enc["u"] and np.abs(arrays["u"]).max() < 2**31:
        arrays["u"] = arrays["u"].astype(np.int32)
    sheet = {k: g[k] for k in ("name", "version", "counts", "drawings", "relations", "start_pos", "scale",
                               "spread", "meta") if k in g}
    sheet["_enc"] = enc
    # derivations are verified; whatever does not derive is stored verbatim
    nxl = list(T["nx"])
    parl = [list(r) for r in T["par"]]
    sid = list(T["sid"])
    d = _derive_trans(nxl, parl, sid)
    if not all(deep_equal(d[c], T[c]) for c in ("p1", "p2", "f1", "f2")):
        sheet["_trans_ctx"] = {c: T[c] for c in ("p1", "p2", "f1", "f2")}
    if not deep_equal(_derive_strokes(nxl, parl, sid, len(g["strokes"])), g["strokes"]):
        sheet["_strokes"] = g["strokes"]
    else:
        sheet["_n_strokes"] = len(g["strokes"])
    extra = sorted(k for k in T if k not in ("p1", "p2", "f1", "f2", "nx", "rem", "u", "par", "sid"))
    if extra:
        sheet["_trans_extra"] = {k: T[k] for k in extra}
    back = decode_hand_json(arrays, sheet)
    if not deep_equal(back, g):
        bad = [k for k in g if not deep_equal(back.get(k), g[k])]
        raise AssertionError(f"hand codec round trip differs in {bad}")
    return arrays, sheet


def decode_hand_json(arrays: dict, sheet: dict) -> dict:
    """(tables.npz arrays, sheet.json.gz) → the research grammar JSON."""
    enc = sheet.get("_enc", {})
    nx = [NX[int(c)] for c in np.asarray(arrays["nx"]).tolist()]
    par_all = _unpack(arrays["par"], enc.get("par")).tolist()
    par = [row[:1] if k == "corner" else row for k, row in zip(nx, par_all)]
    sid = [int(s) for s in np.asarray(arrays["sid"]).tolist()]
    ctx = sheet.get("_trans_ctx") or _derive_trans(nx, par, sid)
    trans = {"p2": ctx["p2"], "p1": ctx["p1"], "nx": nx, "f2": ctx["f2"], "f1": ctx["f1"],
             "rem": _unpack(arrays["rem"], enc.get("rem")).tolist(),
             "u": _unpack(arrays["u"], enc.get("u")).tolist(), "par": par, "sid": sid}
    trans.update(sheet.get("_trans_extra", {}))
    strokes = sheet.get("_strokes")
    if strokes is None:
        strokes = _derive_strokes(nx, par, sid, int(sheet.get("_n_strokes", 0)))
    g = {k: copy.deepcopy(v) for k, v in sheet.items() if not k.startswith("_")}
    g["trans"] = trans
    g["strokes"] = strokes
    g["stroke_lengths"] = _unpack(arrays["stroke_lengths"], enc.get("stroke_lengths")).tolist()
    return g


@loader("hand")
def _load_hand(entry: dict, folder: Path):
    from ._research import grammar as gm  # noqa: PLC0415
    arrays = read_npz(folder / entry["files"]["tables"])
    sheet = read_json_gz(folder / entry["files"]["sheet"])
    return gm.Grammar.from_json(decode_hand_json(arrays, sheet))


# ---------------------------------------------------------------------------
# tempo codec (a research gesture_timing.Timing, float64 — lossless)
# ---------------------------------------------------------------------------

TEMPO_ARRAYS = ("t", "speed", "phi", "jitter", "jerk", "pause")


def encode_tempo(tm) -> tuple[dict, dict]:
    arrays = {k: np.asarray(getattr(tm, k), dtype=bool if k == "pause" else np.float64) for k in TEMPO_ARRAYS}
    sheet = {"label": tm.label, "meta": _jsonable(tm.meta)}
    back = decode_tempo(arrays, sheet)
    for k in TEMPO_ARRAYS:
        if not np.array_equal(getattr(back, k), getattr(tm, k)):
            raise AssertionError(f"tempo codec round trip differs in {k}")
    return arrays, sheet


def decode_tempo(arrays: dict, sheet: dict):
    from ._research.gesture_timing import Timing  # noqa: PLC0415
    a = {k: np.array(arrays[k], dtype=bool if k == "pause" else np.float64) for k in TEMPO_ARRAYS}
    for v in a.values():
        v.setflags(write=False)
    return Timing(a["t"], a["speed"], a["phi"], a["jitter"], a["jerk"], a["pause"], label=sheet.get("label", ""),
                  meta=dict(sheet.get("meta", {})))


@loader("tempo")
def _load_tempo(entry: dict, folder: Path):
    return decode_tempo(read_npz(folder / entry["files"]["profile"]), read_json_gz(folder / entry["files"]["sheet"]))


@loader("corpus")
def _load_corpus(entry: dict, folder: Path):
    """A corpus entry is an index: its data IS the entry (counts, manifests,
    local path). Use `local_path(entry)` to reach the extraction."""
    return copy.deepcopy(entry)


def local_path(entry: dict) -> Path:
    """Absolute path of a corpus entry's local extraction (may not exist on
    this machine — scans never leave `.local/`)."""
    return REPO / entry["provenance"]["local_path"]


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.generic):
        return o.item()
    return o


# ---------------------------------------------------------------------------
# the library
# ---------------------------------------------------------------------------

class Library:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root is not None else ROOT
        self._cache: dict = {}
        self._lock = threading.Lock()

    # -- reading --
    def kinds(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.name for p in self.root.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))

    def ids(self, kind: str) -> list[str]:
        d = self.root / kind
        if not d.exists():
            return []
        return sorted(p.name for p in d.iterdir() if (p / "entry.json").exists())

    def folder(self, kind: str, id: str) -> Path:
        return self.root / kind / id

    def has(self, kind: str, id: str) -> bool:
        return (self.folder(kind, id) / "entry.json").exists()

    def entry(self, kind: str, id: str) -> dict:
        p = self.folder(kind, id) / "entry.json"
        if not p.exists():
            raise LibraryError(f"no library entry {kind}/{id}; {kind} entries: {self.ids(kind)}")
        e = json.loads(p.read_text())
        missing = [k for k in REQUIRED if k not in e]
        if missing:
            raise LibraryError(f"library entry {kind}/{id} lacks {missing}")
        return e

    def entries(self, kind: str | None = None) -> list[dict]:
        kinds = [kind] if kind else self.kinds()
        return [self.entry(k, i) for k in kinds for i in self.ids(k)]

    # -- policy --
    def check(self, entry: dict, purpose: str = "generate", items=None) -> None:
        """Raise PolicyError if `entry` may not be used for `purpose`."""
        if purpose not in PURPOSES:
            raise ValueError(f"purpose must be one of {PURPOSES}")
        if purpose == "measure":
            return
        tag = f"{entry['kind']}/{entry['id']}"
        if entry["policy"] not in POLICIES:
            raise PolicyError(f"{tag}: unknown policy {entry['policy']!r} (treated as restricted)")
        if entry["policy"] == "measure-only":
            allow = set(entry.get("generative_items") or [])
            if items is not None and allow and set(items) <= allow:
                return
            hint = f" (generative_items allow-list: {sorted(allow)})" if allow else ""
            raise PolicyError(f"{tag} is measure-only: statistics yes, generation never{hint}")
        corpus = (entry.get("provenance") or {}).get("corpus")
        if corpus and self.has("corpus", corpus):
            ce = self.entry("corpus", corpus)
            if ce["policy"] == "measure-only":
                sheets = [s.split("#")[0] for s in entry["provenance"].get("training_sheets", [])]
                allow = set(ce.get("generative_items") or [])
                bad = sorted(s for s in sheets if s not in allow)
                if bad or not sheets:
                    raise PolicyError(f"{tag} was learned from measure-only sheets {bad or '(unrecorded)'} "
                                      f"of corpus {corpus}")

    def load(self, kind: str, id: str, purpose: str = "generate", items=None):
        """The entry's data through the policy gate (decoded by the kind's
        loader; cached per process — treat the result as read-only)."""
        e = self.entry(kind, id)
        self.check(e, purpose, items)
        folder = self.folder(kind, id)
        key = (kind, id, (folder / "entry.json").stat().st_mtime_ns)
        with self._lock:
            if key not in self._cache:
                fn = _LOADERS.get(kind)
                if fn is None:
                    self._cache[key] = {"entry": e, "folder": folder,
                                        "files": {k: folder / v for k, v in e["files"].items()}}
                else:
                    self._cache[key] = fn(e, folder)
            return self._cache[key]

    # -- writing --
    def save(self, entry: dict, files: dict | None = None, *, overwrite: bool = False) -> dict:
        """Write `library/<kind>/<id>/`: data `files` {relative path: bytes |
        existing Path} and entry.json (files + size_bytes filled in).
        Refuses to replace an existing entry unless overwrite=True."""
        e = copy.deepcopy(entry)
        for k in ("id", "kind", "label", "policy"):
            if not e.get(k):
                raise LibraryError(f"entry needs {k!r}")
        if e["policy"] not in POLICIES:
            raise LibraryError(f"policy must be one of {POLICIES}")
        if not str(e["id"]).replace("_", "").replace("-", "").replace(".", "").isalnum():
            raise LibraryError(f"entry id {e['id']!r}: use [a-z0-9_.-]")
        folder = self.folder(e["kind"], e["id"])
        if (folder / "entry.json").exists() and not overwrite:
            raise LibraryError(f"{e['kind']}/{e['id']} exists (overwrite=True to replace)")
        folder.mkdir(parents=True, exist_ok=True)
        names = {}
        size = 0
        for rel, data in sorted((files or {}).items()):
            dst = folder / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            b = Path(data).read_bytes() if isinstance(data, (str, Path)) else bytes(data)
            dst.write_bytes(b)
            names[Path(rel).name.split(".")[0]] = rel
            size += len(b)
        if files is not None:
            e["files"] = names
        e.setdefault("files", {})
        e["size_bytes"] = size if files is not None else e.get("size_bytes", 0)
        e.setdefault("version", 1)
        e.setdefault("created", _dt.date.today().isoformat())
        e.setdefault("provenance", {})
        e.setdefault("notes", "")
        ordered = {k: e[k] for k in REQUIRED}
        ordered.update({k: v for k, v in e.items() if k not in ordered})
        (folder / "entry.json").write_text(json.dumps(_jsonable(ordered), indent=1, ensure_ascii=False) + "\n")
        self._cache = {k: v for k, v in self._cache.items() if k[:2] != (e["kind"], e["id"])}
        return ordered

    # -- reporting --
    def size(self, kind: str | None = None) -> int:
        base = self.root / kind if kind else self.root
        if not base.exists():
            return 0
        return sum(p.stat().st_size for p in base.rglob("*") if p.is_file())

    def table(self) -> str:
        rows = []
        for k in self.kinds():
            rows.append(f"== {k} ({self.size(k) / 1024:.1f} KB)")
            for e in self.entries(k):
                rows.append(f"  {e['id']:<14} {e['policy']:<13} {e['size_bytes'] / 1024:8.1f} KB  {e['label']}")
        rows.append(f"total {self.size() / 1024:.1f} KB")
        return "\n".join(rows)


_DEFAULT: Library | None = None


def default() -> Library:
    """The committed library (or $GESTURE_KIT_LIBRARY if set)."""
    global _DEFAULT
    root = os.environ.get("GESTURE_KIT_LIBRARY")
    want = Path(root) if root else ROOT
    if _DEFAULT is None or _DEFAULT.root != want:
        _DEFAULT = Library(want)
    return _DEFAULT


def entries(kind: str | None = None) -> list[dict]:
    return default().entries(kind)


def entry(kind: str, id: str) -> dict:
    return default().entry(kind, id)


def ids(kind: str) -> list[str]:
    return default().ids(kind)


def load(kind: str, id: str, purpose: str = "generate", items=None):
    return default().load(kind, id, purpose, items)


def save(entry: dict, files: dict | None = None, *, overwrite: bool = False) -> dict:
    return default().save(entry, files, overwrite=overwrite)


def size(kind: str | None = None) -> int:
    return default().size(kind)
