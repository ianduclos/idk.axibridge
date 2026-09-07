> Supporting review evidence. The primary review in REVIEW.md owns prioritization, interpretation and final recommendations. Source-only findings are not independently reproduced unless stated.

# AxiBridge interaction-source audit

Scope: bounded, read-only source review of the current desktop/browser UI. I read `CLAUDE.md`, the design framing in `axibridge/static/style.css`, `docs/IDEAS-drawing-machine-session-2026-09-05.md`, current `index.html`, relevant frontend modules, `STATUS.md`, `HANDOFF.md`, and the Apple-design reference files for accessibility, layout, typography, and color. I did not run the app. I inspected three live-walkthrough captures as interaction/layout evidence only: `01-empty-compose.png`, `04-second-reading.png`, and `09-second-1100.png`; I did not judge their drawings. Statements below labeled **evidence** are source or capture facts; statements labeled **review hypothesis** remain interpretations to test.

The target I used is a personal experimental drawing instrument: fast and deep for its owner, legible enough that a new collaborator can orient without flattening the artistic vocabulary into generic productivity UI. I did not judge the drawings or infer anything about abstraction quality.

## Overall reading

The interaction design has a strong core. The “bench & bed” distinction is explicit and disciplined: paper is the sole light surface; color is budgeted for ink, machine state, and current action (`axibridge/static/style.css:1-25`, `:38-81`). `01-empty-compose.png` confirms the intended hierarchy: the pale sheet dominates, while the dense chrome recedes without becoming generic dark-dashboard furniture. Main-canvas state and machine truth stay visible regardless of inspector tab (`axibridge/static/index.html:213-252`). Second Reading exposes exact, consequential state in text — working turn, kept layer, rendered/not rendered, queued control turn, active versus pending boundary (`axibridge/static/js/second_reading_bench.js:331-393`, `:425-432`). `04-second-reading.png` and `09-second-1100.png` show that Working, Kept, Turn, rendered point count, and active/pending boundary are visible together. It also retains drafts during an app run and makes the session limit visible (`axibridge/static/js/second_reading_bench.js:17-20`; `axibridge/static/index.html:419-424`). These choices support an instrument rather than a form-filling app.

The primary design debt is interaction infrastructure around that core. Custom menus, tabs, modals, collapsers, layer rows, drawing surfaces, tooltips, and status changes mostly work by pointer and CSS class, with little accessible state or focus management. The other urgent debt is recovery: loading a project can replace an unsaved in-memory project without a guard.

Apple-reference principles used: keyboard-only operation and gesture alternatives (`/Users/ianduclos/.agents/skills/apple-design/references/hig/accessibility.md:94`, `:110`); screen-reader descriptions (`accessibility.md:56`); persistent rather than time-boxed feedback (`accessibility.md:120`); desktop text defaults/minima and scalable layouts (`typography.md:13`, `:62`; `layout.md:48`); contrast and non-color state (`accessibility.md:35`, `:50`; `color.md:17`, `:29`).

## Findings

### 1. Critical — loading can silently discard unsaved work; there is no recovery slot

**Evidence.** The project is held in memory and the roadmap explicitly records the missing unsaved-work guard and desired recovery autosave (`ROADMAP.md:633-639`). New Project warns before replacement (`axibridge/static/js/settings.js:189-194`), and Restart uses a two-click warning (`settings.js:137-155`), but Load directly posts and refreshes with no warning or dirty check (`settings.js:196-203`). The server replaces the current project, geometry, assets, staging documents, and history (`axibridge/api.py:2078-2099`). The header shows only the project name, backend state, and estimate; no dirty/saved state is rendered (`axibridge/static/index.html:113-119`; `main.js:441-463`).

**Review hypothesis.** This is the highest practical risk in a long improvisational session. “Load” looks ordinary but is at least as destructive as “New.” The owner may learn the hazard; a visiting user will not.

**Concrete fix.** Add a server-owned monotonically increasing project revision and saved revision. Render `name •` or `Edited` beside the project name when they differ. Before New, Load, Import, or Restart, present one consistent in-app choice: Save and continue / Continue without saving / Cancel. Add periodic atomic autosave to a separate recovery slot, as the roadmap already specifies, and offer Restore Recovery only when its revision is newer than the last explicit save. Do not autosave into the named project folder.

**Tradeoff.** Dirty tracking touches every mutation boundary and recovery consumes disk. A server revision is more reliable than trying to infer dirtiness from frontend actions, and the separate slot preserves intentional saves.

