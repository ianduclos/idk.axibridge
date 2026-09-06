# Drawing machine — session insights, 2026-09-05

Brainstorm with Ian and Astra, following `BRIEF-new-generator.md` and the
earlier generator passes. This records a developing direction, not an
implementation brief or a new set of aesthetic rules. No generator or bench
changes were made during the initial brainstorm. The follow-on implementation
is distinguished from that discussion below.

## Ian's clarifications — carry these forward

- **Potent abstraction, with the appearance of deliberation.** Figuration is
  unnecessary and, if present, should be slight. “Almost something” is the
  useful territory: half the time the association cannot be named; the other
  half, naming it would be a stretch.
- **Oehlen is an aesthetic vector, not a recipe.** Consider what the images
  do, their context and relationships. Do not reverse-engineer their surface
  techniques into a generator. The ambition is to go beyond the reference,
  not reproduce its vocabulary.
- **Alternating human and machine activity sounds right.** The bench is
  intended as a more interactive, flexible surface for involved generators.
  Ian explicitly welcomes modifying, optimising and developing it for this
  purpose or others. That permission is not a decision to implement every
  interaction proposed here.
- **The brief's “rejected” list is not a blacklist.** Repetition, texture,
  scatter, prettiness and other supposedly excluded techniques can produce
  excellent results when well executed. Legible history is interesting, but
  not a universal requirement or guarantee of quality.
- **Do not inherit the previous model's aesthetic conclusions as facts.**
  In particular, its account of the homeostat's aesthetic achievement is
  provisional. Ian finds the present result weak, despite selecting some
  promising captures. “We're doing centaur work here.”
- **Focus on one generator.** The original request favours sustained work on
  a single generator, alongside a critique of how the roadmap chooses and
  frames ideas.

## Reference and reading

Ian supplied `8print.jpg`, an Oehlen reference:
`/Users/ianduclos/_SecondBrain/03_Resources/Visual Assets/Visual References/8print.jpg`.
The file remains at that location; it was not copied into this repository.

The following is Astra's reading of the image, not a claim about the artist's
intent or an interpretation Ian has explicitly endorsed.

The image repeatedly changes where its authority seems to lie. The heavy
bent black element asserts itself without settling the composition. Finer
structures cross its territory and establish other readings of space. Some
passages suggest depth; others insist on the surface. Local continuities do
not assemble into one consistent world.

Long thin lines have reach disproportionate to their weight. Congested
passages hold attention without becoming centres that organise everything
else. Unequal elements retain independence while becoming consequential to
one another. They do not all negotiate, harmonise or acknowledge the same
situation.

This suggests an important distinction: **appearance of deliberation need
not mean that every mark visibly responds to every other mark.** Insistence,
interruption, disregard and shifts in dominance can also carry it. A machine
whose contradictions are always dutiful responses could become aesthetically
overly obedient.

## Critique of the inherited framing

These are Astra's arguments, offered for further testing.

1. **A mechanism's name does not establish its aesthetic consequence.**
   Fatigue does not automatically give meaningful history; crisis does not
   automatically make marks read as decisions; a budget does not automatically
   create stakes. A distance budget may merely shorten a drawing. Prediction
   error may merely produce restless texture.
2. **Permanence already supplies consequences.** An early mark can enable or
   constrain later decisions without the machine simulating distress.
3. **Continuity is an advantage, not a law.** Pen lifts can articulate a
   passage, preserve a gap or allow a return. Compulsory continuity risks
   turning every relationship into a connecting line.
4. **Parameter smoothness is not an aesthetic disqualification.** Individual
   results can be specific within a smoothly varying family. Discontinuity can
   be just as generic.
5. **Resemblance to a PNG is not a useful medium test.** A preview should
   resemble the plot. Physical scale, ink accumulation, registration,
   sequence and permanence are more useful concerns.
6. **The relations critique is promising but insufficient.** “First-order
   statistics” is loose terminology for the homeostat's measures. The more
   useful criticism is that it remembers activity without representing what
   that activity has established. Adding parallelism and enclosure scores
   alone could still produce a sophisticated pattern arranger.

The two homeostat captures inspected were
`shots/homeostat-bench-0904/01-knots-and-a-long-travel.png` and
`02-two-masses-one-thread.png`. Astra saw a promising contrast between knots
and spacious travel, but little visible evidence of the claimed regime
transitions. The differences in density largely retained one handwriting.
This is a reading of those captures, not an exhaustive evaluation of the
generator or a paper test.

## How the generator proposal changed during the conversation

### Initial proposal: reinterpret its own marks

Working name **Second Reading**, not an agreed module name. A machine would
retain several geometric interpretations of a passage, develop one, then
reconsider it as later marks change the drawing. Ink stays; interpretation
changes. It would remember curves, junctions, intervals, open enclosures and
alternative groupings rather than only occupancy or turn statistics.

