# Idea pass 3 — AARON mechanisms, context, felt-tip color (July 2026)

Third concept pass, grounded in Harold Cohen's AAAI-1988 paper *How to Draw
Three People in a Botanical Garden*
(https://www.aaronshome.com/aaron/publications/how2draw3people.pdf).
Companion to `docs/IDEAS-generators.md` (pass 1, the hand) and
`docs/IDEAS-oehlen-pass.md` (pass 2, regime collision). Motivation: the
two_hands source is a good tool but chaotic — AARON's coherence comes from
mechanisms it lacks, and Cohen documented them concretely.

## AARON's mechanisms (from the paper — the raw material)

1. **Closure by imaginary destinations.** Closed forms drawn "rather like
   the way one might drive a closed path in a parking lot by imagining a
   series of intermediate destinations, veering towards each in turn and
   finally returning to one's starting point" — under a standing
   **never-overlap injunction** that forces mid-line plan changes. Spatial
   identity is the *result* of a linear operation, not its cause.
2. **The conceptual core.** Every later closed form starts as a
   skeleton/scribble (marked cells); the form is **embodied** by a
   feedback-mode maze-walk around the core — "no line is ever fully planned
   in advance." A **carefulness parameter** varies along the body: "a thigh
   rather loosely — at some distance from the core and with a relatively
   low sampling rate — while … a hand close to the core and with a high
   sampling rate." Sharp concavities are special-cased → the
   self-overlapping folding of outlines.
3. **Everything consults the drawing.** "All higher-level decisions are
   made in terms of *the state of the drawing*" — space availability is
   sensitive to the whole decision history. No eraser; foreground-first;
   once forms became thing-like, **occlusion became the fundamental
   principle of pictorial organization**.
4. **Composition = find space.** "Put it where you can find space for it,"
   plus a crude floor plan (2D allocation projected to a ground plane) just
   for where feet land and how tall things are.
5. **Knowledge levels.** Declarative (parts) → exemplary (proportions) →
   structural (articulations) → functional (legal ranges) → behavioral
   (**balance and gesture**). Plants: an entire flora from a few
   morphological variables (branching, limb thickness vs. level, leaf
   clustering, size).

Why two_hands reads chaotic against this: perception + response but no
closure, no thing-ness, no space discipline. All three are existing
axibridge primitives (filled paths, occlusion masks, z-order).

## The proposals

### A. Core-figure generator (the flagship)

Grow a skeleton first — plant-morphology variables or a figure armature
with a **balance constraint** — then **embody**: a closed outline walked
around the skeleton chasing imaginary destinations, carefulness varying
along the body (this is the freehand controller with per-segment
confidence/step modulation). Output closed + `filled=True`. Place several
foreground-first under the never-overlap rule by checking the mask of
what's already placed — the richness is in the mid-flight swerves, per
Cohen. Quasi-figurative, coherent, all machinery exists.

### B. Context awareness: the sheet-snapshot asset

Generators are pure and can't see other layers — but they can see assets.
One endpoint/button rasterizes the current resolved output into an asset
(`sheet#now`); every image-driven generator becomes context-aware for
free: a negative-space filler (horror-vacui dial), two_hands v2 whose
agents perceive the actual sheet, a "respond" generator that
echoes/avoids/annotates existing marks. AARON's "decisions in terms of the
state of the drawing," axibridge-native, zero architecture change.

### C. Color for transparent felt tips (overlap = multiply = free third color)

- **Overprint zones**: posterize an image / take filled shapes into 2–3
  color zones and emit the **pairwise intersections as first-class shapes
  drawn in both pen layers** (shapely intersections; occlusion margins
  already model registration slop).
- **Cohen's color logic**: late AARON colored by rules over *value*
  relationships, hue nearly free. Assign pens to tonal bands by value
  rule, randomize hue within bands — palettes weird in hue, always right
  tonally.
- **Duotone density mixing**: cross-hatch two transparent colors at
  complementary densities from one darkness map — a hue gradient from two
  pens.
- **Repetition as pressure**: N passes darken transparent ink; per-path
  `weight` from any map = tonal drawing with one pen (pairs with the
  motion-trails roadmap item).

### D. linedraw v2 (flexible, sophisticated)

Decompose the pipeline into swappable stages: edge extraction
(Sobel/XDoG/coherence), stroke *tracing* (orientation-aware chaining,
curvature smoothing, min length), and **flow-aligned tonal work** —
streamline hatching following the image's local gradient/structure
direction (etching/hedcut), not one global angle. **Multi-layer output by
tonal band**, each band its own texture/angle/**pen** (PathDocument
already supports multi-layer returns) — plugs straight into C's felt-tip
separations. Add a carefulness curve (tight on edges, loose in tone).

### E. Smaller

- **Balance rule** as a reusable constraint (things must plausibly stand —
  AARON's behavioral level; potent even for abstraction).
- **Carefulness** promoted to a first-class effect param varying along
  paths near features.
- **Foreground-first composer recipe**: large filled forms with
  never-overlap, then small marks find space — the antidote to all-over
  chaos.

Pull order: A → B → C+D together (they share multi-layer-per-pen
plumbing) → E opportunistically.
