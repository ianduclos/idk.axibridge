"""Synthesis HTTP boundary (S4): the bench's catalogue, the writers (compose,
recompose), locks and the ripple setting's holds, validation, saved
syntheses, and Keep as a group. Previews go through the normal generator
preview endpoint with the `synthesis` source (its `preview_extra` carries the
played log the two editors overlay). None of these routes touches the
machine (MCP: no motion-shaped segment; `synthesis` tool in axibridge_mcp).

Every route takes and returns whole scores: the bench owns its history, the
server owns validation. Contract: docs/SYNTHESIS.md.
"""
from __future__ import annotations

import copy
import random
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError

from .synthesis_store import synthesis_store

router = APIRouter(prefix="/synthesis")

WRITERS = ("listen", "arch", "ccolour")
ROLES = ("speaker", "listener", "found", "made", "line", "mask", "sealed", "unseen", "cover", "container",
         "counter", "traverse", "passer", "flicker", "intruder", "echo", "calm", "nest", "bind")
FRAME = [250.0, 175.0]
SEED_MAX = 2**31 - 1


def _call(fn, *args, **kwargs):
    from .sources._synthesis import frozen_library as FL  # noqa: PLC0415
    from .sources._synthesis.kit import core  # noqa: PLC0415
    try:
        return fn(*args, **kwargs)
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'")) from exc
    except ValidationError as exc:
        raise HTTPException(400, "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                                           for e in exc.errors()[:6])) from exc
    except (ValueError, OSError, core.KitError, FL.LibraryError) as exc:
        raise HTTPException(400, str(exc)) from exc


class Lib(BaseModel):
    library: str | None = Field(default=None, pattern=r"^[0-9a-f]{12}$")
    pins: list[dict[str, Any]] = Field(default_factory=list, max_length=128)


def _lib(body: Lib):
    from .sources.synthesis import SynthesisParams  # noqa: PLC0415
    return SynthesisParams(library=body.library, pins=body.pins).frozen_library()


def _checked(score: dict, body: Lib) -> dict:
    """A score through the generator's own checks (bounds, executor, devices), normalised."""
    from .sources.synthesis import SynthesisParams  # noqa: PLC0415
    return SynthesisParams(score=score, library=body.library, pins=body.pins).score


# ---------------------------------------------------------------------------
# the catalogue
# ---------------------------------------------------------------------------

def _gallery() -> list[dict]:
    from .sources._gesture_studies import studies as ST  # noqa: PLC0415
    from .sources._synthesis.kit import _writers  # noqa: PLC0415
    docs = {w["id"]: w["doc"] for w in _writers.writer_list()}
    builtin = {s.id: s for s in ST.builtin_studies()}
    out = [{"id": f"writer:{w}", "kind": "writer", "writer": w, "label": builtin[w].label if w in builtin else w,
            "notes": docs.get(w, ""), "thumb_study": w if w in builtin else None, "family": "Score writers"}
           for w in WRITERS]
    for s in ST.builtin_studies():
        if s.engine != "kit" or s.id in WRITERS:
            continue
        out.append({"id": f"study:{s.id}", "kind": "sealed", "study": s.id, "label": s.label,
                    "notes": (s.notes or "").split("\n")[0][:200], "thumb_study": s.id,
                    "family": getattr(s, "family", None) or "Studies as one sealed layer"})
    return out


@router.get("")
def catalogue() -> dict[str, Any]:
    """Everything the bench offers: relations (phase, params with bounds), writers (params), the kit's
    voices / modulators / renderers (params), library options, devices, Flexoki inks, roles, the
    gallery's starting points, the bounds and the frozen versions."""
    def build():
        from .sources import synthesis as SY  # noqa: PLC0415
        from .sources._synthesis import devices as DV  # noqa: PLC0415
        from .sources._synthesis import engine as EN  # noqa: PLC0415
        from .sources._synthesis import frozen_library as FL  # noqa: PLC0415
        from .sources._synthesis.kit import _relations, _writers, core  # noqa: PLC0415
        tech = core.describe()
        return {"relations": _relations.relation_list(), "writers": _writers.writer_list(),
                "techniques": {k: tech.get(k, []) for k in ("voice", "modulator", "renderer")},
                "library": {k: FL.options(k) for k in ("hand", "tempo", "dance_trail")},
                "devices": DV.catalogue(), "inks": EN.flexoki(), "roles": list(ROLES),
                "gallery": _gallery(), "saved": [_saved_out(x) for x in synthesis_store.list()["items"]],
                "limits": {"layers": SY.MAX_LAYERS, "relations": SY.MAX_RELATIONS, "points": SY.MAX_POINTS,
                           "bytes": SY.MAX_BYTES, "frame": SY.MAX_FRAME, "seed": SEED_MAX},
                "snapshot": FL.current_snapshot(), "frozen_from": SY.frozen_from(),
                "default_frame": FRAME}
    return _call(build)


# ---------------------------------------------------------------------------
# writers
# ---------------------------------------------------------------------------

class Start(Lib):
    gallery: str = Field(pattern=r"^(writer|study|saved):[A-Za-z0-9_-]{1,80}$")
    seed: int | None = Field(default=None, ge=0, le=SEED_MAX)
    params: dict[str, Any] = Field(default_factory=dict, max_length=32)


def _sealed_score(study_id: str, seed: int | None) -> dict:
    from .sources._gesture_studies import studies as ST  # noqa: PLC0415
    s = ST.builtin(study_id)
    if s.engine != "kit":
        raise ValueError(f"{study_id} is not a kit study; it cannot be a sealed layer")
    r = copy.deepcopy(s.recipe)
    W, H = (float(v) for v in r.get("frame") or FRAME)
    composer = {k: v for k, v in r.items() if k not in ("frame", "seed")}
    sd = int(r.get("seed", 0)) if seed is None else int(seed)
    return {"version": 2, "frame": [W, H], "seed": sd, "margin": 0.0, "label": s.label,
            "layers": [{"id": "S", "role": "sealed", "pen": "black", "label": s.label, "seed": sd,
                        "composer": composer}],
            "relations": [], "decisions": {"bench": {"from": f"study:{study_id}"}}}


@router.post("/start")
def start(body: Start) -> dict[str, Any]:
    """A gallery card → a score: a writer composes (at `seed`, random when absent), a study opens as one
    sealed layer at its own seed (or `seed`), a saved synthesis opens as saved."""
    def go():
        from .sources._synthesis import engine as EN  # noqa: PLC0415
        kind, key = body.gallery.split(":", 1)
        seed = body.seed if body.seed is not None else random.randint(1, 99_999)
        if kind == "writer":
            if key not in WRITERS:
                raise KeyError(f"no writer {key}")
            score = EN.compose(key, lib=_lib(body), frame=FRAME, seed=seed, params=body.params)
            score.setdefault("label", key)
        elif kind == "study":
            score = _sealed_score(key, body.seed)
        else:
            score = synthesis_store.get(key)["score"]
        return {"score": _checked(score, body)}
    return _call(go)


class Compose(Lib):
    writer: Literal["listen", "arch", "ccolour"]
    seed: int = Field(ge=0, le=SEED_MAX)
    params: dict[str, Any] = Field(default_factory=dict, max_length=32)
    frame: list[float] | None = Field(default=None, min_length=2, max_length=2)
    region: list[float] | None = Field(default=None, min_length=4, max_length=4)
    ground: dict[str, Any] | None = None


@router.post("/compose")
def compose(body: Compose) -> dict[str, Any]:
    """Ask a writer for a score (on an optional ground: another writer's, or Ian's, layers)."""
    def go():
        from .sources._synthesis import engine as EN  # noqa: PLC0415
        lib = _lib(body)
        ground = _checked(body.ground, body) if body.ground else None
        score = EN.compose(body.writer, lib=lib, frame=body.frame or FRAME, seed=body.seed, params=body.params,
                           region=body.region, ground=ground)
        return {"score": _checked(score, body)}
    return _call(go)


class Recompose(Lib):
    score: dict[str, Any]
    seed: int = Field(ge=0, le=SEED_MAX)
    locked: list[str] = Field(default_factory=list, max_length=24)
    locked_relations: list[str] = Field(default_factory=list, max_length=64)
    writer_index: int = Field(default=-1, ge=-8, le=8)
    params: dict[str, Any] | None = None


@router.post("/recompose")
def recompose(body: Recompose) -> dict[str, Any]:
    """Ask the writer again with a new seed, around the locked layers (pinned first, if they aren't) and
    the locked relations (kept when both their ends survive; else listed in `dropped`)."""
    def go():
        from .sources._synthesis import engine as EN  # noqa: PLC0415
        lib = _lib(body)
        score = _checked(body.score, body)
        need = [i for i in body.locked if not next((L for L in score["layers"] if L["id"] == i), {}).get("lock")]
        if need:
            score = EN.pin(score, need, lib=lib)
        writers = score["decisions"].get("writers") or []
        if not writers:
            raise ValueError("this score has no writer to ask: recompose works on a written score")
        mine = set(writers[body.writer_index]["layers"])
        locked = [i for i in body.locked if i in mine]
        out = EN.recompose(score, lib=lib, locked=locked, seed=body.seed, writer_index=body.writer_index,
                           params=body.params)
        for k in ("label", "notes"):             # the writer names a fresh score; a recomposed one keeps its name
            if score.get(k) and not out.get(k):
                out[k] = score[k]
        if (score["decisions"].get("bench") or {}) and not out["decisions"].get("bench"):
            out["decisions"]["bench"] = copy.deepcopy(score["decisions"]["bench"])
        keep = {R["id"]: R for R in score["relations"] if R["id"] in set(body.locked_relations)}
        dropped = []
        if keep:
            have = {L["id"] for L in out["layers"]}
            rels = [R for R in out["relations"] if R["id"] not in keep]
            for rid, R in keep.items():
                ends = (R["src"] if isinstance(R["src"], list) else [R["src"]]) + [R["dst"]]
                if all(v == "*" or v in have for v in ends):
                    rels.append(R)
                else:
                    dropped.append(rid)
            cand = {**out, "relations": rels}
            try:
                out = _checked(cand, body)
            except ValueError:
                dropped = sorted(keep)
        return {"score": _checked(out, body), "dropped": dropped}
    return _call(go)


# ---------------------------------------------------------------------------
# locks and the ripple setting
# ---------------------------------------------------------------------------

class Ids(Lib):
    score: dict[str, Any]
    ids: list[str] = Field(default_factory=list, max_length=24)


@router.post("/lock")
def lock(body: Ids) -> dict[str, Any]:
    """Lock layers: each keeps its played lines (a pin) and its seed, so edits upstream don't move it."""
    def go():
        from .sources._synthesis import engine as EN  # noqa: PLC0415
        return {"score": _checked(EN.pin(_checked(body.score, body), body.ids, lib=_lib(body)), body)}
    return _call(go)


def _unlocked(score: dict, ids) -> dict:
    out = copy.deepcopy(score)
    want = set(ids)
    for L in out["layers"]:
        if L["id"] in want:
            L.pop("pin", None)
            L.pop("lock", None)
    bench = out.setdefault("decisions", {}).setdefault("bench", {})
    if bench.get("held"):
        bench["held"] = [i for i in bench["held"] if i not in want]
    return out


@router.post("/unlock")
def unlock(body: Ids) -> dict[str, Any]:
    """Unlock layers: their pins go (they follow again); they keep their own seed. Layers the ripple
    setting held are released the same way."""
    return _call(lambda: {"score": _checked(_unlocked(_checked(body.score, body), body.ids), body)})


class Hold(Lib):
    score: dict[str, Any]
    edited: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    ripple: Literal["all", "direct", "none"] = "all"


def direct_listeners(score: dict, played: dict, edited: str) -> set[str]:
    """Layers that hear `edited` directly: the dst of a grow relation naming it in its src, and every
    layer a played event paired with it (either side)."""
    out: set[str] = set()
    for R in score["relations"]:
        srcs = R["src"] if isinstance(R["src"], list) else [R["src"]]
        if edited in srcs and R["dst"] != "*":
            out.add(R["dst"])
    for ev in played.get("log", []):
        if ev.get("outcome") in ("silent", "spent"):
            continue
        srcs = ev.get("srcs") or [ev.get("src")]
        if edited in srcs:
            out.add(ev.get("dst"))
        if ev.get("dst") == edited:
            out.update(srcs)
    out.discard(edited)
    out.discard(None)
    return out


@router.post("/hold")
def hold(body: Hold) -> dict[str, Any]:
    """Before an edit of layer `edited`: the ripple setting's holds. `all` holds nothing (Follow);
    `direct` locks every layer except the edited one and its direct listeners; `none` locks every other
    layer. Held layers are listed in `decisions.bench.held` (the bench shows them and releases them)."""
    def go():
        from .sources._synthesis import engine as EN  # noqa: PLC0415
        from .sources._synthesis.kit import _synth  # noqa: PLC0415
        lib = _lib(body)
        score = _checked(body.score, body)
        ids = {L["id"] for L in score["layers"]}
        if body.edited not in ids:
            raise KeyError(f"no layer {body.edited}")
        if body.ripple == "all":
            return {"score": score, "held": []}
        free = {body.edited}
        if body.ripple == "direct":
            sheet, _ = EN.play({**score, "devices": []}, lib)
            free |= direct_listeners(score, _synth.played(sheet) or {}, body.edited)
        want = [L["id"] for L in score["layers"]
                if L["id"] not in free and not L.get("lock") and L["role"] != _synth.UNSEEN]
        if not want:
            return {"score": score, "held": []}
        out = EN.pin(score, want, lib=lib)
        bench = out.setdefault("decisions", {}).setdefault("bench", {})
        bench["held"] = sorted(set(bench.get("held") or []) | set(want))
        return {"score": _checked(out, body), "held": want}
    return _call(go)


@router.post("/validate")
def validate(body: Ids) -> dict[str, Any]:
    """A score through every check the generator makes, normalised; 400 with the reason otherwise."""
    return _call(lambda: {"score": _checked(body.score, body)})


# ---------------------------------------------------------------------------
# saved syntheses + keep
# ---------------------------------------------------------------------------

def _saved_out(item: dict) -> dict:
    return {"id": item["id"], "kind": "saved", "label": item["label"], "notes": item.get("notes", ""),
            "created": item.get("created"), "thumb": item.get("thumb", ""), "gallery": f"saved:{item['id']}",
            "family": "Saved syntheses"}


class Save(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    score: dict[str, Any]
    thumb: str = Field(default="", max_length=120_000)
    notes: str = Field(default="", max_length=2000)


@router.get("/saved")
def list_saved() -> dict[str, Any]:
    def go():
        saved = synthesis_store.list()
        return {"items": [_saved_out(x) for x in saved["items"]], "warnings": saved["warnings"]}
    return _call(go)


@router.post("/saved")
def save(body: Save) -> dict[str, Any]:
    return _call(lambda: _saved_out(synthesis_store.save(label=body.label, score=body.score, thumb=body.thumb,
                                                         notes=body.notes)))


@router.delete("/saved/{sid}")
def delete_saved(sid: str) -> dict[str, Any]:
    _call(synthesis_store.delete, sid)
    return {"ok": True}


class Keep(BaseModel):
    params: dict[str, Any]
    replace: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")


@router.post("/keep")
def keep(body: Keep) -> dict[str, Any]:
    """Keep the score as ONE undo step: a group named after it, one `synthesis` layer per score layer
    that drew (each on its pen, `show: layer`), plus a Measure layer when devices drew. `replace`: a
    kept synthesis group to swap in place (reopened in the bench)."""
    from .session import session  # noqa: PLC0415

    def go():
        group, layers = session.keep_synthesis(body.params, replace=body.replace)
        return {"group": group.model_dump(), "layers": [layer.model_dump() for layer in layers]}
    return _call(go)
