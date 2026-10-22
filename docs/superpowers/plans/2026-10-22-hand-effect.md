# Hand Effect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new effect, "Hand", that redraws any line with one of Ian's frozen Gesture Studies hands: it follows the line, strays within a knob, bends at its own scale, and can be told to wander.

**Architecture:** A pure numpy engine (`axibridge/effects/_hand/engine.py`) offsets a lightly smoothed copy of the input sideways by a lateral signal derived from the chosen hand's own turning (its high-passed heading, integrated), squashed into a soft band with an exact hard ceiling. The effect module (`axibridge/effects/hand.py`) wraps it with bounded params, per-path seeds, closure/`filled` preservation, and a pinned library hash. Hands are read only through `sources/_gesture_studies/frozen_library.py`; the frozen kit is not edited.

**Tech Stack:** Python 3 / Pydantic v2 / numpy / scipy (already dependencies); vanilla ES modules (forms.js) built by Vite; pytest + Playwright.

**Spec:** `docs/superpowers/specs/2026-10-22-pen-fill-hand-design.md` — part C, Settled 3 and 5, and "C, settled with Ian before planning".

## Global Constraints

- One input path in → one continuous path out; never a lift. A closed input stays closed (first == last exactly) and keeps `filled`; an open input keeps its exact end points.
- All 44 library hands are offered as they are (near-retraces allowed).
- Stray is a soft band with a hard ceiling: default mode typical deviation within `stray`, never beyond `2 × stray`; "let it wander" widens the band to `3 × stray` and the ceiling to `5 × stray`. Deviation = distance from the output point to the nearest point of the INPUT polyline.
- Two equal main knobs: `stray_mm` and `bend_mm`. Corners round a little, always within the ceiling.
- Effect contract (`tests/test_effect_contract.py`, `docs/MODULES.md` effects section): pure, deterministic, filled ⇒ closed, every numeric field bounded; seed from `ctx.seed` + the effect's `seed`, never layer_id; never raise on a stored project (an unknown/withdrawn hand passes the path through unchanged and logs once).
- Read hands only through `frozen_library` (`FrozenLibrary`, `FL.options`); never read `tools/`, `.local/`, or call `kit/library.local_path()`; never edit files under `sources/_gesture_studies/kit/` (sha256-checked).
- Kept layers pin the hand's 12-hex hash and keep it across refreezes (as Gesture Studies does); presets never carry the pin.
- Tests never touch port 2942; UI tests need `npm run build` first. No wall-clock asserts in tests (they run on the Pi too).

## Review Focus

1. A tiny or degenerate input (single point, 2 points, a path shorter than one step, coincident points) — returned unchanged (copy, same `filled`), never NaN. Test in Task 1 (and the registry contract test covers the dot).
2. A closed filled shape with sharp corners (square) at a large stray — output stays closed, `filled` kept, every point within the ceiling of the input outline. Test in Task 1.
3. A hand id stored in a project that the current library no longer has — resolve passes the line through unchanged, no exception. Test in Task 3.
4. Tweening between two layers whose hand effect differs only in `stray_mm` — morphs (numbers lerp), the pin string steps. Test in Task 3.
5. Very long dense input (a sketch-fitted path of ~2 m) — finishes in well under a second on the Mac (reported, not asserted). Task 1 report.

---

### Task 1: The follow engine

**Files:**
- Create: `axibridge/effects/_hand/__init__.py`, `axibridge/effects/_hand/engine.py`
- Test: `tests/test_hand_engine.py`

**Interfaces:**
- Produces: `follow(points: np.ndarray, closed: bool, grammar, rng: np.random.Generator, stray_mm: float, bend_mm: float, wander: bool, step: float = 0.3) -> np.ndarray` (shape (M, 2); closed → last row equals first exactly; open → first/last rows equal the input's exactly). `load_hand(hand_id: str, pin_hash: str | None) -> grammar | None` (None when the id is unknown; uses `FrozenLibrary`, cached by the library's own cache). `MODES = {"follow": (0.6, 2.0, 1.5), "wander": (1.8, 5.0, 4.0)}` — (typical-band factor, ceiling factor, high-pass cutoff in units of `bend_mm`).