**Evaluation.** Make a human turn in Second Reading, Keep as layer, alter an effect, then exercise Load, New, Import, and Restart. Each path must report the same dirty state; Cancel must preserve exact geometry, branches, and selection; recovery after forced process termination must restore the latest atomic snapshot.

### 2. High — “reading” names two different things, while “kept” can be mistaken for disk persistence

**Evidence.** The first row labels the branch selector `reading` (`axibridge/static/index.html:413-417`). The next row has a separate `Reading` selector whose values are response policies (`index.html:425-442`). Branch options are programmatically named Reading 1, Alternative N, or Human revision (`axibridge/static/js/second_reading_bench.js:265-274`, `:475-493`, `:636-650`). “Keep as layer” reports `Kept as layer` (`index.html:445-452`; `second_reading_bench.js:339-342`), but the design contract says a recipe becomes durable only after the containing project is saved (`docs/plans/second-reading.md:82-87`).

**Review hypothesis.** “Second Reading” is a good generator identity, but using reading for both a continuation and an engine/policy makes instructions harder to parse. “Kept” accurately means promoted from draft to project, yet the adjacent green state can read as safely saved.

**Concrete fix.** Keep the generator name Second Reading and preferably keep the studio verb `Keep as layer`. Rename only the branch label to `Alternative` (options `1 · Original`, `2 · Alternative`, `3 · Human revision`) and the policy field to `Response mode`. Append `project edited` in the header after Keep. In the green state, say `Kept as layer · <name>` until the project is saved, then `Saved in project · <name>`.

**Tradeoff.** “Keep” has studio warmth and less database flavor than “Add,” so normalizing it would weaken the instrument for little gain. The dirty marker can carry the persistence distinction.

**Evaluation.** Ask a first-time user: “Switch to another continuation, change how the machine responds, keep this version, then make it safe to quit.” Their interpretation should map to Alternative, Response mode, Add/Keep, then Save without explanation.

### 3. High — both popups lack dialog semantics and focus management

**Evidence.** The animation and process popups are plain `div` backdrops containing plain `div.preview-modal`; they have no `role="dialog"`, `aria-modal`, or `aria-labelledby` (`axibridge/static/index.html:332-374`, `:388-498`). Opening Second Reading or a generic process only sets `hidden = false` and a title (`axibridge/static/js/second_reading_bench.js:283-301`; `process.js:123-139`). Process Escape closes but opening does not move focus, closing does not restore it, and focus is not trapped (`process.js:91-117`, `:262-278`). The animation popup is wired to its Close button, with no Escape path found (`axibridge/static/js/plot.js:532-568`, `:2008-2035`).

**Review hypothesis.** Keyboard focus can remain on obscured controls behind the scrim, so Tab may operate the hidden context mentally even though the popup is visually dominant. Screen readers receive no boundary or title announcement.

**Concrete fix.** Give each modal panel `role="dialog" aria-modal="true" aria-labelledby="…"`; on open, save `document.activeElement` and focus the primary control or heading; constrain Tab/Shift-Tab to the dialog; make the background inert; support Escape consistently; restore focus to Bench/Watch/Render on close. Keep backdrop click dismissal as a pointer convenience.

**Tradeoff.** A focus trap adds code around highly dynamic forms. A small shared modal controller prevents the two popup implementations drifting.

**Evaluation.** Open each popup from keyboard, traverse it in both directions, press Escape during idle and playback, then verify focus returns to the invoking control. Repeat with VoiceOver and confirm one dialog title is announced.

### 4. High — the fast-tooltip implementation can erase accessible names from icon-only controls

**Evidence.** On first pointer hover, the tooltip broker copies `title` into `data-tip` and removes the actual `title` attribute (`axibridge/static/js/main.js:803-823`). It listens only to pointerover/out/down, not focus (`main.js:811-830`). Several controls are icon-only and depend on `title`, including the three Shape primitives (`axibridge/static/index.html:148-152`) and dynamically generated visibility/occlusion/duplicate/delete buttons (`axibridge/static/js/compose.js:1052-1055`, `:1111-1129`, through helper `btn` at `compose.js:1230-1237`). `data-tip` has no accessibility semantics.

**Review hypothesis.** Before hover, `title` may provide a fallback accessible name; after hover, the same button can become unnamed to assistive technology. Keyboard users never see the fast tooltip, so the expert hints disappear precisely for the input mode that needs them.

