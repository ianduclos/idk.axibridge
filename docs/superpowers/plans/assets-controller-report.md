# Assets controller handoff

Implemented `axibridge/static/js/assets_tab.js`. Exports:

- `initAssetsTab({ onAssetsChanged = () => {} } = {})`: renders Gallery, SVG import, image/video and sequence import, clear unused assets, and Depth Pro into `#tab-assets`.
- `renderAssetList()`, `uploadAssetFiles(files, options = {}, busyEl = null)`, `refreshDepthProStatus()`, and `setAssetProgress(frac, msg)`.

Integration completed by the lead: added the Assets tab button/body, called `initAssetsTab({onAssetsChanged: ...})` after state hydration and before panel collapse memory, and routed SSE `gen` events to `setAssetProgress` as well as Compose's progress handler. The callback refreshes Compose's source and detail asset selects. Imported `uploadAssetFiles` into Compose for canvas drop. Removed the old Gallery/import/assets markup and handlers plus the old asset-list/Depth Pro functions from Compose. Canvas drop wiring remains in Compose. Gallery insert's existing `gallery.js` handler already switches to Compose and selects the inserted layer.

The new `tests/test_assets_tab_ui.py` covers image upload/clear, SVG import staying on Assets with the prior layer selected, Gallery insertion returning to Compose, and the progress element's location. `tests/test_recovery_ui.py` covers startup selection, explicit discard, Save/Continue/Cancel, error handling, force reopen and acknowledgment. After shared-file wiring, `.venv/bin/python -m pytest -q tests/test_assets_tab_ui.py tests/test_recovery_ui.py` passed: 10 tests in 12.45 seconds. A prior built startup failure was traced to `main.js` dropping its `setSeqProgress` import; the lead restored it, and a fresh isolated Chromium smoke then loaded 37 generator options without page or console errors. Integrated visual evidence is in `shots/recovery-groups-0930/README.md`. No full suite was run by this worker.

Final browser follow-up: preset/menu/700 px precision checks passed (20). The
Settings tab's overflow was caused by engraved letter-spacing within five grid
cells; the lead removed tab letter-spacing. All seven screenshots were recaptured
from the final build with no page errors and no tab overflow at both sizes.
