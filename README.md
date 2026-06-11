# axibridge

A locally-run, full-stack **layer compositor for the AxiDraw V3 pen
plotter**. Generate or upload geometry as layers on a canvas that *is* the
machine bed (300 × 218 mm — what you see is where it plots), shape each
layer with a non-destructive effect stack, resolve fill-aware occlusion
between layers, and plot pass-by-pass with a global pen library whose
barrel-diameter-driven offsets keep multi-pen passes registered on the sheet.

An experimental instrument, not a production plotting tool: motion
parameters are first-class controls, soft limits are toggleable, and a **raw
EBB console** sits underneath the planner. Why it's built this way:
[ARCHITECTURE.md](ARCHITECTURE.md). How to extend it:
[docs/MODULES.md](docs/MODULES.md). Working in the repo with an agent:
[CLAUDE.md](CLAUDE.md).

## What's in the box

- **The canvas** — an SVG-native editor over the full machine reach:
  select / multi-select, move / scale / rotate handles, a movable A4 paper
  guide for registration ("origin = guide corner" binds the frame to the
  taped sheet), portrait/landscape *display* rotation (geometry never
  changes), schematic and **ink-simulation** views (true stroke widths and
  transparency), draw-order shading, travel overlay, and accelerated
  animated playback of the planned job.
- **Layers** — provenance (generator params or uploaded SVG), affine
  transform, reorderable **effect stack** (paper-space: a mm is a mm at any
  scale; ships with coherent noise-field jitter and multipass), pen
  reference, and occlusion: per-layer *occluder* / *receives* flags with a
  signed margin (+gap / −bleed). **Preview, estimates and plot all consume
  the same resolved geometry** — the one invariant.
- **Pens** — a global library (colour, calipered barrel ⌀, line width,
  opacity, optional per-pen pen-heights). One two-pen calibration of the
  V-cradle holder makes every pen's nib offset derivable from its diameter;
  passes land registered across pen swaps. Guided wizard included.
- **Three execution backends**, deliberately not feature-symmetric, each
  advertising capabilities so the UI never shows dead knobs:
  **native** (pyaxidraw + plotink: full motion params, jog, raw EBB
  trapdoor), **simulator** (whole app usable unplugged), **saxi** (thin CLI
  hand-off to saxi's planner).
- **Projects are folders** — a diff-able `project.json` plus the source
  SVGs; zip export/import. Pen library and machine settings (estimator
  calibration, host/port) stay machine-level in `~/.axibridge/`.

## Install

Requires Python ≥ 3.10.

```bash
git clone <this repo> && cd axibridge
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[occult,dev]"

# Official AxiDraw API (native backend only — not on PyPI):
pip install https://cdn.evilmadscientist.com/dl/ad/public/AxiDraw_API.zip

# Optional, saxi backend (needs Node.js):
npm install -g saxi
```

Without pyaxidraw or saxi the app still runs — those backends report
themselves unavailable *naming the interpreter they're missing from* (the
classic failure is installing pyaxidraw into a different Python; the
diagnostic makes that a one-glance fix), and the simulator carries the full
workflow.

## Run

```bash
axibridge                      # 0.0.0.0:2942 — open http://localhost:2942
axibridge --host 127.0.0.1     # local only
pytest                         # 24 tests, all hardware-free
```

**macOS double-click:** `launch/axibridge.command` — pins the venv
interpreter (the one with pyaxidraw), starts the server, opens the browser.

**Always-on (launchd):** `launch/com.axibridge.plist` — ~0% CPU idle but a
constant ~100 MB resident set held 24/7; right for an always-reachable Pi,
usually wrong for intermittent desktop use. Install notes in the file.

> **No authentication, by design.** The server binds the LAN for the
> Pi/Tailscale workflow and trusts the network. Bind `127.0.0.1` or keep it
> on a tailnet if that's not your situation.

## Deploy headless on a Raspberry Pi 5

```bash
sudo apt install python3-venv
git clone <this repo> ~/axibridge && cd ~/axibridge
python3 -m venv .venv && .venv/bin/pip install -e ".[occult]"
.venv/bin/pip install https://cdn.evilmadscientist.com/dl/ad/public/AxiDraw_API.zip
sudo usermod -aG dialout $USER    # serial permission; re-login
```

`/etc/systemd/system/axibridge.service`:

```ini
[Unit]
Description=axibridge AxiDraw interface
After=network.target

[Service]
ExecStart=/home/pi/axibridge/.venv/bin/axibridge
User=pi
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now axibridge
```

Frontend is zero-build (vanilla ES modules, vendored fonts — works offline);
SSE reconnects across roaming; all state lives server-side, so any browser
on the tailnet picks up the same canvas. `tailscale serve 2942` gives HTTPS.

## The five-minute tour

1. **Compose**: generate a polygon (filled) and a lissajous; drag them to
   overlap on the canvas. Mark the polygon *occluder* — the curve clips
   around it live. Dial the margin negative and watch it bleed instead.
   Stack a coherent jitter on either layer; scale the layer and note the
   wobble stays in mm.
2. **Pens**: add your pens — caliper the barrels. Assign one per layer.
3. **Plot** (simulator first): pick a layer as target, Plot,
   pause/resume/stop, watch live position on the canvas. Then the native
   backend: connect, jog, pen-height test with live sliders, plot for real.
   Swap pen, next layer — passes register via the holder calibration
   (Plot tab wizard, once).
4. **Raw EBB** (native): `QM`, `V`, `SM,1000,500,500`… replies surfaced.
   Below-the-planner territory; soft limits deliberately don't apply.
5. **Save** — the project folder is plain JSON + SVGs; commit it, diff it,
   zip it elsewhere.

## Repo map

```
axibridge/
  model.py          # PathDocument — the geometry⇄execution contract
  compose.py        # layer model + compositor (occlusion, resolve) — v2's spine
  session.py        # one open project; THE resolve pipeline
  registry.py       # Source / Effect / Transform protocols + registration
  sources/ effects/ transforms/   # drop-in modules (see docs/MODULES.md)
  stores.py         # global pen library + machine settings (~/.axibridge/)
  project_io.py     # project folder save/load/zip
  calibration.py    # holder-offset wizard + pen height test geometry
  estimate.py       # time estimator (NOT a planner; constants in Settings)
  svg_io.py         # fill-aware SVG reader (svgelements) + vpype interop
  backends/         # base protocol, native, simulator, saxi
  machine.py        # port arbitration, job thread, soft limits
  api.py events.py app.py
  static/           # zero-build frontend (canvas editor, tabs, forms)
launch/             # macOS .command launcher + launchd plist
tests/              # 24 hardware-free tests
```
