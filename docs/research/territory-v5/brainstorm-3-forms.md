# Territory v5 brainstorm 3: strange but coherent forms

Lens: open outlines from the v2 contour network turn into forms that make you ask what is going on. Brainstorm only. Nothing here has been built or plotted.

## What Ian's sketch actually does

Read as mechanisms, not as a picture:

- (s1) **A single line becomes a doubled line.** The top arch is two parallel strokes with open ends. That is a tube or lip seen from its cut end, so it is an aperture made from nothing more than a line doubling.
- (s2) **Bundles sit where forms press together.** The basin under the central mass has 3 to 5 near-parallel passes. The free lobes have one or two. Weight comes from repeated passes along a *shared* edge, not from fill.
- (s3) **Lines enter a lobe and curl.** A hook enters the right lobe from outside and stops. It reads as the surface turning away.
- (s4) **The upper left is a fanned sheaf.** It is a different register: one gesture repeated with drift.
- (s5) **Almost nothing is closed**, but everything touches something.

The coherence comes from continuity and from lines being shared. The strangeness comes from one line doing different jobs. The ideas below build that out.

## Ideas

### 1. The line that changes jobs (border to lip to fold to thread)
**Decision:** a line does not have one identity. It becomes something else as it passes through different situations.
**Mechanism:** walk each v2 contour by arc length and assign a regime at each sample from data already in the engine:
- **border**: where the contest `s` is near `eps`, draw a plain line.
- **lip**: where a border meets an outer edge, add an inward offset copy 1.5 to 3 mm away, on the side that arrived later.
- **fold**: at curvature peaks above a threshold, with at most 3 per cell, the pen reverses. It runs back parallel 2 to 4 mm inside for 10 to 30 mm, then stops.
- **thread**: where the contour leaves every territory and runs into a void or off the edge of the field, continue along the tangent as a single stroke with a slow gravity sag for 20 to 60 mm.

It stays one pen-down polyline, so continuity carries the coherence.
**Weight:** folds and lips double the ink locally and threads thin it out. Weight follows events, not areas.
**Failure:** reads as ribbon or drapery, or as a calligraphic flourish.
**Kill:** folds show up at regular intervals, or on every lobe. If more than a third of the cells on a contact sheet read as "ribbon", stop.

### 2. Aperture with a foreign inside
**Decision:** a form opens, and what is inside obeys a different rule from what is outside.
**Mechanism:**
1. **Pick the mouth.** Choose 1 or 2 dash gaps (from the v2 fade gaps) of 8 to 30 mm where the same camp label lies on both sides of the gap.
2. **Build the opening.** The chord between the two ends is the mouth. The far rim is an arc that bulges into the territory, from the inflation height of the camp mask (v4 `inflate`, local bbox only). The near lip is doubled, as in s1, and both ends curl inward.
3. **Fill it with foreign material.** Run a second `runTerritory` at 3 to 5 times smaller scale with a different seed and clip it to the aperture. Let its contours stop *on* the lip, not short of it. The other option is a sparse net (idea 3).

**Weight:** the inside is dense and fine, the lip is doubled, and the outside stays open.
**Failure:** porthole or picture-in-picture. A clean oval lip reads as an inset frame. Two apertures side by side read as eyes and a face.
**Kill:** any cell that reads as a face or mask. Also kill if the lip reads as a drawn ellipse rather than a contour opening up. Never place two apertures level with each other.

### 3. Net on one lobe, as an event
**Decision:** one form in the drawing gets a skin. It is the exception, not a texture.
**Mechanism:**
1. **Choose the lobe.** Take the largest late-arrival territory or the one with the most shared border. Exactly one per cell.
2. **Build the surface.** Height comes from `inflate` on that camp's mask.
3. **Draw two families of lines.** One is isolines of that height. The other is gradient-flow lines seeded evenly along the lobe's border. Draw both sparsely: 6 to 10 lines per family, spaced wider at the crown and tighter toward the rim, so the mesh wraps.
4. **Let the net misfit the outline.** Shift it 2 to 6 mm and rotate it a few degrees so it slips off one side and overshoots the contour. Tear 1 or 2 holes where cells are dropped.

**Weight:** the netted lobe is the heaviest passage in the cell and everything else stays open. That is Ian's "more weight at parts".
**Failure:** globe, wireframe, fishnet stocking, CAD mesh.
**Kill:** the lobe reads as a sphere or as a rendered 3D wireframe. Also kill if the net lies exactly inside the outline, because a fitted net stops being strange.

