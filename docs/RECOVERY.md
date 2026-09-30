# Kept-project recovery

Recovery protects kept layers, hierarchy, sources, imported media, project
settings, frozen staging sheets and the last four saved undo states. Unkept
bench drafts remain outside recovery; the recovery dialog says this explicitly.
Previews, timeline scrubbing and machine motion do not count as edits. Asset
uploads validate detached bytes before publication; failed replacement preserves
the original asset. Publication shares the Session lock and rejects results
computed for a project that has since been replaced.

The server observes persistent content under the Session lock. Its metadata
exposes `dirty`, monotonic `revision`, `session_id` and `recovery` (checkpoint
name/time/revision or an error). Returning to saved content through Undo is clean.
The header's dot marks unsaved edits; its tooltip reports the last checkpoint
or recovery failure. A successful checkpoint leaves content dirty until saved.

Every 30 seconds, changed dirty content is captured into a detached snapshot and
written below the machine config's `recovery/` directory. Each session has a
current ZIP and a previous valid fallback. Archives contain their metadata,
project and source files together. Temporary files, fsync and atomic replacement
protect the previous checkpoint on write failure. Named project folders are
written only through explicit Save/Export/Import.

Startup offers Restore, discard the selected candidate and start fresh, or keep
candidates for later. Older projects appear in the same selector. Restored
content stays unsaved. New/Load/Import require Save, Continue with recovery,
Discard or Cancel when dirty; checkpoints survive switching until their project
is saved or explicitly discarded. Failed import validation keeps the open
project and its recovery. There is no automatic expiry.

Native close checkpoints before allowing the window to close and cancels on
failure. The existing owned-server active-plot guard still runs first. Restart
requires explicit `continue_with_recovery` for dirty content, checks the latest
revision before execution, and refuses a failed checkpoint. Save, checkpoint and
replacement coordinate through one recovery write lock; disk writes use detached
content and revision checks prevent later edits being marked saved or replaced.

Native window behavior and paper output remain manual acceptance.
