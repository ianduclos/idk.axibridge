"""Measuring devices on a synthesis (S4): Gesture Studies' device layer over this kit.

`_gesture_studies/devices.py` (one source: the catalogue, spec checking,
cancellable, memoised `apply` with the layer's own library as the kit's
default) is loaded a second time over the synthesis kit (`_shared.load`).
The bench offers its 13 round-15 devices plus the round-16 process documents
(`mdoc_*`), which read the played score every synthesis carries.
"""
from __future__ import annotations

from ._shared import load

_gs = load("devices")

# round 16's process documents (results/round16-*.md: staff, unheard, provenance; census, ledger, sympathy)
MDOC = {
    "mdoc_staff": {"label": "Staff of the score", "place": "beside", "side": "bottom", "size": 50.0,
                   "shown": [("kinds", "Name each relation"), ("label_h", "Lettering, mm")],
                   "empty": "Nothing to read: no relation acted."},
    "mdoc_unheard": {"label": "Unheard", "place": "beside", "side": "right", "size": 110.0,
                     "shown": [("drop", "Take out only these kinds"), ("tol", "Unchanged within, mm")],
                     "slow": "plays the score a second time without its relations",
                     "empty": "Nothing to read: no relation changed a line."},
    "mdoc_provenance": {"label": "Provenance", "place": "beside", "side": "right", "size": 70.0,
                        "shown": [("mm", "Ink each hand laid")],
                        "empty": "Nothing to read: no hand drew here."},
    "mdoc_census": {"label": "Census of crossings", "place": "over",
                    "shown": [("style", "Style"), ("read", "Read")],
                    "empty": "Nothing to read: no lines meet."},
    "mdoc_ledger": {"label": "Ledger of the score", "place": "beside", "side": "right", "size": 110.0,
                    "shown": [("max_rows", "Most rows"), ("drawn_by", "Rules drawn by")],
                    "slow": "slow while a hand draws the rules",
                    "empty": "Nothing to read: no relation acted."},
    "mdoc_sympathy": {"label": "Sympathy", "place": "over",
                      "shown": [("style", "Style"), ("gain", "Magnified by")],
                      "empty": "Nothing to read: nothing moved in sympathy."},
}
_gs.CATALOGUE.update(MDOC)

DeviceError = _gs.DeviceError
catalogue = _gs.catalogue
check_specs = _gs.check_specs
apply = _gs.apply
grown_frame = _gs.grown_frame
DEFAULT_SIZE = _gs.DEFAULT_SIZE
MAX_DEVICES = _gs.MAX_DEVICES


def named_hands(specs: list[dict]) -> list[str]:
    """Library hands the devices name (both ledgers' hand-drawn rules), pinned at Keep."""
    out = list(_gs.named_hands(specs))
    reg = _gs._registry()
    for s in specs:
        if s["id"] == "mdoc_ledger":
            hand = s.get("drawn_by", next(p.default for p in reg["mdoc_ledger"].params if p.name == "drawn_by"))
            if hand:
                out.append(hand)
    return out
