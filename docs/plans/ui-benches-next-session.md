# Next session: Compose layout and an open bench architecture

Agreed with Ian on 7 September 2026 after the UI review, cosmetics pass and
10-question design interview. This is a brief for design work, not approval to
implement a new layout or architecture.

## Start here

1. Read `CLAUDE.md`, `ARCHITECTURE.md` and `docs/MODULES.md`, then the current
   `STATUS.md` and `HANDOFF.md`.
2. Read the [holistic review](../reviews/ui-review-2026-09-07/REVIEW.md) and
   [cosmetics evidence](../reviews/ui-review-2026-09-07/cosmetics/README.md).
   The review's proposals are not all accepted decisions.
3. Produce concrete layout mockups for Compose, Second Reading and Homeostat,
   together with a basic open bench architecture proposal. Show the common
   structure and the generator-specific differences. Discuss radical changes
   with Ian before implementation.

## Agreed design direction

1. Improve **space and hierarchy** next. The intended feel is an **artist's
   instrument**: precise and tactile, with room for uncertainty. Preserve surprise
   in the human–machine exchange; experimental character need not make the
   interface difficult to understand.
2. Design Compose and benches together. Use predictable, collapsible control
   groups and retain a compact persistent layer list in Compose, expandable when
   composition needs it.
3. At small window sizes, give benches' drawing areas priority. In Compose,
   keep more editing controls exposed for precise adjustment. Do not impose one
   identical density policy on both.
4. Give bench-oriented generators a clearly labelled **Benches group within the
   existing generator picker**. A top-level Benches tab was not selected.
5. Broader reorganisation of sections, labels and interaction sequences is
   allowed as a design exploration. Ian said: “run it by me if the change is too
   radical.” Bring concrete, reviewable mockups and trade-offs, not an abstract
   approval question.
6. An expandable popup is a candidate, not a settled requirement. Ian is open
   to presentation options. Bench identity must survive changes in presentation.
7. Retain Flexoki and offline Roboto Mono. Avoid treating this as permission
   for a generator-policy change or aesthetic scoring system.

## Open architecture brief

Ian's requirement: “I want them to be able to have complex interactions with
the rest of the program eventually, but still consider them all benches.”

A bench is a coherent family of working environments, with specific interactions
for its generator. Do not reduce every bench to a standard parameter form and
playback controls, or make Second Reading the definition of all benches.

The proposal should settle the following, using concrete examples from Second
Reading and Homeostat and checking compatibility with the other current benches:

1. **Identity and discovery:** what makes something a bench; how it registers,
   exposes capabilities and appears in the picker. Examine whether bench
   identity should be independent of having a time axis.
2. **Shared lifecycle and presentation:** opening, returning, closing and
   disposing of work; what belongs to the shared shell versus each bench;
   whether compact/expanded presentation affects any working state.
3. **Specific interactions:** how a bench supplies its own controls, input
   handling, drawing interactions and feedback without accumulating special
   cases in the shared host.
4. **Application exchange:** extension points for future interaction with layers,
   selection, timeline and other application services. Distinguish observations
   from explicit commands that change the project. Use a few concrete scenarios
   to test the model; do not implement every imagined integration now.
5. **State and history:** who owns working state, alternatives and saved state;
   preservation across closing/reopening; local versus project undo; explicit
   creation or modification of project content and failure/cancellation handling.
6. **Evolution:** the smallest useful common contract, a migration path for
   current benches, and checks that a new specialised bench can join the family
   without rewriting the host. Assess existing vanilla modules before proposing
   a framework migration.

These are decisions to resolve next session, not API contracts already agreed.
An extensible architecture should make richer interactions possible without
committing this next pass to implementing them all.

## Current implementation evidence

At cosmetics commit `0d97df5`, `compose.js` offers Bench based on `moduleAxis`;
`process.js` supplies the generic process popup and specialised Second Reading
routing. Sources with explicit time axes include Second Reading, Homeostat,
Venation and Grammar. The effective-axis fallback also matters when defining
future membership; do not turn this example list into a hard-coded registry.

The source descriptor already has `time_axis` and `bench_capabilities`; Second
Reading declares intervention and branching capabilities. Capabilities alone do
not supply its event contract. Current generic Watch is read-only, and the
ordinary bench creates a layer rather than mutating an existing layer. Preserve
these current behaviours unless a reviewed design explicitly changes them.
Generator purity, the shared resolve path and existing coordinate contracts
remain load-bearing. Future project changes should be deliberate application
operations, not hidden generator side effects.

## Review and acceptance for the design work

Show desktop and compact layouts, collapsed and expanded control groups, and
how the user moves between Compose and a bench without losing context. Include
Second Reading's human turn/continue/alternative/keep cycle and Homeostat's
parameter/playback/telemetry workflow. Explain what stays common and what differs.

Deliver the mockups plus the architecture proposal and a bounded implementation
sequence. Review radical changes with Ian before coding. This is the next
session's work; no mockup or architecture implementation is claimed complete.

## Verified baseline and remaining judgement

The cosmetics pass is committed as `0d97df5`; the review is `7bc46fb`. Its recorded
verification was 1,267 hardware-free tests passing, followed by all 96 UI tests
passing after final label/hover polish; build, typecheck and isolated built/source
browser checks passed. Those results belong to the implementation session and
were not rerun for this documentation-only wrap-up.

Native macOS/Pi appearance, physical input feel and paper output still need
Ian's judgement. No push, application restart or hardware action is part of this
handoff. The pre-existing untracked `.agents/skills/pi/` is unrelated; leave it
alone. Broader review findings remain open unless explicitly covered above.
