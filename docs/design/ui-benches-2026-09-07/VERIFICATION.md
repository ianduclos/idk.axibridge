# Study verification — 8 September 2026

**Ready for Ian to check.** This is browser verification of a disconnected design
artifact, not application acceptance or a claim about physical input feel.

1. `check_study.py` opens the local HTML in headless Chromium. Fifteen layout
   combinations cover three workspaces, desktop/900px/700px widths, and both bench
   presentations. Each checks horizontal overflow, complete paper containment,
   paper aspect ratio and successful local image loading.
2. The interaction sequence checks capture cancellation via Escape, stored-example
   continuation, branching, comparison, failure/Keep gating, retry without advancing,
   simulated Keep, return/resume, popup expansion without losing the selected
   alternative, expanded layer dock, picker entry and sampled Homeostat playback.
   A separate actual 720px browser viewport checks page overflow.
3. The primary visually inspected desktop Compose and both benches, compact controls,
   comparison plus failure, and narrow Compose. An initial comparison crop under
   reduced stage height was corrected with stage-local width/height fitting; the
   final check explicitly asserts both comparison images stay inside that stage.
4. Fixtures are reproducible with `make_fixtures.py`; every generator SVG has its
   exact parameter JSON. Homeostat's displayed telemetry is labelled illustrative.
   The style and fonts load locally; the mockup needs no application server.

[Machine-readable check results](assets/browser-checks.json). No browser page errors
were reported. The full application suite/build/typecheck were not rerun because
application sources and dependencies were untouched. Prior implementation test
counts remain historical evidence in STATUS.md.

## Captures

| # | Workspace | Desktop | Compact | Small |
|---|---|---|---|---|
| V1 | Compose | [1440](assets/compose-desktop-embedded.png) | [900](assets/compose-compact-embedded.png) | [700](assets/compose-small-embedded.png) |
| V2 | Second Reading, workspace | [1440](assets/second-desktop-embedded.png) | [900](assets/second-compact-embedded.png) | [700](assets/second-small-embedded.png) |
| V3 | Second Reading, popup | [1440](assets/second-desktop-popup.png) | [900](assets/second-compact-popup.png) | [700](assets/second-small-popup.png) |
| V4 | Homeostat, workspace | [1440](assets/homeostat-desktop-embedded.png) | [900](assets/homeostat-compact-embedded.png) | [700](assets/homeostat-small-embedded.png) |
| V5 | Homeostat, popup | [1440](assets/homeostat-desktop-popup.png) | [900](assets/homeostat-compact-popup.png) | [700](assets/homeostat-small-popup.png) |

1. [Expanded compact controls](assets/second-compact-controls.png).
2. [Comparison with shared frame](assets/second-compact-compare.png).
3. [Local failure with comparison](assets/second-compact-failure.png).
4. [Expanded layer dock](assets/compose-compact-expanded-layers.png).
5. [Actual narrow browser](assets/compose-actual-narrow.png).

The compact shelf deliberately scrolls; complete drawing frames and primary actions
remain in the working area. Small comparison panes remain small rather than cropping
to fill. Owner trial should decide whether comparison should automatically close the
control shelf or remain an explicit choice. This is an open comfort question, not a
reason to claim fit alone settles the layout.