**Concrete fix.** Never remove the naming source. On initialization, copy every title to `aria-label` only when the element lacks visible text and an accessible name; leave `title` in place or suppress the native tooltip without deleting semantics. Show the custom tooltip on `focusin` as well as pointer hover, give the bubble `role="tooltip"`, and connect it with `aria-describedby` while visible. Update both `aria-label` and tooltip text when states change (Adding/Subtracting, visible/hidden).

**Tradeoff.** Leaving `title` can produce a duplicate native bubble. If visual duplication matters, use an explicit `data-tip` plus stable `aria-label` in markup/helpers rather than mutating title on hover.

**Evaluation.** Inspect the accessibility tree for Rectangle, visibility, occluder, duplicate, and delete before and after hovering each; names must remain stable. Tab to them and confirm the same concise hint appears without pointer movement.

### 5. High in browser mode — the custom menubar claims menu semantics without menu keyboard behavior

**Evidence.** Menu panels have `role="menu"`, while their children are buttons, labels, and an anchor without `role="menuitem"`/menuitemcheckbox (`axibridge/static/index.html:28-71`, `:86-110`). Opening a menu only toggles a class and `aria-expanded`; it does not move focus (`axibridge/static/js/menu.js:19-41`). The only keyboard behavior is Escape closing all menus; there are no arrow, Home/End, Enter/Space, or focus-return rules (`menu.js:61-66`). The in-page menubar is hidden in the native shell (`axibridge/static/style.css:216-227`), so this chiefly affects browser use.

**Review hypothesis.** Tab eventually reaches every item, but the declared role tells screen readers to expect the standard menubar/menu interaction. That mismatch is more confusing than either a real menu or an ordinary row of disclosure buttons.

**Concrete fix.** Choose one semantics deliberately. For the browser fallback, either implement a standard menubar with roving tabindex and arrow-key movement, or remove `role="menu"` and treat each trigger as a disclosure button controlling a normal grouped panel. The latter is smaller and acceptable for a personal instrument; the native app keeps the real system menu.

**Tradeoff.** Full menu behavior improves desktop convention but adds edge cases. Disclosure semantics preserve the existing DOM and ordinary Tab order.

**Evaluation.** In browser mode, operate File → Open, View → Ink, and Machine → Pen up using keyboard only. Focus order, announcement, submenu switching, Escape, and return focus must be predictable.

### 6. High — selected tab, tool, view, and mode states are visual classes rather than accessible states

**Evidence.** Inspector tabs are navigation buttons controlling hidden panels, with no tablist/tab roles, `aria-selected`, or `aria-controls` (`axibridge/static/index.html:281-294`). Tab switching only toggles `.on` and `hidden` (`axibridge/static/js/main.js:659-673`). Tool selection and View orientation/mode likewise toggle `.on` with no `aria-pressed` or radio-group state (`main.js:716-723`, `:460-462`; `index.html:58-66`). The visual state is an underline and changed text color (`axibridge/static/style.css:755-784`), which is good non-color visual differentiation, but it is absent from the accessibility tree.

**Review hypothesis.** A screen-reader user can activate these controls but cannot reliably learn which inspector, tool, orientation, rendering mode, primitive, or add/subtract mode is current.

**Concrete fix.** Implement the inspector as `role=tablist` / `role=tab` / `role=tabpanel`, with `aria-selected`, `aria-controls`, roving tabindex, and Left/Right keys. Give mutually exclusive tool/view/primitive groups radiogroup semantics or consistently set `aria-pressed`; set `aria-pressed` on add/subtract toggles. Centralize class and ARIA updates in each existing state-sync function.

**Tradeoff.** Native radio inputs would supply semantics automatically but could constrain the instrument styling. ARIA on current buttons keeps the visual language intact if state updates remain single-source.

**Evaluation.** With the screen covered, use VoiceOver to identify and change the inspector tab, active drawing tool, portrait/landscape, schematic/ink, shape primitive, and subtract mode. Each group must announce its current state before action.

### 7. High — collapsible panels and both resize handles are pointer-only custom controls

