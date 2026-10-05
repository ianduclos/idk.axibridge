# Territory02 — revised agent loop

Adopted on 5 October after Ian asked to change the loop. This is the operating
protocol for the next study. The workflow has changed; a new drawing round has
not been run. The [brainstorm](territory02-brainstorm-2026-10-05.html) remains a
set of possibilities, not a requirement to implement every mechanism.

**The unit of work is a particular drawing and its revisions.** Three makers
receive the same starting states, make consequential whole-sheet proposals,
and return actual geometry. The primary owns direction and integration; a
separate Sol reads the results. Ian sees the first small sheet before round two.
No automatic convergence, winner selection or production replacement.

## 1. Prepare a small, shared starting set

The primary inspects and freezes two actual drawings from the rough
three-material studies, including a less resolved case. Select them by looking
at whole drawings and details; record paths, seeds, source hashes and why each
is useful. Earlier enthusiasm for a family does not establish a preferred seed.
All three makers receive both identical states and full-resolution views.

Use the existing 0.1 mm stroke and physical page dimensions. A maker may change
most of a drawing, remove inherited stars, replace paths, change fills, cut,
reconnect or abandon an edit. Retain the starting state and intermediate files.
There is no preservation quota and no required number of bulbs or corners.
References describe possibilities; do not copy Ian's drawn contours.

## 2. Three briefs, different decisions

These are starting restrictions for one small round, not permanent styles.
Each maker owns a separate folder under `tools/territory02/editor-loop/` and
must not modify shared renderers, other makers' files, old studies or production.
Use Sol for the bounded maker assignments; at most three supporting agents run
at once. Makers do not delegate. The primary sets contracts and inspects work.

| Maker | Opening move | Freedom after that move | Failure to watch |
|---|---|---|---|
| A — material | Begin by editing an actual rough body: carve, compact, remove, split or expose it. | Rebuild smooth edges or passages wherever the changed material suggests them; alter the whole sheet. | A textured blob with decorative holes; grain pasted along the familiar curves. |
| B — connections | Change what connects, continues, stops or disappears in the existing geometry. | Cut and exchange continuations; merge boundaries; rearrange or replace material and paths. | Spaghetti, ornamental knots, or an unchanged drawing with extra junctions. |
| C — composition | Reorganize groups at the scale of the sheet: placement, scale, omission or overlap. | Introduce an independent smooth or angular construction, allow unequal dominance, redraw groups. | A collage of isolated stickers or the same silhouette under a new arrangement. |

Shared dispatch brief:

> Inspect both starting drawings at whole-sheet and close scale. For each,
> make one substantial proposal and one revision in response to looking at
> that proposal. You may keep the earlier stage if the revision loses something.
> Work with actual geometry, using a local script or explicit edits as useful;
> do not first build a reusable generator. Render and inspect each stage.
> Return both stages, your chosen stage, and at most three sentences about
> what changed, what may have been lost, and what still feels repetitive.
> A direction may fail. Do not compensate with an elaborate explanation.

Each maker delivers four edited states in total: two inputs × two stages.
Only one chosen stage per input enters the first contact sheet. Preserve all
four for population and history review. If a brief proves unproductive, record
that rather than inventing a success. Use only the smallest representation the
edit needs; there is no shared new engine to build yet.

## 3. Assemble evidence before naming mechanisms

The primary checks finite, bounded, reproducible geometry and consistent stroke
and framing. Keep these checks separate from artistic judgement. Record page
scale, clipping, accumulated ink and any export limitation; do not equate those
measurements with quality. No physical plotting is part of this screen study.

The first contact sheet contains **eight whole drawings**: six maker choices,
an untouched earlier reference, and a previously weak result. Give all cells
stable neutral IDs and keep the mapping in a separate manifest. Randomize their
order once and retain it across review. The full-resolution drawings must be
available alongside the sheet: thin lines cannot be judged from thumbnails alone.
Controls test the review; they do not establish objective winners or losers.

Archive the twelve edited states and two inputs in a separate history sheet.
Do not build a new gallery interface before this first checkpoint. Reuse a
simple HTML sheet with full-size links and a short accompanying reading.

## 4. Review in two passes

Once the makers finish, use one separate `gpt-5.6-sol` reviewer under the
[drawing-review skill](../../.agents/skills/drawing-review/SKILL.md). Give it
actual images, neutral IDs and the decision under review. Withhold maker briefs,
preferences, identities and control labels for its initial reading where possible.
Use a small unlabeled pair with an omitted or moved passage to calibrate its
reasoning; disclose the change afterward. Record any prior exposure honestly.

First read whole sheets and full-size views. Ask:

- Which drawings invite another look, and what visibly causes that? None is a valid answer.
- Which relationships recur across the set even when the silhouettes differ?
- Which awkward passage would you protect? What is weak or still uncertain?

Then reveal starting states, both stages, relevant close views and calibration
changes. Ask what the edits gained or lost, and whether the history changes the
initial reading. Mechanism descriptions come last. A crop can support a local
observation; it cannot establish that the whole sheet works. Do not require
praise for every maker, beauty scores or agreement with the primary.

The primary inspects all stages too, retains disagreements and rejects unsupported
attribution. A compelling result can remain causally unexplained; a controlled
comparison can be informative while aesthetically dull.

## 5. Show Ian the first sheet, then branch

Deliver the eight-cell HTML sheet, full-size access and a short reading before
investing in another round. Invite responses to concrete cells or passages:
keep, undo, intensify, combine provisionally, or leave alone. This checkpoint
implements Ian's request to see evidence before choosing convergence. Silence
selects nothing. The first round is complete at this handoff.

Round two follows Ian's response rather than an automatic three-maker repeat.
The primary assigns edits to named drawing states and visible relationships,
incorporating both his response and the independent critique. A maker may switch
briefs, retain a failure, or fork two incompatible continuations. The number of
branches follows the useful questions; it need not stay three.

Repeat the neutral whole-sheet review, then inspect histories. Keep unchanged
ancestors in the comparison so accumulating complexity cannot masquerade as
progress. End with separate results and possible convergence strategies, each
linked to specific evidence and a risk of loss. Ian chooses whether to combine.

## 6. Generalize only after examples warrant it

A useful individual drawing does not prove a useful generator. If Ian wants a
repeatable instrument after these edits, identify which relationships should
survive and test the smallest rule set on unseen starting states. Freeze the
rules before that test and show the entire test population, including failures.
Free editing and this generalization test answer different questions.

The record for each state needs only: stable ID, parent ID, maker, source input,
reproduction command or saved editable geometry, render path, brief edit note,
and any reviewer/user response. Store this beside the study; preserve branches
instead of overwriting earlier results. Reports are HTML. Do not infer a new
production default, a merge of directions, or paper success from screen review.
