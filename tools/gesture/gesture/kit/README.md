# gesture kit: how to add a technique

The kit turns the gesture research into parts you can combine. Hands, tempos
and corpora are saved in a library. Techniques are small modules of four
kinds, and a **recipe** (plain JSON) says how to combine them. The spec is
`docs/superpowers/specs/2026-10-17-gesture-kit.md`; the reason for it is in
`results/round8-review-2026-10-17.md`: keep distinct grammars whole and set
them side by side, never average them.

```python
import sys; sys.path.insert(0, "tools/gesture")       # run from the repo root
from gesture import kit
sheet = kit.run({"seed": 7000, "voice": {"id": "drift"}})   # = the Hand Drift bench default
kit.preview(sheet, ".local/gesture/out/kit/mine.jpg")       # image + mine.recipe.json beside it
kit.list()                                                  # every module and its params
kit.library.entries("hand")                                 # what the library holds
```

Use the research interpreter only: `.local/gesture/.venv/bin/python`.

## The rule that lets you work in parallel

**A new technique is a new file in `tools/gesture/gesture/kit/`.** The kit
imports every module file in the package on first use (`pkgutil`, sorted by
name). So you never need to edit `__init__.py`, `core.py`, `library.py`, or
another agent's file:

- Name the file after your technique, e.g. `voices_chimera.py` or
  `modulators_accumulate.py`. The `<kind>s_<topic>.py` pattern keeps them
  grouped.
- Files that start with `_` are skipped, so use that prefix for private
  helpers.
- Ids are global within a kind. Registering an id that another file already
  owns raises `RegistrationError`. Run `kit.list()` and choose a new id.
- If your file fails to import, the error goes into `kit.DISCOVERY_ERRORS`
  and a warning is raised. Other techniques keep working.
  `test_kit.py::test_seed_modules_registered_and_listed` asserts that this
  dict is empty, so a broken file still fails the suite.
- Write tests in your own file, `tests/test_kit_<topic>.py`. Leave
  `test_kit.py` alone unless you are changing the core.

## The pipeline

```
recipe ─► arranger(ctx, parts)                  places parts in the frame
              part.voice(box)   ─► voice(ctx, **params)          -> list[Mark]  (fitted into box)
              part.modulate(ms) ─► modulator(ctx, marks, **p)    -> list[Mark]  (chained, in order)
       ─► renderer(ctx, marks, **params) per part                -> list[Ink]
       = Sheet(frame, marks, inks, meta)
```

All geometry is in **sheet millimetres** with y pointing down. The frame
defaults to 267 × 180 mm. Modulators run after placement, on final mm
geometry, so mm params such as nib width and pen stay physical.

## The four kinds and their signatures

```python
from .core import P, Mark, Ink, voice, modulator, renderer, arranger, fitted, refit

@voice("myvoice", params=[P("hand", "ref", "matisse", "the grammar", kind="hand"),
                          P("length", "float", 3.0, "in R", min=0.2, max=12.0)],
       doc="one line, my way")
def myvoice(ctx, *, hand, length):
    g = ctx.use("hand", hand)              # library + policy gate; recorded in sheet.meta["library"]
    rng = ctx.rng("grow")                  # or np.random.default_rng(ctx.seed) to match the bench
    pts_px = ...                           # grow in any native space (e.g. the 1000×1200 px research frame)
    return fitted([pts_px], ctx.box, channels=[{"voice": ...}], metas=[{"voices": [hand]}])

@modulator("mymod", params=[...], doc="...", reach=lambda p: 0.0)
def mymod(ctx, marks, **params):           # returns NEW marks; carry every channel you didn't write
    return [m.evolve(channels={"emphasis": ...}) for m in marks]

@renderer("myink", params=[P("pen", "float", 0.4, "mm", min=0.05, max=3.0)], reach=lambda p: p["pen"] / 2)
def myink(ctx, marks, *, pen):
    return [Ink(m.points, closed=False, filled=False, pen=pen) for m in marks]

@arranger("myarr", params=[...])
def myarr(ctx, parts):                     # each part: .voice(box), .modulate(marks, box), .run(box)
    out = []
    for p, box in zip(parts, my_boxes(ctx.box, len(parts))):
        out += p.run(box)                  # marks keep meta["part"]; the core renders per part
    return out
```

- **voice**: makes centrelines. It must fit its marks into `ctx.box`, given
  as `(x0, y0, w, h)` mm. Use `fitted(...)` so that `meta["fit"] =
  {scale, offset}` is recorded; the `grid` arranger needs it to set lines
  at one common scale (`refit(marks, box, scale=s)`).
