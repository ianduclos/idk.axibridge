"""Registry-wide module-contract enforcement.

The effect contract (docs/MODULES.md) has always been prose: be pure, be
deterministic, preserve ``filled``/closure, bound every numeric param. Prose
protects nothing — these tests run the whole registry through the contract so
every CURRENT and FUTURE module is covered the moment it registers, with no
per-author opt-in. (`test_view_coherence.py` is the precedent: a design
position locked as a test.)

What is deliberately NOT asserted here: that a closed input yields a closed
output. Effects legitimately transform geometry (hatch_fill adds open hatch
lines, fat_tube replaces a spine with an outline, clipping can open a loop) —
the enforceable invariant is the one-way implication ``filled ⇒ closed``: an
open path claiming to be filled is always a bug, because occlusion masks
polygonize filled paths only when they close (compose.build_mask).
"""

import copy

import pytest

from axibridge import registry
from axibridge.model import Path, is_closed
from axibridge.registry import EffectContext

# Parametrization reads the registry at COLLECTION time, but registration
# only happens when load_builtin_modules() imports every module in the
# packages (normally the app lifespan does this) — without this call the
# registry is empty here and every parametrized test silently skips, which
# is exactly the failure mode a contract test must not have.
registry.load_builtin_modules()

# Fixtures sized to the bed, varied enough that structure-following effects
# (eyelets, parasite_line, freehand) have something to bite on: a filled
# square occluder, an open wiggle with corners, and a single-point dot.
def _fixture_paths() -> list[Path]:
    square = [(60.0, 60.0), (100.0, 60.0), (100.0, 100.0), (60.0, 100.0), (60.0, 60.0)]
    wiggle = []
    for i in range(24):
        x = 30.0 + i * 5.0
        y = 140.0 + (12.0 if (i // 4) % 2 else -12.0) * ((i % 4) / 3.0)
        wiggle.append((x, y))
    return [
        Path(points=square, filled=True),
        Path(points=wiggle, filled=False),
        Path(points=[(150.0, 30.0)], filled=False),  # a dot
    ]


def _ctx() -> EffectContext:
    return EffectContext(layer_id="contract", translation=(3.0, 4.0), seed=1234)


def _dump(paths: list[Path]) -> list[tuple[bool, list[tuple[float, float]]]]:
    return [(p.filled, list(p.points)) for p in paths]


def _run(effect_id: str) -> tuple[list[Path], list[Path]]:
    eff = registry.effects()[effect_id]
    ok, reason = eff.available()
    if not ok:
        pytest.skip(f"{effect_id} unavailable: {reason}")
    paths = _fixture_paths()
    return paths, eff.apply(paths, eff.Params(), _ctx())


@pytest.mark.parametrize("effect_id", sorted(registry.effects()))
def test_effect_purity_input_unmutated(effect_id):
    paths, _ = _run(effect_id)
    frozen = copy.deepcopy(_dump(paths))
    eff = registry.effects()[effect_id]
    eff.apply(paths, eff.Params(), _ctx())
    assert _dump(paths) == frozen, f"{effect_id} mutated its input"


@pytest.mark.parametrize("effect_id", sorted(registry.effects()))
def test_effect_deterministic_under_fixed_ctx(effect_id):
    _, first = _run(effect_id)
    _, second = _run(effect_id)
    assert _dump(first) == _dump(second), (
        f"{effect_id} is not deterministic under fixed (params, ctx)"
    )


@pytest.mark.parametrize("effect_id", sorted(registry.effects()))
def test_effect_filled_implies_closed(effect_id):
    _, out = _run(effect_id)
    for i, p in enumerate(out):
        if p.filled:
            assert is_closed(p.points), (
                f"{effect_id} output path {i} claims filled=True but is not "
                f"closed — occlusion masks would silently degrade it to a "
                f"stroke band"
            )


def _unbounded_numerics(params_cls) -> list[str]:
    schema = params_cls.model_json_schema()
    bad = []
    for name, prop in schema.get("properties", {}).items():
        if prop.get("type") in ("number", "integer"):
            # a Literal/const numeric (e.g. rotate: Literal[0, 90, 180, 270])
            # is bounded by enumeration — tighter than any min/max
            if "enum" in prop or "const" in prop:
                continue
            if "minimum" not in prop or "maximum" not in prop:
                bad.append(name)
    return bad


def test_every_numeric_param_is_bounded():
    """CLAUDE.md: "Bound every numeric field — unbounded values reach an
    open-loop machine." Verified clean across the whole registry on
    2026-07-19; this keeps it that way."""
    offenders = {}
    for eid, eff in sorted(registry.effects().items()):
        bad = _unbounded_numerics(eff.Params)
        if bad:
            offenders[f"effect:{eid}"] = bad
    for sid, src in sorted(registry.sources().items()):
        bad = _unbounded_numerics(src.Params)
        if bad:
            offenders[f"source:{sid}"] = bad
    assert not offenders, f"unbounded numeric params: {offenders}"
