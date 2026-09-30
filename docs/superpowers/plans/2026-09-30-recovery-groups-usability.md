# Recovery, groups and everyday usability — implementation plan

Approved by Ian in this chat on 2026-09-30. Implementation is one integrated
multi-agent pass. Baseline: main 92ed5cf (Territory + static sidebar + Gallery
accessibility correction), 1,698 passed / one native-launch skip.

## Binding outcomes

- Generators retain the first static position in Compose; layers dock stays taller.
- Server dirty/recovery tracking covers kept layers/groups/assets/staging/project
  settings/undo/redo; previews, scrubbing and machine activity do not dirty it.
- Changed projects snapshot every 30 seconds and before native close, restart or
  replacement. Detached complete snapshots include source geometry, uploaded SVG,
  media assets, sheets and the existing saved-history depth. Atomic archives in
  CONFIG_DIR retain a previous valid fallback and surface write errors.
- Startup offers Restore or Start fresh with name/time and older candidates.
  Unsaved project recoveries survive switches until explicitly saved/discarded.
- Native close saves recovery without a save prompt, refuses on failure and keeps
  active-plot protection. Dirty New/Load/Import offer Save, Continue with recovery,
  Discard or Cancel. Restart refuses dirty state without explicit continuation
  after a successful checkpoint. Unkept bench drafts are outside recovery.
- Nested named/visible affine groups preserve flat drawing order and animation
  ownership. Only consecutive canonical siblings may be grouped; animation families
  are units. Identity grouping leaves drawing/overlap unchanged.
- All layer types, regions, Animate chains and linked tweens are supported. Group,
  Ungroup, rename, hide/show, duplicate, delete, nest and block reorder are required.
  Click selects the outermost group in the editing context; double-click enters;
  Escape exits. Members remain editable. Translation/rotation/nonuniform scaling
  and normalized atomic multi-selection transforms each make one undo entry.
- Group placement precedes millimetre effects; common ancestry is factored out of
  tween references so shared placement applies once. Reparent/Ungroup preserve
  evaluated placement and live references; group visibility preserves member flags.
  No group occlusion mask. Validate cycles, membership, split families and singular
  placements before mutation. Older projects load ungrouped; new hierarchy is versioned.
- Assets tab sits between Compose and Plot, owning imports/assets/Depth Pro/Gallery
  and visible progress. Canvas drop continues binding current generator; SVG import
  preserves selection behavior; Gallery insert selects and returns to Compose.
- Arrow 1 mm / Shift-arrow 10 mm, Cmd/Ctrl-D duplicate, Cmd/Ctrl-G group,
  Shift-Cmd/Ctrl-G ungroup, 1–5 tabs. Respect fields, tools and modals. Seed rerolls
  share normal form commits and schema bounds. Preset select/apply stays visible;
  Save/Update folds into a disclosure. No Cmd-K launcher in this pass.

## Ownership / sequence

Lead owns Project/group/frame contracts, Session tracking and atomic operations,
resolver/tween integration, API/lifecycle, shared UI integrations, group canvas
interaction, shortcuts and acceptance. Lead fixes shared contracts before workers
integrate. At most three supporting Sol workers, no further delegation.

A owns detached recovery storage and storage tests only. Capture interface:
RecoverySnapshot(project, source_geometry, svg_files, assets, staging_documents,
history, revision, session_id, project_dir). Store creates timestamps and exposes
write/list/load/discard; no singleton Session imports.
B owns new assets_tab.js and focused Assets browser tests only; lead removes old
Compose controls and wires fifth tab/progress. Exports initAssetsTab,
renderAssetList, uploadAssetFiles, refreshDepthProStatus, setAssetProgress.
C owns forms.js seed controls and module_library.js preset disclosure plus focused
control tests only. Lead owns shared main.js/compose.js/index.html/style.css.
Workers do not commit/stage shared files; lead commits inspected checkpoints.
Independent bounded reviews follow integration, using available slots.

## Group placement contract

Group matrix chains remain metadata, never geometry mutation. Normal layers use
ancestor world placement times local transform before effects. Tween references
are evaluated relative to the common group ancestry; apply the tween group's
placement after interpolating endpoint transforms and before endpoint effects.
Retain legacy master placement and ungrouped behavior. Preserve coordinate-frame
adjustments when structural reparenting changes ancestry, without modifying shared
external reference layers. Cache keys include all relevant placement contexts.
Lead will validate nonidentity master placement and nested linked references before
UI integration. Effective visibility applies at every resolve/region/preview path.

## Verification

Tests first for new contracts. Recovery: crash/restart, corrupt current + fallback,
failed writes, complete assets/sheets/history, detached serialization, switches,
close guards, stale revisions and clean previews. Groups: identity equivalence,
nested visibility, general affine transforms, all tween frames, fixed millimetre
widths, reference integrity on structural operations/duplicate/delete, validation
atomicity, undo/redo and save/load/export. UI: Assets/drop/Gallery, typed selections,
edit context, all shortcuts/focus guards, seed/preset controls and recovery dialogs.
Full pinned hardware-free pytest suite, typecheck/build and visual checks at
1024×768 and 1500×950. Update ARCHITECTURE/MODULES/ROADMAP/STATUS/HANDOFF, commit
verified work. Native/paper acceptance remains Ian's; no feature merge or push
without another instruction (the latest merge instruction settled the baseline).
