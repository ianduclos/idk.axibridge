# Prosody and accumulation (round 9) — 2026-10-17

Thread `prosody_accumulation`. Round-8 principles 3 (weight as emphasis) and 4
(accumulation becomes a sign), built as kit modules and tried on the Hand Drift
lines. Code: `gesture/kit/prosody_{voices,modulators,renderers,arrangers}.py`,
`experiments/prosody_accumulation.py` (stages `field solid sign duet`),
`tests/test_prosody_accumulation.py` (11 tests, about 3 s). Per-tile previews and
their recipes (43 `.recipe.json`) are in `.local/gesture/out/prosody_accumulation/`,
and the numbers are in `numbers.json` there.

## What I built

| kind | id | what |
|---|---|---|
| voice | `drift_tokens` | the seed `drift` line, byte-identical (tested), plus `token` (the grammar's segment index) and `tok_turn` (the corner opening it): the grammar's syllables, including boundaries that leave no geometric trace |
| modulator | `prosody` | the line hears its own events (hand switch, corner, curvature peak, inflection, token boundary, dwell if a tempo ran first), and a rhythm picks which ones carry stress: `event`, `regular` (a metre whose beats snap to events, rest otherwise), `syncopated` (loud off-beats over quiet downbeats), `phrase` (end-weighted). Loud stresses become masses, quiet ones become nib. `unit` = pulse or segment (the stretch the event opens). `lead` makes the stress anticipate or lag the event. `contrast` makes salience relative to the event's neighbourhood. Writes `emphasis`, `r`, `W`, `M` |
| renderer | `restate` | mashq by machine: each emphasised stretch is written again n = 1 + (copies − 1)·peak^γ times, nearly on top of itself, so quiet stresses get fewer copies. `bound` = hull or contour closes the heap into an object |
| renderer | `coil` | a mass built from line whose core is the line itself: rings offset outward from the stretch, or one contiguous spiral |
| arranger | `call_response` | the limb. Every part after the first re-decides its stresses so they fall where the part before it is silent, judged over the whole stretch it would ink. `time` reads both lines by share of arc length, and events just after a loud call get a bonus. `space` reads whatever of the other line passes within the radius. Layout `single` or `rows` |

## Numbers

**Field vs prosody** (one line: matisse > shikasta > lichtenberg, chain, seed
7000, length 3, about 1 m). `lift` = density of strong events (salience ≥ 0.6)
inside the weighted stretches ÷ their density over the whole line. Above 1
means weight lands where something happens.

| # | regime | weighted share | heavy runs | lift |
|---|---|---|---|---|
| a | field noise | 0.52 | 9 | 0.82 |
| b | timing Staccato | 0.27 | 29 | 1.48 |
| c | prosody event, pulse | 0.06 | 10 | **3.76** |
| d | prosody event, segment | 0.14 | 10 | 2.31 |
| e | regular, metre 3 | 0.24 | 10 | 1.06 |
| f | syncopated | 0.24 | 14 | 1.55 |
| g | phrase (end-weighted) | 0.21 | 14 | 1.98 |
| h | pulse, lead −8 mm | 0.07 | 10 | 0.97 |
| i | Staccato → prosody | 0.17 | 10 | 1.96 |

The field weights half the line and is slightly anti-aligned with events
(0.82). Prosody weights 6–24 % of it. The metre (e) and anticipation (h) fall
back to about 1, which is what they should do: a metre lands on its beat
whether or not anything happens there, and an anticipating stress sits *before*
the event.

**Sign threshold** (one loud stretch restated; coverage of the fixed region
stretch ± 2.5 mm; legibility = share of inked pixels crossed by exactly one line):

| copies | 1 | 2 | 3 | 5 | 8 | 12 | 20 | 40 |
|---|---|---|---|---|---|---|---|---|
| coverage | .07 | .12 | .16 | .23 | .31 | .38 | .51 | .64 |
| legibility | 1.0 | .95 | .86 | .76 | .65 | .52 | .44 | .31 |

**Call and response** (leader matisse > shikasta > lichtenberg, follower bubble >
hokusai, seed 7100):

- In time, rows layout: the share of u where both lines are stressed fell from 0.028 to **0.000**. Correlation along u fell from −0.01 to −0.14.
- In space, one surface: follower stresses with a loud leader stretch within 15 mm fell from 13.6 % to **0 %**.

## Images

1. `prosody_accumulation-field-vs-prosody.jpg`: nine regimes on one line. In
   c, d and g, most of the line is wire and a few decisive weights land on the
   events. In e you can see quiet and loud: quiet stresses ink as thin nib
   strokes, loud ones as masses. That is principle 3 working ("the same
   utterance quiet and loud").
2. `prosody_accumulation-solid-vs-linebuilt.jpg`: the same stresses six ways.
   Regime solids (a, b) set against restatement, restatement + contour bound,
   coil spiral, and a 3× hull "cartouche".
3. `prosody_accumulation-sign-threshold.jpg` + `-sign-whole.jpg`: the sweep in
   detail and on the whole line (5× vs 20×).
4. `prosody_accumulation-call-response.jpg` (eight tiles) and
   `-d-time-strips.jpg`: the two lines' emphasis drawn as a score; the answer
   moves into the leader's rests. Tile g is the strongest single image: the
   leader carries black masses, and the follower answers in restated,
   bound line. Two distinct grammars of weight share one surface.

## Surprises

1. **Prosody depends on the hand.** With absolute salience, the matisse third
   (smooth curves, few events) got no stress at all and Lichtenberg's corners
   took all of it. That is coherent: each hand keeps its own stress pattern.
   But it starves the smooth hands, so I added `contrast` (salience relative to
   ±60 mm, default 0.5) to restore some stress there.
2. **Pure restatement never blobs.** In mashq, the 20× collapse came from the
   coincidence fill rule. Line-only restatement saturates instead into a dark
   brushy ribbon (40×: coverage 0.64, legibility 0.31) that still reads as
   many strokes. The sign threshold is a dial, not a cliff. Legibility crosses
   0.5 between 12 and 20 copies, and 3–8 copies stays "visibly rewritten"
   (0.86–0.65). This agrees with the mashq band.
3. **The bound changes the category.** The same six copies with a contour
   bound read as objects (cartouches, pods), not emphasis. The hull at 3× is
   the most "near-object" of the set. That is principle 4's second half
   ("a bound turns process into an object"), and it is a separate dial from
   the copy count.
4. **The segment unit (stress the stretch an event opens) is what makes
   restatement read.** A 10 mm pulse is too short to rewrite visibly. A whole
   token or straight run being rewritten reads as a word said twice.
5. **The time strips are a piece in themselves.** Two rows of stress blips are
   a score of the duet, in the spirit of D, "process as material".

## Failures / duds

- The first event rhythm piled every stress into the first 40 % of the line.
  Salience saturated at 1.0 (switches + coincidences) and ties broke by
  position. Fixed by grading switches by how long the new hand holds the line
  (a flicker in the cross-fade is weaker than a takeover), and by not clipping
  merged salience.
- The first `call_response` only checked silence at the event point. A segment
  stress then ran on into the leader's stress, giving 6 % overlap. It now
  checks the whole inked extent, quiet stresses count as speech, and overlap
  is 0.
- `restate` 6× at sheet scale (drift 0.7 mm on a 267 mm sheet) is almost
  invisible in solid tile c. Accumulation needs either a bound or ≥ 8 copies to
  carry across a whole sheet.
- The metre (e) is honest but dull: it weights the line regardless of events
  (lift 1.06).

## Proposed kit-core changes (not made)

1. The seed `drift`/`hand` voices should carry `token` + `tok_turn` (cheap; the
   token list is already computed and dropped). Then `drift_tokens` retires.
2. A modulator cannot see other parts, so call-and-response had to be an
   arranger that re-modulates after placement. A small sanctioned hook would
   generalise it: for example `ctx.placed` (marks of earlier parts), or a
   sheet-level "listen" stage after the arranger. Duets, annotation and
   crossing would all use it.
3. Ink `meta["role"]` convention (`line` / `restate` / `bound` / `coil`) so
   metrics and future plot passes can address construction separately.
4. `kit.preview(..., window=(x0, y0, w, h))` for detail crops, so zoomed
   result tiles come straight from preview. Right now I crop
   `render_image` output.

## Next limb

Accumulation as **response**: the follower answers a leader's loud mass by
*restating the leader's stretch* in its own hand, nearby (annotation, principle 6).
Also worth trying: let restatement count follow the `phrase` rhythm, so a
phrase builds 1 → 3 → 8 copies towards its end and closes with a bound,
turning a sentence into an object.