**Evidence.** Every `.panel > h2` toggles collapse on click (`axibridge/static/js/main.js:833-845`) and is styled with a pointer cursor (`axibridge/static/style.css:569-587`), but headings are not focusable buttons and expose no expanded state. The Layers heading is also an `h2` with an onclick handler (`axibridge/static/index.html:307-315`; `compose.js:922-934`). Sidebar and Layers resize grips are bare `div`s with pointer handlers (`index.html:283`, `:308`; `main.js:781-800`; `compose.js:936-960`) and no separator role, accessible value, or keyboard adjustment.

**Review hypothesis.** Full Keyboard Access can reach controls inside expanded panels but cannot intentionally expand a collapsed one. A saved narrow sidebar or short layers dock may therefore be unrecoverable without a pointer.

**Concrete fix.** Put a real button inside each heading, preserving the engraved visual, with `aria-expanded` and `aria-controls`; use the same for Layers. Make grips focusable separators with orientation, min/max/current values and Arrow-key increments; add a context-menu or Settings command for Reset panel sizes.

**Tradeoff.** Focus rings on the structural chrome add visual activity. Restrict them to `:focus-visible`, which the design system already handles well (`style.css:178-183`).

**Evaluation.** Save the inspector at minimum width and Layers at minimum height, reload, disconnect the pointer, then restore useful sizes and open every collapsed panel from the keyboard.

### 8. High — the layer list's core selection, rename, and ordering model is not keyboard-operable

**Evidence.** A layer row is a plain draggable `div`; selection is row click, rename is a double-click counter, and ordering is HTML drag-and-drop (`axibridge/static/js/compose.js:1023-1038`, `:1062-1104`, `:1151-1160`, `:1240-1288`). Rows receive neither tabindex nor listbox/option semantics. The global Delete shortcut works only after `S.selection` exists (`axibridge/static/js/main.js:1024-1037`). Keyframe ordering is also drag-only, while copy/paste state is exposed only through right-click context menus (`compose.js:1382-1423`, `:1516-1558`).

**Review hypothesis.** This creates a sharp novice/expert inversion: the interface resembles a desktop layer editor, but familiar keyboard paths (Up/Down selection, Shift range, Return/F2 rename, modifier-arrow reorder, keyboard context menu) are absent. Expert shortcuts begin only after pointer selection.

**Concrete fix.** Treat the layer dock as a focusable listbox with roving focus. Support Up/Down selection, Shift+Up/Down range extension, Return or F2 rename, Space visibility toggle, and Command+Up/Down reorder; expose duplicate/delete/occlusion through buttons and a keyboard-invocable context menu. Mirror the pattern for keyframes, with explicit Move earlier/later commands as a fallback to drag.

**Tradeoff.** Modifier keys can collide with canvas nudging if later added. Scope shortcuts to focus within the dock and display them in tooltips/menu labels.

**Evaluation.** From a fresh tab stop, select a layer, extend to three, rename one, duplicate, reorder, toggle visibility, copy/paste a keyframe state, and undo — without pointer input.

### 9. High, with a deliberate scope boundary — drawing surfaces are pointer-only and screen-reader silent

**Evidence.** The main drawing surface is an unlabeled, non-focusable `svg` (`axibridge/static/index.html:175-176`). Brush code explicitly notes that the canvas is not focusable (`axibridge/static/js/brush.js:56-58`). Pen, brush, shape, and Second Reading capture attach pointer handlers (`pen.js:38-47`; `brush.js:45-54`; `shapes.js:46-68`; `second_reading_bench.js:243-247`, `:590-603`). Second Reading changes the button text to “Draw on the paper,” but the paper itself remains an unlabeled SVG (`second_reading_bench.js:566-575`).

**Review hypothesis.** Reproducing freehand drawing with arrow keys would be artificial and could dilute the instrument. The actionable issue is that assistive technology gets neither a surface description nor a non-gesture route to the same project-level result.

**Concrete fix.** Give each SVG an accessible name and live summary: sheet dimensions, layer count/selection, and, for Second Reading, current turn and instruction. Make the stage focusable when capture is armed and let Escape cancel. Offer an explicit alternative route where practical — import SVG, enter shape dimensions, or add a machine turn without drawing — rather than simulating freehand drawing by keyboard. Document pointer drawing as an intentional modality limitation.

**Tradeoff.** Detailed path narration would be noisy and aesthetically misleading. Summarize structure and state; do not pretend a screen reader can substitute for visual judgment of the drawing.

**Evaluation.** With VoiceOver, locate the main sheet and Second Reading sheet, learn whether capture is armed, cancel it, continue a machine turn, and add an imported/numeric element. Confirm the app remains navigable even where freehand input is unavailable.

