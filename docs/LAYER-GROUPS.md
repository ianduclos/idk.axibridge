# Layer groups

Project format 3 adds nested `LayerGroup` records and `CanvasLayer.group_id`.
Existing projects migrate as ungrouped. The flat bottom-to-top `Project.layers`
order remains authoritative for plotting, regions and occlusion. Groups have
names, affine placement, visibility and a parent; they introduce no combined
occlusion mask. Each group's descendants occupy one consecutive block. An
Animate master and all owned keys form one sibling item.

Select neighboring siblings and use Group (⌘/Ctrl-G). Grouping creates identity
placement without changing geometry or overlap. Group rows offer Enter,
rename, show/hide, duplicate, delete, Ungroup and block movement. The Move
control reparents a selection into a chosen group or Root. Cycle, incomplete
family, invalid membership and singular placement requests fail before mutation.

A canvas click selects the outermost group within the editing context. Double
click enters it; Escape exits. Member layer and animation key controls stay
available inside. Existing canvas handles translate, rotate and stretch
horizontally/vertically. Typed selections remove selected descendants of an
ancestor; atomic transforms, duplicate, deletion and multi-Ungroup make one undo
entry. Arrow keys move 1 mm, Shift-arrow 10 mm; ⌘/Ctrl-D duplicates.

Resolve applies group world placement before millimetre-based effects. Ordinary
layers use `group_world × layer_local`. Interpolation references remove common
ancestry before affine interpolation; output group placement is applied once.
Internal input/reference frame adjustments preserve evaluated placement when
reparenting or ungrouping without changing external reference layers. These
adjustments remain live: subsequent endpoint edits still affect interpolation.
Nested linked interpolation retains generator parameter morphing and carries
its extra source placement relative to the legacy reference frame. Persisted
reference baselines keep nested morphs stable when ordinary endpoints move
between groups. Reflected midpoint frames retain drawing output. Shared
ancestry cancels before affine interpolation, including nonuniform scaling. Cache keys include placement/reference context.

Group visibility gates members without overwriting their own flags. Ungrouping
hidden content retains inherited visibility separately; an explicit member
show/hide clears that inherited gate. Consolidation and merging bake world
geometry back into the surviving parent frame so existing placement and fixed
millimetre effects are preserved. Capture recipes, recovery, history and exports
carry hierarchy; frozen tray documents remain paper-space output.

The Assets tab owns Gallery, SVG/media import and Depth Pro. Canvas dropping
still feeds the current generator. Tab shortcuts 1–5 select Compose, Assets,
Plot, Pens and Settings. Editing shortcuts defer to fields, drawing tools and
modal editors. Preset selection/application stays visible; management folds
under Manage presets, and seed dice follow the normal bounded form change path.