The initial examples leaned toward bodies, folds, attachments and emergent
things. Ian's clarification exposed a risk: this could become a competent
producer of ambiguous little organisms. That is not the desired destination.

### Revised emphasis: change what matters in the drawing

Retain reinterpretation, but let what changes be the role of a passage:
background, interruption, scaffold, obstruction or main event. Object
recognition is not necessary.

The proposed central activity is **developing and displacing commitments**:

- Establish something strongly enough for an expectation to form.
- Pursue it beyond the first interesting mark.
- Make an action that changes its standing in the whole drawing.
- Decide what to develop next, including what to leave stranded.

This is a possible behaviour, not a mandatory dramatic arc. Always creating
order and then disrupting it would become another predictable trick.

An action may be one stroke, a sustained family of marks, or a return to a
distant passage. One generator needs a range of action sizes; composition
should not depend entirely on millimetre-by-millimetre steering discovering
larger structure by accident.

**Selective attention** is the key candidate capability. The machine can
pursue one relationship while disregarding another: acknowledge a rhythm but
ignore its boundary; cross a dense area without changing behaviour, then
become attentive to an almost empty one. Independence and responsiveness
should both remain available.

There is no implemented mechanism for this yet. Intersections and spacing
are relatively direct to measure; dominance and productive indifference are
much harder. Naming these qualities does not implement them. A few concrete
operations, judged through drawings, are a better starting point than a
purported universal score for good abstraction.

## The bench: verified present state and proposed direction

Inspection was of `axibridge/static/js/process.js`, the popup markup in
`static/index.html`, its CSS, and related code. No app was listening on port
2942. **The bench was not exercised live in this session.**

Current implementation:

- Bench mode provides generator parameters, seed reroll, playback, scrubbing
  and creation of a new layer at the selected moment. Watch mode inspects a
  committed layer without editing it.
- Changing a non-time parameter regenerates the trajectory; it does not
  preserve the past and alter only the continuation.
- The visible graph records **point count at visited axis positions**. It
  does not display the process's internal telemetry, despite the brief
  describing that capability. Trajectories retain telemetry, but the current
  bench renderer does not use it.

Proposed interactions for alternating human and machine work:

- **Keep this moment:** preserve an exact, recoverable state before trying
  something else.
- **Continue from here:** explore a different continuation with earlier
  marks preserved.
- **Take a turn:** add a human stroke or passage, then let the machine
  encounter the changed drawing.
- **Direct attention:** select something to develop, revisit or leave alone.
- **Compare continuations:** inspect a few alternatives side by side.

These are not a final interface specification. For example, “leave alone”
could mean preserving marks or preserving the space around them; those have
different consequences. Recorded interventions are a candidate route to
reproducible runs, already suggested in `IDEAS-pass4.md`, but the event model,
continuation semantics and caching have not been designed here.

The artistic purpose is to let Ian change the terms of the machine's
activity, then give it enough independence to offer something he would not
already have drawn. Selection among completed outputs is only one part of
that relationship.

## Implications for the roadmap

Astra's proposed change in priorities, not an edit to `ROADMAP.md`:

- Reuse, cheap implementation and general applicability are engineering
  advantages after an artistic hypothesis earns attention. “Effect first,”
  “nearly free” and “shortest hop” should not by themselves select the next
  artistic investigation.
- The core-figure proposal's concern with established structure is useful,
  but its figurative vocabulary should not govern this direction.
- Bring human intervention forward as part of the experiment, rather than
  postponing it until an autonomous generator is considered complete.
- Keep field techniques and morphing available without treating their
  accumulation as evidence of growing drawing intelligence.
- Tighten the loop between making, retaining, comparing and plotting work.
  The homeostat bench README says its selected captures cannot be exactly
  regenerated. Preserving discoveries is a concrete priority.

## Candidate first experiment and open questions

Use **one shared opening and several continuations from the same generator**.
Ask whether a continuation materially changes how the opening reads while
retaining enough independence to surprise us. No experiment was run here.

Useful checks proposed during the conversation:

- Point to a later intervention that changes the reading of an earlier
  passage.
- Change an opening mark and look for a specific downstream consequence,
  rather than unrelated random changes everywhere.
- Judge the final sheet without telemetry; playback may deepen it but should
  not be needed to rescue it.
- Begin with sparse enough work that density cannot conceal a weak mechanism.
  This is an experimental tactic, not a prohibition on dense results.

Still unresolved: the actual mark and action vocabulary; how attention is
chosen and sustained; how larger compositional consequences are represented;
how the machine leaves a passage unfinished or stops; and how human input
changes a continuation. The artistic promise is not yet an algorithm.

## Related context

- `BRIEF-new-generator.md` — inherited brief, now qualified by Ian's words above.
- `IDEAS-generators.md` — intentional line, rehearsal and earlier agents.
- `IDEAS-oehlen-pass.md` — regime collision and reference interpretation.
- `IDEAS-aaron-pass.md` — structure and thing-like organisation.
- `IDEAS-pass4.md` — cybernetic framing, processes and recorded intervention.
- `../shots/homeostat-bench-0904/README.md` — bench observations and capture gap.

