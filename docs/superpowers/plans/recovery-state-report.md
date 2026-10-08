# Recovery state handoff

Implemented `axibridge/recovery_state.py` and `tests/test_recovery_state.py`. The primary integrates the mixin into `Session`; this worker did not edit `session.py` or shared files.

Integration: inherit `RecoveryStateMixin` before `Session`'s other bases and call `self.init_recovery_state()` at the end of `Session.__init__`, after the project, maps, history, and lock are initialized. Call `begin_project()` after New/Load establishes the new project and assets; call `mark_saved()` only after a successful named save. `checkpoint_recovery()` captures under `Session._lock`, writes without that lock, and returns store metadata. `recovery_status()` returns `{dirty, revision, session_id, recovery}`; the nested recovery dict holds successful metadata and/or an `error` string after a failed write. `recovery_store` lazily constructs `RecoveryStore` and can be used by integration to list/load/discard.

The fingerprint covers project settings/layer metadata, non-tween source geometry list identities, uploaded SVG content, staging metadata/document identities, capture snapshot identity, and immutable asset contents (updated by the lead after asset race review). It excludes serializer-generated source and sheet paths, derived tween geometry, render caches, and preview/scrub state. Strong references keep identity comparisons safe. A return to the saved content becomes clean; each observed state change increments the revision. `capture_recovery()` detaches mutable model and map state while sharing geometry lists under the repository's immutable geometry contract.

Verification: test collection initially failed on the missing module. Final `.venv/bin/python -m pytest -q tests/test_recovery_state.py tests/test_recovery_storage.py`: **16 passed**. Compileall of both recovery modules and `git diff --check`: passed. The full suite was not rerun; the primary owns integrated verification.

Integrated follow-up: recovery writes and Save/replacement serialize with an
RLock; clean checkpoints do not recreate archives. API asset handlers validate
detached content and publish under the Session lock only if the project token
is still current. Failed same-name uploads retain prior bytes and stay clean.
Six asset regression checks and five recovery race checks pass; integrated
full-suite evidence belongs to the execution ledger.
