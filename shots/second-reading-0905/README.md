# Second Reading — first comparison study

2026-09-05. Screen/geometry evidence only; no real plot was run.

## How to try it

Restart the normal AxiBridge app so it loads the new source and built frontend.
Choose **Second Reading** in Generate, then **Bench**. It opens at turn 12.
Use the turn slider to inspect an earlier state; **Continue one turn** develops
it. **Your turn** lets you draw one stroke on the paper before the machine
resumes. **Try another** keeps the prefix and explores a different continuation.
The reading selector returns to previous alternatives.

Behavioural sliders queue changes for the next turn. Revising an earlier turn
creates an alternative instead of replacing its old future. **Keep as layer**
creates a normal project layer without closing the bench. Save the project to
retain that layer after restarting. **Resume in bench** works on a copy of a
kept recipe. Unkept alternatives survive popup close/reopen, but not a browser
restart. Undo/Redo inside the bench, including the keyboard shortcuts, affects
the working score rather than the project behind the popup.

Seed and surface size apply only when **New drawing** is pressed. This clears
the working score; local Undo can recover it.

## Reading the study

`overview.png` has six rows, seeds 1, 4, 12, 23, 42 and 91. Each row has:

1. A shared prefix at turn 4.
2. Continuation A, seed 11 from turn 5, shown at turn 12.
3. Continuation B, seed 29 from turn 5, shown at turn 12.
4. Continuation C, seed 71 from turn 5, shown at turn 12.
5. Continuation seed A with one fixed human-style polyline inserted at turn 5.

That polyline is a controlled experimental input, not a recorded performance
by Ian. Each `seed-NN.json` contains complete validated recipes and decision
histories. `seed-NN-0.svg` is the prefix; suffixes 1–3 are continuations and 4
is the intervention. SVGs are real millimetre geometry with a nominal 0.3 mm
stroke. The PNG previews are comparisons, not calibrated ink simulations.

Reproduce the study from the repository root with:

```sh
.venv/bin/python tools/second_reading_study.py
```

`bench.png` and `bench-compact.png` are actual browser captures at 1500 × 950
and 1280 × 800, using seed 23 at turn 12. The temporary inspection server used
isolated stores and no hardware connection, and was stopped afterward.

## Primary agent's visual judgement

**Most promising: seed 23, continuation A and the intervention case.** The
initial angular passage gains a second direction of development. The inserted
stroke extends the spatial argument across the sheet, and the subsequent
machine passages change their position and relationships. This is evidence
that intervention can do more than append an isolated decoration. It is still
an angular construction with repeated motifs, not the full ambition of the
Oehlen discussion.

**A different useful case: seed 12, continuation C versus intervention.** The
long curving development alters the extent of the sparse opening; the inserted
angular stroke acquires concentrated weight and a distinct role against it.
There is visible disproportion, but some long continuations simply leave the
sheet. Boundary clipping prevents a false wall-following behaviour; it does
not guarantee a convincing ending.

**Weakest: seed 42, continuation A.** Most of the page remains unaffected and
the added activity is tiny. Seed 1's B is a clear echo operation but reads
readily as a repeated motif. Several other cases make polite little fans or
thicken existing material without changing its standing in the drawing.

The initial render exposed exponential shrinking when concentration targeted
the output of concentration. Returning to its material ancestor improved the
scale of the resulting activity. Traversals between joined passages now avoid
zero-length shared endpoints. Both repairs stay within the four initial
actions. Neither turns the vocabulary into a general composition system.

The instrument now allows the intended experiment. The drawings do **not**
establish that selective attention alone achieves potent abstraction. The next
iteration should use Ian's interventions and compare their continuations,
especially passages that change the importance of existing material. That
evidence should determine whether to strengthen these actions before adding
any new vocabulary.

## Measured performance and checks

Final verification: **1,225 tests passed** in the full hardware-free suite;
`npm run build`, `npm run typecheck` and `git diff --check` passed. The suite
reports one existing Starlette/httpx deprecation warning. No real plot ran.

`full-bound-performance.json` records 54 runs at all 64 turns, across six
seeds, three surface sizes and three reach settings. On this Mac, the slowest
was **23.2 ms cold** (rounded up) and **0.06 ms warm** for geometry generation;
the largest measured output was 8,727 points. These are observations, not
hardcoded performance tests.

`api-performance.json` records full preview requests through FastAPI TestClient
at turn 64 on six seeds: at most **34.9 ms cold** and **6.3 ms warm** (rounded
up), including response generation. These are in-process API timings, not
network or browser paint timings. The browser itself was exercised by
acceptance tests and visual inspection.

Mechanism tests independently check echo geometry, extension tangency,
traversal endpoints, arc-length concentration, clipping, exact prefixes,
no-op controls, future events, bounded input and saved recipe replay. Browser
tests cover capture, scrubbed revision, alternatives, Undo/Redo, late preview
responses, pause during a request, Keep, reopening drafts, saved-layer
isolation and restoring the generic Watch coordinate frame.

## Review and orchestration record

The primary agent implemented the engine and public contracts and reviewed
the drawings. Sol supplied the first bench implementation; Terra supplied
independent tests. Sol hit its usage limit before frontend polish completed,
and the separate Sol reviewer also stopped at its usage limit before delivering
a report. **An independent final review was not completed.**

The primary agent took over the frontend and final audit. That review found
and fixed missing scrub support, reset inputs overwritten during rerender,
branch selection reset before its handler read it, playback restarting after
Pause, wrong effective controls on resumed recipes, silent captured-point
truncation, and keyboard Undo reaching the project behind the bench. Tests were
extended to cover the significant user-facing failures.

For the next iteration: retain the primary agent as engine/artistic owner and
integrator; use Sol for a bounded interaction task, Terra for independent
verification, and a read-only reviewer after integration when capacity permits.
Supporting agents supply changes and evidence, not artistic acceptance.
