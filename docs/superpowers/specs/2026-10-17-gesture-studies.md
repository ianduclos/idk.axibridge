# Gesture Studies — saved pieces with their own controls (2026-10-17)

Ian: "These feel like pieces and I'm afraid to overcook or have an instrument
that encompasses too much … save these, each with its own relevant
parameters, still able to have dynamism, and develop on top, but without
overcrowding the generator dropdown." Decision (questions UI, 2026-10-17):
**one bench with its own dropdown, called "Gesture Studies"; the Hand Drift we
built first is the first study.**

## What a study is

A study = a frozen **recipe** (gesture-kit JSON) + the few **controls** that
matter for it + a **version** and **parent**. Controls are pointers into the
recipe (a JSON path such as `parts.0.voice.hands`) with a label, type, bounds
and default; everything else in the recipe is fixed for that study. Seed is
always a control.

```json
{"id": "two_voices", "label": "Two voices, one surface", "version": 1,
 "parent": null, "created": "2026-10-17", "source": "kit demo 4 (round 9)",
 "recipe": { … kit recipe … },
 "controls": [
   {"path": "parts.0.voice.hands", "label": "Heavy voice route", "type": "hands", "min": 2, "max": 4},
   {"path": "parts.1.voice.hand", "label": "Dry voice", "type": "hand"},
   {"path": "parts.0.modulators.0.amount", "label": "Field amount", "type": "float", "min": 0, "max": 2},
   {"path": "seed", "label": "Seed", "type": "int", "min": 0, "max": 2147483647}]}
```

## Where things live

- **Built-in studies** ship in the app: `axibridge/sources/_gesture_studies/studies/<id>/study.json`.
- **Saved studies** (forks made in the bench) go to a machine-level store beside
  the pens and the gallery (`stores.py` conventions, `AXIBRIDGE_CONFIG_DIR` in
  tests), so they persist across projects. Promoting a saved study into the
  repo is a later script, not a UI action.
- **Kept layers** embed the full resolved recipe (study id + version + control
  values + the recipe snapshot), so a layer never changes when a study is
  edited, renamed or deleted, and travels inside the project folder.

## Engine

The app never reads `tools/` or `.local/`. The kit modules the built-in
studies need are frozen into `axibridge/sources/_gesture_studies/kit/` (same
discipline as `_hand_drift`: header with the research commit, a freeze script
in `tools/gesture_studies/freeze.py`, numpy/scipy/shapely only, every
generative library hand/tempo/trail frozen — see below). Freeze from the committed
HEAD, never from files being edited. Same recipe ⇒ same paths as the research
kit (parity test).

## New hands flow in (Ian, 2026-10-17)

"If they use the line corpuses and we add more, make them accept the new
ones." Hand / tempo / dance-trail controls list every generative entry of that
kind in the frozen library; the freeze script freezes all of them (policy gate
applied), so refreezing after new hands are learned adds them to every study
with no study edits. Kept layers pin the entry's version/content hash so a
refreeze never changes them.

## The bench

One generator **"Gesture Studies"** in the dropdown (`library_bench`), adapter
`gesture-studies` v1 (`new`, `resume`). Inside: a **study dropdown**; only the
chosen study's controls; live preview; presets (existing shared controls);
**Keep as layer**; **Save as new study** (name, records parent + version); an
**Edit recipe** drawer (advanced: the full recipe JSON, validated) for
developing a study further. Hand Drift appears as the first study with its
existing controls and identical output; the standalone Hand Drift generator
stays registered so existing layers resolve, but leaves the generator dropdown.

## First set (Ian's picks from rounds 8–9)

1. Hand Drift (first study; identical to the bench).
2. Danced chain — kit demo 2 (chain joins, Staccato timing, nib e).
3. Two voices, one surface — kit demo 4.
4. Drawing and its measure — the annotated sheet (drift + handover + its κ chart).
5. Shape atlas — atlas + ledger drawn by Matisse.
6. Conversation — poly_converse (Cohen-like scattered units).
7. Annotated page — poly_page P2 (two columns, danced-nib brackets/underlines).
8. Three voices — mantis dance-itself × polygon_walk wire × aaron wire.

Recipes are saved beside every round-9 image under `.local/gesture/out/<thread>/`
(and `tools/gesture/results/voices_machine-*.recipe.json`).

## Not decided here

The node-editor question (ROADMAP "Far / undecided") stays open: a study is a
recipe with exposed controls, not a graph editor.

