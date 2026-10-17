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
in `tools/gesture_studies/freeze.py`, numpy/scipy/shapely only, frozen library
entries for the hands/tempos/trails the studies use). Freeze from the committed
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