- **modulator**: writes channels on placed marks. It may resample or
  displace points. Use `Mark.resampled(step)` or `Mark.remap(s_new,
  points=...)` so that every other channel is interpolated along. Splitting
  or merging marks is allowed, as long as the channels are carried.
- **renderer**: inks marks as `Ink(points, closed, filled, pen, meta)`.
  `closed` means the first point equals the last. `filled` means an outline
  ring that should occlude. A part can override the sheet renderer with
  `"renderer"` in its recipe entry.
- **arranger**: composes the sheet from parts and returns placed Marks.
  `single` overlays every part on the same box (polyphony on one surface).
  `grid` gives each part its own cell.
- **reach** (optional, any kind): `fn(params) -> mm`, how far ink can spread
  from a centreline. The sheet inset is the largest reach over all modules
  in the recipe, unless the recipe sets `margin`.

## Marks and channels

A `Mark` holds `points (N, 2)`, `channels {name: (N,)}` and `meta`.

- **Required channels** are `r` (regime: 0 wire, 1 nib, 2 mass), `phi`
  (nib angle in radians, period π), `W` (nib width, mm) and `M` (mass
  width, mm). A missing required channel is filled from `DEFAULT_CHANNELS`
  (0, 35°, 3.5, 9), which are the bench defaults.
- **Optional channels in use**:
  - `voice`: index into `meta["voices"]`, the hand speaking at each point
  - `tremor`: lateral offset applied, in mm
  - `dance_t`: seconds into the dance
  - `emphasis`: reserved for weight-as-stress
- **Unknown channels pass through.** The core checks after every
  modulator: if a channel present on every input mark is missing from an
  output mark, it raises `ChannelError`. To carry channels, use
  `m.evolve(channels=..., meta=...)`, which merges, or `m.remap(...)` /
  `m.resampled(...)`, which interpolate.
- **Interpolation.** A new channel is interpolated linearly by default.
  Declare other behaviour once, at import time, with
  `kit.channel_kind("mychan", "nearest" | "axial")`. Use "nearest" for
  categorical channels and "axial" for angles of period π.
- **Purity.** Marks and Inks are immutable: their arrays are read-only and
  writing to one raises. Always return new objects. `meta` is deep-copied
  on construction.

## Determinism

- Part *i* gets the seed `recipe seed + i` (`core.part_seed`). This matches
  the Hand Drift bench, where line *i* uses seed + *i*, so bench recipes
  reproduce exactly. The seed never depends on other parts.
- For every other random draw, use `ctx.rng(*tags)`. It seeds a numpy
  Generator from (part seed, stage, module id, tags). String tags are
  folded with CRC-32 (`core.tag`).
- **Never** use `hash()`, which is salted per process, `random`, or the
  global numpy RNG. Never iterate a `set`, or anything whose order could
  change between runs, when that order affects output. Sort it first.
- Sheet-level things that all parts share, such as a spatial field, are
  seeded from `ctx.sheet_seed`.
- Same recipe ⇒ identical output, across processes and `PYTHONHASHSEED`.
  `test_kit.py` checks this in subprocesses.

## Params

`P(name, type, default, doc, ...)` takes one of these types:

| type | value | extra arguments |
|---|---|---|
| `int`, `float` | a number | `min` and `max` are both required; unbounded values are refused |
| `bool` | true / false | |
| `str` | any string | |
| `choice` | one of a fixed set | `choices=(...)` |
| `ref` | one library id | `kind=` (a library kind) |
| `refs` | a list of library ids | `kind=`, `min_len`, `max_len` |
| `floats` | a list of numbers | |

Pass `optional=True` to allow `null`.

- `kit.validate(recipe)` checks every id, param, bound and library ref, and
  fills in defaults.
- The specs are exported as JSON by `kit.describe()`, so a future bench can
  render controls from them.
- The id `id` is reserved.

## Recipes

```json
{"label": "optional", "frame": [267, 180], "seed": 7000, "margin": null,
 "arranger": {"id": "grid", "cols": 0},
 "parts": [
   {"voice": {"id": "drift", "hands": ["matisse", "shikasta", "lichtenberg"], "joins": "chain"},
    "modulators": [{"id": "timing", "tempo": "staccato"}],
    "renderer": {"id": "nib", "style": "e"}},
   {"voice": {"id": "hand", "hand": "marden"}}],
 "renderer": {"id": "wire", "pen": 0.4}}
```

- **Shorthand.** For one part you can write a top-level `voice` and
  `modulators` instead of `parts`.
