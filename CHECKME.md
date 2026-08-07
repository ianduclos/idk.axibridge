# Check when you're home — 2026-08-07

Everything below passed its tests. None of it has passed *your eyes*, and the
first group is the part no test here can reach. Delete this file once you've
been through it.

## Only verified against fakes — most likely to be wrong

**Relaunch AxiBridge (quit fully, not a reload) for anything in this group.**

- **Machine menu greying.** With nothing connected the whole Machine menu
  should be grey. Connect the simulator: pen up/down and the origin items
  should come alive, jog too (the simulator advertises it). Verified only
  against real AppKit objects and a faked bridge — never a real menu.
- **Menu checkmarks.** View should tick your current orientation, render mode
  and whichever overlays are on, and the ticks should follow when you change
  them from anywhere.
- **Edit / View merged into the system menus.** Undo/Redo above Cut/Copy/Paste;
  Portrait/Landscape above Enter Full Screen. No duplicate Edit or View.
- If any of this misbehaves: `cat ~/Library/Logs/axibridge-shell.log` — it
  records the merge, the resulting bar, every state sync and every swallowed
  exception. That is the file that turned four silent failures into one.

## Verified against the simulator only — real machine untested

- **The status line during a plot.** Progress, time left, X/Y, pen up/down,
  and Pause/Resume/Stop, under the sheet, on every tab.
- **est / ink / lifts must survive the job** — it used to be overwritten by
  "remaining …" mid-plot and never restored.
- **Plot by pen.** The target picker now offers `pen: <name> (N layers)`.
  Worth one real multi-pen sheet: pick a pen, plot, swap, pick the next.

## New since you last looked — all taste, mined from the August review

- **Sliders are faders now**: 12px groove, machined cap, and the fill is
  graphite instead of `--live`. That last bit was a real bug — three sliders
  on screen all claimed the selection colour, i.e. "you are here", at once.
- **The canvas well has a lamp**: brightness falls off from the sheet to the
  frame. The old page-wide gradient is gone.
- **Sentence case below panel level** (`Fine tuning`, `Placement`, `Pen &
  occlusion`), body ink one step quieter, panel headings unchanged.
- **The window title says `axibridge — <project>`.**

## Verified in a browser — just taste, not correctness

- **The toolbar** is one row of tools and zoom-fit. Does losing the overlays
  to the View menu cost you anything in practice?
- **Layer list:** drag to reorder (drop line shows where it lands), ⌥-drag to
  duplicate, double-click a name to rename in place. The ↑ ↓ buttons are gone.
- **Occlusion channels** are two A/B/C/D segmented groups instead of eight
  tickboxes.
- **Plot tab** is five panels; the machine ones are in Settings now.

## Known and deliberate

- Below ~900px window width the canvas top edge shifts 10px. That is the
  HEADER wrapping, not the toolbar, at a width where the canvas is ~260px.
- Jog is a menu item now on your ruling — use it that way, then tell me
  whether it earns its place.
