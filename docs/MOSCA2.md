# Mosca 2

Mosca 2 combines a page composer, Territory, the earlier flowing drawings, and
a fresh response from the fixed-weight Mosca fly model. Open **Generate →
Mosca 2 → Bench**. The original Mosca recording bench remains available.

1. Load one of six starting pieces, or generate a Territory and add one of
   seven preserved flowing drawings. Select a part to move, rotate, scale,
   hide or remove it.
2. Click or drag the arrow on the sheet to place the fly and set its heading.
   Set seed, duration, gesture size and contact strength. Contact at zero is
   the control: the current page supplies no tactile drive.
3. Run a fresh bout. The page is fixed during the run; progress displays its
   growing response. Cancel discards the pending response.
4. Inspect Before, Added only and Combined in history. Undo last response
   returns to the previous page. Keep saves the exact visible geometry as a
   normal AxiBridge layer; select it and Resume to reopen an independent draft.
   Save the AxiBridge project to retain the composition between sessions.

Resume restores the page, settings and recorded exchanges. It does **not**
restore a neural checkpoint. Each Run starts a fresh brain with the chosen
seed. Earlier parts and the new ink both feed the fly during that bout.

## What the brain controls

The unchanged Mosca network produces left/right motor activity, which drives
the earlier flowing body (`speed_per_hz=.0009`, `turn_per_hz=.0064`,
`trace_tau=20`). An authored DNg13 decoder chooses drawing or pen lift at
100 ms intervals, with 300 ms persistence and 1000 ms minimum hold. The
flowing renderer adds bands and echoes to the resulting spine in 500 ms batches.
These mappings are designed; the network has not learned composition.

The page is sensed at the original two front sensor positions, expressed in
paper millimetres. Gesture size scales the body, sensors and flowing treatment
together. Nearby ink stimulates the two tactile populations independently;
own ink younger than 200 ms is ignored. Outside-paper motion lifts the pen,
and clipped strokes never connect a departure to a later re-entry. Placement
uses a 2 mm margin inside the physical 300 × 218 mm bed.

Six starting pieces are authored arrangements of recorded model output and
Territory geometry. They are source material, not evidence that the brain
composed those arrangements. [The earlier studies](MOSCA-TERRITORY-STUDIES.md)
retain the source lineage and review history.

## Runtime and portability

The neural job runs in a separate cancellable process. It reads Mosca source
and data from `AXIBRIDGE_MOSCA_DIR` (the existing mosca-draw checkout by default),
uses Node for the preserved flowing renderer, and does not install packages.
`AXIBRIDGE_MOSCA2_PYTHON` and `AXIBRIDGE_MOSCA2_NODE` can select compatible
existing runtimes. Otherwise Python discovery tries the application interpreter
and compatible existing cached environments; Node discovery uses PATH and
usual local install locations. Missing runtime disables new bouts, while
materials, editing, Keep, saved projects and plotting remain available.

One job runs at a time, with 1–12 simulated seconds and an eight-minute wall
timeout. Closing the bench cancels its pending run. Output is validated before
completion; project mutation occurs only through the usual Keep endpoint.
Saved parts and history contain exact bounded geometry, settings, events and
provenance. No model files are needed to reopen or resolve them. Geometry
budgets are 32 parts, 12 exchanges, 50,000 strokes and 500,000 total stored
points; the input page for a new run has a 250,000-point ceiling.

The single normal AxiBridge resolve pipeline still owns preview and plotting.
The bench itself never sends motion commands.

## Validation and remaining acceptance

A real six-second paired run with seed 31, the same page and start, and
contact strength 100 versus zero changed both motor/spike hashes and pen-lift
time (0 versus 3300 ms). Brain fingerprint and weight hash were identical.
This demonstrates consequential input to this model, not intelligence,
learning, or a general improvement in composition. Evidence is preserved in
the study lab's `mosca2-delivery` directory alongside screenshots.

A further run removed only a 6 mm line beside the starting point, keeping seed
31 and contact 100. Motor output changed again (about 633 versus 584 mm of
deposited ink), with identical source and weight hashes. This verifies sensitivity
to local page geometry as well as contact strength. The new response was kept,
exported and resumed through the real browser; all 374 combined strokes resolve
at their exact physical coordinates. The six-second response is a compact
local passage, not an automatically composed whole page.

Native-window usability and plotted results remain for Ian to judge. The
next useful artistic experiment is a matched page intervention: same seed
and start, move a single existing passage, and compare the resulting exchange
against contact-off. Keep weak and uneventful runs in that comparison.
