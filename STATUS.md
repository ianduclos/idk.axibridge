---
project: idk.axibridge
state: active
updated: 2026-07-10
machine: mac+pi
summary: Uncanny push complete — the Pi's unattended run shipped all four generators (merged d53580d, suite 275 green both machines); live server restarted on current code after a version-skew report.
next:
  - Try the new vocabulary on paper — misremembered/two-hands/grammar sources, region-bitmapped compositions, tube interlocks (recipes in docs/IDEAS-oehlen-pass.md)
  - Sheets workflow v2 per the 2026-07-10 analysis (see conversation/ROADMAP): staged captures as the interp substrate, stepper ergonomics
  - Glyph grammar (Oehlen item 4) + tuning notes in docs/plans/pi-generators-RESULTS.md (lattice grammar, subtree-propagating violations, misremembered on a real photo)
  - Workbench v2 when felt — mouse drawing, scrap editing (docs/IDEAS-oehlen-pass.md §0)
handoff_for: null
---

# idk.axibridge — status

**Session 2026-07-10 — the uncanny-generator push (9 commits on `main`,
suite 241 green Mac / 242 Pi).** Two idea passes are now repo docs:
`docs/IDEAS-generators.md` (Cohen/intentional-line direction) and
`docs/IDEAS-oehlen-pass.md` (Oehlen regime collision, with a shipped/pending
ledger). Shipped from them:

- `effects/freehand.py` — the Cohen kernel: eye-leads-hand spring-damper,
  steering-space tremor, per-stroke fatigue, drawn-then-snapped closure.
- `effects/bitmap.py` + `effects/fat_tube.py` — the regime vocabulary
  (staircase quantizer anchored to layer translation; round-capped filled
  pipes that occlude/interlock via existing masks).
- **Region layers** (`CanvasLayer.region`): a layer's placed silhouette
  masks, and its effect stack applies to the layers below (inside clipped +
  effected, outside untouched). Resolve order is now
  `occlusion(regions(effects(transform(source))))` — ARCHITECTURE.md
  "Resolve order". Regions render dashed, never plot, and tween for free.
- **Generation workbench** (⚗ Bench button): stateless playground popup
  (`POST /api/workbench/preview` touches no session/undo/lock), global
  scrap library (`scraps.py`, `~/.axibridge/scraps/` — frozen SVG + recipe),
  import live (generator layer + effects) or baked (frozen SVG, named).

**Infrastructure:** repo is on GitHub — `github.com/ianduclos/idk.axibridge`
(private); `main` is the shared trunk (old `feat/grid-sheets` absorbed by
fast-forward). idkpi has a full dev clone at `~/idk.axibridge` (write deploy
key, green venv — needs `httpx2` there, newer starlette) and a systemd user
timer that fired **08:33 WEST 2026-07-10** running Fable 5 unattended
against `docs/plans/pi-generators.md` (continue-strokes, misremembered
image, bézier shape grammar with transgression budget, two hands
negotiating) — results push to `feat/pi-generators`, never main. The
`.claude/skills/pi` skill documents the whole Pi workflow durably.

## Prior arc

**Grid sheets (2026-07-07, merged into main 2026-07-10).** Plot many
timeline frames onto one physical sheet (1/2/4/16 per page) without the
destructive contact-sheet bake; `session.sheet_document` is transient
plot-time assembly through `resolved()` only, one shared scale, grouped by
pen. Tests: `tests/test_sheets.py`. Known limitation: `doc_to_svg` colours
sheet SVG layers from vpype's palette, not the exact pen colour.

July 2026 animation arc (18 commits, suite 177 at the time): frame-sequence
assets with video import; master timeline scrubbing through the single
resolve path; one-click animate; clip-follow; plot-time crop; pywebview app
shell (`launch/AxiBridge.app`). Frame-ladder recipe in `ROADMAP.md`.

Architecture and module contracts: `ARCHITECTURE.md`, `docs/MODULES.md` —
non-negotiable invariants (single resolve path; scrubbing never mutates
stored state). Deployment note: two AxiDraw modes contend for the serial
port — Mac-driven pi_ssh (default, live-verified) vs Pi-served
`axibridge.service` at `idkpi:2942` (disabled by default). See
`../../02_Areas/__claude/SYSTEM.md` arms table.
