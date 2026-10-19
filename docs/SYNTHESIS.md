# Synthesis bench (S4, 2026-10-19)

A score of layers and the relations between them, played by one executor.
A composer (a *writer*) proposes the score; Ian edits, locks and recomposes
it; Keep adds it to the project as a group. Design:
`docs/synthesis-bench/design-2026-10-19.md` (§9 interaction, §10 placement,
§11 Ian's decisions); build plan and the S4-start decisions:
`docs/superpowers/plans/2026-10-19-synthesis-bench-build.md`.

## Pieces

| Piece | File |
|---|---|
| frozen kit (separate copy, refreeze often) | `axibridge/sources/_synthesis/kit/` ← `tools/synthesis/freeze.py` |
| hand library (shared with Gesture Studies, append-only) | `axibridge/sources/_gesture_studies/library/`, read through `_synthesis/frozen_library.py` |
| devices (Gesture Studies' 13 + round 16's six process documents) | `_synthesis/devices.py` |
| playing a score, layer paths, the played summary | `_synthesis/engine.py` |
| the generator (`synthesis`, param = the score) | `axibridge/sources/synthesis.py` |
| keep as a group / replace a kept group | `axibridge/synthesis_session.py` |
| HTTP | `axibridge/synthesis_api.py` (`/api/synthesis/*`) |
| saved syntheses (machine-level) | `axibridge/synthesis_store.py` (`~/.axibridge/synthesis/`) |
| MCP | `axibridge_mcp/tools_synthesis.py` (`synthesis` tool) |
| bench UI | `axibridge/static/js/synthesis_bench.js` (adapter `synthesis`) |

`_synthesis/frozen_library.py` and `devices.py` are Gesture Studies' own
modules loaded a second time as modules of `_synthesis` (`_shared.load`), so
their `.kit` imports bind to the synthesis kit: one source, two kits.

Refreeze (after research changes are committed):

    .local/gesture/.venv/bin/python tools/synthesis/freeze.py

It copies every kit module the executor, relations, writers, devices and the
Gesture Studies recipes reach (imports followed from `SEED_GLOBS`), appends
any new library entries without moving Gesture Studies' `current`, and
writes parity fixtures to `tests/fixtures/synthesis/` (the frozen copy must
reproduce the research kit, and its writers the same scores, first).

## The score (the generator's param)

The v2 score of `tools/gesture/gesture/kit/_synth.py` (its docstring is the
contract: layers, relations, wildcards and filters, budgets, seeds, pins,
devices). Bounds the app adds (`sources/synthesis.py`): ≤ 24 layers, ≤ 64
relations, ≤ 150 000 literal points across lines, base and pins, ≤ 4 MB of
JSON, frame ≤ 600 mm. Layer params:

- `score` — stored normalised (the executor's `validate`, devices checked);
- `show` — `all` | `layer` (with `layer`: a score layer id) | `measure`;
- `library`, `pins` — filled at Keep (`complete_params`: the snapshot and
  every library entry the played score used).

The bench owns `score.decisions.bench` (free-form): `held` (layers the ripple
setting locked), `from` (the gallery card), `ripple` (the setting).

## Preview

`POST /api/generators/preview {"module": "synthesis", "params": {...}}`
returns the usual `lines`, `layers` (one per score layer that drew, in plot
order, then `Measure`), `styles` (runs of paths with colour + pen width) and:

    "synthesis": {
      "layers":    [{"id": "L2", "role": "speaker", "pen": "black", "paths": 8}, …],   // doc layer order
      "relations": {"R1": {"fired": 1, "applied": 1, "outcomes": {"imitate": 1},
                           "pairs": [["L2", "L4"]]}, …},     // fired == 0 → the arc is dashed
      "decisions": {…}, "seconds": {"marks", "inks"}, "cache_hits": n,
      "devices": [{"id", "inks", "seconds", "error"?}] | null, "frame": [W, H]}

`fired` counts outcomes that changed something; `silent`, `spent`, `cross`
and `unplaced` are neutral.

Ink is clipped at the frame path by path (never rescaled), so a kept
group's members stay in register and a held layer stays where it was.

**What a lock holds** (`_synth.pin`): the layer as it stands once grown —
its part drawn and its grow relations played (where it was placed, what it
heard) — and its final lines, at full float precision. At its step it is
laid down as grown and every relation plays as before (what it does to the
other layers stays); when the score has played it is reset to its final
lines. So locking alone changes nothing on the sheet, and no edit anywhere
moves a locked line (ripple `none` moves only the edited layer). A pin
costs its lines twice in the score (about 1.4 MB for a fully held listen
sheet); the played log may still name a gap in a held line that the reset
then hides.

## Endpoints (`/api/synthesis`, none touches the machine)

| Method | Path | Body → result |
|---|---|---|
| GET | `` | catalogue: `relations` (id, phase grow/contact, doc, params with type/min/max/choices), `writers` (id, doc, params), `techniques` {voice, modulator, renderer: [spec]}, `library` {hand, tempo, dance_trail: options}, `devices`, `inks` (Flexoki name → hex), `roles`, `gallery` (writers, every kit study as `study:<id>`), `saved`, `limits`, `snapshot`, `frozen_from`, `default_frame` |
| POST | `/start` | `{gallery: "writer:listen" \| "study:leaf_miner" \| "saved:<id>", seed?, params?}` → `{score}` |
| POST | `/compose` | `{writer, seed, params?, frame?, region?, ground?}` → `{score}` |
| POST | `/recompose` | `{score, seed, locked: [layer ids], locked_relations: [ids], writer_index?, params?}` → `{score, dropped}` — locked layers are pinned first; the writer builds its palette around their pens (Ian); a locked relation is kept when both ends survive |
| POST | `/lock` | `{score, ids}` → `{score}` (pins: each layer keeps its lines as grown — placed, and what it heard — and its seed; locking alone changes nothing on the sheet) |
| POST | `/unlock` | `{score, ids}` → `{score}` (pins removed, seed kept; also releases ripple holds) |
| POST | `/hold` | `{score, edited, ripple: all \| direct \| none}` → `{score, held}` — call BEFORE applying an edit to `edited`: `direct` locks every layer except it and its direct listeners (grow relations naming it, and every layer a played event paired with it); `none` locks every other layer; `all` holds nothing (Follow) |
| POST | `/validate` | `{score}` → `{score}` normalised, or 400 with the reason |
| GET/POST | `/saved` | list; save `{label, score, thumb?: PNG data URL ≤ 120 kB, notes?}` |
| DELETE | `/saved/{id}` | delete a saved synthesis |
| POST | `/keep` | `{params, replace?: group id}` → `{group, layers}` — one undo step; `replace` swaps a kept synthesis group's members in place (same group, same transform) |

Every body also takes `library` / `pins` (a resumed layer's).

## Keep as a group

One app layer per score layer that drew, on a library pen of exactly its
Flexoki colour (missing pens are added), plus a `Measure` layer when devices
drew (first when every device sits under). All members carry the same
completed params, so they resolve one played sheet and stay in register.
Reopening any member in the bench edits the score with `show: all`; keeping
again with `replace` swaps the group.

## Bench interaction (design §9, study bench v3, Ian's decisions)

- **Two editors over one score**: a layer stack (one row per layer: role,
  technique / hand, pen, lock, dice; relation chips under it) and the arc
  diagram (layers along a line in drawing order, relations as arcs; drag
  between layers to add one, click an arc to edit it, drag a layer to
  reorder; a relation that never fired is dashed). Selecting in one selects
  in the other and highlights the layer's lines on the canvas.
- **Dice**: per control, per layer (its `seed`, or its hand), per relation
  (its `seed`), per sheet (the score `seed`).
- **Locks** at three levels: a control (Shuffle leaves it), a layer
  (`/lock`), a relation (Recompose keeps it).
- **Shuffle** varies every unlocked control; **Recompose** asks the writer
  for a new structure around the locks.
- **Ripple** (Ian, 2026-10-19): a bench setting `all` (default, Follow) /
  `direct` / `none`; held layers are shown as held and can be released.
- **History strip** of whole scores with their previews; **gallery** of
  starting points (writers, studies as one sealed layer, saved syntheses);
  **Measure** (devices as an optional layer); pen-colour previews.
