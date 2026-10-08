# Mosca 2 bench implementation

Approved direction: give the more complex Mosca × Territory experiment a
native Mosca 2 bench, preserving the original Mosca bench and the earlier
flowing line. Implementation is isolated in `codex/mosca2-bench`.

## Contracts

1. A frozen `mosca2` source stores exact paper-space parts and exchanges;
   generation imports no neural runtime. Keep/Resume use normal bench adapters
   and the normal source/resolve/project pipeline.
2. A draft composer loads the six preserved pieces, generates Territory,
   adds the seven earlier flowing sources, and transforms individual parts.
3. An immutable page snapshot drives one isolated full-brain process. The
   original flowing kinematics, decoder and renderer travel together. Sensors
   share paper coordinates with rendered ink, including new ink after a
   200 ms exclusion. There is no learning or continued-neural-state claim.
4. New responses append only to their unchanged originating draft. History
   offers before/additions/combined, cancellation and consistent undo. Saved
   geometry remains portable without Mosca data or runtime.

## Implementation and checks

1. Register bounded models and pure replay; verify exact geometry and portable
   project save/load/ZIP. Bounded Sol assignment: source and source/API tests.
2. Implement geometry mapping, worker and cancellable job/API boundary.
   Verify request bounds, snapshots, malformed results, failure and cancellation.
3. Implement bench UI and adapter. Bounded Sol assignment: JS/CSS, then UI
   regression tests. Primary owns shared integration and final acceptance.
4. Run a real paired contact-on/off experiment against unchanged weights;
   inspect the actual browser Run → Keep → Resume workflow and exports.
5. Ask Astra for a bounded critical review, fix material issues, run relevant
   tests plus the full hardware-free suite, typecheck/build, and document
   remaining native/paper acceptance. Commit the verified checkpoint.

No model installation, live-app restart, hardware activity or push is part of
this isolated implementation. Main-branch integration is a separate explicit
history operation under the shared workshop rules.
