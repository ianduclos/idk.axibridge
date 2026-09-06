# Second Reading — first interactive slice

2026-09-05. Implements the experiment agreed after
`../IDEAS-drawing-machine-session-2026-09-05.md`. This is a drawing instrument
for testing an artistic hypothesis, not a claim to have solved composition.

## What the machine does

`second_reading` is an accumulative process. Turn 0 makes two unequal strokes;
turns 1–64 each add a passage. A passage can contain several strokes, but is
remembered as one item with bounds, direction, endpoints, length, construction,
ancestry and explicit target relationships.

Four actions share that memory: extend an endpoint, echo an entire passage,
traverse between two passages, and concentrate parallel strokes around a
selected arc-length interval. The first target's construction — angular or
cubic — carries into its development. Human input is preserved as a polyline
and becomes another targetable passage. The engine does not identify objects.

Attention persists for 2–5 machine turns. Recurrence controls whether its
target comes from recent or older material; reach controls extent, displacement
and curvature. These are concrete policies, not quantities claiming to
measure deliberation or artistic quality. There is no global harmony score,
image model, compulsory crisis or fixed order/disruption cycle.

Engine details live in `sources/_second_reading.py`; the source wrapper and
validated recipe live in `sources/second_reading.py`. The wrapper owns replay,
the engine owns geometry. Geometry always enters the existing compositor as
an ordinary generator layer. No machine backend is involved in the bench.

## Replay contract

Parameters include bounded `turns`, `width`, `height`, `seed`, `persistence`,
`reach`, `recurrence`, and a hidden list of discriminated events:

- `stroke`: turn and `points` as `[x_mm, y_mm]` pairs; occupies that turn.
- `controls`: turn and any nonempty subset of the three behavioural controls.
- `branch`: turn and a continuation seed.

Turns are integers 1–64 for events; opening turn 0 cannot be replaced by an
event. Events are nondecreasing by turn, with at most one of each kind at a
turn. Controls and branch changes commute, but both must precede a stroke at
the same turn. A recipe holds at most 128 events and 20,000 captured points.
Coordinates must be finite and inside the declared working surface; a stroke
must have at least two distinct points. Invalid input is rejected, not clipped
or silently dropped.

Every turn's random stream derives from original seed, turn and active
continuation seed. Future events cannot affect an earlier turn. A changed
branch seed resets the current commitment; a no-op branch does not. Changed
persistence or recurrence requests a new commitment at that turn; reach acts
on the current commitment's geometry. No-op control events do not perturb
randomness or reset attention. Human input resets attention after contributing
its own passage, making the next machine choice able to target it.

The trajectory cache remains a full bounded run. Its key contains the event
recipe but excludes the inspected turn. Branches replay from the start with
their own event lists; they do not reuse a mutable live simulation or splice
in a second geometry representation. This is fast enough for this slice.

Working alternatives keep their recipes separately. A branch made at N keeps
events through N, drops its own future, and receives a branch event at N+1.
The original alternative remains available. Keep creates an ordinary layer;
saved generator params therefore retain the score without a file-format
migration. Existing SVG source snapshots round coordinates to six decimals;
recipe replay remains exact, while snapshot roundtrips have that pre-existing
precision limit.

## Bench and preview contracts

Source descriptors now declare `bench_capabilities`, defaulting to an empty
list. Second Reading opts into `intervene` and `branch`. These capabilities
select the specialised interactive bench; existing Watch and other generator
benches retain their own semantics.

`Step.metadata` and `Trajectory.metadata` carry discrete action information
separately from numeric telemetry. `/api/generators/preview` adds optional
`process` data with the current turn, generator-supplied metadata and numeric
telemetry. Existing geometry fields are unchanged. Metadata never becomes
geometry, a plot command, or an alternative evaluator.

The bench exposes Continue/Play, Your turn, Try another, alternatives,
Undo/Redo, Keep and New drawing. Behavioural controls affect the future;
seed and surface size belong to an explicit new drawing. Kept layers can
resume as working copies, never as silent edits to the saved layer. A kept
recipe is durable once the containing project is saved; unkept alternatives
only survive within the current app session.

Keep must use the exact successfully previewed recipe. Pending and stale
responses cannot authorise a save. Pointer previews are temporary, replaced
by server-generated paths on release. Optional action details are hidden by
default, so the picture is available for judgement without an explanation.

