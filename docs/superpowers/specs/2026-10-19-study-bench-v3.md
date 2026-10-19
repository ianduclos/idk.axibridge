# Study bench v3 — usability, UI, dynamism (brainstorm, 2026-10-19)

Ian, 2026-10-19: "go in the study bench and improve the usability, ui, and
dynamism of the studies". When choosing improvements: "Randomize hands,
randomize seeds. Maybe before you start brainstorm how the ui can be nicer to
use. I tried some studies and some faders didnt seem to change anything."
He picked: the study gallery picker, devices as an optional layer, a faster and
clearer preview. New studies: arch, listen, river_zoom (Sol 6.1 build).

This bench is the last before the synthesis bench, so it doubles as a
rehearsal for that one's interaction: browse, vary, lock, compare, keep.

## What's wrong now (observed in a test app on a temporary port)

1. **Dead faders.** An audit moved every control of every study to other
   values and checked whether the drawing changed (`fader_audit` below). Most
   dead controls are conditional: in Hand Drift, seven of 22 controls (tempo,
   wrist nib, amount, nib width, mass width, nib angle, ink) act only when
   Regimes is on, which is off by default. The UI shows them as if they
   worked.
2. **Choosing a study** is a bare dropdown of 28 names. You choose by name,
   not by eye.
3. **Variation is one step at a time.** "Next seed" adds one; there is no
   random, no random hands, no way to see several at once.
4. **The layout fights the drawing.** It opens as a modal with a small canvas.
   The controls sit in a narrow column under presets (presets come before the
   study picker). Seed is at the bottom of a long scroll.
5. **Slow studies look frozen.** Shape atlas takes about 76 s and Ledger about
   38 s. The other 26 take under 3 s.
6. **The preview is ink-black** for every study except the chorus. Multi-pen
   studies lose their colour structure, the thing Ian liked in ccolour.

## Brainstorm: moves

**A. Every control is alive, or says why not.** Studies declare
dependencies (`"when": {"key": "regimes", "not": "off"}`). The UI dims a
control that does nothing now, with the reason ("acts when Regimes is on").
A test asserts every non-conditional control changes the drawing, as the
alive test does for the new studies. Controls found truly dead are removed.

**B. Study gallery.** A full-panel grid of cached thumbnails (rendered once
per study version on the server, then from disk), grouped by family: Hands
and drift, Measurement, Several voices, Swell, After Oehlen, Rivers,
Composers. Each card shows the name, one line of Ian's own words from the
study's notes, and a slow-study badge. Clicking a card opens that study. The
dropdown stays as the compact form.

**C. Dice.** One die next to the seed (random, not +1) and one beside each
hand control (a random hand from the library). "Shuffle" varies every
unlocked control within its bounds. Each control gets a lock, so you can
shuffle the rest around what you like. All of it is undoable.

**D. A history strip.** The last 12 previews as small thumbnails under the
canvas; click one to go back to it. Variation becomes browsable without
extra server work, since the thumbnails are the previews already drawn.

**E. Layout.** Opens full-screen, canvas first. The right column holds, in
order: study (name + gallery button), seed + dice + shuffle, the study's
controls (conditional ones dimmed), Measure (devices), then Advanced
(presets, save as new study, recipe) collapsed. Sliders show their value as
you drag; studies under 1 s preview live while dragging (throttled), slower
ones on release.

**F. Preview.** Each ink in its pen colour, at its width. The previous
drawing stays visible, dimmed, while the next one draws, with an elapsed
timer for slow studies. Previews are cached by parameter hash, so going back
in history or undoing is instant. Slow studies get a server-side result cache
too.

**G. Measure (devices as an optional layer).** A Measure section with the
round-15 devices as toggles: off by default ("has to be optional"), each with
its placement. Keep adds the devices as their own layer (a group with the
drawing), so they can be hidden or plotted with their own pen.

## Not now (synthesis bench)

Editing the score's substructure, an unseen base picture, combining studies
on one sheet. The score and device contracts from round 15 are the
foundation; see the synthesis-bench prep notes.
