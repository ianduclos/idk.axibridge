# Dance → structure, drawn in hands (round 8, 2026-10-16)

Ian's idea: "contemporary dance pose extraction for the topology layer — get the
gestures, then abstract and combine to turn non-human."

Files:

- `gesture/dance.py`: BVH and ASF/AMC parsers with forward kinematics (numpy), views, structures, non-human operators and body regimes.
- `experiments/dance_structure.py`: subcommands `structures measure hands regimes limb chimera fieldview`.
- `tests/test_dance.py`: 8 tests, 1 s.

Raw outputs are in `.local/gesture/out/dance_structure/`. Nothing was plotted
and nothing was downloaded. Video (Motion Bank Hay) was skipped because no pose
estimator is installed.

**Look at these first:**

1. `dance_structure-chimera-shikasta.jpg`
2. `dance_structure-limb-mantis.jpg`
3. `dance_structure-structures.jpg`

## What was built

- **Parsers and FK.** BVH works with any channel order, including the 6-channel joints in the E2 files. ASF/AMC uses the CMU convention: M = M_parent·C·E·C⁻¹, and the bone end is the joint.
  - Body-part aliases work across the skeletons (`lhand`, `rfoot`, …).
  - The up axis is detected automatically.
  - Tests check FK on hand-computed toy skeletons in both formats.
  - Every source loads in about 0.1–0.3 s per 30 s window.
- **Structures.** All are `Drawing`s that follow the README contract. Trail strokes carry per-point `speed` and `acc` in meta.
  - **trails** (M1): effector trails cut into phrases at minima of whole-body energy.
  - **strobe** (M2b): the skeleton at held poses, Marey-style.
  - **relative**: one joint's path seen from another joint.
  - **graft**: dancer B's limbs carried on dancer A's root path.
  - **chimera**: trail pieces cut at their own speed minima, then re-attached end to start into one contiguous line.
    - Each join is a sharp turn (0.5–1.5 rad).
    - Some pieces run backwards in time.
    - Pieces mix dancers and limbs.
  - **impossible_tree** (M5a): a branching planar skeleton bent by the dancer's z-scored 3D joint flexion. Each branch gets its own limb and a canon lag.

## Numbers: does dance occupy its own region of structure space?

**Yes, and far out.** The comparison set:

- 41 dance structures;
- 8 oehlen trees;
- 92 real drawings (`topology/real.json`);
- 215 generated drawings (`gen_features.json`).

All are measured on the 40 topology features, centred on the real drawings and
scaled by the pooled sd. Full table: `out/dance_structure/measure.md`. Scatter:
`dance_structure-space.jpg`.

| # | group | distance from the real centroid |
|---|---|---|
| 1 | real Matisse / Hokusai / Ingres | 1.1 / 1.4 / 1.3 |
| 2 | oehlen tree | 6.9 |
| 3 | strobe (stick figures) | 7.1, nearest to gen v3 |
| 4 | dance trails | 9.4 |
| 5 | animal-mime trails | 10.2 |
| 6 | relative | 11.5 |
| 7 | non-human operators | 13.2 |

Logistic-regression AUC, dance vs real = 1.00, and dance vs Oehlen = 1.00. Dance
is a third region, not a variant of either.

The shift is carried by these features (pooled-sd units):

1. **L joins** +3.1. Phrase cuts end one stroke exactly where the next begins.
   - Their deflection is 1.08 rad in contemporary trails, against 1.18–1.32 in real drawings.
   - So the body's phrase boundaries are corners, like the joins in real drawings.
2. **Self-crossing strokes** +2.9. 52 % of dance strokes cross themselves; real long strokes never do.
3. **Cells per ink** +2.7.
4. **Contact degree** +2.5.
5. **X per ink** +2.3. That is 8–21 crossings per R against 0.2 in real drawings.
6. **Near-ends** −2.2. 0.10 in dance against 0.59 in real drawings. **Dance lines never stop just short of another line.**
7. **Isolated strokes** −2.0. Everything touches.

Dance is loops and crossings with no near-misses: the opposite of Matisse's aimed
near-meetings.

The non-human operators push further out on the same features. They do not head
back toward real drawings or trees.

## The images

