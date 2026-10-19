# FROZEN from research commit c712045: tools/gesture/gesture/kit/devices_mdoc_provenance.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Device `mdoc_provenance` (round 16, thread D `mdoc`): which hand, corpus
and source every line descends from.

A tree read right to left: the sheet; its layers in drawing order (each in
its own ink); the hands that drew each layer, with the ink each laid; the
source each hand was measured from (the dataset its library entry names,
and how many sheets or takes trained it), grouped under its corpus family.
A layer with no hand of its own — an echo, a calm, a nest, a bind, the void
— descends from the layer it heard, drawn as a hook between the two layers
with the relation's name: that is a line's descent too.

It reads, in order: the `voice` channel and `voices` in mark meta (kit
voices); a sealed composer's inner score (its layers' `hand` params, and
its relations for the hand-less layers); a v1 composer's recorded score;
ccolour / arch plans (object → hand); the recipe part's voice. Library ids
come from `sheet.meta["library"]` and the library entries' provenance.
"""
from __future__ import annotations

from collections import Counter, OrderedDict

import numpy as np

from . import devices_mdoc_read as D
from . import devices_meas_read as R
from ._devices import device
from .core import P

DERIVED = ("echo", "calm", "nest", "bind", "imitate", "exaggerate", "translate", "refuse", "mask", "answer",
           "ride", "carry", "catch")


# ---------------------------------------------------------------------------
# reading descent
# ---------------------------------------------------------------------------

def _plan_hands(meta, logs: dict) -> list[str]:
    """ccolour / arch: the object's hands from the arranger's plan (the log
    rides on one mark of the sheet; `logs` holds it by arranger)."""
    for key in ("ccolour", "arch"):
        log = logs.get(key)
        if not isinstance(log, dict) or "obj" not in meta:
            continue
        plan = log.get("plan") or {}
        obj = meta["obj"] if isinstance(meta["obj"], (list, tuple)) else [meta["obj"]]
        kind = str(obj[0])
        if kind == "made" and len(obj) > 1 and isinstance(obj[1], int) and obj[1] < len(plan.get("made", [])):
            return [plan["made"][obj[1]]["hand"]]
        v = plan.get(kind)
        if kind == "found":
            out = []
            for f in plan.get("found", []):
                if len(obj) < 2 or f.get("kind") == obj[1]:
                    vv = f.get("voice", {})
                    out += list(vv.get("hands") or ([vv["hand"]] if vv.get("hand") else [])) + \
                        ([vv["stems"]] if vv.get("stems") else [])
            return out
        if isinstance(v, dict):
            return list(v.get("hands") or ([v["hand"]] if v.get("hand") else []))
    return []


def _score_layer_hand(lay: dict) -> list[str]:
    p = lay.get("params") or {}
    for k in ("hand", "trail", "stems"):
        if p.get(k):
            return [str(p[k])]
    v = p.get("voice") or {}
    if isinstance(v, dict):
        if v.get("hand"):
            return [str(v["hand"])]
        if v.get("hands"):
            return [str(x) for x in v["hands"]]
    return []


def _derived_from(sc: dict, lid: str) -> tuple[str, str] | None:
    """(src layer, kind) of the relation a hand-less layer was made by."""
    for r in sc.get("relations", []):
        if r.get("dst") == lid and r.get("kind") in DERIVED and r.get("src") != lid:
            return str(r["src"]), str(r["kind"])
    return None


def descent(sheet) -> dict:
    """{layers: OrderedDict id → {hands: {hand: mm}, colour, tag, from: (src, kind) | None},
    hands: OrderedDict hand → {mm, family, source, sheets}}"""
    L = D.layers(sheet)
    sc = D.any_score(sheet) or {}
    lib = {str(e.get("id")): str(e.get("kind")) for e in sheet.meta.get("library", [])}
    river = [i for i, k in lib.items() if k == "river_stems"]
    inner = {lay["id"]: lay.get("inner") for lay in sc.get("layers", []) if lay.get("inner")}
    logs = {k: R._arranger_log(sheet, k) for k in ("ccolour", "arch")}
    out_layers: "OrderedDict[str, dict]" = OrderedDict()
    for lid, info in L.items():
        if not info["visible"]:
            continue
        hands: Counter = Counter()
        frm = None
        for m in info["marks"]:
            Lm = m.length()
            w = R._voice_weights(m)
            if not w and m.meta.get("voices"):
                vs = [str(v) for v in m.meta["voices"]]
                w = {v: Lm / len(vs) for v in vs}
            if not w and m.meta.get("inner_layer") and lid in inner:
                il = next((x for x in inner[lid].get("layers", []) if x["id"] == m.meta["inner_layer"]), None)
                hs = _score_layer_hand(il) if il else []
                if not hs and il:
                    if il.get("technique") == "river_zoom" and river:
                        hs = river[:1]
                    else:
                        d = _derived_from(inner[lid], il["id"])
                        while d and not hs:
                            src = next((x for x in inner[lid]["layers"] if x["id"] == d[0]), None)
                            hs = _score_layer_hand(src) if src else []
                            d = _derived_from(inner[lid], d[0]) if not hs else d
                w = {h: Lm / len(hs) for h in hs}
            if not w:
                hs = _plan_hands(m.meta, logs)
                w = {h: Lm / len(hs) for h in hs} if hs else {}
            if not w and info["score"]:
                hs = _score_layer_hand(info["score"])
                if not hs and info["score"].get("technique") == "river_zoom" and river:
                    hs = river[:1]
                w = {h: Lm / len(hs) for h in hs} if hs else {}
            if not w and not info["score"] and not any(logs.values()) and m.meta.get("of_role") != "sealed":
                hs = R._recipe_hands(sheet, int(m.meta.get("part", 0) or 0)) if not D.played(sheet) else []
                w = {h: Lm / len(hs) for h in hs} if hs else {}
            for h, x in w.items():
                hands[h] += x
        if not hands and sc:
            frm = _derived_from(sc, lid)
        out_layers[lid] = {"hands": dict(hands), "colour": info["colour"], "tag": D.layer_tag(L, lid), "from": frm,
                           "mm": float(sum(m.length() for m in info["marks"]))}
    all_hands: "OrderedDict[str, dict]" = OrderedDict()
    for lid, v in out_layers.items():
        for h, mm in sorted(v["hands"].items(), key=lambda t: -t[1]):
            e = all_hands.setdefault(h, {"mm": 0.0, **source_of(h)})
            e["mm"] += mm
    return {"layers": out_layers, "hands": all_hands}


def source_of(hid: str) -> dict:
    """{family, source, sheets}: the corpus family and the dataset the
    library entry names (its `rights` head), and how many sheets trained it."""
    from . import library  # noqa: PLC0415
    fam = R.family(hid)
    for kind in ("hand", "river_stems", "dance_trail", "tempo"):
        try:
            e = library.entry(kind, hid)
        except Exception:  # noqa: BLE001
            continue
        p = e.get("provenance") or {}
        rights = str(p.get("rights") or p.get("description") or "")
        head = rights
        for sep in (":", ",", "("):
            head = head.split(sep)[0]
        head = head.replace(".csv", "").replace("-harvest", "").replace("comparison-", "").strip()
        if head.lower().startswith("ian's own"):
            head = "mosca-draw"
        words, s = head.split(), ""
        if words and len(words[0]) > 16:
            s = words[0][:16]
        for wd in words:
            if len((s + " " + wd).strip()) > 16:
                break
            s = (s + " " + wd).strip()
        n = len(p.get("training_sheets") or [])
        return {"family": fam if kind == "hand" else ("river" if kind == "river_stems" else fam),
                "source": (s or kind).upper(), "sheets": n}
    return {"family": fam, "source": "UNKNOWN", "sheets": 0}


# ---------------------------------------------------------------------------
# the tree
# ---------------------------------------------------------------------------

def _elbow(a, b, xm):
    return np.array([a, [xm, a[1]], [xm, b[1]], b], float)


@device("mdoc_provenance", family="process", params=[
    P("label_h", "float", 1.4, "lettering cap height, mm", min=0.6, max=6.0),
    P("pen", "float", 0.16, "pen, mm", min=0.05, max=1.0),
    P("ink", "str", "black", "ink for the tree (hand→layer branches take the layer's ink)"),
    P("mm", "bool", True, "print the ink each hand laid, mm"),
], doc="the descent of every line: sheet ← layers ← hands ← sources, grouped by corpus; hand-less layers hang "
       "from the layer they heard")
def mdoc_provenance(dctx, sheet, *, label_h, pen, ink, mm):
    x0, y0, w, h = dctx.region
    pad = min(3.0 + 0.04 * min(w, h), 8.0)
    x0, y0, w, h = x0 + pad, y0 + pad, w - 2 * pad, h - 2 * pad
    dsc = descent(sheet)
    lays, hands = dsc["layers"], dsc["hands"]
    th = label_h
    head = R.text("PROVENANCE", x0, y0, th)
    if not lays:
        return R.inks(head + R.text("NO LINES TO TRACE", x0, y0 + 2 * th, 0.7 * th), pen=pen, colour=ink)
    head += R.text("SOURCE", x0, y0 + 2.2 * th, 0.7 * th)
    cx = {"src": x0, "hand": x0 + 0.40 * w, "layer": x0 + 0.70 * w, "sheet": x0 + w}
    head += R.text("HAND", cx["hand"], y0 + 2.2 * th, 0.7 * th)
    head += R.text("LAYER", cx["layer"], y0 + 2.2 * th, 0.7 * th)
    top, bot = y0 + 4.5 * th, y0 + h - 2.0 * th
    # sources grouped by family, in the order their hands first appear
    srcs: "OrderedDict[tuple, list]" = OrderedDict()
    fam_order: list[str] = []
    for hd, e in hands.items():
        if e["family"] not in fam_order:
            fam_order.append(e["family"])
    for f in fam_order:
        for hd, e in hands.items():
            if e["family"] == f:
                srcs.setdefault((f, e["source"], e["sheets"]), []).append(hd)
    hand_order = [hd for v in srcs.values() for hd in v]
    nl, nh, ns = len(lays), max(len(hand_order), 1), max(len(srcs), 1)
    rows = max(nl, nh, ns + len(fam_order))

    def ys(n, k):
        return top + (k + 0.5) * (bot - top) / n

    y_lay = {lid: ys(nl, i) for i, lid in enumerate(lays)}
    y_hand = {hd: ys(nh, i) for i, hd in enumerate(hand_order)}
    # sources: a gap between families
    slots, y_src, fam_y = [], {}, {}
    k = 0
    for f in fam_order:
        fam_y[f] = k
        k += 0.6
        for key in srcs:
            if key[0] == f:
                slots.append((key, k))
                k += 1
    for key, kk in slots:
        y_src[key] = top + (kk + 0.5) * (bot - top) / max(k, 1)
    letters, branches = [], []
    tw = 0.75 * th
    # sheet node
    seed = (sheet.meta.get("recipe") or {}).get("seed", "")
    ymid = (top + bot) / 2
    letters += R.text("SHEET", cx["sheet"], ymid - th * 1.2, 0.8 * th, anchor="right")
    letters += R.text(str(seed), cx["sheet"], ymid + 0.3 * th, 0.8 * th, anchor="right")
    sheet_x = cx["sheet"] - R.text_w("SHEET", 0.8 * th) - 1.5
    lay_w = max(R.text_w(v["tag"], tw) for v in lays.values())
    xm_sheet = (cx["layer"] + lay_w + sheet_x) / 2
    for lid, v in lays.items():
        y = y_lay[lid]
        letters += R.text(v["tag"], cx["layer"], y - tw / 2, tw)
        branches.append(_elbow((cx["layer"] + lay_w + 1.0, y), (sheet_x, ymid), xm_sheet))
    # hands → layers, in the layer's ink
    hand_w = max([R.text_w(R.short(hd, 7) + (f" {hands[hd]['mm']:.0f}" if mm else ""), tw) for hd in hand_order] + [1])
    xm_hl = (cx["hand"] + hand_w + cx["layer"]) / 2
    coloured = []
    hook_x = cx["layer"] - 1.2
    for lid, v in lays.items():
        for hd in v["hands"]:
            gap_a, gap_b = cx["hand"] + hand_w + 2.0, cx["layer"] - 7.0       # each hand its own riser
            xm = gap_a + (hand_order.index(hd) + 0.5) / len(hand_order) * max(gap_b - gap_a, 1.0)
            coloured.append((_elbow((cx["hand"] + hand_w + 1.0, y_hand[hd]), (cx["layer"] - 1.0, y_lay[lid]), xm),
                             v["colour"]))
        if not v["hands"] and v["from"] and v["from"][0] in y_lay:
            a, b = y_lay[v["from"][0]], y_lay[lid]
            hook = np.array([[cx["layer"] - 0.6, a], [hook_x - 1.6, a], [hook_x - 1.6, b], [cx["layer"] - 0.6, b]])
            coloured.append((hook, v["colour"]))
            letters += R.text(v["from"][1].upper(), hook_x - 2.2, (a + b) / 2 - 0.35 * tw, 0.7 * tw, anchor="right")
            hook_x -= 1.0
        elif not v["hands"]:
            letters += R.text("BY THE COMPOSER", cx["layer"] - 1.5, y_lay[lid] - 0.3 * tw, 0.6 * tw, anchor="right")
    for hd in hand_order:
        lab = R.short(hd, 7) + (f" {hands[hd]['mm']:.0f}" if mm else "")
        letters += R.text(lab, cx["hand"], y_hand[hd] - tw / 2, tw)
    # sources → hands
    src_w = max(R.text_w(f"{key[1]} {key[2]}" if key[2] else key[1], tw) for key in srcs) if srcs else 1
    xm_sh = (cx["src"] + src_w + cx["hand"]) / 2
    for key, hs in srcs.items():
        y = y_src[key]
        letters += R.text(f"{key[1]} {key[2]}" if key[2] else key[1], cx["src"], y - 0.5 * tw, tw)
        for hd in hs:
            branches.append(_elbow((cx["src"] + src_w + 1.0, y), (cx["hand"] - 1.0, y_hand[hd]), xm_sh))
    for f in fam_order:
        yf = top + (fam_y[f] + 0.3) * (bot - top) / max(k, 1)
        letters += R.text(f.upper(), cx["src"], yf - 0.4 * tw, 0.8 * tw)
        letters.append(R.rule(cx["src"] + R.text_w(f.upper(), 0.8 * tw) + 0.8, yf, cx["src"] + src_w, yf))
    letters += R.text("N = SHEETS OR TAKES THAT TRAINED THE HAND / MM = INK IT LAID HERE", x0, y0 + h - 0.6 * th,
                      0.65 * th)
    out = R.inks(head + letters + branches, pen=pen, colour=ink, role="provenance")
    for p, c in coloured:
        out += R.inks([p], pen=pen, colour=c, role="provenance-branch")
    return out
