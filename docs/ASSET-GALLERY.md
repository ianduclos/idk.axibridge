# Asset gallery

The gallery keeps finished line shapes locally, across all projects. Open
**Gallery** in Compose to browse thumbnails, search names/notes/tags/origins,
filter by tag or generator, and adjust thumbnail size. Newest captures appear
first. Search, filters, size and scroll position survive closing the panel
within the current app page.

**Save to gallery** is available in the selected layer's Effects area and in
the process/Homeostat, Second Reading and Magnetic benches. A compact dialog
shows the captured shape, a suggested name, optional comma-separated tags and
a note. Saving leaves the original layer or working bench untouched.

Layer capture includes its transform and own effects, before external regions,
occlusion or plot-pass operations. Animation capture uses the current timeline
frame. Region-only layers have no drawable output to collect. Bench capture
uses the exact completed preview recipe and full generator geometry, not the
rounded/simplified preview lines. Pending renders and gestures disable capture.

Select an asset to inspect or edit metadata. **Add as layer** creates an
independent baked layer at its original physical size and orientation,
centered on the current paper guide. There is no automatic fit for oversized
assets. The layer has an empty effect stack and normal default pen behavior;
its placement and new effects can be edited normally. Insertion is undoable.
Deleting or changing the library original cannot affect inserted copies.

## Storage and API contract

`gallery.py` owns `CONFIG_DIR/gallery/<id>.json` (normally
`~/.axibridge/gallery/`). Version-1 records contain metadata and ordered,
full-precision paths including closure and filled flags. Writes use a lock,
temporary file, flush/fsync and atomic rename. Invalid records are omitted
from listings with a warning. The metadata index is derived from file
timestamps; files remain authoritative.

`gallery_api.py` exposes `/api/gallery` list/save, `/prepare`, `/{id}`
detail/update/delete, `/{id}/thumbnail` and `/{id}/insert`. List/detail payloads
exclude geometry. Thumbnails are derived SVGs requested lazily; display
sampling never changes stored paths. Generator provenance is descriptive,
not a recipe or a live dependency.

Preparation accepts either `{kind: "layer", layer_id, master_t}` or
`{kind: "generator", module, params}`. It freezes a full snapshot and returns
`capture_id`, preview SVG and metadata. Save accepts that ID plus name/tags/note.
The capture ID becomes the asset ID, making a repeated save idempotent.
Captures are transient: one hour, at most 16 entries and a 3-million-point
budget, protecting the newest drawing. Expired captures require reopening
the save dialog. Uncertain writes are not automatically retried.

Inserted geometry uses the existing project snapshot format, with 17-digit
coordinate serialization rather than six-decimal rounding, so project
folders remain portable without the library. The gallery has no separate
plot path or hardware operations. Folders, synchronization, recipe recall,
multi-layer capture and bulk management are deferred.
