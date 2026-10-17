"""Frozen Hand Drift engine — a vendored, trimmed copy of the gesture research.

FROZEN FROM research commit c897f28 (2026-10-17), `tools/gesture/gesture/`:
`grammar.py` (order-2 token chain, `generate_tokens`, `tokens_to_points`),
`curvature.py` (`integrate_kappa`), `hybrid.py` (`HybridGrammar`,
`route_weights`, `drift_line`), `regime.py` (RegimeStroke, footprint, render,
from_field), `penrender.py` (nib styles a / b+ / c / e / c+e), `regime_field.py`
(`noise_fronts`) and `gesture_timing.py` (`ink_profile`, `line_profiles`).

Research keeps evolving in `tools/gesture/`; this copy does not follow it.
The animation stability contract (equal params ⇒ equal geometry) means a
kept layer never changes underneath the user, so edits here are deliberate
version changes, never syncs. Only what the drift and its regimes use is kept;
behaviour is otherwise unchanged except where marked "app:" (no PIL in the
pen-lift chaining mask; outline rings kept separate so they can be `filled`).

Dependencies: numpy, scipy, shapely. Data: `hands/` (frozen grammars and
dance tempo profiles, written by `tools/hand_drift/freeze.py`).
"""

FROZEN_FROM = "c897f28"