- **Defaults.** `arranger` defaults to `single` and `renderer` to `wire`.
- **The run.** `kit.run(recipe)` returns a `Sheet`. `sheet.recipe` is the
  normalized recipe, with every default written out. `sheet.meta["library"]`
  lists every library id used, with its version and policy.
- **Saving.** Save the recipe next to every result image; `kit.preview`
  does this as `<stem>.recipe.json`. That file is how a result is
  reproduced and recombined.

## The library

Each entry is one folder: `tools/gesture/library/<kind>/<id>/entry.json`
plus its data files. Kinds so far:

| kind | loads as | data files |
|---|---|---|
| `hand` | research `grammar.Grammar` | `tables.npz` + `sheet.json.gz`, lossless |
| `tempo` | research `gesture_timing.Timing` | `profile.npz` |
| `corpus` | an index of `.local/gesture/corpus/<name>` | none: counts, manifests and policy live in `entry.json` |

**Adding an entry** creates its own folder; there is no shared index to edit:

```python
from gesture.kit import library as L
L.save({"id": "myhand", "kind": "hand", "label": "My hand", "version": 1,
        "policy": "generative",              # or "measure-only"
        "provenance": {"corpus": "earth", "training_sheets": ["bc-07"], "research_file": "..."},
        "notes": "what it is, where it came from"},
       {"tables.npz": L.npz_bytes(arrays), "sheet.json.gz": L.json_gz_bytes(sheet)})
```

- **Encoders.** Use `L.encode_hand(grammar.to_json())`, which asserts an
  exact round trip, and `L.encode_tempo(timing)`.
- **New kinds.** Add folders under `library/<newkind>/`. If the data needs
  decoding, register a decoder in your technique file with
  `@library.loader("newkind")`. Without one, `load` returns
  `{"entry", "folder", "files"}`.
- **Size.** Keep the committed library under ~10 MB in total
  (`L.size()`). It is about 1 MB today. Scans and extracted strokes stay in
  `.local/` and are never committed.
- **Regenerating.** `tools/gesture/build_library.py` regenerates the seed
  entries only. Entries you add are left alone.

## Policy (binding)

- `policy` is either `"generative"` or `"measure-only"`.
- `ctx.use(...)` / `library.load(kind, id)` asks for generation by default.
  For a measure-only entry it raises `PolicyError`, a subclass of the
  research `calligraphy.PolicyError`. Statistics are allowed through
  `purpose="measure"`.
- **Qur'anic and devotional calligraphy is measure-only.** Never output
  legible Arabic. Call outputs "line studies after the X hand"
  (docs/research/gesture-corpus/calligraphy-arabic.md, "Adopted policy").
- **Corpus entries.** The `calligraphy` and `print` corpora are
  measure-only. `calligraphy` carries `generative_items`, the allow-list:
  manifest content type exercise / poetry / document, nothing left to
  verify, minus `script_syntax.EXCLUDE_GENERATIVE` (wc-30).
- **Hands trained on a corpus.** A hand that records `provenance.corpus` is
  re-checked against that corpus's allow-list every time it is loaded for
  generation. Record `training_sheets` honestly.
- **Corpora give behaviours, never forms** (round-8 review, E).

## Previewing

- `kit.preview(sheet, path, px_per_mm=6, label="auto")` draws the inks at
  their pen width on warm paper (#FFFCF0) with a label strip, and writes
  the recipe beside the image.
- `kit.render_image(...)` returns the PIL image instead of writing it.
- `kit.contact(images, cols, title=...)` tiles several images into one
  sheet.
- `sheet.to_svg(path)` writes a plain mm SVG.
- Images only: never plot, and never touch the app or the MCP from here.
  Example: `experiments/kit_demo.py`.

## Seed modules (v1)

| kind | id | what |
|---|---|---|
| voice | `hand` | one hand, whole, via `hybrid.drift_line` with a single hand (the bench's "each") |
| voice | `drift` | a route of hands; blend `mixture` / `interp`; joins `smooth` / `chain` |
| modulator | `wire` | r = 0 |
| modulator | `constant` | set r / phi / W / M |
| modulator | `timing` | dance tempo: stillness → mass, flow → nib at the wrist, speed → dry line; adds tremor. Burst signs are not in v1 |
| modulator | `field` | a regime field over the sheet: `noise` (the bench), `axis`, `bands`, `radial`, `margins` |
| renderer | `wire` | one polyline per mark |
| renderer | `nib` | research `regime.render` + `penrender.nib_style`, styles a / b / b+ / c / e / c+e |
| arranger | `single` | every part fills the frame |
| arranger | `grid` | one part per cell, one common scale |
