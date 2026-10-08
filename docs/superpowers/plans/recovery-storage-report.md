# Recovery storage handoff

Implemented `axibridge/recovery.py` and `tests/test_recovery_storage.py` only.

Interface:

- `RecoverySnapshot(project, source_geometry, svg_files, assets, staging_documents, history, revision, session_id, project_dir)` is a dataclass. `history` uses the existing project I/O four-item history tuples.
- `RecoveryStore(root: Path | None = None)` defaults to `CONFIG_DIR / "recovery"`.
- `write(snapshot) -> dict` returns `id`, `revision`, `name`, UTC `created_at`, and `project_dir`.
- `list_entries() -> list[dict]` returns newest first. An entry served from the prior archive includes `fallback: true`.
- `load(recovery_id) -> (metadata, loaded_project)` returns the metadata plus the six-item tuple from `project_io.load_project`.
- `discard(recovery_id) -> None` removes only that ID's current and previous archives.

The ZIP includes `recovery.json` beside the ordinary project files. Writes build in a temporary folder, reuse `project_io.save_project` and `export_zip`, fsync a temporary ZIP, rotate a valid current ZIP to the prior slot, and atomically replace the current ZIP. A failed replacement leaves a valid archive loadable. Loading extracts with `project_io.import_zip` into a temporary directory, then loads all content into memory. IDs accept 8–64 hex characters or canonical hyphenated UUIDs.

Verification: initial test collection failed with the missing module; the UUID test failed before UUID support was added. Final `.venv/bin/python -m pytest -q tests/test_recovery_storage.py`: **10 passed**. `.venv/bin/python -m compileall -q axibridge/recovery.py` and `git diff --check`: passed. The full suite was not rerun; the lead owns integrated verification.
