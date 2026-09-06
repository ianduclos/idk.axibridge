# Recovery, midway review and lead decision — 6 September 2026

## Recovery evidence

Recovered the early engine from the prior task's completed tool output:
`01a0703b-e3ab-71e2-ae68-5200be9f5e5a`, 5 September, 06:29:48 UTC,
ordinal 192 (the paired source/engine read). This is recovery, not a visual
reconstruction. `_second_reading_first.py` preserves the policy and construction;
its only new seam is an optional boundary callback, unused in baseline mode.
The shared replay runner retains the later capture smoothing and event validation.

All 30 original `shots/second-reading-0905` cells match path counts, point counts,
coordinates within the historical six-decimal SVG precision, and every recorded
decision field. This is stronger than a screenshot resemblance; it is still not
a claim that every undocumented intermediate development state was recovered.
The regression test repeats this comparison against the historical files.

## Midway evidence and reviewer calibration

`shots/second-reading-recovery-0906` is the pre-review population. A = first,
B = shapes, C = relations; rows are seeds 1/4/12/23/42/91 and columns are turns
5/6/8/12. Each row has the same exact prefix and captured input through turn 5;
reading changes at turn 6. B/C use the same geometry stream. Different targets
or geometries after that naturally change later developments. The isolated
`exchanges.png` and recipe decisions distinguish latest-input response from
older-material response. These are controlled recipes, not Ian's hand use.

Sol read neutral sheets, close views and K/L/M/N before their mechanisms. Its
report is `second-reading-0906-sol.md`. It distinguished the original central
cusp from the added repeated right-bend hooks, noticed that removing the first
echo loosened rather than destroyed the relation, and found the translated-path
variant less concentrated. It did not simply praise greater disruption. Its
sequence pass correctly revised attribution: the cusp and counterlines predate
the human stroke, while the answer brings that stroke into their neighbourhood.

There is a remaining calibration limit: its first pass described N as having a
rib removed before seeing the key. That was visually correct, but the language
blurred observation with a causal account. Its image-first discussion of an
upward counterline also read more confidently than the sequence warranted. The
second pass explicitly corrected this. No new skill instruction was added:
the existing observation/provenance rule covers the issue, and adding prose to
force agreement is not calibration. The grid-snapped L is a crude regularisation
probe, not a persuasive example of expert tidying. Screen-only; no paper verdict.

## Lead judgement and focused revision

I retain Sol's central-cusp observation, but do not take K's narrow preference
over N as a mandate for density. Row 1 is largely unchanged locally, and rows
5/6 demonstrate how reinforcement becomes an effect rather than a new invitation.
The relational pocket in C4 changes the empty left side usefully; C1's rounded
return risks a familiar enclosure. The population does not establish a superior
replacement for First, so First remains the default.

The focused revision changes echo deformation from point index to travelled
arc length. The old method let irregular capture sampling create a repeated
hook at every echoed corner. The final B3-4 removes those hooks, preserves the
original central cusp, and keeps the long counterline and unequal intervals.
This is a geometry correction with the same response policy, not another
attention mechanism. Pre-review SVGs/PNGs and `experiment-before.py` survive;
`tools/second_reading_recovery_study.py --before --output <new-directory>`
reproduces that geometry experiment. Default output is the final study directory.

Boundary rows F compare clip / contain / whole-fit for seeds 4/12/42 at turn 16.
These are whole-run alternatives, not isolated last-turn causal comparisons.
Containment can produce squeezed edge runs (F2/F3); whole-fit preserves the long
excursion and inter-passage proportions (F2-3), though the larger excursion can
make the older knot small (F3-3). Keep all three choices. Prefer whole-fit for
trying the element workflow; do not turn that preference into a new default for
historical recipes.

## Alternating bench use

The lead drove a separate, temporary browser/server with isolated configuration
and autoconnect disabled. `bench-*.json/png` in the final study preserve the actual
captured pointer events and successive screenshots. Starting at seed 12, turn 4,
I placed a broad rising line through the small existing region, inspected two
answers, then added a small angular return on the left and switched to Relations.
Its next three turns made a returning loop at the left end of the earlier band.
I then added a larger right/downward open contour overshooting the nominal sheet,
continued three turns and kept the result. No hardware was used. The temporary
server was terminated. This is lead-driven use, not user acceptance.