### 10. High — errors and changing machine/process state are neither persistent nor announced

**Evidence.** The always-visible global error is a plain span (`axibridge/static/index.html:252`) and is cleared after eight seconds (`axibridge/static/js/main.js:115-125`). Machine state, queue state, connection pill, and process preview state are also plain spans updated by text replacement (`index.html:117`, `:241-252`, `:406-412`; `main.js:441-459`; `second_reading_bench.js:337-349`). Animation progress is a styled `div` without progressbar semantics (`index.html:372`; `style.css:826-833`). No `aria-live` usage exists in the reviewed source.

**Review hypothesis.** A transient API or hardware error can disappear before it is read, and a nonvisual user receives no announcement when the plotter connects, starts, pauses, requests a pen swap, finishes, or fails. Announcing every position tick would be equally unusable.

**Concrete fix.** Keep the latest error until dismiss or the next successful retry and add a compact Error details affordance. Use `role=status aria-live=polite` for coarse connection/job/bench transitions and `role=alert` for blocking errors. Give progress bars `role=progressbar` with min/max/current. Throttle announcements to meaningful phase changes; never announce carriage coordinates or every rendered frame.

**Tradeoff.** Live regions can chatter during playback and SSE updates. Separate visual high-frequency readouts from a low-frequency announcement string.

**Evaluation.** Simulate backend unreachable, preview failure, project import failure, plotting progress, pause/resume, pen swap, and completion. Check that sighted status stays compact, errors remain recoverable, and VoiceOver announces one useful sentence per phase.

### 11. Medium-high — destructive confirmations expire in 2.5 seconds

**Evidence.** Restart arms a “sure? unsaved work is lost” state and resets after 2500 ms (`axibridge/static/js/settings.js:137-148`). Layer delete/un-animate likewise changes a small icon button to “sure?” or “restore?” for 2500 ms (`axibridge/static/js/compose.js:1120-1140`). The accessibility reference recommends avoiding time-boxed controls because people may need longer to process or navigate them (`accessibility.md:120`).

**Review hypothesis.** The pattern feels quick for the owner but can fail under motor hesitation, screen magnification, or cognitive interruption. The word “sure?” also omits the target exactly when consequence matters.

**Concrete fix.** Keep the armed state until explicit Cancel, Escape, focus leaving the relevant row, or action completion. Name the target and consequence: `Delete “Contour 3”? Undo available` / `Restart and discard unsaved changes?`. For undoable layer deletion, consider immediate delete plus a persistent Undo action; retain stronger confirmation for restart and cascade deletion.

**Tradeoff.** Persistent inline confirmations occupy space. Replace only the row's action cluster, not the whole panel, and allow Escape.

**Evaluation.** Arm delete/restart, wait ten seconds, navigate away and back, and complete/cancel by keyboard and pointer. Verify accidental double clicks do not trigger irreversible work.

### 12. Medium-high — small type and one semantic color sit below comfortable accessibility margins

**Evidence.** The root is fixed at 13 px (`axibridge/static/style.css:103-109`). Engraved headings/tabs default to 10 px uppercase with 1.6 px tracking (`style.css:128-141`); hints and row labels are 11.5 px (`style.css:620-625`); Second Reading state/new-drawing/help text is 11 px (`style.css:904-930`); many transport and layer buttons are 10–11 px (`style.css:430-481`, `:1063`, `:1114`). Roboto Mono is intentionally used throughout (`style.css:23-35`, `:162-175`). The reference recommends 13 pt as the desktop default and 10 pt as a minimum, and asks custom type to remain legible/scalable (`typography.md:13`, `:62`). CSS pixels are smaller than points at standard desktop scaling. Separately, `--rust` is `#c0644c`; the main bench is `#1c1b19` and raised controls are `#262420` (`style.css:38-43`, `:79-81`). Danger buttons use rust as 12.5 px text (`style.css:631-657`). WCAG relative-luminance calculation gives approximately 4.24:1 on `--bench` and 3.81:1 on `--bench-rise`, below 4.5:1 for small text. There is no increased-contrast override (`style.css:103-106`, `:1234-1236`).

**Review hypothesis.** The one-face instrument voice is distinctive and worth keeping. The risk comes from combining mono glyphs, uppercase tracking, soft ink, and sub-12 px size in dense control rows; this may be stylish at the owner's exact setup but brittle on a high-resolution or distant display. The muted rust suits the housing, but destructive-state labels are the wrong place to spend contrast below the floor.