- [ ] **Step 1: Write failing tests** (`tests/test_hand_engine.py`; use 3 hands that exist: `matisse`, `river_meander`, `dance_staccato`; fixtures: open S-curve 400 mm, closed square 80 mm, open zigzag with 90° corners):
  - `test_never_beyond_ceiling`: for each hand × seeds 0..4 × fixtures × stray ∈ {1, 5, 20} × wander ∈ {False, True}: max distance from output to the densely resampled input polyline ≤ ceiling × stray + 1e-6.
  - `test_typical_deviation_tracks_stray`: median deviation at stray 10 > median at stray 2 (same hand/seed/fixture), and median ≤ stray in follow mode.
  - `test_bend_size_changes_scale`: count sign changes of the signed lateral offset along the S-curve; at bend_mm 5 > at bend_mm 60.
  - `test_wander_departs_further`: median deviation wander > follow at the same stray/seed.
  - `test_ends_and_closure`: open → output[0] == input[0] and output[-1] == input[-1] exactly; closed → output[0] == output[-1] exactly.
  - `test_deterministic_and_finite`: same rng seed → identical arrays; all finite.
  - `test_degenerate_inputs_pass_through`: 1 point, 2 coincident points, a 0.1 mm segment → returned equal to the input.
  - `test_unknown_hand_loads_none`: `load_hand("no_such_hand", None) is None`.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_hand_engine.py` → FAIL (module missing).
- [ ] **Step 3: Implement.** Algorithm (the parts the tests don't determine):
  1. Resample the input at `step` by arc length (closed: include the closing segment). Fewer than 3 samples or length < 2·step → return the input unchanged.
  2. Base line = Gaussian smoothing of the resampled input with σ = 0.5·stray_mm (in samples: σ/step), periodic when closed, ends pinned when open (smooth, then blend the first/last 3σ back to the original with a smoothstep) — this is the "corners round a little".
  3. Hand stream: `gm.generate_tokens(g, rng, length=L / bend_mm, ...)` then `gm.tokens_to_points(toks, bend_mm, (0,0), 0.0, step)` (find the exact kit signatures in `sources/_gesture_studies/kit/_research/grammar.py` near :1110 and :1183, and how `grammar.restyle` near :2205 calls them — mirror its arguments). Take the stream's heading θ(s), resampled onto the input's N samples by arc-length fraction.
  4. High-pass: θ_hp = θ − gaussian(θ, σ = cutoff·bend_mm) (unwrap θ first; periodic filter when closed).
  5. Lateral offset d = cumulative ∫ sin(θ_hp) ds; remove slow drift d −= gaussian(d, 2·cutoff·bend_mm).
  6. Scale to the band: d ·= band·stray_mm / max(rms(d), 1e-9); squash: d = C·tanh(d / C) with C = ceiling·stray_mm.
  7. Ends: open → multiply d by a smoothstep taper over min(L/4, 3·bend_mm) at each end; closed → subtract the linear ramp (d[-1] − d[0])·s/L so the seam meets.
  8. Output = base + unit normal(base) · d.
  9. Hard guarantee: build a `scipy.spatial.cKDTree` over the input resampled at step/2; any output point farther than C from it is pulled along the line to its nearest input point until exactly C away.
  10. Closed → append output[0]; open → set output[0], output[-1] to the input's exact end points.
  Call `render_work.checkpoint()` once per path if the engine loops (see `docs/MODULES.md` "long loops").
- [ ] **Step 4: Run** the test file → PASS. Time `follow` on a 2 m S-curve for 3 hands and put the numbers in the report.
- [ ] **Step 5: Commit** `feat(hand): an engine that lets a library hand follow a line`.

### Task 2: The Hand effect

**Files:**
- Create: `axibridge/effects/hand.py`
- Modify: `axibridge/registry.py` only if the library category must be registered there (`_EFFECT_LIBRARY_CATEGORIES`, category "line" like `freehand`)
- Test: `tests/test_hand_effect.py`

**Interfaces:**
- Consumes: Task 1 `follow`, `load_hand`, `MODES`.
- Produces: effect id `"hand"`, `HandEffect.Params` fields: `hand: str = "matisse"` (pattern `^[a-z0-9_]{1,64}$`, `json_schema_extra={"format": "library-hand"}`, title "Hand"), `stray_mm: float = 3.0` (0.1..30, title "Stray (mm)"), `bend_mm: float = 20.0` (1..200, title "Bend size (mm)"), `wander: bool = False` (title "Let it wander"), `seed: int = 0` (0..99999, group "Fine tuning"), `step: float = 0.3` (0.1..2, group "Fine tuning"), `pin: str | None = None` (pattern `^[a-z0-9_]{1,64}@[0-9a-f]{12}$`, `json_schema_extra={"hidden": True}`).

- [ ] **Step 1: Write failing tests:** effect registered; on a filled closed square → one path, closed, `filled` True; on two subpaths → each gets a different seed (outputs differ for identical inputs placed apart); `seed` and `ctx.seed` both change the output; unknown `hand` → paths returned unchanged (equal points) and no exception; the registry-wide `tests/test_effect_contract.py` passes with `hand` registered (run it).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** mirroring `axibridge/effects/freehand.py` (seed derivation `base_seed = (params.seed*31 + ctx.seed) & 0x7FFFFFFF`, per path `np.random.default_rng([base_seed, idx])`; return `Path(points=..., filled=path.filled)`). `pin` (if present and its id equals `hand`) selects the pinned hash; otherwise the current snapshot.
- [ ] **Step 4: Run** `tests/test_hand_effect.py tests/test_effect_contract.py tests/test_freehand.py` → PASS.
- [ ] **Step 5: Commit** `feat(hand): the Hand effect`.

### Task 3: Pinning, presets, labels in the form

**Files:**
- Modify: `axibridge/registry.py` (optional `EffectModule.complete_params(params: dict) -> dict`, default identity), `axibridge/session.py` (call it wherever an effect step is added or its params change — find the single place effects are written, near `update_layer` ~:942-975, and the add-effect path), `axibridge/registry.py` `_PRESET_EXCLUSIONS` (`("effect", "hand"): ("pin",)`), `axibridge/effects/hand.py` (`complete_params`: set `pin = f"{hand}@{hash}"` from the current snapshot when `pin` is missing or its id ≠ `hand`), `axibridge/static/js/forms.js` (`format: "library-hand"` → a `<select>` of `{id, label}` from the existing gesture-studies options endpoint for kind `hand` — find it in `gesture_studies_api.py` ~:51; fetch once and cache; show labels, store ids)
- Test: `tests/test_hand_effect.py` (backend), `tests/test_hand_effect_ui.py` (UI)

- [ ] **Step 1: Write failing tests:**
  - `test_adding_hand_effect_pins_current_hash` (through the API the UI uses to add/patch effects): stored params gain `pin == "<hand>@<12 hex>"` matching `FL.options("hand")`.
  - `test_changing_hand_repins`: patch `hand` to another id → `pin` follows.
  - `test_pinned_hash_survives_snapshot_change`: monkeypatch the current snapshot's hash for that hand to a different value → resolve still loads the pinned entry (assert via `load_hand` call args or identical output to before).
  - `test_withdrawn_hand_passes_through`: a project whose step has `hand: "gone_hand"`, `pin: "gone_hand@0123456789ab"` resolves; the layer's paths equal the effect's input.
  - `test_presets_exclude_pin`: saving a starting-settings preset of a layer with the hand effect omits `pin`.
  - `test_tween_of_stray_morphs`: two layers identical but `stray_mm` 2 vs 10 → the tween at t=0.5 resolves with `stray_mm` 6 (inspect the blended params or the deviation lies between).
  - UI `test_hand_dropdown_shows_labels`: add the Hand effect to a pen layer in the UI; the Hand select's visible option text is a label (e.g. contains a space or capital) while its value is an id; choosing another hand changes the resolved ink.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** the new tests + `tests/test_module_library*.py tests/test_tween.py tests/test_effect_contract.py`, `npm run typecheck` → PASS.
- [ ] **Step 5: Commit** `feat(hand): kept layers pin the hand; the form lists hands by name`.

### Task 4: Docs, contact sheet, full verification

**Files:** Modify `docs/MODULES.md` (effects list: Hand — what it does, the two knobs, wander, pinning, the optional `complete_params` hook for effects), `ROADMAP.md` only if it lists the hand effect as pending.

- [ ] **Step 1:** Update docs.
- [ ] **Step 2:** Render a contact sheet for Ian (NOT committed; write to the scratchpad path given in the dispatch): every hand applied to the same test drawing (an S-curve, a square, a zigzag — about 120 × 80 mm) at defaults, one cell per hand labelled with its label; plus a second sheet of 6 chosen hands × (follow, wander) × stray (2, 8). PNG via the repo's existing SVG/PNG rendering path or matplotlib if available in the venv (check; don't add dependencies).
- [ ] **Step 3:** `npm run typecheck && npm run build && .venv/bin/python -m pytest -q` → all pass (report counts; rerun a browser failure alone before calling it a flake).
- [ ] **Step 4: Commit** `docs(hand): the Hand effect in MODULES`.
