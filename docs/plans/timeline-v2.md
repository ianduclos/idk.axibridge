# Plan (loose): timeline v2 — keyframe chains, a bottom bar, a quantized scrub

Opened 2026-08-11 by Opus 5, for Ian to annotate and for later agent runs
(Sonnet/Opus) to build against. Deliberately loose in the
`hatch-connect-strokes-v2.md` sense: the direction is agreed, the mechanics
below are argued from the code but are still judgment calls, and every place
where the choice is Ian's is marked **OPEN QUESTION** with a recommendation
rather than settled.

**CLOSED 2026-08-11 — the whole build order shipped** (`4cebea7` → `e1dee75`,
suite 843 → 947). Slice headers below carry their commit; **§6 is the closing
ledger** — read it for what landed, what was superseded on the way, and what
is deliberately still open. §§1-5 are left as written, i.e. as the argument
that produced the round, not as a description of the code today.

Covers HANDOFF's **A1** (timeline/animation rethink) and **A2**
(staging/printing/batching intuitiveness) in one document, because they share
one piece of state — "which frame / which sheet am I on" — and designing them
apart is how you get two steppers that disagree.

Companion context: the 2026-08-10→11 perf round (`9649d8d`, `fb959d5`) is the
reason several things below are cheap now that were not cheap in July. Read
`axibridge/gencache.py`'s docstring and `STATUS.md`'s round-2 section first.

---

## 0. What does NOT change

Stated up front because three of the proposals below look like they touch the
resolver and do not.

- **The single resolve path.** Preview, estimate, sheet assembly, plot and
  export continue to flow through `session.resolved*()` →
  `compose.resolve_project()` (`ARCHITECTURE.md` "The resolve invariant";
  `session.py:2157-2186`). Nothing here adds a second geometry path. The
  chain work lives entirely inside `tween.materialize()` /
  `tween.effective_generator()`, which are already called from that one path.
- **Resolve order.** `occlusion(regions(effects(transform(source))))` is
  untouched. A chain is still one ordinary layer whose *source geometry* is
  materialised before `resolve_project` runs — same slot a tween occupies
  today (`session.py:2182`).
- **Scrubbing never mutates.** `master_t` stays ephemeral: clip-follow
  overrides live in a throwaway dict (`session.py:2188-2200`), stored
  `layer.source.params` are never written by a scrub (`session.py:2259-2263`),
  and the undo history and saved bytes are byte-identical with and without a
  scrub. Everything below preserves this; in particular **the timeline bar
  never PATCHes anything** (the existing scrub object already has this
  discipline — `compose.js:118-147`).
- **Tween/module purity.** Effects and generators never mutate input paths;
  `Path.filled` and closure survive; geometry lists are replaced wholesale,
  never edited in place. The chain work adds no in-place mutation.
- **Endpoint fidelity.** `t=0` reproduces A exactly and `t=1` reproduces B
  exactly (`tween.py:12-20`). The chain generalisation must keep the same
  promise at *every* keyframe, not just the two ends — see S2's tests.
- **`estimate.py` is still an estimator**, and the frame-grid work does not
  make it a scheduler.

---

## 1. Findings

Every claim here was checked against the code at `361b5ad`; the probe in
Appendix A was run against the real `Session`. **Line numbers are relative to
`361b5ad`** — the concurrent E-batch was already editing `index.html` (+16
lines above line 96) and `plot.js` (+9 above line 493) while this was written,
so grep the named symbol rather than trusting the number if it does not land.

### F1 — the brief's working hypothesis for chains is **false as stated**

The brief proposed: a chain A>B>C>D is sugar over N keyframes plus N−1
`follow_master` tweens with windows `[k/(N-1), (k+1)/(N-1)]`, needing no new
resolve semantics.

The window mapping composes exactly as hoped — but the *visibility* does not.
Outside its window a tween **holds its endpoint and keeps drawing**; it does
not disappear. Both halves are verified:

- `session.py:2275-2286` clamps master into the window, so before
  `window_from` local `t` = 0 (A) and after `window_to` local `t` = 1 (B).
  `tween.resolve_local_t` (`tween.py:331-348`) mirrors it for nested tweens.
  Pinned already by `tests/test_tween.py:194-203`
  (`test_window_holds_a_before_and_b_after`).
- Nothing anywhere makes a tween resolve to empty outside its window.
  `compose.resolve_project` skips only `layer.visible == False`
  (`compose.py:827`, `compose.py:893`), and `visible` is stored state.

Probe result (Appendix A) — three rectangle keyframes at width 20/60/100,
two segment tweens windowed `[0,0.5]` and `[0.5,1]`, both visible:

| master_t | seg0 width | seg1 width |
|---|---|---|
| 0.00 | 20 (=K0) | 60 (=K1, held) |
| 0.25 | 40 | 60 (held) |
| 0.50 | 60 (=K1) | 60 (=K1) |
| 0.75 | 60 (held) | 80 |
| 1.00 | 60 (held) | 100 (=K2) |

At every t **both segments draw**. A 4-key chain built this way would put
three overlapping copies on the sheet — and, worse, would plot them.

The near-miss is instructive though: the inactive segments hold *exactly* a
keyframe. So the composition is correct if and only if exactly one segment is
visible, and visibility would have to be a function of `master_t` — which is
precisely the thing scrubbing is forbidden to write. **The sugar hypothesis
dies on the no-mutation invariant, not on the window math.**

### F2 — what a chain has to be instead: one layer, piecewise in global `u`

The shape that fits the existing code with the least new surface: a chain is
**one tween layer** carrying an ordered list of keyframe layer ids, and
`materialize` reduces a global position `u ∈ [0,1]` to `(segment, local t)`.

Why this is cheap rather than a rewrite:

1. `materialize` already receives both values it needs —
   `override_t` (the window+curve-mapped master value) and the raw
   `master_t` — and the session computes them without knowing what the tween
   does with them (`session.py:2274-2286`, `session.py:2321-2322`).
   **Reinterpreting `override_t` as global `u` needs zero session changes on
   the resolve path.**
2. `_source_paths_at` (`tween.py:454-489`), `lerp_affine`, `_effects_at` and
   `check_compatible` are all already *pair*-shaped. A chain calls them on
   the active consecutive pair. No new blending code.
3. **`sweep` generalises for free.** A sweep already stamps at fixed global
   positions `i/(sweep+1)` (`tween.py:534-535`) and those positions are
   time-invariant by design (`tween.py:52-59`). Under a global-`u`
   parameterisation those same positions map through the chain, so a swept
   chain is a ladder across the whole motion — the visually useful reading,
   and it degenerates to today's behaviour at 2 keys.
