# Gesture kit — saved grammars + combinable technique modules (2026-10-17)

Ian, after trying the Hand Drift bench ("works amazing"): "consider having these
grammars and corpora saved, and have a lot of these different modules of how
they can be employed, and then be able to combine the techniques in different
ways … keep this open experimentation approach." Round 9 (new voices, prosody
and accumulation, polyphonic sheets) builds INTO this kit instead of producing
one-off experiments.

Research side only (`tools/gesture/gesture/kit/`). The app keeps its frozen
Hand Drift engine; a later bench can freeze kit recipes the same way.

## 1. Library — everything learned is saved, with provenance

`tools/gesture/library/` (committed): one folder entry per item, so parallel
work adds entries without touching a shared index.

```
library/<kind>/<id>/entry.json   # id, kind, label, version, created, provenance,
                                 # policy ("generative" | "measure-only"), notes,
                                 # files: {name: relative path}, size_bytes
library/<kind>/<id>/<data files> # npz / json.gz — compact, lossless where cheap
```

Kinds: `hand` (a learned line grammar), `tempo` (a dance timing profile),
`shapes` (a shape vocabulary), `corpus` (an INDEX of an extracted corpus:
counts, source manifests, where the local extraction lives under `.local/` —
scans and extracted strokes stay local, never committed), and room for new
kinds. `kit.library` loads/saves entries, lists them by kind, and is the single
**policy gate**: asking for a `measure-only` entry for generation raises
`PolicyError` (Qur'anic/devotional calligraphy is measure-only; never output
legible Arabic). Budget: keep the committed library under ~10 MB total; report
sizes. Seeded with the round-8 hands (matisse, hokusai, ingres, shikasta,
nastaliq, marden, lichtenberg, bubble), the six tempo profiles, and index
entries for every corpus under `.local/gesture/corpus/`.

## 2. Marks — the common currency between stages

A `Mark` is one line in sheet millimetres with per-point **channels**:
`points (N,2)`, `channels: dict[str, (N,) array]` — at least `r` (regime
0 wire … 1 nib … 2 mass), `phi` (nib angle), `W` (nib width), `M` (mass width);
optional `voice` (which grammar speaks at each point), `emphasis`, `tremor`, …
— plus `meta` (voice id, hand log, provenance ids). Stages may add channels;
unknown channels pass through untouched. Purity: stages return new Marks,
never mutate inputs.

## 3. Four kinds of technique module (registered by decorator)

- **voice** — makes centrelines: `voice(ctx, **params) -> list[Mark]`
  (seed v1: `hand` (one grammar), `drift` (route through hands; blend
  mixture|interp; joins smooth|chain)).
- **modulator** — writes channels: `modulate(ctx, marks, **params) -> marks`
  (seed v1: `wire`, `timing` (tempo entry), `field` (noise fronts), `constant`).
- **renderer** — inks marks: `render(ctx, marks, **params) -> list[Ink]`
  where `Ink` = polyline + `closed` + `filled` (seed v1: `wire`, `nib` with
  styles a|b+|c|e|c+e).
- **arranger** — composes a sheet from PARTS, each part being its own
  voice → modulators chain: `arrange(ctx, parts, **params) -> list[Mark]`
  placed in the frame (seed v1: `single`, `grid` — the bench's "each").

Modules live in files under `kit/` and register themselves with
`@voice("name")`, `@modulator(...)`, `@renderer(...)`, `@arranger(...)`;
`kit` auto-imports every module file in the package, so adding a technique is
adding a file. Each module declares a small param spec (name, type, bounds,
default, one-line doc) so a future bench can render controls from it.

## 4. Recipes — combinations as data

```json
{"frame": [267, 180], "seed": 7000,
 "arranger": {"id": "grid"},
 "parts": [
   {"voice": {"id": "drift", "hands": ["matisse", "shikasta", "lichtenberg"], "joins": "chain"},
    "modulators": [{"id": "timing", "tempo": "staccato"}]},
   {"voice": {"id": "hand", "hand": "marden"}, "modulators": []}],
 "renderer": {"id": "nib", "style": "e", "pen": 0.4}}
```

`kit.run(recipe) -> Sheet` (marks + inks + meta incl. every library id used);
`kit.preview(sheet, path)` writes the standard ink-on-paper image. Each part
may override the renderer. Deterministic: per-part seeds derive from the
recipe seed and the part index only (never `hash()` or set order); same recipe
⇒ identical output across processes and `PYTHONHASHSEED`. A recipe saved next
to every result image is how a result is reproduced and recombined.

## 5. Acceptance for the skeleton

A recipe reproduces the Hand Drift bench's default drift (same hands, seed,
joins) closely enough to be the same drawing; tests cover registry
auto-discovery, recipe determinism across hash seeds, the policy gate,
channel pass-through, and library round-trip; `kit.list()` prints every
module with its params. One example script renders a 2×2 sheet of four
recipes.
