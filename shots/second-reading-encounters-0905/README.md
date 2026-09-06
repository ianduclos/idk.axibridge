# Second Reading — local encounters, 5 September 2026

A refinement of the response revision, not another grammar expansion. Two
existing operations can now take account of an encounter with older material:

- Surround/traverse may lift the new line at one crossing, allowing the older
  line to read in front. Earlier paths are never cut or rewritten.
- Concentration may centre its short physical accent at a crossing of the
  target with another passage. This moves the accent, without changing its
  random length/spacing choices.

Both remain optional. Coincident runs and shared endpoints do not count as
crossings. Detection considers at most twelve recent passage spines and retains
at most eight distinct encounters. Cached bounding boxes reject distant
candidates; actual spine geometry locates contacts, including on human curves.
It does not see every path within a multipath passage or understand all spatial
relationships. It is deliberately a local, selective vocabulary.

The context decision has a separate copied random stream, so discovering an
encounter does not consume the geometry's random choices. Context passage IDs
and a short response description are included in process metadata and ancestry.

## Look at encounter-details.png first

Each row holds the existing drawing, primary target, action and random stream
fixed. The two right-hand panels use identical crop extents: the middle ignores
context; the right attends to it. This is a diagnostic of the same move, not two
selected continuation seeds presented as a causal comparison. The first seed
that demonstrates each response is chosen explicitly and saved in the JSON.

The top row shows the new contour yielding at a crossing. The bottom row shows
an accent move from the upper bend to the encounter on the right. The effect is
legible locally; it does not by itself make the whole drawing compelling.
`encounter-details.json` records the prefix recipe, random seed, target/context
IDs and exact proposed geometry. Reproduce with `tools/second_reading_encounters.py`.

## Broader study and judgement

`interventions.png` repeats the three controlled inputs from the last revision.
`overview.png` retains all six seed studies, including failures. JSON/SVG recipes
are alongside them. These use the current engine from turn zero, so their prefix
is not an exact frozen prefix of the previous engine's study. The detail study
above is the strict same-prefix comparison.

The short gap makes an older line's continuity consequential. The moved accent
can give an intersection weight instead of merely embellishing an isolated bend.
These are modest improvements in how an answer relates to the drawing.
At sheet scale the work still often reads as several similarly fluent contours.
The new rule should not become a weaving style in which every crossing receives
a little underpass. Its present response is partial and optional, but even that
needs judgement through actual alternating use.

Next useful evidence: Ian's own interventions at a promising middle state, with
one-step alternatives before committing to a long continuation. No automatic
beauty score, new grammar catalogue or claim that paper evaluation is complete.

The original response study remains in `shots/second-reading-response-0905/`.
Historical recipes are not version-pinned to historical engine code.


## Verification

1,238 tests pass; one app-shell lifecycle test skips to protect Ian's running
server on port 2942. Browser acceptance, frontend build and typecheck pass.
New independent geometry tests check shared-end/coincident-run exclusion,
exact new-line gap geometry and old-line preservation, context-driven accent
placement with the same stream, deliberate nonresponse, and replay metadata.

54 full 64-turn generation cases: maximum 111.3 ms cold, 0.119 ms warm, 7,672
output points. These are local Python generation measurements, not browser or
HTTP latency. Raw records: `full-bound-performance.json`. No hardware commands
were sent. Changes remain local and uncommitted.
