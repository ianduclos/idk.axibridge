# Form controls handoff — 2026-09-30

## Behavior

- `forms.js`: bounded numeric fields named `seed` gain an accessible dice button beside the number input. A click chooses within the schema bounds (inclusive integer maximum and correct exclusive-bound handling), updates the number and slider, and calls the existing setter once. Rendering does not roll a value. Unsafe or missing integer ranges do not create an arbitrary fallback range.
- `module_library.js`: preset select and Apply remain visible. Save as preset and Update selected retain their classes and handlers inside a closed `Manage presets` disclosure. Existing selection, busy locking and update-disabled rules remain in place.
- `tests/test_form_comfort_ui.py`: real-browser tests cover unchanged seed on render/reload, a persisted single reroll commit at the inclusive maximum, lower-bound selection, disclosure visibility, save, update and Apply.

## Verification

- `.venv/bin/python -m pytest tests/test_form_comfort_ui.py -q` → 3 passed (built frontend fixture).
- `npm run typecheck` → passed.
- `git diff --check` → passed.

## Integration note

`tests/test_module_library_ui.py::test_failed_save_keeps_dialog_name_and_does_not_duplicate` clicks Save as preset while the disclosure is closed. Immediately before that click (currently line 82), open `controls.locator('details summary').click()`. This shared test was left to the lead per file ownership. No other shared test references the hidden Save/Update buttons.

Integration is complete: the shared module-library test opens Manage presets,
and preset undo assertions compare persistent content independently of the
monotonic recovery revision. Subsequent bounded group acceptance added distinct
multi-frame sampling, varying topology, reflected midpoint and Unanimate cases;
the final focused group acceptance run passed all 12.
