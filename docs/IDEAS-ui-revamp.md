# UI ideas — making axibridge a serious instrument

Loose brainstorm, 2026-07-26 (Opus 5), asked for after the zero-build
invariant was reopened on 2026-07-25. Not commitments — ROADMAP.md
"Far / undecided — UI revamp" holds the conviction ordering and the
reopening criterion, and **this document does not change the invariant.**
It exists to make the choice concrete: what "serious UI" actually means
here, what each tooling tier buys, and what is buildable today regardless.

## The framing

The tooling question got asked first because an emoji icon was ugly. That's
backwards. Ask instead: *what does this instrument fail to do that a serious
one does?* — then see which of those answers are gated on tooling. Working
through the list, the honest finding is:

> **Most of what would make axibridge feel serious is not gated on the build
> question at all.** The single biggest structural upgrade — deriving the
> frontend's model of the server contract from the server — is also
> in-bounds today. The bundler buys real things, but they sit behind
> features that don't exist yet.

So the ordering below is by *what it does for the operator*, with the
tooling tier marked per item, not the other way round.

Second framing rule, borrowed from what this tool is: **the canvas is the
instrument, the panels are its controls.** Every question of "where does
this go" resolves against that. Today the canvas toolbar is a junk drawer of
eight unrelated control groups on one row (view · mode · zoom · 3 checkboxes ·
animate + speed · A/B capture's 4 widgets · tool segment · brush select),
because it was the nearest flat surface each time something shipped. That's
the clutter the ROADMAP's "near term" section already names, and it is the
first thing a stranger would notice.

---

## Tier 0 — buildable today, invariant untouched

Nothing here needs npm, a bundler, or a decision about either.

### 0.1 Canvas layout grammar (the junk-drawer fix)

Adopt the layout every editor a plotter user has already used converges on,
because it costs nothing and instantly reads as a tool rather than a form:

- **Left rail, vertical, icon-only** — tools (select · draw · pen · brush).
  Tools are modes; modes belong in one persistent place, not inline among
  toggles. Vertical also stops the row overflowing every time a tool ships.
- **Top bar, context-sensitive to the active tool** — select ⇒ align /
  numeric transform; draw ⇒ brush + width; pen ⇒ snapping. This is where the
  A/B capture cluster and animate + speed go too: they are *task* controls,
  not always-on chrome.
- **Right inspector** — properties of what's selected (already correct).
- **Bottom status bar** — machine state, plot economics (§0.2), warnings.
  `#canvas-status` is already there and under-used.

View / mode / paper-guide / travel / draw-order are *view state*, not tools —
they belong in a single "View" popover (the menubar already has one) with
keyboard shortcuts, not five permanent widgets.

### 0.2 Make the plot economics visible — the highest-value single change

This tool exists to move a pen. Almost nothing about the *cost* of the
current design is on screen. Put in the status bar, live off every resolve:

| readout | why it matters |
|---|---|
| pen-down distance | ink and time |
| **pen lifts** | the number `connect_strokes` / `min_stroke` exist to reduce |
| pen-up travel | the number `estimate.py` already models |
| est. time | exists as a pill; belongs beside its inputs |
| path count | proxy for file/plan size |

The hatch work of 2026-07-26 is the argument: `connect_strokes` took a
trefoil from 37 lifts to 3 and *cut* ink 15%, and the only way to see that
today is to read a test's numbers. With the readout, every fill param
becomes tunable against a number instead of a vibe. Cheap: `estimate.py`
computes most of it already.

Follow-on, same idea: a **before/after chip** when a param change alters the
economics ("lifts 37 → 3"), which turns the readout into feedback.

### 0.3 Keyboard, and a command palette

A bench instrument is used with one hand on the machine. Missing, all cheap:

- `V` / `D` / `P` tool switching; `Space` pan; `Esc` always returns to
  select (pen already treats Esc as discard — keep that, but make Esc from
  *no* pending state mean "back to select").
- Arrow-key nudge on selection (ROADMAP near-term already lists this),
  `⇧` for coarse; `[` / `]` for layer order; `⌘Z` / `⇧⌘Z` (exists).
- **`⌘K` command palette** — ~150 lines of vanilla, and the single best
  "serious tool" signal available. It makes a hundred commands discoverable
  without adding one pixel of chrome, and it is the standard escape valve
  for a UI whose feature count has outgrown its surface. It also degrades
  the toolbar-crowding problem from urgent to cosmetic: anything that
  doesn't earn permanent space still has a home.

### 0.4 Layer list: solo, drag-reorder, multi-select

A compositor without **solo** is missing its most-used verb — "show me just
this one" is how you debug a stack. Drag-to-reorder and shift/⌘ multi-select
are the other two the list is visibly missing (ROADMAP near-term has
drag-to-reorder). All three are hand-rollable; all three get easier under
Tier 1, which is exactly the trigger condition in §T1.

### 0.5 Canvas render cost — a real, unglamorous optimization

`canvas.js` emits **one `<path>` element per resolved `Path`** (lines
~230-266). A hatch fill at 0.3 mm spacing on a single shape resolves to 1178
paths; a hatched multi-layer project is trivially tens of thousands of SVG
nodes, rebuilt from scratch on every resolve, every slider tick.

But look at the attributes: `stroke`, `stroke-width`, `stroke-opacity`,
`fill`, linecap/linejoin are **per layer**, not per path — in schematic mode,
in ink mode, and for regions alike. Only `show_order` (which ramps opacity
per path) genuinely needs one element each. So:

> merge every path in a layer into **one** `<path>` with a concatenated `d`,
> exactly as the existing `layer-hit` path already does one line below, and
> split into per-path elements *only* when `showOrder` is on.

Node count per layer drops from O(paths) to O(1). Hit-testing is unaffected
— it already goes through the separate wide `layer-hit` path. This is ~15
lines and is the kind of thing that decides whether dragging a spacing
slider on a hatched layer feels alive or gluey.

Not yet benchmarked in a browser — the arithmetic (1178 nodes → 1) is the
claim, the frame-time win needs measuring before it's quoted as a number.

Adjacent micro-wins, same file: the travel overlay builds one `<polyline>`
per hop (same merge applies); `x.toFixed(3)` per coordinate is the hot
inner loop for dense generators.

### 0.6 Types from the server, without a compiler — the sleeper

The frontend's model of `PathDocument` / layers / module schemas is
**remembered, not derived**. Every field name in `compose.js` is a guess
that happens to be right. The IPR is defined once in Pydantic and already
published as JSON Schema (that's how `forms.js` auto-renders controls) — so:

```
# a dev-machine command, run when the API changes; output is CHECKED IN
openapi-typescript http://localhost:2942/openapi.json -o static/js/api-types.d.ts
```

…consumed by `// @ts-check` + JSDoc in the existing `.js` files. Result:
real cross-file type checking against the *actual* server contract, catching
the "passed a layer where an id was expected" class and, more valuable,
"this field was renamed server-side three commits ago".

**This does not touch the invariant.** The invariant bars a compiler or
bundler from the *edit-reload loop* (CLAUDE.md, ARCHITECTURE.md "Stack").
A generator whose output is a checked-in, human-readable declaration file,
run by hand on a dev machine, is in the same category as the vendored SVG
icons that shipped 2026-07-25: tooling, not a build step. The served file is
still the real source; the Pi is unaffected; view-source still works.

Worth stating plainly because it reframes the whole question: **"generate it
offline and check it in" is a whole tier the ROADMAP's three-way framing
(zero-build / vendored-ESM / bundler) doesn't currently name**, and it
captures most of what people actually want TypeScript for here.

### 0.7 Machine-state honesty

The failure modes are physical and the UI is quiet about all of them. From
this repo's own history: `axicli` "plots" silently with nothing moving when
the barrel-jack PSU is missing (a whole debugging session, 2026-07-22);
the serial port can be held by the other AxiDraw mode; the Pi can be
unreachable. A panel that states *which* backend is live, *whether* the port
is held, and *when* the last motion command actually produced motion, is a
seriousness signal no amount of visual polish substitutes for.

Pairs with the ROADMAP's standing **unsaved-work guard** debt (autosave to a
recovery slot; `/server/restart` refusing on unsaved changes) — same
category: the instrument should not lose or lie about state.

### 0.8 Visual system

Tokens before taste: one CSS custom-property scale for spacing, type, radius,
and semantic colors (`--accent`, `--warn`, `--pen-swatch-…`), then make every
control read from it. 456 lines of hand CSS is small enough that this is an
afternoon and large enough that it has already drifted. Then: finish the icon
pass ROADMAP already scoped (`⛶ ▶ ⇄` and the panel glyphs) **as one pass**,
and give focus states and empty states the same attention as the happy path
("no layers yet — add a source" beats a blank canvas).

Consider a light theme only after tokens exist; before that it's 456 lines of
find-and-replace.

---

## Tier 1 — one vendored ESM file (htm+preact or lit), no npm

### T1 What it actually buys here

Not "components are nice". One specific, evidenced bug class:

`renderLayerList()` does `wrap.innerHTML = ""` and rebuilds. Every piece of
UI state that lives in the DOM — scroll position, focus, `<details>`
open/closed, in-progress rename — is destroyed and must be manually
re-established. This has already been paid for twice: URGENT item #8
("Effect-step boxes must not collapse on regenerate" — fixed with an
`openGroups` Set plus a `stateKey` threaded through *all six* `renderForm`
call sites) and `collapsedTweens` persisted to `localStorage` to survive the
same rebuild. Both are hand-rolled reconciliation.

The second, quieter cost: **render cascades**. `renderLayerList()` calls
`renderBenchAction()`, `renderTimeline()`, `renderLayerDetail()`; forget one
call in a new code path and the UI is silently stale. That's a derived-state
problem being solved by hand.

A keyed reconciler makes both disappear: state preservation is the default,
and derived panels re-render because their inputs changed, not because
someone remembered to call them.

**Trigger to adopt (proposed):** the *next* time a re-render state-loss bug
or a stale-panel bug appears, or the first panel body that needs the same
list-with-per-row-controls pattern a fourth time. Not before — the existing
code works, and one vendored file is only cheap if it replaces something
that's actually hurting.

**Scope discipline if adopted:** panel bodies only (Compose / Plot / Bench /
Timeline lists). `canvas.js`, `pen.js`, `draw.js` stay hand-written — direct
SVG manipulation at pointer-event rates is the one place a reconciler is a
liability, not an asset.

---

## Tier 2 — a real bundler / TypeScript / compiled framework

ROADMAP's criterion stands and this document does not weaken it: reopen only
when a *specific* wanted feature genuinely needs compiled reactivity or
cross-file TS, **and** Tier 1 has been tried and demonstrably isn't enough.

What sharpens since it was written:

- §0.6 removes the strongest everyday argument for Tier 2 (types) without
  paying for Tier 2. Whatever remains of the TS case is about *authoring*
  ergonomics, not about correctness.
- The two features that would genuinely force it are unchanged and both
  still hypothetical: **a node editor** and **a dope-sheet / keyframe
  editor**. Both are graph-and-state-heavy UIs where hand-rolled
  reconciliation stops being a nuisance and starts being the whole task.
- If Tier 2 ever happens, the Pi consideration is narrower than it sounds
  (checked 2026-07-25: Pi-scheduled agents work through pytest and PIL
  renders, never a browser) — but the *served artifact* must stay
  view-source debuggable, or the reason the invariant existed is gone.

**Anti-goal, stated once:** none of this is a case for moving geometry
client-side. The single-resolve invariant is why this tool can be trusted,
and a thin frontend is a *feature* — it is also, incidentally, why the
"you need a real framework for a large client data layer" argument does not
apply here.

---

## Ledger

**Shipped**
- Vendored inline SVG toolbar icons (2026-07-25) — the first Tier-0 tooling
  move, and the proof that "tooling ≠ build step" is workable in practice.

**Proposed, Tier 0, roughly in value order**
1. Plot-economics readout in the status bar (§0.2)
2. Canvas path merging (§0.5)
3. `⌘K` command palette + tool/nudge keys (§0.3)
4. Canvas layout grammar: left rail + contextual top bar (§0.1)
5. Generated API types + `// @ts-check` (§0.6)
6. Layer solo / drag-reorder / multi-select (§0.4)
7. Machine-state panel + autosave guard (§0.7)
8. CSS tokens, then finish the icon pass (§0.8)

**Waiting on a trigger**
- Tier 1 vendored ESM — trigger in §T1.
- Tier 2 bundler — ROADMAP's criterion, unchanged.

**Explicitly not proposed**
- Client-side geometry, a canvas library (fabric/konva — the 2026 rejection
  still holds), a CSS framework, or a light theme before tokens exist.