## Bounds and first visual tuning

Machine-derived passages are limited to six paths sharing a budget of 384 points;
captured input is preserved within its separate 20,000-point bound. Target
selection inspects at most twelve passage descriptors. Curves are clipped at
real segment/rectangle intersections; the pen is never reflected along a wall.
If an action falls entirely outside, the engine tries three alternatives,
then makes an inward echo known to fit rather than yielding a blank turn.

The first comparison study revealed two mechanical routes to aesthetically
negligible marks. Concentrating on a concentration repeatedly shrank the
worked interval below useful scale; the selector now returns to that passage's
material ancestor. Traversal between already joined passages selected their
shared endpoint and produced zero length; it now prefers endpoint pairs at
least 0.5 mm apart when available. These are local repairs within the four
actions, not a new aesthetic optimiser.

## Evidence and remaining judgement

`tools/second_reading_study.py` produces six shared openings at turn 4, three
continuations from each, and a controlled inserted stroke followed by the
same continuation seed as A. It saves every recipe, decision history, SVG and
comparison image in `shots/second-reading-0905/`. Weak cases remain in the
study. The inserted stroke is a fixed experimental input, not a claim that a
person performed those particular marks in the bench.

Tests cover independent geometric properties, exact replay and prefixes,
validation, saved recipes, API metadata and bench interactions. Performance
measurements and visual findings are recorded beside the study. Passing tests
establishes the instrument's mechanics; it does not establish artistic success.

Paper remains untested. The next artistic question is whether Ian's own
interventions give the existing vocabulary enough consequence to develop, or
whether its passages remain too uniformly polite. Resolve this with the bench
and specific drawings before adding more actions, models or global scores.

## Orchestration

The primary agent owns the mechanism, event/API contracts, integration and
visual judgement. Sol implements the bounded bench frontend; Terra develops
independent verification. A separate read-only review follows integration.
No supporting agent chooses the artistic goal, expands scope or delegates.
Findings are evidence for the primary agent's review, not automatic acceptance.


## Revision after Ian's visual feedback

The first geometric study and the rejected organic overcorrection remain as
historical evidence. Current construction mixes loose curves with rounded
straight runs and retained hinges. Two new actions, fold and graft, supplement
the original four; concentration is rarer and less coiled. Details and honest
strong/weak comparisons: `shots/second-reading-mixed-0905/README.md`.

Stroke events now accept optional smoothing in [0,1], default 0 for legacy
recipes. The bench writes 0.6. Raw samples remain recorded; authoritative
geometry applies bounded corner-aware smoothing during deterministic replay.
A raw stroke is still one turn and is targetable through its rendered passage.
Current verification: 1,232 tests, build and typecheck pass. This supersedes
original-study aesthetic recommendations above; paper remains untested.

## Current response revision (supersedes the mixed grammar revision)

Ian prioritized perceptible novelty in the human/machine exchange and selective
response to existing material. Attention now persists independently of operation:
repeated target/action pairs lose probability without an obligatory cycle.
Five active operations: extend, echo, traverse, surround, concentrate. Actual
contour geometry informs direct cubic constructions and whole-passage transfers;
fold/graft templates no longer run. Openness and span are incremental descriptors.
Events and bench contracts are unchanged. Physical concentration makes six
pen-scale passes rather than a field of parallel echoes.

Controlled same-prefix/input comparisons, full recipes, honest failure cases,
and performance measurements: `shots/second-reading-response-0905/README.md`.
The previous studies are historical evidence, not current engine recommendations.

## Local encounter refinement

Surround/traverse may yield at a crossing with existing material; concentration
may centre on a crossing of its target with another passage. Choice is optional,
using a copied random stream so geometry choices do not shift when context is
found. Inspection is bounded to twelve passage spines/eight distinct contacts,
with cached bbox rejection and exact spine intersections. Shared endpoints and
coincident runs do not count. Context IDs join target metadata and ancestry;
optional `response` metadata describes the response. Past geometry stays exact.

A private `consider_context` argument supports strict diagnostic comparisons;
it is not a new user control or alternate plotting path. Encounter geometry,
selection and the response constructions remain separate modules. The detail
study freezes the prefix/action/stream, unlike historical whole-engine studies.
See `shots/second-reading-encounters-0905/README.md`.