## Implementation follow-on, 2026-09-05

Ian subsequently selected and authorised an interactive first slice. It is
implemented as `second_reading`: four passage actions, recorded human turns,
future control changes and preserved continuations, with a specialised bench.
The operative contracts are in `plans/second-reading.md`; actual comparison
drawings, timings and visual criticism are in
`../shots/second-reading-0905/README.md`.

The experiment now exists, but the artistic argument remains open. The
stronger angular cases show that an intervention can redirect subsequent
relationships; several curved cases stay quiet or become repeated motifs.
The primary agent tuned two sources of negligible marks within the original
vocabulary, retained weak cases, and proposes Ian's own interventions as the
next evidence. Nothing has been plotted.


## Feedback: between geometry and the homeostat

Ian liked the interaction but found the first machine drawings too geometric,
symmetric and predictable. He requested light smoothing of human input while
keeping deliberate corners. The first organic revision was too close to the
homeostat. His correction was to work between these poles and introduce one
or two new grammars, not to keep amplifying organic motion.

Implemented mixed construction, fold and graft actions, and corner-aware
capture smoothing. The six-seed comparison retains weak cases rather than
presenting a chosen highlight as representative. The key finding is that new
vocabulary can still become decorative repetition under a held commitment.
Seed 12 A changes scale and context; seed 23 mostly elaborates one cluster.
Next test: more selective continuation of a relationship and better reasons
to leave a target, before adding more action types. Full visual findings and
recipes: `shots/second-reading-mixed-0905/README.md`.

## The priority is perceptible novelty in the exchange

Ian clarified that the first version's responsiveness was better even though
its shapes and tight parallel lines were unsatisfying. The mixed revision
mostly yielded similar, entropic outcomes. Organic-versus-geometric was an
inadequate axis for deciding what to improve.

The new references sharpen the distinction: shaped empty space; a line that
changes roles; almost-bodies; and passages with different authority. These are
readings of the references, not recipes for reproducing their surface techniques.
The last Oehlen painting exceeds this instrument's medium; its incompatible
spatial and material claims remain useful context without promising simulation.

Ian endorsed the reading, with a correction: the machine should also respond
(or decline to respond) to what is already there, not automatically prioritize
his latest stroke. The aim is a legible but surprising consequence that offers
him another move. Unrelated variety is insufficient.

Implemented a response revision: held attention can change operation, selective
habituation lowers the weight of repeated target/action pairs, and older material
remains eligible. Direct geometry now carries/changes contour relationships,
opens space, and gives short passages physical weight. Retired fold/graft response
templates. The fixed-prefix intervention study is the main evidence:
`shots/second-reading-response-0905/README.md`. Root owns this revision and visual
judgement; no further supporting agent was needed for this bounded experiment.

## Continue through local encounters

Ian found the response revision interesting and asked to continue. This pass
keeps that direction and tests a narrower idea: the same new contour can give
an existing line greater authority by yielding at their crossing. A short
physical accent can also move to an actual encounter between passages. Neither
response is compulsory and no earlier paths are rewritten.

A strict comparison now freezes the drawing, target, operation and random
stream while enabling/disabling contextual response. This is stronger evidence
than comparing outputs of different whole-engine revisions from the same seed:
the latter changes the prefix too. The local effect is perceptible, but the
whole sheets still share too much fluent contour. Do not confuse an intelligible
mechanism with artistic success. Evidence: `shots/second-reading-encounters-0905/README.md`.

## Closing correction and next-session agreement — 6 September

Ian's verdict supersedes the positive readings earlier in this log: little
progress, slightly better than version 2, less responsive than the first version.
Keep the interactive bench and smoothing; recover that first response baseline,
improve unequal proportions, and include occasional homeostat gestures. Save
the tapered/accumulating finish for a later effect. Explore smarter selective
response to existing material and distinct Attention/Departure/Scale controls.

The workflow makes elements on the bench for later composition on the main
canvas. Hard clipping is often a liability. Compare contained edge-aware forms
with a wider working area and whole-element fitting, without separately shrinking
each reply or moving the view under a human stroke. These are next experiments,
not already implemented capabilities.

The reviewer must attempt the intuitive side of coherence: apparent “badness”
can invite thought, but is not sufficient to sustain interest. A sheet need not
produce interesting figures all the time; quiet and failed stages are valuable
evidence. Project skill `.agents/skills/drawing-review/SKILL.md` records this
role. An initial blind Sol sheet review is retained in `docs/reviews/`; it was
useful but made a composite-provenance error, now addressed in the skill.
Full calibration remains work for the next session. The primary agent stays
in the driver's seat. Start at `docs/plans/second-reading-next-session.md`.
