# Generator and effect browsers

Compose has separate **Browse all…** entry points for generators and effects.
These are selectors: **Use** prepares existing controls rather than editing
geometry. Choosing a generator clears the live layer latch and prepares new
material. Choosing an effect prepares **Add** on the selected layer.

Visible category chips filter generators by Procedural,
Image or Bench (Bench membership can overlap); effects by Line, Shape or
Agnostic. Effect categories describe intended input, not output geometry:
Ribbon takes lines even when it creates filled ribbons. The detail pane shows
a larger copy of the same identifier SVG, without another render.

Optional personal ratings run from 1 to 5 and can be cleared; favorites remain
independent. Sort by name, rating, most-used, least-used or recently used.
Usage records successful generation/application through the regular controls,
not browser selection, previews or preset draft loading. A coalesced generator
edit run counts once; effect reorder, removal, enable toggles and unchanged
settings do not count. Undo/redo and project reopening leave these personal
statistics alone. Usage starts when this feature is installed, with no invented
history. Failed usage persistence is logged without failing a project edit.

Press Enter to turn a tag into a removable box. Frequently used tags are offered
for quick entry; Save tags persists the edited set.

Names lead the browser. Small fixed examples identify each tool; they do not
change with your drawing. Search covers names, descriptions, personal tags
and preset names. Presets stay grouped under their owning tool and have no
thumbnails. Stars narrow the quick dropdowns; with no stars, all tools remain
visible. The currently selected tool stays available even when unstarred.
Search, filters and scroll survive closing the browser within the app page.

## Named starting settings

Generator controls, editable working benches and individual effect controls
share the same preset row. Choose **Defaults** or a named preset, then
**Load preset** for a draft or **Apply preset** for an existing layer/effect.
Selecting an item alone does not apply it. Existing geometry changes through
the normal generator/effect pipeline with one undo checkpoint. Read-only Watch
views have no preset controls.

**Save as preset** creates a named variation; duplicate names are allowed.
**Update selected** explicitly replaces that preset's settings. Editing the
working controls never updates saved presets automatically. Rename and delete
are available in the browser; deletion requires confirmation and leaves
already applied settings alone. Failed saves retain the entered name.

Presets remember starting parameter values and seeds. They exclude source
image references, captured paths, intervention histories and UI state. Current
compatible image inputs are retained when loading; other excluded interaction
state resets to defaults. In particular, Magnetic's captured arrangements and
four-corner blends are not part of a module preset; Second Reading starts with
fresh interventions and branches. These presets are distinct from Magnetic's
in-bench arrangement corners and from the asset gallery's finished geometry.

A generator preset applied to baked geometry uses the existing regeneration
semantics and requires confirming replacement of that bake. Missing modules
or incompatible parameter values produce an explanation without applying;
the saved record remains available for renaming or deletion.

## Storage and extension contract

The module library lives under `CONFIG_DIR/module-library/`, independently of
projects and gallery assets. Its versioned JSON contains stable preset IDs,
module kind and ID, name, timestamps, parameter values, and module preferences
(stars/tags, ratings and usage). Locked atomic writes protect edits. Presets do not embed source
images, geometry or project references.

The `/api/module-library` boundary lists presets/preferences and provides
preset create/detail/update/delete, preset resolution, preference updates and
module identifier thumbnails. Source and effect IDs are separate namespaces.
Resolution validates against current schemas, supplies defaults for newly
added fields and rejects incompatible saved values rather than silently
ignoring them. Extraction and resolution share the same exclusion policy.

Module metadata exposes representative settings and explicit preset
exclusions. When adding a module with captured interaction fields, declare
those exclusions and test their reset behavior. Fixed identifying examples
must exercise the actual module with appropriate input, rather than reuse
unrelated geometry as a placeholder. Image fixtures render in an isolated
process so library browsing cannot replace the project's asset store.
Identifier work is lazy and bounded. Successful SVGs are atomically cached on
disk under the module library so closing the browser or restarting the backend
does not rerun them. A content key includes implementations, shared helpers,
examples and fixtures, plus bundled fonts for text tools. Shared code changes
can invalidate multiple identifiers. Failed identifiers leave the tool name
available. Cached thumbnails never become saved or plotted geometry.

Preset thumbnails, saved effect chains, bundled source images, live comparison,
synchronization and a command launcher are deferred.
