"""Browser contracts for the Territory bench: live dials, locks, Back, and Keep = what is on the stage."""
from __future__ import annotations

import json

from test_acceptance_ui import _get, frontend_mode, select_layer, server, ui  # noqa: F401 (fixtures)


def _open(page) -> None:
    page.wait_for_function("() => !!document.querySelector('#gen-select option[value=territory]')")
    page.select_option("#gen-select", "territory")
    page.click("#btn-bench")
    _drawn(page)


def _drawn(page) -> None:
    page.wait_for_function("""() => { const c = document.querySelector('#territory-canvas');
      return c && !c.hidden && +c.dataset.strokes > 0 && document.querySelector('#tb-keep')?.disabled === false; }""",
                           timeout=30_000)


def _recipe(page) -> dict:
    return json.loads(page.locator("#territory-canvas").get_attribute("data-rendered-recipe"))


def _set(page, key, value) -> None:
    page.locator(f"#tb-d-{key}").evaluate(
        "(el, v) => { el.dispatchEvent(new Event('pointerdown')); el.value = v;"
        " el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }", value)


def test_territory_dials_locks_back_and_keep(ui, server):
    _open(ui)
    first = _recipe(ui)
    _set(ui, "complexity", 0.9)
    ui.wait_for_function("() => JSON.parse(document.querySelector('#territory-canvas').dataset.renderedRecipe).dials.complexity === 0.9")
    _drawn(ui)
    before = _recipe(ui)
    ui.click("#process-territory .tb-lock[data-lock=complexity]")
    ui.click("#tb-surprise")
    ui.wait_for_function(f"() => document.querySelector('#territory-canvas').dataset.renderedRecipe !== {json.dumps(json.dumps(before, separators=(",", ":")))}",
                         timeout=30_000)
    _drawn(ui)
    assert _recipe(ui)["dials"]["complexity"] == 0.9          # locked dial survived Surprise me
    ui.click("#tb-back")
    ui.wait_for_function(f"() => document.querySelector('#territory-canvas').dataset.renderedRecipe === {json.dumps(json.dumps(before, separators=(",", ":")))}",
                         timeout=30_000)
    _drawn(ui)
    assert _recipe(ui) == before and before != first
    strokes = int(ui.locator("#territory-canvas").get_attribute("data-strokes"))
    ui.click("#tb-keep")
    ui.locator("#tb-kept", has_text="Kept as a new layer").wait_for()
    layer = _get(f"{server}/api/project")["layers"][-1]
    assert layer["source"]["generator"] == "territory"
    params = layer["source"]["params"]
    assert len(params["strokes"]) == strokes
    assert params["recipe"]["seed"] == before["seed"] and params["recipe"]["complexity"] == 0.9
    assert not ui.errors


def test_territory_resume_restores_the_recipe(ui, server):
    _open(ui)
    _set(ui, "density", 0.8)
    ui.wait_for_function("() => JSON.parse(document.querySelector('#territory-canvas').dataset.renderedRecipe).dials.density === 0.8")
    _drawn(ui)
    kept = _recipe(ui)
    ui.click("#tb-keep")
    ui.locator("#tb-kept", has_text="Kept as a new layer").wait_for()
    ui.click("#process-close")
    layers = _get(f"{server}/api/project")["layers"]
    select_layer(ui, 0)   # the dock lists the newest layer first
    ui.click("#process-resume")
    ui.wait_for_function("() => document.querySelector('#process-popup')?.classList.contains('territory-bench')")
    _drawn(ui)
    assert _recipe(ui) == kept and len(layers) >= 1
    assert not ui.errors


def test_territory_version_8_planes_fill(ui, server):
    _open(ui)
    _set(ui, "density", 1)
    ui.wait_for_function("() => JSON.parse(document.querySelector('#territory-canvas').dataset.renderedRecipe).dials.density === 1")
    _drawn(ui)
    grown = int(ui.locator("#territory-canvas").get_attribute("data-strokes"))
    ui.click("#tb-fill-v8")
    ui.wait_for_function("() => JSON.parse(document.querySelector('#territory-canvas').dataset.renderedRecipe).v8 === true")
    _drawn(ui)
    assert ui.locator("#tb-d-planes").is_hidden() and ui.locator("#tb-d-mutate").is_hidden()
    assert "version 8" in ui.locator("#tb-recipe").text_content()
    assert int(ui.locator("#territory-canvas").get_attribute("data-strokes")) != grown
    ui.click("#tb-keep")
    ui.locator("#tb-kept", has_text="Kept as a new layer").wait_for()
    assert _get(f"{server}/api/project")["layers"][-1]["source"]["params"]["recipe"]["fill"] == "v8"
    ui.click("#tb-back")
    ui.wait_for_function("() => JSON.parse(document.querySelector('#territory-canvas').dataset.renderedRecipe).v8 === false")
    assert not ui.errors
