# Synthesis bench — build plan (2026-10-19)

Builds what `docs/synthesis-bench/design-2026-10-19.md` designs (§11 holds
Ian's four decisions). Order Ian set: **S0′ → S2 → S4**, then **S3**.
Decisions made for this plan are in the last section.

## Assumptions and the risky parts (read before an unwatched stretch)

- **The risky part of S0′** is that it edits the executor every round-16
  result rests on. Before any edit, a golden file records a hash per sheet for
  every round-16 relation test, the bridge, integ16 at all four dial stops, and
  the mdoc devices. S0′ is done when those hashes are unchanged (bit-identical,
  not "close"), and the round-16 suites still pass.
- **Porting listen into relations will not be bit-identical** to round-15
  listen. Parity here is by eye: the same seeds side by side, judged by Ian.
- **The app is untouched until S4.** S0′ and S2 live in `tools/gesture/` only,
  and the synthesis bench gets its own frozen kit, so Gesture Studies and its
  kept layers can't shift because of this work.
- S4 touches the app (new source, endpoints, MCP freshness, bench UI). Test
  servers only on temporary ports with `AXIBRIDGE_CONFIG_DIR` isolated; never
  port 2942 or AxiBridge.app. Commits at verified checkpoints, never a push.

## S0′ — close the ten contract gaps (lead, default-preserving)

Files: `kit/_synth.py`, `kit/_relations.py`, `kit/core.py` (param type only),
`kit/_devices.py`, a new `kit/_measure.py`. Every addition is opt-in; a score
that doesn't use it plays exactly as today.

| # | gap | fix |
|---|---|---|
| 1 | `*` can't skip a layer | relation keys `except: [ids]` and `roles` / `not_roles` filters on a wildcard; the bridge drops its 156 named pairs |
| 2 | relations can't see pen width | executor tags every mark `pen_mm` from its layer's renderer spec, as it tags `colour` |
| 3 | no dict param | a bounded `weights` param type (known keys → floats in [0, 1]); `crossing` accepts `weights` as well as its five floats |
| 4 | no relation-only layer | a layer with none of part / lines / composer starts empty; validation requires a grow relation into it |
| 5 | added marks take the layer's renderer | a mark may carry `own_pen` (colour + renderer spec); the ink pass groups by it and `_keep_meta` leaves it alone |
| 6 | no sheet-wide budget | optional relation key `budget` (max firings across all its pairs); `rctx.remaining()`; the executor counts |
| 7 | event refs shift after later cuts | every grown mark gets a stable `mid` and `s0` on the uncut line; `cut`/`remap` carry them; events add `mid` + uncut `s` beside today's fields |
| 8 | counterfactuals by hand | `synth.replay(score, drop=…, keep_only=…)`; `mdoc_unheard` switches to it (its output unchanged) |
| 9 | beside panels don't stack | `"stack": true` on beside devices shares one panel, split along it |
| 10 | no shared library measure | `kit/_measure.py`: hdist's "measure a line against the library", used by hdist_measure |

Plus one gap found while planning: **bind hears two layers**. `src` may be a
list of earlier ids for grow relations.

Checkpoint: golden hashes equal, round-16 suites + `test_kit_synth.py` +
new tests per gap pass → commit (one per gap group).

## S2 — composers as score writers

### S2a. listen writes scores (Opus thread; lead reviews)

1. **listen's eight kinds become relations** (`relations_listen.py`, grow):
   imitate, exaggerate, translate (the listener's own hand, the heard stretch
   spliced in with its own pen: gaps 4 and 5), refuse (detour), echo, calm,
   nest, bind (two srcs). Placement moves in with them: a listener picks its
   gesture from its src at play time, lies beside it and avoids the ink on
   the sheet then (Ian's "Follow"). The void becomes a `mask` contact
   relation with depth (cuts layers before it, later layers cross it).
2. **`listen_writer`** returns a score fragment for a region and a ground:
   speakers as parts with their written centre and turn; listeners as
   relation-grown layers; the void; all five awareness relations over
   `*` → `*` except the void (Ian: awareness everywhere). It writes as it
   plays (the density band needs the ground), through the executor and its
   cache. Decisions it took (counts, kinds, palette, bold voice) go in
   `decisions`.
3. **The balance dial is its first control**: `balance`
   none / one / speakers / all sets each grown layer's voice (`hand` or
   `hdist_zoom`); default `one`, all four stops kept (Ian: "both are nice as
   options").
4. **Lock** pins a layer: the executor keeps its played lines and skips
   regrowing it, so upstream edits don't move it.

Checkpoint images (seeds 15101–15108, unpicked): round-15 listen / integ16 dial
/ score-written listen at `one` and `speakers`; plus an edit test (swap a
speaker's hand, listeners follow). Lead's read written first → review page →
**keep going** (Ian chose not to block here).

### S2b. arch, then ccolour (Opus for arch, Codex Sol 6.1 for ccolour)

- arch: carry, reverse and ride as three relations (today arch collapses them
  into ride), answer from arch and the chorus; arch writes a score.
- ccolour writes a score.
- **Sealed layers for the rest**: every gallery composer runs as a `composer`
  layer confined to a region; a sweep test covers all 31 studies.
- Two composers on one sheet (listen in one region, arch in another, crossing
  between them) as the proof of problem 2.

Review page for S2b. **Wrap-up here** and S4 in a fresh session (this
session's context will be long by then).

## S4 — the app bench (Codex Sol 6.1 builds, lead reviews and commits)

Before starting: install Playwright chromium (Ian: yes).

1. **Freeze**: `tools/synthesis/freeze.py` from `git archive HEAD` into
   `axibridge/sources/_synthesis/kit/` (own `FROZEN.json`, own parity
   fixtures: listen / arch / ccolour scores, a sealed layer, a base). Hands
   come from Gesture Studies' append-only library, pinned by snapshot + hash.
2. **One generator**, `synthesis`: its param is the score (bounded: ≤ 24
   layers, ≤ 64 relations, size cap on literal lines), plus `show`
   (all / one layer / measure), library snapshot and pins.
3. **Keep as a group**: one app layer per score layer on its pen, plus a
   Measure layer when devices are on; one undo step; a kept group reopens in
   the bench (the chorus pattern in `gesture_studies_session.py`).
4. **API** `/api/synthesis/*` (relations, composers, compose, recompose,
   preview, keep); the MCP follows in the same commits.
5. **The bench UI** (`static/js/synthesis_bench.js`), full-screen like v3:
   - the layer stack: one row per layer (role, technique, pen, lock, dice),
     relation chips under each row;
   - the arc diagram as an editor: drag between layers to add a relation,
     click an arc to edit it, drag a layer to reorder; the played log
     overlaid (a relation that never fired is dashed);
   - selecting in one selects in the other and highlights the lines;
   - v3's interaction: alive / dimmed controls, dice (control, layer,
     relation, sheet), locks at three levels, Shuffle and Recompose, a history
     strip of whole scores, the gallery (listen and arch open as written
     scores, the other studies as one sealed layer), Measure, pen colours.
6. **Verification**: backend tests, UI acceptance tests in chromium, a check
   in the in-app browser on a temporary port. Then "ready for you to check" in
   the app (your relaunch), never "works".

## S3 — the unseen base (after S4)

Picture → `extract_hybrid` → lines with width; one captured canvas layer; the
whole canvas captured. The `base` layer (role unseen) already exists in the
score; S3 adds the three sources, "recapture" in the bench and a device that
documents the base in the margin.

## Who does what

- **Lead (this session, Opus 5.5)**: S0′ itself (contract), every brief,
  review of every diff and image, reads before Ian's notes, commits.
- **Opus subagents**: the sharp ports (listen's relations and writer, arch).
- **Codex Sol 6.1**: ccolour writer, the S4 app build pieces (study-build
  rule in `GESTURE-BANK-PROCESS.md` §8).
- **Sonnet**: tests per gap, the sealed-layer sweep, review image scripts.
- **Haiku**: very low-stakes chores (contact sheets, link checks), supervised.
- Agents run one at a time in the main checkout unless each owns only new
  files.

## Decisions for this plan (Ian, 2026-10-19)

1. **Edits ripple: Follow.** Listeners are relations and re-place themselves
   beside an edited source; speakers keep their written place; a lock pins a
   layer.
2. **Freeze: a separate kit copy** (Ian left it to the lead: "studies are
   done, this bench we might develop"). The studies stay stable while this
   bench is refrozen often; the hand library is shared because it is
   append-only and content-addressed.
3. **Review gate**: publish the review pages and keep going; stop only before
   the S4 freeze.
4. **Chromium**: install at the start of S4.
