# Recovery, groups and Assets visual evidence — 2026-09-30

Captured from the final five-tab built frontend in headless Chromium against a real axibridge server on a temporary port with a temporary `AXIBRIDGE_CONFIG_DIR` and `AXIBRIDGE_NO_AUTOCONNECT=1`. No plotter or user project was accessed.

The seeded project, “Nested marks study,” has three polygon layers in two nested groups (“Inner marks” inside “Outer composition”) and a generated 128×96 PNG asset named `synthetic-study.png`. Compose screenshots enter the outer group and expand the Layers dock so the nested group and its sibling are visible. Assets screenshots show the real uploaded asset and the Depth Pro status. A recovery checkpoint of this same project was written to the temporary config store, then the server was restarted to show the startup offer with project name and timestamp.

| View | 1024×768 | 1500×950 |
|---|---|---|
| Compose, nested group context | [compose-1024x768.png](compose-1024x768.png) | [compose-1500x950.png](compose-1500x950.png) |
| Assets | [assets-1024x768.png](assets-1024x768.png) | [assets-1500x950.png](assets-1500x950.png) |
| Startup recovery offer | [recovery-1024x768.png](recovery-1024x768.png) | [recovery-1500x950.png](recovery-1500x950.png) |

[assets-depth-1024x768.png](assets-depth-1024x768.png) shows the lower part of the Assets tab after scrolling.

The browser reported no page errors or tab-strip overflow in these captures. Visual inspection is provisional until Ian checks the native app. At 1024×768, the expanded Layers dock exposes the nested group but compresses the sibling layer name and actions; the Depth Pro controls sit below the Assets tab fold and require scrolling. At 1500×950, all Assets sections and their status are visible together. The recovery dialog fits both viewports.
