# Ribbon effect shipping pass — 2026-09-08

Ian approved shipping the accepted open-path ribbon study as a registered effect.
D3 (one oscillating envelope crossing its source) is the next separate effect,
sharing profile/geometry helpers; explicitly deferred this pass.

Production contract: pure Python `Ribbon`, paper-space mm, closed/dot inputs
bypass, grouped Pydantic schema. Preserve accepted seeded profiles, normalized A/B
blend, corner handling, self/inter-path masks, silhouettes, outline mode, side
wavelengths, edge interpolation and pen density. Pen density reads the assigned
layer pen through EffectContext, with pen-dependent cache keys. No runtime Node.
Port geometry in internal units at 4/mm to preserve the tested study constants;
all public inputs/outputs and parameters remain millimetres.

New optional controls: crest softening (accepted default .055 wavelength), seeded
asymmetry in approach/departure smoothing; remove_outer pairs as a global cutoff.
Retain min(length-budget, total-removed) so length-culled short lines stay unchanged
until the global cutoff reaches them. Keep at least one strand pair.

User agrees a later popup/live preview would suit parameter density. This pass
uses grouped forms (Shape, Rhythm, Strands, Output), not a new bench architecture.

Validate Python-vs-study profiles/geometry, effect purity/closure, masking/fill
metadata, seeded softening, auto pen density/cache invalidation, grouped schema
in real UI and the hardware-free suite. No push or plotter actions. A running
native app must not be interrupted with unsaved work.
