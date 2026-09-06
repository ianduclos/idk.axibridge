# Second Reading — agreed next experiment, 6 September 2026

## Read this before continuing implementation

Ian's latest judgement overrides the optimistic readings in older study READMEs:
**the first version was more responsive; later versions made little progress.**
He wants to preserve useful parts and rebuild from that response behaviour,
not keep refining the latest encounter mechanism by default.

The current code is the encounter revision. No restoration or selectable first
baseline has been implemented. The existing controls are still Persistence,
Reach and Recurrence; the proposed new controls and boundary treatment below
are not shipped. This distinction is important when starting a fresh session.

## What to preserve and explore

- Keep the interactive bench, event replay, branching, Keep/Resume and light
  corner-aware smoothing of human strokes.
- Recover the first response behaviour as an available baseline. Improve shapes
  and unequal proportions without simultaneously replacing the response policy.
- Occasional homeostat-like wandering/gathering/broken gestures belong among
  possibilities; don't turn the whole machine into the homeostat again.
- The thin-to-thick accumulation finish is worth preserving as evidence, but
  defer developing it to a later effect. It should not carry this experiment.
- More awareness of relationships in existing material, including older machine
  ink and shaped space. It may ignore the newest human stroke. Awareness must
  earn its place through perceptible, consequential novelty, not explanations.
- Prototype Attention (current passage ↔ wider drawing), Departure (close
  relationship ↔ substantial transformation), Scale (local ↔ broad answer).
  These are experimental meanings, not finalized parameters or migration rules.
- Bench → layer is an element-making workflow. Hard clipping often damages an
  element. Compare edge-aware containment with overshooting the nominal sheet
  and fitting the whole element. Preserve inter-passage proportions, stable
  capture coordinates and physical bed bounds on the kept/plot-resolved result.
  Avoid shrinking each new response independently or automatic view motion while
  drawing. Slight clipping or homeostat-like boundary turns can be useful.

Ian explicitly gave the lead design freedom. Do not ask him to restate these
preferences or choose a boundary solution before making a reviewable experiment.
Do not assume a wider work surface or a Fit command already exists.

## Baseline recovery: known evidence and limits

The original study is `shots/second-reading-0905/`: six seed rows, per-cell SVGs,
recipe JSON and decision metadata, bench screenshots, README and measurements.
The first engine was never committed separately in this session. The preceding
repository commit (`3fe79b7`) predates Second Reading entirely. Thus a simple
checkout of an old git revision cannot recover that implementation.

Inspect available prior task/tool history for the first engine before assuming
reconstruction is necessary. The current `_second_reading.py` still contains
original analytic echo/extend/traverse/concentrate helpers; the initial study's
JSON/SVGs provide independent checks. If reconstruction is needed, label it as
such and compare its geometry and response decisions to those saved artifacts.
Do not claim exact restoration on the strength of vaguely similar screenshots.
Keep historical SVGs; historical params replay through current source and are
not version-pinned executable snapshots. The wrapup commit preserves today's
experimental engine so it can be revisited without being the default baseline.

## Lead and reviewer

The primary agent owns artistic hypothesis, implementation, event/public
contracts, scope, integration and final acceptance. Use one bounded **Sol**
aesthetic reviewer midway, via `.agents/skills/drawing-review/SKILL.md`.
It does not edit code or delegate. Other bounded mechanical support may use
Sol/Terra only when useful; at most three supporting agents, and no competing
contract changes. Do not launch agents just to satisfy an orchestration diagram.

The reviewer reads iteration populations, not just highlights. Interesting
figures are not expected at every turn. Quiet, weak and almost-promising stages
are nutritious evidence. The reviewer should distinguish mere disruption from
interest that sustains attention, and protect useful awkwardness without
romanticizing arbitrary mess. No beauty score, polishing mandate or demand for
uniform success. Ian's “badness invites thought, something else holds it” framing
and early AARON reference are in the skill's aesthetic brief.

Calibrate the reviewer before relying heavily on it: neutrally labelled sheets,
then a small set of tidied/disrupted/passage-removed variants. Read images first,
then sequences and mechanism explanations. Judge whether it notices defensible
relationships and admits uncertainty, not whether it selects the lead's winner.
The wrapup includes a small forward-test report if Sol completes; that alone
is not a validated aesthetic judge. See `docs/reviews/drawing-review-skill-trial.md`.

## Proposed working sequence

1. Establish and preserve the first-version baseline, honestly documenting
   recovery/reconstruction. Test exact replay and event semantics.
2. Improve geometry/proportions separately; introduce an occasional homeostat
   gesture. Retain the baseline for comparison.
3. Explore element containment/whole-element fitting and distinct parameter
   meanings. Keep the single resolve path and stable intervention coordinates.
4. Test a small set of competing relational responses against the simpler mode,
   using fixed prefixes and interventions where causal comparisons are claimed.
5. Give Sol whole iteration sheets plus close views midway. Read its evidence,
   retain meaningful disagreements, then make one focused revision.
6. Verify, preserve recipes and images including weak cases, and hand the bench
   back for actual alternating use. A paper test remains a later user choice.

## Where things are

- Replay/parameters: `axibridge/sources/second_reading.py`
- Descriptors/attention and original analytic helpers: `_second_reading.py`
- Opening and capture smoothing: `_second_reading_gestures.py`
- Current response construction: `_second_reading_responses.py`
- Current optional crossing/accent context: `_second_reading_encounters.py`
- Bench frontend: `axibridge/static/js/second_reading_bench.js`
- Module/preview contracts: `docs/plans/second-reading.md`, `docs/MODULES.md`
- Session insights: `docs/IDEAS-drawing-machine-session-2026-09-05.md`
- Studies: `shots/second-reading-{0905,organic-0905,mixed-0905,response-0905,encounters-0905}/`
- Reproduction: `tools/second_reading_{study,interventions,encounters}.py`. Defaults
  now write `shots/second-reading-latest/`; pass `--output` for a new dated study.
  Do not overwrite the original baseline evidence with current-engine output.
- Tests: `tests/test_second_reading.py`, Second Reading cases in `tests/test_acceptance_ui.py`

Read root `CLAUDE.md`, `ARCHITECTURE.md`, `docs/MODULES.md` as required by AGENTS.
Tests use the pinned `.venv`; rebuild frontend after edits. Use temporary test
servers with isolated config/no autoconnect. Leave Ian's running app and unsaved
work alone. Never send hardware commands as part of this experiment.


## Wrapup verification

1,239 tests passed on 6 September; frontend build and typecheck passed. Separate
Playwright capture/Keep/Resume smoke: three passed on a throwaway isolated server,
terminated by fixture teardown. All three study scripts ran successfully into a
temporary output directory after their defaults were changed to protect historical
studies. Skill validator passed; Sol's small independent forward-test and the
lead's critique are in `docs/reviews/`. No hardware or remote push was performed.