## Studies v2 (2026-10-17, after the round-10 review)

Ian's notes on round 10 (`tools/gesture/results/round10-review-2026-10-17.md`)
turned into seven new built-in studies, appended after the first eight:

| id | from | controls |
|---|---|---|
| `numbered_atlas` | `measure_pairs-pair_atlas` — "amazing. keep as is" | the recipe verbatim; only the drawing's route (hands, blend, joins) and the seed. A development of the drawing or the specimens is a new study, never an edit of this one |
| `dance_atlas` | `measure_pairs-pair_dance` — "love this as well" | the dance, body ends, start, seconds, seed |
| `margin_chart` | `measure_pairs-pair_margin` — "super nice" | route, joins, layout (margin / diptych / under: the layouts sheet minus its first cell, the wrap), rows, what the numbers mark, seed |
| `merged_shadow` | `measure_pairs-shadow_turns` (+ the shadow sheet's variants) — "love all the different options" | route, law, side, shape, close, gap, gain, seed |
| `chorus` | developments `c5-four-ghost` — "I like these specific ones with multiple pens" | voices (2–4: the first n are exactly those of the full chorus), who answers whom, by space or time, hearing radius, leader route, seed |
| `sampler` | combo_search, sampling only — "I dig the unbred ones more" | the seed (it picks the whole combination) |
| `ledger_straight` | `measure_pairs-pair_ledger` — "an option to keep some of the lines in the graph straight" | drawing hand, ledger hand (or the machine), straight lines (none / rules / text / rules+text), a further seeded share of straight lines, the hand's share of turning, seed |

Research changes behind them, all additive with defaults that reproduce
earlier output bit for bit: `kit/sampler.py` (combo_search's sampler with
the pools as an argument: its priors reproduce combo_search exactly; the
library's pools add every other generative hand, so new hands enter the
sample space on a refreeze); `measure_pair` `straight` / `straight_share`
(a straight line is still restyled and the result dropped, so the hand's
generator advances as before and every other line is unchanged);
`dev_chorus` `voices`; and exact clothoid speed-ups (see below).

**Chorus kept as a group.** A study with `"keep": "voices"` keeps as ONE undo
step (`POST /api/gesture-studies/keep`): a layer group named after the study,
one ordinary `gesture_studies` layer per voice inside it, all carrying the
same params pinned once plus `voice` (which part that layer draws). Resolve
stays the single path: each layer resolves the same recipe (the engine shares
one kit run between them) and keeps only its voice's ink, fitted as one
drawing so voices stay in register. Each voice goes to a library pen of
exactly its Flexoki ink, a different pen per voice; a missing one is added to
the pen library as "Flexoki <ink>" and reused by the next chorus. Moving or
hiding the group moves or hides every voice; each pen plots as its own pass.
Resuming any voice reopens the whole chorus; Keep from there makes a new
group. The bench draws each voice in its ink (the preview payload names the
layers of a multi-ink document).

**Sampler.** Engine `sampler`: the study recipe is `{frame, seed}`; the seed
picks a combination from the frozen library's pools (`kit/sampler.sample`).
A kept layer stores the combination (`sampled: {of, recipe}`), so neither a
refreeze nor a sampler change can alter it; a different seed is a different
sample. The bench shows the sampler's one-line summary; Edit recipe shows the
sampled kit recipe; Save as new study keeps the combination as a kit study.

**Pinning rule (Ian: "stay pinned; explicit update").** A resumed layer keeps
its library snapshot and entry hashes through every edit, so a control only
changes what it controls; its hand / tempo / dance controls list the hands of
ITS snapshot (`GET /api/gesture-studies/library/{snapshot}`). "Update to
current library" (shown only when the layer's snapshot is not the current one)
clears the pins on purpose; Keep then pins the current library. Keep drops
pins of entries no control names any more. Presets stay study-level: applying
one starts from the current library.

**Clothoid speed.** The Shape atlas spent its time in the clothoid fit's
stage-2 greedy (≈2000 least-squares solves per chart line). Two exact
memos — the SSE of each knot configuration (the greedy re-visits ~35 % of
them) and each piece's column list — plus cheaper cache keys give ~1.45× on a
first fit; a per-process fit memo makes a refit of the same polylines free (a
chart redrawn through another hand or another amount). Bit-identical on the
453 recorded chart strokes and on every parity fixture.