The fixed workspace keeps captures in stable coordinates. The kept document
uses one uniform affine for all visible passages. The bench displays those same
preview lines through the inverse affine; no alternate plot geometry exists.
Older raw prefixes remain unchanged even though the fitted on-paper size can
change as the element grows. The actual UI sequence also exposed a hidden-label
CSS override; the final UI only shows the controls relevant to its reading.

The next judgement belongs to alternating use: does a response offer a move
worth taking, including when it ignores the latest stroke? More machinery is
not the next default action. Paper remains untested.

## Final integration findings

The third bench intervention is **not** answered directly. Turns 13–15 extend
passage 12 (machine turn 11), then its descendants, leaving the new broad contour
alone. The leftward angular excursion answers the small returning loop. This
changes the two sides' authority, but also makes the result sprawling; it is a
useful unresolved case, not a selected success.

The Keep screenshot exposed a placement defect after generation: portrait's
ordinary quarter-turn could put a 272 mm-wide fitted element outside the 218 mm
bed height. The source now declares its document frame through the opt-in
`placement_frame` contract. Session applies one uniform frame placement in either
orientation; view changes use relative frame transforms, so a roundtrip restores
scale. Tests cover actual resolved bed bounds for every boundary choice, both
views, and exact roundtrip affine recovery. The original failed Keep screenshot
and project JSON are retained as evidence; `bench-kept-project-after-placement.json`
and `kept-on-bed.svg` record the corrected same recipe. The bench screenshots also
predate the hidden-control CSS fix. The final UI acceptance checks confirm only
the relevant controls appear and fit capture resumes in the same work frame.

Warm generation measured at roughly 0.2–0.4 ms for the sampled seed-12 fit recipes;
cold runs were 33–107 ms including all 64 trajectory steps. These timings describe
this machine and small sample, not an interaction-latency guarantee.

## Verification completed

Final hardware-free suite: **1,255 passed** (one existing Starlette/httpx
deprecation warning). Frontend build and typecheck passed. The focused
replay/placement/view/bench set passed 105 tests after the last placement edits.
A separate temporary-browser check resumed the exact final captured recipe and
saved `bench-final-ui-resumed.png` / `kept-final-canvas.png`; resolved bounds for
that portrait Keep are x 99.62–200.38 mm, y 3.11–214.89 mm. All temporary servers
were terminated. The user's running app and unsaved work were not restarted or
edited; no hardware commands or remote push occurred.

## Control comparison

Terra's `controls.png` / `controls-recipes.json` holds prefix, t5 stroke and
stream constant for seeds 12/23, varies one control at t6, and shows t8. Attention
has a clear discrete shift at 1; 0 and .5 can coincide for these fixed streams.
Departure changes the bend/transfer more modestly. Scale changes the width of
seed 23's open interval markedly, but does **not** change seed 12's echo: the
current echo takes its extent from the target. Thus Scale is not yet a universal
answer-size dial. Keep that limitation visible rather than claiming three
finished orthogonal controls. This is the experimental meaning to test at the
bench, not a reason to redesign the policy before Ian uses it.

## User follow-up cleanup (supersedes the default recommendation above)

Ian asked for visible pen smoothing, removal of thick parallel stacks, a seed
randomizer, a brief parameter guide, boundary checking and the general agent
protocol in AGENTS.md. Responsive is now the default; thick reinforcement is
removed from all ordinary policies. Historical comparisons require the hidden
historical_stacks flag, and archive tools set it explicitly. Turn inside now
makes a rounded inward reflection. The bench exposes next-stroke smoothing,
previews it live, preserves pending seed/size/boundary across renders, and labels
active versus pending boundaries. Fit displays the nominal sheet as a dashed guide.
Terra handled the bounded UI edits/tests; the primary owned engine and integration.

Latest verification: 1,262 passed, 1 skipped; frontend build/typecheck passed;
14 Second Reading browser acceptance tests passed separately. The final temporary
browser screenshot is `shots/second-reading-cleanup-0906/bench.png`; the server was
terminated. This is ready for Ian to check, not user-visible acceptance. The
referenced `~/.Codex/HOST.md` is absent, so no host-dependent shared feed or vault
write was attempted. The project-local boundary note is in CHANGES.md.