4. **Effects and occlusion carry across segments automatically**, which is
   the brief's explicit question. The chain layer's own effect stack,
   transform, pen and occlusion flags apply *after* materialisation through
   the ordinary pipeline (`tween.py:60-63`); per-keyframe stacks still blend
   inside a segment via `blend_effect_stacks` (`tween.py:395-420`). Nothing
   is per-segment except the pair being blended.
5. Isometric spacing is **derived, not stored**: segment k spans
   `[k/(N-1), (k+1)/(N-1)]`. Inserting or deleting a keyframe re-spaces the
   whole chain with no windows to maintain, which is the entire reason Ian
   asked for "isometric".

The chain's own `window_from`/`window_to` keep their present meaning at the
outer level (map master into the chain's global `u`), so a chain still
composes inside a longer timeline exactly as an A/B tween does.

### F3 — the plumbing that assumes exactly two refs

`Session._tween_refs` returns a 2-tuple (`session.py:780-783`) and its callers
unpack it positionally. A chain with mid keyframes dangles unless all of these
learn "N refs":

| Site | File:line | What breaks without the change |
|---|---|---|
| cascade delete, rule (a) | `session.py:830-836` | deleting a mid keyframe leaves a broken chain |
| cascade delete, rule (b) | `session.py:844-846` | hidden mid keyframes are never collected |
| un-animate restore | `session.py:862-875` | reads `a_ref, _ =` — fine, but must not restore a mid key |
| dependency order | `session.py:768` | a nested chain materialises against stale inner geometry |
| tween cache key | `session.py:2292` | **silently wrong cache hits** when only a mid keyframe changed |

The cache-key one is the dangerous member of the set: `_TweenEntry.refs` pins
the `id()`s the key names (`session.py:73-81`), and a key that omits the mid
keyframes would happily serve stale geometry after a mid-key edit.

Also name-coupled: `_animation_keyframes_for` requires exactly 2 refs and the
`" ▸ A"` / `" ▸ B"` name suffixes (`session.py:785-799`) to decide what
travels with a deleted tween. Chain keys should keep the `▸ ` convention
(`▸ A`, `▸ B`, `▸ C`…) and that check should become a pattern match, not a
membership test.

### F4 — video needs nothing new to coexist with a chain

Clip-follow already rides the **raw** master value, independently of any
tween window or chain segment:

- A visible `frame_follow` generator gets an ephemeral clip-advanced overlay
  (`session.py:2188-2240`), keyed on `{params, offset, master_t}`.
- A *hidden* keyframe does **not** get that overlay — `_clip_overrides` skips
  `not layer.visible` (`session.py:2209`). It gets its clip advance the other
  way: `effective_generator` folds the raw master into the endpoint's frame
  offset (`tween.py:370-372`) and `_source_paths_at` folds that into the
  generator's `frame` param (`tween.py:479-485`). This is the parameter
  route, and it is why the frame ladder works today.
- Consequence worth writing down: **a chain over non-generator sources (the
  structural/pointwise route, `tween.py:489`) gets no clip advance.** Only
  the parameter route folds frames. That is existing behaviour, not a
  regression, but it is the answer to "why did my video chain freeze".

So: a video layer and a chain sit side by side on the same master timeline,
each reading the same `master_t`, and "A>D with enough video frames" needs
**nothing new at all** — a `frame_follow` clip layer plays across `0..1` with
no tween whatsoever (`session.py:571`, which defaults `frame_follow` on for
sequence-driven layers at creation). The chain is for what *else* changes
while the clip plays.

### F5 — where the timeline lives today, and what moving it costs

- The panel is `#timeline-panel` inside the **Compose sidebar tab**
  (`compose.js:261-271`): a `<input type=range id="master-t" step="0.001">`
  plus a `t = 0.000` readout, wired at `compose.js:397-410`.
- Visibility today: shown when the project has **any tween layer at all, or
  any layer whose `image` param ends in `#`** (`compose.js:178-193`). The
  *stricter* predicate the brief asks for — any `follow_master` tween or any
  `frame_follow` layer — is already computed two lines below as `hasFollow`
  (`compose.js:188-190`), where it currently only drives a nudge hint.
  Moving to the strict predicate therefore costs one line and orphans the
  hint (see P4).
- "Selecting a keyframe jumps the timeline" is `jumpTimelineToKeyframe`
  (`compose.js:149-172`). Two couplings to preserve: it early-returns on
  `$("timeline-panel")?.hidden`, and it deliberately declines for
  `cosine_pingpong` (B is reached mid-window, so there is no honest jump
  target) — `compose.js:161`.
- The canvas column is `#canvas-area` = toolbar / `#canvas-wrap` /
  `#canvas-status` (`index.html:123-212`). The natural mount for the bar is
  **between `#canvas-wrap` and `#canvas-status`**.
- Careful: the status line **already carries a transport** — `▶ Animate plot`
  + speed (`index.html:207-210`), gated on `S.plan?.moves?.length`
  (`main.js:521-534`). That replays the *planned job*, which is a different
  thing from scrubbing the master timeline. Two "play" buttons a few pixels
  apart meaning different things is a real hazard; see P1.

### F6 — the frame grid and the slider live in different modules with no shared truth

- The grid is `animT(i) = tFrom + (tTo - tFrom) · i/(n-1)` (`plot.js:1036-1038`),
  computed off the module-level `anim` object (`plot.js:650-658`) which is
  populated from the Animation panel's inputs by `pullAnimControls`
  (`plot.js:1040-1055`).
- Everything that plays or renders already goes through it: live preview
  (`plot.js:1099`, `plot.js:1109`), the raster popup render (`plot.js:1275`),
  frame capture (`plot.js:763`), single-frame plot (`plot.js:457`), and the
  export/sheet paths server-side use the identical formula
  (`session.py:1211-1213`, `api.py:1114-1115`). **The brief's premise holds:
  playback is entirely fixed-step; `#master-t` is the only continuous-`t`
  producer in the app.**
- But `anim` is private to `plot.js` and the slider is in `compose.js`.
  Quantizing the slider requires the grid to be readable from outside
  `plot.js`. Lowest-collision fix: **export a tiny accessor** from `plot.js`
  (`export function frameGrid()` returning `{n, tFrom, tTo}`) rather than
  hoisting the whole `anim` object into `S` — see the E6 collision note in
  §5.

### F7 — what the new caches actually reward, and what they don't

From the round that just landed (`STATUS.md`, 2026-08-10→11): a cold frame
~2.5 s, **a revisited frame sub-millisecond**. The mechanisms:

- `gencache` memoises `generate()` on `(source id, canonical params, asset
  version)` with **random** eviction, chosen precisely because scrub/loop
  access is cyclic and LRU at capacity has a 0% hit rate on it
  (`gencache.py` docstring, lines 17-21).
- `Session._tween_cache` and `_clip_cache` hold **one entry per (layer,
  master value) visited** (`session.py:266-274`), budgeted by
  `TWEEN_CACHE_BUDGET_POINTS = 3_000_000` with random eviction
  (`session.py:62-68`).
- The grid-sheet caches `_frame_lru` (144 entries) / `_frame_bbox` are keyed
  `(t, pens-sig, assets-sig)` and are **cleared on every checkpoint**
  (`session.py:293-301`, `session.py:1039-1069`).

The design consequence is sharp: **a cache entry is keyed on the exact float.**
A continuous slider produces a fresh float per pixel of travel, so today the
slider is the one interaction in the app that guarantees a miss on every tick,
while playback of the same animation is nearly free. Quantizing the slider to
`animT(i)` makes scrubbing and playback share keys — that is the whole prize,
and it is why A1.4 belongs in this round rather than "later".

Honest limits to write into the UI copy: the tween/clip caches are *not*
cleared on a project mutation (only `_restore` clears them,
`session.py:326-336`) — they simply stop matching, because the key embeds the
endpoint definitions and geometry `id()`s. And eviction is random and
budget-driven, so a "cached" tick can go stale silently. Ticks are a hint.

### F8 — "start from sheet 7" is one missing input, not a missing feature

The two-axis stepper already has the state:

- `anim.sheet` (page) × `anim.pass` (pen pass) — `plot.js:650-658`,
  `plot.js:1022-1034` (`stepSheetPass`), `plot.js:1318-1351`
  (`renderAnimStepper`).
- `currentSheetSpec()` puts `page: anim.sheet` into every spec it builds
  (`plot.js:669-674`), which feeds the plan overlay, the canvas preview, the
  estimate and `POST /api/plot/start` (`plot.js:461-464`).
- `refreshSheetInfo()` re-fetches that page's ordered pen passes
  (`plot.js:979-1002` → `GET /api/animation/sheet_info`, `api.py:1131-1163`).

What is missing is any control that *sets* `anim.sheet` to a chosen value.
The only movements are `Skip pass →` (advance one, `plot.js:437-447`), the
SSE-driven auto-advance after a job completes (`plot.js:1572-1584`), and
`Reset`, which slams `i/sheet/pass` to 0 (`plot.js:429-435`). So mid-sequence
starts are currently done by pressing Skip eighteen times.

Server side there is nothing to add: `page` is already a first-class
parameter of `sheet_document` / `SheetSpec` / `sheet_info`
(`session.py:1137-1188`, `api.py:1428-1445`, `api.py:1131`), and the shared
scale is computed across the **whole** animation on purpose, so page 7
rendered on its own is identical to page 7 of a full run
(`session.py:1018-1023`, `session.py:1211-1216`). **Starting from sheet 7 is
already correct; it is just not reachable.**

For tray groups the situation is different but similarly small: every staged
sheet already renders its own Preview / Insert / per-pass plot buttons
(`plot.js:938-947`), so any sheet is one click away — what is missing is
*where was I* (no done/current marking).

### F9 — the tray A>B fence removes no code; it prevents four growths

Ian's simplification — tray-to-tray transitions reserved for simple A>B
animations — is a scope fence, and it is worth being blunt: **there is
nothing to delete.** `interpolate_captures` / `_captures_compatible` /
`_interpolate_layer` / `relayout_capture` (`session.py:1783-1844`,
`session.py:1660-1705`, `session.py:1866+`) all work today and all serve A>B
captures.

What the fence buys is that these four never have to learn chains:

1. `_interpolate_layer`'s tween branch lerps `TweenParams` field-wise
   (`session.py:1688-1700`). A list-valued `keys` field would fall through
   `_lerp_value`'s final `return va if t < 0.5 else vb` (`tween.py:122`) —
   i.e. it *steps* rather than crashes, so a chain in a capture degrades
   safely, but "step the whole chain at 0.5" is not a meaningful transition.
2. `_captures_compatible` would need a chain-shape equality rule
   (`session.py:1783-1800`).
3. `relayout_capture`'s batch re-run would need chain-aware source snapshots.
4. The client mirror `interpolateBlocker` (`plot.js:728-741`) would need the
   same rule again, in JS.

So the fence is worth taking — as a guard plus a clear message, not as a
deletion. One nuance the brief's phrasing would over-reach on: **capturing
one frame of a video and interpolating two such captures works today** (
`kind="frame"` + `master_t`, `plot.js:760-763`, `api.py:1228-1241`), and
refusing it would remove working behaviour. See **OPEN QUESTION Q5**.

---

## 2. Open questions (Ian's calls)

### Q1 — chain data model: where does the keyframe list live?

| | Option | Cost | Consequence |
|---|---|---|---|
| a | **`TweenParams.keys: list[str]`** on the existing tween layer; `a`/`b` kept in sync as `keys[0]`/`keys[-1]` for back-compat | ~1 field + F3's ref plumbing | One layer, one effect stack, one pen, one occlusion setting for the whole chain. `sweep` and windows keep working. Old projects load unchanged (`keys` empty ⇒ classic A/B). |
| b | A new `source.type = "chain"` alongside `"tween"` | Duplicates `materialize`, `check_compatible`, the cache path, the cascade, the UI section | Cleaner conceptually; two code paths that must not drift — the exact failure the 2026-07-19 unification round was fought to avoid (`tween.py:336-338`). |
| c | First-class grouping in the layer list (a real parent/child node) | New model in `compose.py` + the layer dock + save format + undo | Best long-term UI story; a whole round on its own, and ROADMAP already parks "keyframe lists vs layer pairs vs named channels" as the real cost (`ROADMAP.md:574-577`). |

**Recommendation: (a).** It is the only one that keeps the promise "no new
resolve semantics" honest, and it answers the brief's "how do occlusion and
effects carry across segments" with *they are the layer's, they always were*.
(c) stays open — (a) does not foreclose it, because a grouping UI could later
present the same `keys` list.

### Q2 — where does `time_curve` apply on a chain?

- **Global** — ease the whole A→D motion; keyframes are just waypoints
  passed through at constant-ish speed. Cheapest: map `u` through the curve
  once, exactly as today.
- **Per segment** — cosine easing at every key means the motion *settles* on
  each keyframe and pushes off again. A genuinely different aesthetic (much
  more "pose-to-pose animation"), and arguably what a keyframe *means*.

**Recommendation: global for the first build**, because it is the literal
generalisation of today's behaviour and needs no new field; note per-segment
as the follow-up dial (`time_curve` gains an `ease_each` option) once there is
a chain on the bench to look at. `cosine_pingpong` on a chain should mean
A→D→A over the whole timeline (global), which the global reading gives free.

### Q3 — does the timeline slider snap, and how do you escape it?

- **a. Always snap** to the frame grid. Perfect cache alignment, but you can
  never look between frames — and "between frames" is where a morph artefact
  usually hides.
- **b. Snap by default, hold a modifier for continuous** (⌥ or ⇧, matching
  `forms.js`'s existing shift-fine-tune idiom from `d74f357`).
- **c. Free scrub, ticks are decoration.** No cache win; today's behaviour
  plus marks.

**Recommendation: (b)**, with the snap being what the arrow keys and the jump
buttons always do. The fine-scrub escape costs one `event.shiftKey` check and
protects against the one thing quantization genuinely loses.

### Q4 — what range does the bar span when `t from` / `t to` ≠ 0 / 1?

The frame grid is `n` samples over `[tFrom, tTo]` (`plot.js:1036-1038`), but
the master timeline is `0..1` and a tween window can sit anywhere in it
(`tween.py:103-110`).

- **a. Bar spans `0..1`**; ticks at the `n` frame positions; the
  `[tFrom, tTo]` sub-range shaded; snapping outside the range uses the same
  step, phase-locked to `tFrom`, so every reachable value still lands on a
  consistent grid.
- **b. Bar spans exactly `[tFrom, tTo]`** — the bar *is* the animation being
  made; anything outside is not part of the output.

**Recommendation: (a).** (b) makes windowed tweens outside the export range
unreachable and silently un-inspectable, which is a debugging trap. (a) costs
a shaded region in the markup.

### Q5 — how hard is the tray-to-tray fence?

- **a. Strict** — refuse interpolation when either capture's snapshot
  contains a chain **or** any `frame_follow` layer. Matches Ian's words
  ("chains and video don't get tray-to-tray") exactly.
- **b. Narrow** — refuse chains; allow video, because a `kind="frame"`
  capture already freezes one clip frame and two of those interpolate
  correctly today (`plot.js:760-763`).

**Recommendation: (b)**, with the refusal message naming the chain layer.
(a) would delete working behaviour to enforce a rule aimed at a feature that
does not exist yet. If Ian wants the harder line anyway it is a one-line
change either way — the guard lives in `_captures_compatible`.

### Q6 — does adding a keyframe to an A/B animation happen in place, or make a new thing?

`animate_layer` produces A/B + tween in one undo step (`session.py:2059-2114`).
For a third key:

- **a. `＋ keyframe` on the tween's Interpolation section**, which duplicates
  the *last* key, names it `▸ C`, hides it, appends to `keys`. Chains grow out
  of the existing Animate flow; there is no separate "make a chain" verb.
- **b. A distinct "Create chain" action** with a keyframe-count field.

**Recommendation: (a).** Ian's ask is "optional A>B>C>D", i.e. the same
animation with more stops — not a second kind of object. One caveat to
decide alongside: duplicating the *last* key means the new key starts
identical to D, so the appended segment is initially static (safe, endpoint
fidelity preserved). Duplicating the *first* would make the tail snap back.
Recommend last.

### Q7 — how much of the Animation panel moves into the bar?

The bar needs at minimum: the scrub, jump-to-ends, and (per the brief) jump
to each checkpoint. The Animation panel additionally has `Live play` / `Frame →`
/ fps / loop (`plot.js:183-189`).

- **a. Bar gets scrub + jumps only.** Play stays in the panel.
- **b. Bar gets the transport too** (play/pause + frame step); the panel keeps
  fps/loop/render/export.
- **c. Bar gets everything, panel loses playback.**

**Recommendation: (b).** Play-while-you-look is the reason the bar is being
moved next to the sheet at all, and it mirrors what already happened to
Pause/Resume/Stop when they left the Plot panel for the status line
(`index.html:190-192`). Keep fps/loop where the other settings are. **Note
the collision with E6** (the render popup work) and see §5.

---

## 2b. Ian's rulings (2026-08-11) — these override the recommendations above

- **Q1 → (a).** `TweenParams.keys` on the existing tween layer.
- **Q2 → per segment** (against the recommendation, deliberately): easing
  applies between each pair of keys, so motion settles at every checkpoint —
  pose-to-pose. Implementation note: apply the curve to each segment's local
  t; a curve that only makes sense over the whole motion (`cosine_pingpong`)
  keeps its global meaning — don't bounce inside a segment.
- **Q3 → (b).** Snap to the frame grid; ⇧ escapes to continuous.
- **Q4 → (a).** Bar spans 0..1, ticks on the grid, the active range shaded.
- **Q5 → refuse chains only** (video keeps tray-blending). AND a clarified
  original intent that AMENDS S7/S8: interpolating two loose sheet captures
  should produce a **sheet group à la P6 that contains copies of the two
  source sheets plus the blends** — Ian's mental model is a 2D frame matrix:
  the video frames in sheet A are the same frames in sheet B; *parameters*
  are what blend across the second axis.
- **Q6 → (a)**, duplicating the previous checkpoint's settings. Plus: a
  right-click menu on a checkpoint with **Copy state / Paste state**
  (whole-checkpoint: generator params, effects, placement). Per-parameter
  copy/paste is deferred to ROADMAP, not built now.
- **Q7 → (a), amended**: the bar gets scrub + jump-to-ends +
  jump-to-checkpoints + **next/previous frame steppers** + **a button that
  opens the render popup**. Play stays in the Animation panel. (S4's Q7(b)
  line below is superseded by this.)
- **Proposals: all ten accepted.** P3 additionally shows a total across all
  sheets. P6 additionally groups sheets born from one animation setup,
  visually distinct from standalone sheets. P10 additionally: while the
  popup renders a sequence, the most recently finished frame stays on
  screen (this part belongs to E6).

---

## 2c. Ian's second rulings (2026-08-11, after the first bench check)

Popup (bench findings): opens from ANY tab (top-level overlay, not
Plot-tab DOM); resolution change triggers a re-render and the label states
the actual on-screen resolution; fps moves INTO the popup; pan must
compensate for zoom scale (currently finicky). ffmpeg becomes a declared
dependency: detection must search well-known locations
(/opt/homebrew/bin, /usr/local/bin) because a Finder-launched app bundle
does not inherit the brew PATH — Ian HAS ffmpeg and the app said he
didn't; that is the bug. Launch script brew-installs when genuinely
absent; UI states status plainly. No embedded binary.

Baking crop: crop mode = **timeline** (default — ONE bbox unioned across
all frames, so relative motion between frames is preserved) or **full
frame** (no crop, negative space kept, always within page bounds). NO
per-frame mode — today's per-frame recentering kills motion and is ruled
out entirely.

Trays: stay FROZEN. The "dynamic tray" feeling comes from the live
project instead: (7a) an always-visible label saying what the canvas
shows — live · sheet n/N vs tray "name" · sheet n/N; (8a) the live sheet
view is STICKY — a param edit re-renders the sheet view in place instead
of dropping to single-frame (the caches make this affordable); (9a) every
frozen tray gains a one-click "re-bake from live". A stored auto-
refreshing tray and "project starts in a tray" are PARKED, not planned.

Sheet grid: replace the 1/2/4/8/16 presets with rows × columns + a
**Bake sheet** button that auto-decides frame orientation (rotate if the
cell aspect fits better) and, when frames exceed cells, produces
⌈frames/cells⌉ sheets straight into a tray. Plot targets the currently
selected tray (one selection, one target, what you see is what plots).

Plot flow (ruled 2026-08-11, after the tray round): **▶ Plot obeys the
view label** — it plots exactly what the canvas shows (live frame, live
sheet, or selected tray sheet); the label is the contract. Multi-pen
plots run as a **guided pass queue**: one press starts pass 1, the status
line reports "pass k/N — <pen>", and between passes the machine holds
with "swap to <pen>, then continue". The tray's per-pass buttons stay as
the out-of-order escape hatch; the all/layer/pen target picker applies
only to the plain live view and greys out on sheet/tray views ("sheet
passes carry their pens"). Known trade, accepted: Plot means
"what's on screen", not "the live project" — the adjacent view label is
the mitigation.

---

## 3. Proposals — animation & staging UX

Cheap-to-veto bullets. Each names the friction it fixes and cites the code.
Ian: strike whatever does not earn its keep.

**P1 — disambiguate the two transports.** `▶ Animate plot` (status line,
`index.html:207-210`) replays the *planned job*; the new bar's play scrubs the
*master timeline*. Same icon, ~40 px apart, completely different meanings.
Cheapest fix: the bar's control is labelled with the frame counter
(`▶ 3/24`), the plot one keeps its words. Consider moving `▶ Animate plot`
back out of the corner if they read as a pair.

**P2 — warn when the frame grid can't see a tween.** A `follow_master` tween
whose window is narrower than one frame step
(`(tTo-tFrom)/(n-1)`) can be skipped entirely by every output — the export,
the sheets and the popup all sample the same grid. One hint line under the
frame count ("2 tweens are narrower than one frame — raise frames to ≥ 40")
turns a mystifying blank sheet into a number to change.

**P3 — the layout summary should say what a *sheet* costs, not just how many.**
`renderLayoutSummary` (`plot.js:1004-1018`) reports frames → sheets → passes.
The estimate for the current page already exists (`/api/plan` with a
`sheet=` spec, `api.py:972-1000`). Appending "· ~8 min" to that line makes
"is this a 20-sheet evening?" answerable before pressing anything.

**P4 — rehome the "nothing follows the timeline yet" hint.** Once the bar's
visibility becomes the strict predicate (F5), the hint's own panel is gone by
definition when the hint would fire (`compose.js:191-192`). It should become
an empty-state on the tween layer's Timeline fold (`compose.js:1474-1481`),
where the checkbox it is talking about actually is.

**P5 — `Reset` should mean "back to where I started", not "back to zero".**
`plot.js:429-435` zeroes `i/sheet/pass`. Once a start-sheet exists (S6),
Reset returning to sheet 0 mid-way through a from-sheet-7 run is a
paper-costing surprise. Reset to the chosen start; a separate `⤒ 1` for the
true beginning.

**P6 — mark staged sheets plotted this session.** `renderStaging`
(`plot.js:924-949`) renders every sheet's buttons identically, so after a
pen swap there is no way to tell which of eleven sheets is next. A
client-side `Set` of `(group, sheet, pass)` fired on `plotStaged`
(`plot.js:813-818`) plus a dim/✓ treatment. No persistence — matches Ian's
"no persistence across project close needed".

**P7 — the tray's A/B pickers and the toolbar's `A · B · ⇄` are two UIs for
one feature.** `ab` (`plot.js:591-637`, quick capture, deletes the superseded
group) and `stage-a`/`stage-b` (`plot.js:905-918`, pick any two existing
groups) both end at `POST /api/staging/interpolate`. That is defensible —
quick vs deliberate — but nothing on screen says so. One line of copy under
the pickers ("or use A · B · ⇄ in the toolbar to capture and blend in one
pass") costs nothing.

**P8 — `interpolateBlocker`'s reasons are good; show them before the click.**
It already computes a precise human reason (`plot.js:728-741`) and puts it
in the button's `title` (`plot.js:743-752`). A `title` is invisible on the
way past. Render it as the hint line under the row when non-null.

**P9 — capture names carry the layout; the tray list doesn't show it.**
`captureStaged` names sheet captures `"24f · 4×2 · fixed"` (`plot.js:773`)
and `pickerLabel` shows the shape in the A/B dropdowns (`plot.js:719-723`),
but `renderStaging`'s group header shows only name + kind + sheet count
(`plot.js:926-935`) while `groupLabel` — which *does* build the richer label
(`plot.js:711-716`) — appears unused in the list. Use it.

**P10 — the render popup and the timeline bar should not both own "which
frame".** The popup keeps its own index (`anim.popupI`, `plot.js:1207-1216`)
over its own rendered set, deliberately decoupled from the live scrub. That
is right while it is a modal. If E6's mp4/gif work makes it more of a viewer,
the honest wiring is: closing the popup leaves the master timeline on the
frame that was on screen. One line in `closeRasterPreview`
(`plot.js:1242-1252`). Flagging only — E6 owns that file region.

---

## 4. Build order

Slices are sized for one agent run each, with the file set they touch so an
orchestrator can parallelise safely. Dependencies are hard unless stated.

### S1 — ref plumbing + one window-mapping helper (backend, no behaviour change) — **SHIPPED** `46ecbfe`

Groundwork. Nothing user-visible.

- Generalise `Session._tween_refs` to return **all** refs; update the five
  call sites in F3's table, including the cache key at `session.py:2292`.
- Extract the window+curve mapping that is currently written twice
  (`session.py:2275-2286` and `tween.py:331-348`) into one helper in
  `tween.py`, used by both. The duplication is already flagged in-code as a
  drift hazard ("the 2026-07-19 unification lesson", `tween.py:336-338`);
  a chain would make it a third copy.
- Generalise `_animation_keyframes_for`'s `" ▸ A"/" ▸ B"` test
  (`session.py:797`) to a suffix pattern.

*Files:* `axibridge/tween.py`, `axibridge/session.py`.
*Tests:* whole suite green unchanged; add a case pinning that a 2-ref tween's
cache key and cascade behaviour are identical before/after
(`tests/test_tween.py`, `tests/test_scrub_caches.py`).

### S2 — chain data model + materialisation (backend) — **SHIPPED** `b071eb6`

Depends on S1. The core.

- `TweenParams.keys: list[str] = []` (empty ⇒ classic A/B; otherwise `a` and
  `b` are maintained as `keys[0]` / `keys[-1]`). Bound the length (≤ 24 is
  plenty; unbounded lists reach an open-loop machine's resolve budget).
- `materialize`: build the list of global `u` values exactly as today
  (`[override_u]`, or the sweep ladder `i/(sweep+1)`), then map each `u` to
  `(segment, local t)` with isometric spacing and call the existing pair
  machinery. 2 keys must be **byte-identical** to today.
- `effective_generator`: chain branch reducing to the active segment pair, so
  a chain can still be an endpoint of another tween (`tween.py:351-392`).
- `check_compatible` over consecutive pairs, with the failing pair named.
- Session methods (each one `_checkpoint()` under `_lock`, no coalescing —
  these are discrete acts): `add_chain_keyframe(layer_id)` (duplicates the
  last key per Q6, hides it, names it `▸ C`…), `remove_chain_keyframe`,
  `reorder_chain_keyframes`.
- API: `PUT /api/layers/{id}/tween` already merges arbitrary values through
  `TweenParams` validation (`api.py:809-813`, `session.py:949-958`) — so
  `keys` rides that; add explicit endpoints only for add/remove (they create
  layers).

*Files:* `axibridge/tween.py`, `axibridge/session.py`, `axibridge/api.py`.
*Tests* (new `tests/test_chain.py` or extend `test_tween.py`):
- a 2-key chain resolves byte-identical to today's A/B tween at 11 sample `t`s;
- **endpoint fidelity at every key**: `master_t = k/(N-1)` reproduces key `k`
  exactly, for N = 3, 4, 5;
- outside the chain's own window, hold key 0 / key N−1 (window semantics
  preserved at the outer level);
- `sweep = 3` on a 4-key chain stamps 3 copies at fixed positions and a scrub
  does not move them;
- cascade-delete a mid keyframe → the chain goes too; delete the chain
  directly → key 0 is restored (un-animate) and the rest sweep;
- save/load round-trip preserves `keys` (`tests/test_save_roundtrip.py`);
- a mid-key edit invalidates the tween cache (extend
  `tests/test_scrub_caches.py`).

### S3 — chain UI in the layer detail (frontend) — **SHIPPED** `14006a1`

Depends on S2's API. **Sequence with E5** — same DOM region.

- Replace `edit A` / `edit B` (`compose.js:1500-1512`) with a keyframe list
  for chains: select / add / remove / reorder, with the classic two-button
  form kept when `keys` is empty.
- Delete `keys` from the auto-rendered schema like `a`/`b` already are
  (`compose.js:1517-1523`) — otherwise `forms.js` will try to render a list.
- Extend `jumpTimelineToKeyframe` (`compose.js:149-172`) to map key `k` →
  `k/(N-1)` mapped through the chain's window; keep the `cosine_pingpong`
  abstention.

*Files:* `axibridge/static/js/compose.js`.
*Tests:* acceptance (`tests/test_acceptance_ui.py`) — animate a layer, add a
keyframe, assert three keyframe entries and that selecting the third moves
the timeline readout. Assert what the user sees, never how it is built.

### S4 — the timeline bar (frontend, structural) — **SHIPPED** `086c365`

Independent of S1–S3 (works with today's A/B tweens; gains checkpoint jumps
once S2/S3 land).

- New markup between `#canvas-wrap` and `#canvas-status` (`index.html:163-181`).
- New `axibridge/static/js/timeline.js` owning the bar; move the scrub object
  (`compose.js:118-147`) into it, keep its no-PATCH discipline verbatim.
- Remove `#timeline-panel` from the Compose tab (`compose.js:261-271`,
  `compose.js:397-411`); `renderTimeline`'s predicate becomes the strict
  `hasFollow` (`compose.js:188-190`); rehome the hint per P4.
- Jump buttons at both ends; per-checkpoint buttons when the project has a
  chain.
- ~~Per Q7(b), play/pause + frame-step in the bar, driving `plot.js`'s existing
  `previewScrub` (`plot.js:1090-1122`) — do **not** re-implement playback.~~
  **Superseded by §2b's Q7 → (a), amended**: the bar got frame steppers,
  checkpoint jumps and a popup button; **play stayed in the Animation panel**.
  The "don't re-implement playback" half still held — the bar's steppers move
  `master-t`, they do not run a loop.

*Files:* `axibridge/static/index.html`, `static/js/timeline.js` (new),
`static/js/compose.js`, `static/js/main.js`, `static/css/style.css`, plus a
small named export from `static/js/plot.js`.
*Tests:* acceptance — bar absent on a fresh static project; present after
`⏱ Animate`; dragging it changes the rendered geometry; it never fires a
project PATCH (assert the project's `updated`/params are unchanged after a
scrub).

### S5 — frame-grid quantization + cached-frame ticks (frontend) — **SHIPPED** `5529abd`

Depends on S4.

- `plot.js` exports `frameGrid()` → `{n, tFrom, tTo}` (F6); the bar snaps per
  Q3(b) and spans per Q4(a).
- Ticks at each grid position; a filled tick for frames fetched **this
  session**. Record on completion in the three places that already know their
  `t`: the bar's own scrub, `previewScrub._run` (`plot.js:1105-1121`), and
  `renderRasterPreview`'s loop (`plot.js:1273-1291`).
- Invalidate the fetched set on any project mutation (conservative: clear on
  the next `refreshProject` following a mutating call). Document in a comment
  that this is a hint, not a guarantee — the server's caches evict randomly
  under a point budget (`session.py:62-68`, `gencache.py:17-21`).
- Arrow keys step one frame; ⇧+drag (or ⌥) escapes to continuous.

*Files:* `static/js/timeline.js`, `static/js/plot.js` (accessor + tick
recording only), `static/js/main.js`.
*Tests:* a unit-ish JS-free check is awkward here; assert via acceptance that
the readout lands on the grid values (`t = 0.143` for frame 2 of 8) and that
arrow-key stepping matches the panel's `Frame →`.

### S6 — start from sheet N (frontend, small, fully parallel) — **SHIPPED** `14006a1`

Independent of everything above.

- In the stepper row (`plot.js:203-211` markup — the `Plot stepper` fold —
  and `plot.js:1318-1351` render):
  a `sheet [ n ] of N` number input + `Start here`, setting `anim.sheet`,
  zeroing `anim.pass`, then `refreshSheetInfo()` + `syncSheetPlan()` — the
  two calls `stepSheetPass` already makes (`plot.js:1026-1030`).
- Same affordance for the single-frame stepper (`frame [ i ] of n`).
- P5's Reset change; P6's plotted-this-session marks in `renderStaging`.

*Files:* `axibridge/static/js/plot.js`.
*Tests:* acceptance — set the sheet box to 3, assert the label reads
`sheet 3/…` and the canvas preview banner names sheet 3
(`sheetPreviewLabel`, `plot.js:698-700`).

### S7 — the tray A>B fence (backend + client mirror) — **SHIPPED** `e1dee75`

Depends on S2 (needs a chain to refuse).

- `_captures_compatible` (`session.py:1783-1800`) refuses per Q5, naming the
  offending layer.
- Mirror in `interpolateBlocker` (`plot.js:728-741`) so the ⇄ button explains
  itself before the click (and P8 renders it).

*Files:* `axibridge/session.py`, `static/js/plot.js`, `tests/test_staging.py`.
*Tests:* a chain-bearing capture pair is refused with a message naming the
layer; an A/B pair and (per Q5b) a video frame pair still interpolate.

### S8 — approved UX proposals — **SHIPPED** `14006a1`, `30e7043`, `e1dee75`

Whatever survives §3, itemised then. Keep as separate small commits.
(All ten were accepted; the per-proposal landing is in §6's table.)

### Parallel-safety map

| Slice | `tween.py` | `session.py` | `api.py` | `compose.js` | `plot.js` | `index.html` | new |
|---|---|---|---|---|---|---|---|
| S1 | ✓ | ✓ | | | | | |
| S2 | ✓ | ✓ | ✓ | | | | |
| S3 | | | | ✓ | | | |
| S4 | | | | ✓ | small export | ✓ | `timeline.js` |
| S5 | | | | | accessor + ticks | | ✓ |
| S6 | | | | | ✓ | | |
| S7 | | ✓ | | | ✓ | | |

Safe concurrency: **S1→S2 sequential**; **S4 concurrent with S1/S2**;
**S6 concurrent with everything**; S3 after S2 and sequenced against E5;
S5 after S4; S7 after S2.

## 5. Known collisions with the concurrent batch

(F6 and Q7 both point here; it was an unnumbered block until the closing pass
gave it its heading.)

- **E5** (keyframe sublayer UX) and **S3** both edit the tween section of
  `compose.js` (`compose.js:1452-1598`). Sequence them; do not run both.
- **E6** (render popup: palindrome, hi-res, mp4/gif) owns
  `plot.js:1139-1316`. S4/S5 must touch `plot.js` **only** at
  `pullAnimControls`/`animT` (`plot.js:1036-1055`) and `previewScrub`
  (`plot.js:1090-1122`), plus one added export. This is why F6 recommends an
  accessor rather than hoisting `anim` into `S` — the hoist would rewrite
  every line E6 is editing.
- **E4** (live generator preview) touches `compose.js`'s generator section,
  not the tween section. No conflict expected.

---

## 6. Closing ledger (2026-08-11) — what shipped, what changed, what stayed open

Written at the end of the round the doc specified, so this file reads as a
complete record without the conversation around it. Everything below landed on
`main` between `4cebea7` and `e1dee75`; the suite went 843 → **947 passed**.
Nothing in the round has had Ian's eyes or a real AxiDraw on it — see
"Deliberately open" and `CHECKME.md`'s 2026-08-11 section.

### 6a. Build order

| Slice | Commit | Landed as specified? |
|---|---|---|
| S1 ref plumbing | `46ecbfe` | Yes. `_tween_refs` returns an ordered list; the window/curve math composes as `map_time_curve(map_window(…))` in one place — deliberately kept as **two** steps so per-segment easing could slot in at S2 without a third extraction. Zero behaviour change, pinned by a test that reproduces the pre-refactor cache-key formula byte-for-byte. |
| S2 chain model | `b071eb6` | Yes, plus one finding: the endpoint snap is load-bearing beyond fidelity. `lerp_params` gates seed reproduction on an **exact** 0/1, so un-snapped float error at `k/(N-1)` would have rolled per-frame seeds silently. A chain that shrinks back to two keys normalises to `keys=[]`, so an older build still reads the project. 39 new tests. |
| S3 chain UI | `14006a1` | Yes. Numbered keyframe list, drag to reorder, ✕ refuses at two keys, `＋ keyframe` is how chains are born, right-click Copy/Paste state. Known wart, noted rather than hacked around: a same-generator paste lands params+effects+transform as **two** undo entries. |
| S4 timeline bar | `086c365` | Yes, minus the Q7(b) play button (superseded — see 6c). `static/js/timeline.js` is new and owns the bar; the scrub object moved **verbatim** from `compose.js` with its no-PATCH discipline intact. Hidden = zero height, canvas top unmoved. |
| S5 quantization | `5529abd` | Yes. `frameGrid()` is the accessor F6 argued for; snapping is phase-locked beyond `[tFrom,tTo]` per Q4(a); ⇧ escapes; ticks brighten once a frame is fetched **this session** and clear on `refreshProject`. The comment says out loud that a tick is a hint, not a guarantee — the server evicts under a point budget. |
| S6 start from sheet N | `14006a1` | Yes, with P5's Reset change and P6's marks in the same commit. |
| S7 tray fence | `e1dee75` | Yes, at Q5's **narrow** reading: chains are refused **by name**, video pairs keep blending. The wiring detail worth keeping: the refusal needs a `has_chain` stamp recorded at capture-store time, because snapshots never ride the wire to the client. |
| S8 proposals | `14006a1`, `30e7043`, `e1dee75` | All ten, see 6b. |

### 6b. Proposals P1–P10 — all ten accepted, all ten landed

| | Landed as | Commit |
|---|---|---|
| P1 | A truthful tooltip on `▶ Animate plot` rather than the proposed `▶ 3/24` counter — it is the app's only other `▶`, and words disambiguate better than a number. | `e1dee75` |
| P2 | A hint naming **how many frames** would make a narrow tween visible. | `e1dee75` |
| P3 | Layout summary prices this sheet **and** the whole run (§2b's addition). | `e1dee75` |
| P4 | The "nothing follows the timeline yet" hint rehomed onto the tween's own Timeline fold when `#timeline-panel` left the Compose tab. | `086c365` |
| P5 | Reset returns to the chosen start, tooltip says so, separate `⤒ 1` for the true beginning. | `14006a1` |
| P6 | Staged passes plotted this session strike through (client-side, no persistence). | `14006a1` |
| P7 | Cross-reference hint under the tray's A/B pickers. | `30e7043` |
| P8 | `interpolateBlocker`'s reason renders under the ⇄ row instead of hiding in a `title`. | `e1dee75` |
| P9 | Delivered en passant with S6 — the richer `groupLabel` is used in the tray list, and animation-born sheet groups carry an ochre edge (§2b's P6 addition). | `14006a1` |
| P10 | Closing the popup leaves the master timeline on the frame that was on screen. | `e1dee75` |

### 6c. Rulings §2b / §2c / plot-flow — and the two supersessions

- **Q1 (a)** `TweenParams.keys` — shipped, ≤ 24 keys, `a`/`b` maintained as the
  ends. **Q2 per-segment easing** — shipped, with globally-meaningful curves
  (`cosine_pingpong`) held global via a named frozenset rather than a special
  case at the call site. **Q3 (b)**, **Q4 (a)**, **Q5 narrow**, **Q6 (a)** —
  all shipped as ruled.
- **Q7 → (a), amended, supersedes S4's Q7(b) bullet.** The bar carries scrub,
  jump-to-ends, checkpoint jumps, frame steppers and a Render-popup button;
  **play stayed in the Animation panel**. S4's bullet is struck in place above.
- **The framing → crop rename** (`7f2e2e8`) is the round's other supersession,
  and it reaches past this doc. `framing = center | fixed` became
  `crop = timeline | full`: `timeline` is the old `fixed` (ONE bbox unioned
  across all frames, so relative motion is preserved), `full` keeps the page
  rect and its negative space, and the per-frame `center` mode — which
  *cancelled* pure-translation animation, and had been documented as a feature
  in ROADMAP's "Sheets workflow v2" since 2026-07-10 — is **deleted**, not
  renamed. Legacy formats load through `_crop_from_format` (either key;
  `center` maps to `timeline`). Two things went with it: the 1/2/4/8/16
  presets left the UI (rows×cols already covered them), and the
  grid-orientation rule generalised from a hardcoded shape lookup to
  "whichever of upright/rotated achieves the larger scale". `Capture to tray`
  is now `Bake sheet` — it always was the bake. Any earlier text in this file
  that says `fixed` (P9's `"24f · 4×2 · fixed"` capture name, for one) predates
  the rename.
- **Trays stay frozen** (§2c): the view label, the sticky live sheet view and
  ↻ re-bake-from-live shipped in `30e7043`. Re-bake is one checkpointed
  `Session` act re-running the group's own format against live state under the
  **same group id**, so undo restores the old bake byte-for-byte; batch groups
  refuse with a visible reason.
- **Plot flow** (`f030acd`): `▶ Plot` routes off `S.docPreview` — the same
  state the view label prints — so what you see is what plots. Multi-pen
  sheets run as a client-side queue over the existing per-pass calls; Stop
  stays live during a hold so a half-run can be abandoned; zero passes refuses
  out loud rather than silently falling back to the live project. Seven
  acceptance tests assert the actual `/api/plot/start` bodies. **This is a
  semantic change** — Plot used to mean "the live canvas" unconditionally.

### 6d. Deliberately open

Not oversights. Each is either waiting on a bench/hardware look or was parked
by ruling.

1. **Hardware pass on the multi-pen pen-swap queue.** Simulator and headless
   only. The two questions a real machine answers: does the hold keep pen
   state correctly mid-job, and does Stop actually clear the queue rather than
   leave it primed for a phantom continue. Tracked in `HANDOFF.md`.
2. **Held-queue-survives-view-change is a deliberate choice, not a settled
   one.** Changing the view during a hold does not drop the queue. That is the
   plot-flow ruling's "what you see is what plots" taken literally, and it is
   exactly the kind of call that wants one real "did that surprise me" at the
   bench before it hardens.
3. **`＋ keyframe`: should the timeline jump to the new key?** It duplicates
   the previous checkpoint (Q6), so the new key is initially identical to its
   neighbour and jumping there shows no change — which is an argument both
   ways. Left as-is (no jump) pending a bench opinion.
4. **Per-parameter copy/paste between checkpoints** — ruled deferred in §2b's
   Q6 and now carried in ROADMAP ("Deferred — per-parameter copy/paste between
   chain checkpoints") with the revisit criterion. Whole-checkpoint Copy/Paste
   is what shipped.
5. **Dynamic (auto-refreshing) trays and "project starts in a tray"** — parked
   by §2c, not planned. The sticky live sheet view is the affordance that was
   meant to remove most of the wanting.
6. **Q1(c), first-class layer grouping**, remains open exactly as argued: (a)
   does not foreclose it, because a grouping UI can present the same `keys`
   list later. ROADMAP's "keyframe lists vs layer pairs vs named channels" note
   is annotated accordingly rather than closed.
7. **F4's consequence stands unaddressed on purpose**: a chain over
   *non-generator* sources takes the structural/pointwise route and therefore
   gets **no clip advance**. Existing behaviour, not a regression, and the
   answer to "why did my video chain freeze".

---

## Appendix A — the probe that killed the sugar hypothesis

Run against a real `Session` with `AXIBRIDGE_CONFIG_DIR` pointed at a temp
dir (the `conftest.py` discipline). Three hidden `rectangle` keyframes at
width 20 / 60 / 100 mm, two visible `follow_master` tween layers with windows
`[0, 0.5]` and `[0.5, 1]`, resolved at five master values. Widths are read off
the resolved geometry's bbox (the default placement transform rotates the
scene, so the rectangle's `width` shows up on the y extent).

```
t=0.00  seg0 w=20   seg1 w=60
t=0.25  seg0 w=40   seg1 w=60
t=0.50  seg0 w=60   seg1 w=60
t=0.75  seg0 w=60   seg1 w=80
t=1.00  seg0 w=60   seg1 w=100
```

Both layers resolve to one path each at every value — i.e. both draw, always.
`tween.materialize` called directly with the same window-mapped `t` gives the
identical numbers, confirming the behaviour is in the tween, not in the
session's overlay bookkeeping.