**Concrete fix.** First fix the responsive clipping in finding 15; do not enlarge everything blindly. Keep Roboto Mono and the engraved/body/readout roles. Raise only consequential microcopy and action/status text to 12–13 px, reserving 10–11 px for nonessential markings. A `Compact / Comfortable` density setting is optional if the owner finds the current density useful. For danger text, choose a verified lighter Flexoki red/orange token that reaches 4.5:1 on both bench surfaces, or keep current rust for the edge/icon and use `--ink-hi` for the small label. Add an increased-contrast override that strengthens soft text, edges, focus, and status distinctions while retaining the dark instrument.

**Tradeoff.** Larger text reduces the visible parameter population and drawing height, and the live captures show that wholesale enlargement would worsen the more urgent viewport problem. Treat this as targeted legibility work. Brighter rust attracts attention; restrict it to armed/destructive state.

**Evaluation.** Compare default and 200% text zoom at 1440×900 and 1024×768. All action names, active/pending boundary text, project state, and plot stop controls must remain readable without overlap or horizontal page scrolling. Measure semantic foreground/background pairs and inspect danger, origin, subtract, focus, connected, moving, and disabled states in normal and increased-contrast modes.

### 13. Medium — file/export controls contain invalid nested interactivity, and Save feedback destroys its shortcut label

**Evidence.** Settings wraps an Export button inside a download anchor (`axibridge/static/js/settings.js:25-31`); animation export repeats `<a><button>` for GIF and MP4 (`axibridge/static/index.html:368-370`). Nested interactive elements can produce duplicate or inconsistent focus/activation semantics. Save confirmation assigns `btn.textContent`, which removes the child `<span class="menu-key">⌘S</span>` defined in markup; after 1.5 seconds it restores only “Save,” not the shortcut span (`index.html:34`; `main.js:483-493`). Resolution and fps labels are not associated with their inputs (`index.html:348-366`).

**Review hypothesis.** These are small implementation details with visible consequences: keyboard users may encounter odd export focus, and the menu loses its shortcut hint after the first successful save.

**Concrete fix.** Style anchors directly as buttons and remove nested buttons. Give resolution/fps `for` associations or wrap their controls. In Save, update a dedicated status child or set a temporary data-state without replacing the button's children; keep the shortcut stable. Prefer a header-level saved/edited state over transiently renaming the menu command.

**Tradeoff.** Direct anchors need shared button classes and disabled-state handling for unavailable MP4. That is still simpler than nested activation behavior.

**Evaluation.** Tab through Settings and animation export, activate with Space/Enter, and inspect focus count. Save twice and confirm `⌘S` remains visible and the native menu state still parses correctly.

### 14. Medium — Second Reading reports queued state, but does not let the user compare current and pending control values

**Evidence.** Control edits are staged for the next turn. Rendering writes the staged value into each slider, compares it with current only to toggle `.staged`, and prints one shared note (`axibridge/static/js/second_reading_bench.js:335-362`). The `.staged` rule only sets `accent-color: var(--ochre)` (`axibridge/static/style.css:918-921`), while the custom slider explicitly removes native appearance and paints the track from `--fader` (`style.css:700-744`), so the accent-color difference may have little or no visible effect depending on engine. Boundary state is much clearer because it prints both active and selected values (`second_reading_bench.js:425-432`).

**Review hypothesis.** The next-turn model is artistically sound: it makes intervention consequential rather than continuously rewriting history. But after moving several sliders, the user sees only proposed values and cannot recover the current values they are departing from. The generic “control change queued” text confirms that something changed, not what.

**Concrete fix.** Reuse the boundary pattern compactly. For changed controls, show `0.42 → 0.68 next turn` in the output, or add one `Next turn: Attention .68, Departure .31` readout. Give staged sliders a visible ochre tick/edge using the custom slider variables rather than native accent-color. Clear the comparison as soon as the next turn commits.

**Tradeoff.** Dual values add numerals under the drawing and may encourage parameter optimization over visual judgment. Show comparisons only for changed controls and keep them in the state row, not over the sheet.

**Evaluation.** Change one, then three controls; scrub backward; switch alternative; continue one turn; undo; redo. At each point, ask “what controls generated the visible turn, and what will change next?” The answer should be available without opening Process details.

### 15. High — the Second Reading sheet is vertically clipped at a common desktop viewport

