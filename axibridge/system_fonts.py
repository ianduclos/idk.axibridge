"""Best-effort discovery of fonts already installed on the machine — how
`text_fill`'s font picker gets real Helvetica/Arial/Times New Roman where
they're actually present, without this repo bundling anything proprietary
(see `axibridge/sources/text_fill.py`'s docstring).

**Never raises.** A search directory that doesn't exist, a font file
fontTools can't parse, a permission error — all skipped silently, one file
at a time, so one weird font can never take the whole catalogue down or
break app startup. On the Pi (none of these directories exist) this
returns an empty list, which is the correct, unremarkable answer: the
bundled variable font and any drag-in fonts still work.

A full scan of ~700 files / ~1100 collection faces takes a few hundred
milliseconds on this developer's Mac (benchmarked), so the whole thing
just runs eagerly and caches in memory — no need for a background index
or an on-disk cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

_SEARCH_DIRS = [
    # macOS
    Path("/System/Library/Fonts"),
    Path("/System/Library/Fonts/Supplemental"),  # Arial, Times New Roman, ... live here
    Path("/Library/Fonts"),
    Path.home() / "Library" / "Fonts",
    # Linux (the Pi has none of these; that's fine, see module docstring)
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path.home() / ".fonts",
    Path.home() / ".local" / "share" / "fonts",
]

_EXTS = (".ttf", ".otf", ".ttc")


@dataclass(frozen=True)
class SystemFont:
    id: str  # stable catalogue id: "sys:<path>#<face index>", or whatever a
             # bundled font registers (see register_bundled)
    label: str  # "Family" or "Family Style" when the style isn't Regular
    path: str
    font_number: int
    source: str  # "system" | "bundled"


_cache: list[SystemFont] | None = None

#: Fonts a source module ships in-repo (e.g. text_fill.py's Recursive),
#: contributed via register_bundled() so /api/fonts stays one generic
#: lookup regardless of how many modules bundle a font — no module-specific
#: wiring needed anywhere outside the module that owns the font.
_bundled: list[SystemFont] = []


def register_bundled(font_id: str, label: str, path: str | Path, font_number: int = 0) -> None:
    _bundled.append(SystemFont(font_id, label, str(path), font_number, "bundled"))


def _iter_font_files():
    seen: set[Path] = set()
    for d in _SEARCH_DIRS:
        try:
            if not d.is_dir():
                continue
            for f in d.iterdir():
                if f.suffix.lower() not in _EXTS or not f.is_file():
                    continue
                rp = f.resolve()
                if rp in seen:
                    continue
                seen.add(rp)
                yield f
        except OSError:
            continue


def _face_label(font: TTFont) -> str | None:
    name = font.get("name")
    if name is None:
        return None
    # typographic family/subfamily (16/17) over legacy (1/2) when present —
    # the legacy pair gets awkward on fonts with many weights in one family
    family = name.getDebugName(16) or name.getDebugName(1)
    sub = name.getDebugName(17) or name.getDebugName(2)
    if not family:
        return None
    if sub and sub.strip().lower() not in ("regular", "normal", ""):
        return f"{family} {sub}"
    return family


def _discover() -> list[SystemFont]:
    out: list[SystemFont] = []
    for path in _iter_font_files():
        try:
            if path.suffix.lower() == ".ttc":
                coll = TTCollection(str(path), lazy=True)
                for i, font in enumerate(coll.fonts):
                    label = _face_label(font)
                    if label:
                        out.append(SystemFont(f"sys:{path}#{i}", label, str(path), i, "system"))
            else:
                font = TTFont(str(path), lazy=True, fontNumber=0)
                label = _face_label(font)
                if label:
                    out.append(SystemFont(f"sys:{path}#0", label, str(path), 0, "system"))
        except Exception:
            continue  # one bad font file must never break the whole catalogue
    out.sort(key=lambda f: f.label.lower())
    return out


def catalogue(refresh: bool = False) -> list[SystemFont]:
    """Bundled fonts (registered by whichever source modules ship one) plus
    the discovered fonts, scanned once and cached. `refresh=True` re-scans
    the filesystem (a font was installed/removed since the app started) —
    bundled entries never need refreshing, they don't change at runtime."""
    global _cache
    if _cache is None or refresh:
        _cache = _discover()
    return [*_bundled, *_cache]


def find(font_id: str) -> SystemFont | None:
    for f in catalogue():
        if f.id == font_id:
            return f
    return None