### 4. Bundled borders: contest becomes tangle
**Decision:** weight belongs where the camps fought, which is s2 in the sketch.
**Mechanism:** each border point already knows how long it was contested. Count the arrivals that redrew nearby borders (v2 already produces near-coincident lines when borders shift, and the reviewer protected those overlaps). Redraw each border segment `n = 1 + k·contest` times with `t_hand` jitter. Let the passes braid with occasional crossings. Where `n` goes above about 6, raise the jitter until the bundle breaks into a textural scribble. Uncontested outer edges stay single and broken.
**Weight:** this is the main weight engine. It is organic line in one place and texture in another, driven by one variable, so it stays coherent.
**Failure:** the NPR "sketchy outline" filter look, where every line is evenly doubled, or hair.
**Kill:** the pass count looks even across a cell. There should be at least a 5:1 ratio between the heaviest and the lightest border, visible in a thumbnail.

### 5. Endings are cusps: contours turn away, they don't stop
**Decision:** a contour that ends inside a form is a surface folding out of sight. This is Koenderink's result on where apparent contours end.
**Mechanism:** at every dash end that falls inside a territory, bend the last 4 to 10 mm toward the concave side and taper it by shortening and slightly waving it. At 1 or 2 ends per cell, add 3 to 6 short strokes on the hidden side, running parallel to the fold, as a hint of the surface behind.
**Weight:** small, but it accumulates at the ends of breaks. It turns the v2 dash gaps into spatial events.
**Failure:** hooks everywhere become the spiral-curl ornament the round-1 review warned against.
**Kill:** hooks read as a repeated motif. Cap them at about 20% of the endings and suppress any within 25 mm of another.

### 6. Two light regimes sharing one line
**Decision:** incompatible spatial readings coexist, split along an existing border.
**Mechanism:**
1. **Split the page.** Pick one long v2 border and call it the seam.
2. **Depth side.** Territories on one side get the round-2 U-style flank hatch from a consistent light at the upper left, with the lit third left bare.
3. **Surface side.** Territories on the other side get flat parallel slats at one global angle that ignore the form and overshoot outlines, like the rays in the reference.

The seam is drawn once and belongs to both readings.
**Weight:** heavy flanks on one side, sparse slats on the other.
**Failure:** two drawings pasted together, or a comic "burst".
**Kill:** the seam doesn't read as one contour doing two jobs, or the slats form a regular grating.

### 7. A body made of refusal (void as a lobe)
**Decision:** the strangest form on the page is not drawn at all.
**Mechanism:** take one void mask (`S[0]`) and make it large. Bundles, nets and hatch from neighbouring forms stop at its edge. Every line that reaches the edge uses the idea 5 turn-back instead of a clip. The void's outline is never drawn. It is implied by the ends of 15 to 30 lines.
**Weight:** none inside and dense at the rim. This is shaped negative space, which the round-1 review said voids failed to deliver.
**Failure:** reads as nothing, the sheet-N problem.
**Kill:** the void doesn't read as a shape in at least 4 of 12 cells.

## Ranking

1. **The line that changes jobs (1).** It is the only idea here that produces strangeness *and* coherence from the same property, one continuous line, and it is literally what Ian's sketch does (s1, s3). It needs no new form family, only the v2 contours plus field lookups, which respects his "b". It also answers "one handwriting everywhere" at the level of a single stroke rather than by mixing renderers.
2. **Bundled borders (4) with a single net lobe (3) as its one exception.** Bundling gives the unequal weight and the organic-to-textural range Ian asked for, driven by composition history, so it means something. The net gives the "what is going on" event. Pairing them keeps the net rare.

The aperture (2) is the most seductive idea and the highest risk (faces). I would try it third, one per sheet, not one per cell.

## Where I disagree with the lead's framing

- **Keep v4 inflation out of sight.** Use it only as a hidden height field for the net, lip depth and flank direction. Never render its isolevels as outlines: that is exactly the "concrete" soft body Ian rejected.
- **Density should come from repetition along shared edges (s2), not from interior fill.** Every interior-fill renderer so far has landed on a named cliché: rings, coral, engraving.
- **"Unpredictable" should be a scarcity budget, not more randomness.** Cap each strange event (fold, aperture, net, cusp) per cell, so every cell gets a different *combination* of events rather than all of them at once. The v2 base already supplies plenty of randomness.
- **Protect the empty ground.** "More dense" should mean denser passages, not a fuller page.