**Evidence.** In `09-second-1100.png` (1100×750), the popup consumes nearly the full viewport and the white drawing sheet is cut off vertically inside the stage. The lead's live measurement found the SVG at 367.5 px high inside a 274.19 px-tall `.preview-stage` whose overflow is hidden. The source sets `.preview-stage { overflow:hidden }`, gives `.process-body` flex growth with `min-height:0`, gives the SVG a viewport-based height, and sets the Second Reading body only a minimum height (`axibridge/static/style.css:840-852`, `:866-880`, `:895-897`). At the larger `04-second-reading.png`, the paper is more dominant but its lower content also reaches the stage edge. The source has a width breakpoint for process controls at 760 px, but no height breakpoint (`style.css:937-941`).

**Review hypothesis.** This is a functional review problem, not an aesthetic opinion about the drawing: the instrument asks the user to judge and intervene on a whole element while hiding part of the work surface. The dense control block is allowed to scroll with the modal, but the paper itself should never be involuntarily cropped.

**Concrete fix.** Size the SVG from the actual available stage rectangle and preserve its aspect ratio within both width and height: make the stage establish the remaining flex height, set `#process-canvas { width:auto; height:auto; max-width:100%; max-height:100%; }`, and ensure the body has a real computed height or aspect-ratio-constrained child. Add a height media query that stacks or collapses secondary state: move New drawing and both details below a disclosure/scroll region before shrinking the paper. Keep the full sheet visible by default; allow deliberate zoom/pan only as an explicit inspection mode.

**Tradeoff.** At 1100×750, showing the full paper makes marks smaller. Hiding secondary setup controls behind progressive disclosure is less damaging than cropping the object being judged, and the controls remain available one scroll/click away.

**Evaluation.** Open Second Reading at 1100×750, 1024×768, 1440×900, and a short wide window, with Clip and Overshoot + fit. The entire nominal sheet/working frame must be visible on open, no stroke may disappear under the stage edge, and all primary actions must remain reachable without scrolling. Then resize live while a draft is open and verify the view does not jump or change recipe state.

## Suggested evaluation sequence

1. **Five-minute novice orientation.** Open an existing project, identify what will plot, find Second Reading, make one machine turn and one human turn, create an alternative, add it to the project, and save. Note every term that needs explanation.
2. **Owner-speed keyboard pass.** Repeat ordinary Compose work with keyboard only: menus, tabs, panel folds, layer select/range/rename/reorder, sliders including Shift fine control, undo/redo/save, modal open/close.
3. **VoiceOver structure pass.** Traverse landmarks, tabs, active tools, layer list, both dialogs, sheet summaries, queued/kept state, errors, machine phases, and progress. Avoid narrating high-frequency geometry/motion.
4. **Recovery drill.** Create unsaved work across ordinary layers and Second Reading, then attempt Load/New/Import/Restart and force-kill the server. Verify explicit save choices and exact recovery.
5. **Legibility/adaptation pass.** Test 1440×900 and 1024×768 at 100% and 200% text zoom, plus the app's narrow breakpoint. The sheet should remain dominant while essential actions stay reachable.
6. **State discrimination pass.** Without relying on color, identify active tool/view/tab, drawing capture, staged next-turn controls, active/pending boundary, resolving/rendered, layer-added/project-edited/project-saved, moving/connected/error.
7. **Failure pass.** Trigger a preview error, bad import, unavailable backend, plotting hold, and server disconnect. Confirm the error persists, the recovery action is clear, and status does not chatter.

## Priority order

Fix 1 first because it protects the work itself, and 15 next because the current viewport can hide the work being judged. Then 3–10 as an accessibility/keyboard infrastructure pass, starting with the tooltip regression and modal focus. Address 2 and 14 together as the Second Reading language/state pass. Fold 11–13 into that work where files overlap.

Several recommendations should remain deliberately bounded. Do not add a light theme just to imitate platform defaults; an increased-contrast version of the dark bench is enough. Do not simulate freehand drawing with arrow keys or narrate path geometry as if that substituted for seeing. Do not replace `Keep`, `Bench`, or `Second Reading` with generic workflow language when a dirty marker and two disambiguated labels solve the real problem. Do not enlarge every label or turn each engraved section into a card; the live Compose capture shows that the controlled density and material hierarchy are part of the instrument's character. Accessibility semantics, focus, and recovery can improve underneath that surface without domesticating it.