**1. Structures** (`dance_structure-structures.jpg`).

- Contemporary trails in 15 s windows read as contiguous, wandering lines. Levitation and Unusual Poses work best.
- Longer windows overdraw into scribble, so the window is capped at 15 s.
- The CMU 55 mimes that travel (mantis, penguin, dragon) give horizontal bands, one each for head, hands and feet, with a footstep rhythm along the floor line. They read like lines of script.
- **Strobe is figurative.** It reads plainly as stick figures. Keep it only as the "human" calibration rung.
- **Hummingbird hand trails are a dud.** Flapping makes zigzag hatching.

**2. Hands** (`dance_structure-hands.jpg`, restyle at amount 0.6).

- Matisse and Hokusai turn the trails into loopy, soft lines. Shikasta adds sharp turns and hooks.
- **At amount 0.6 the hand replaces the dance's own small-scale texture** (σ_s ≈ 0.056 R). The jagged chimera corners become loops.
- If the dance should survive the hand, use amount ≈ 0.3–0.4. I did not test that.

**3. Regimes** (`dance_structure-regimes.jpg`). `compose(structure=<Drawing>)` works as is: it accepts a given Drawing.

| # | field | line / nib / mass | how it reads |
|---|---|---|---|
| R1 | noise | 23–45 % / 18–43 % / 17–49 % | masses swallow the dance |
| R2 | authored axis | about 85–90 % / 9–12 % / 1–5 % | thin |
| R3 | the body's kinematic field | 60–84 % / 13–36 % / 1–3 % | mostly wire, knots at the stillnesses |

**4. Limb, the body's own regimes** (`dance_structure-limb-mantis.jpg`,
`dance_structure-chimera-shikasta.jpg`, diagnostic `dance_structure-kinematic-field.jpg`).

The mapping is stillness → mass, acceleration (when not fast) → nib, and speed →
wire. Values are normalised per drawing, and pauses are dilated to ±0.022 R of arc
so they get visible size.

**It held, better than expected.**

- Masses land where the body paused: at phrase ends, which act as terminal drops, and at footfalls. The penguin and dragon floor lines become rows of beads.
- In the chimera, every re-attachment joint is a velocity minimum, so **every joint of the impossible line becomes a knot**. The line → nib → mass transitions sit exactly at the seams between borrowed gestures. Nobody authored that placement.
- Mantis + hummingbird in the shikasta hand is the most sign-like sheet of the round for me: angular wire, nib flicks, knots at the joints. No figure is readable.

Regime shares per source (self-normalised):

- **Mass** separates the qualities: 7 % Levitation and 6 % OutOfBalance, against 17 % Staccato and 18–19 % Hippo-ballerina and Penguin.
- **Nib** stays near 21 % for every source, because each drawing is normalised to its own percentiles.
- The raw median accelerations differ 16×: Levitation 0.5, Staccato 3.1, OutOfBalance 8.0 body-heights/s². A shared normaliser would make the movement quality visible as regime.

## What failed

1. **The impossible tree.** Every setting I tried (gain 0.08–1.0, branching 2/3, 3–16 tips, projected or 3D flexion) draws the crown's silhouette. The tips sit along a fan, so their trails form a dome of arcs.
   - That is "making trees" by another route.
   - The dance survives only as local scribble at the tips.
   - The first version also drew chords across the sheet: projected bone angles flip when a bone points at the camera, and `np.roll` wrapped the canon lag. Both are fixed: 3D flexion angles, and a padded delay.
2. **Relative and graft** structures scribble at 15 s windows.

## Next limb

1. **Use a shared kinematic normaliser** across a corpus, so that Staccato really is masses and Levitation really is wire. Then rerun the D2 quality test as a regime test.
2. **Chimera with the near-end rule.** Stop some re-attachments a near-gap short, so the line stops just before it touches. Dance lacks near-ends entirely; this would borrow Matisse's aimed near-miss.
3. **Restyle at amount 0.3** to keep the body's own corners.

## Proposed changes to existing modules

None needed. `compose` already accepts a Drawing and a Field.

One optional change, `regime_field.compose`: accept per-stroke r(s) from
`Stroke.meta["r"]`. My nearest-sample Field lookup mixes values where trails
cross.
