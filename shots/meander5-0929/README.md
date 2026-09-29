# Meander 5: the lines make the field (29 September 2026)

Ian's notes on Version 8 are verbatim in `docs/plans/territory-meander-round-5.md`. The fills were hatch planes that ignore the lines, and he wanted "the opposite", with "mutations happening within", after the river image. The brainstorm is `docs/research/meander5/brainstorm.md` (Opus). The reviews are "Meander 5, round 1/2" in `docs/reviews/meander-sonnet.md`. Everything was judged on screen only; nothing was plotted.

## Engine (`t_density.js`, `growField`)

The ground is grown from the drawing as **echo trains**.
- A train starts on a sub-arc of a drawn line, a ribbon or a continuation, preferring the inside of bends.
- Each echo is offset from the *previous* echo, never from the source, so any change is inherited.
- **Migration:** curvature at the scale of the bend (about 16 mm) sets the offset, and the outside of a bend moves faster.
- **Pinch:** the gap varies along the arc and the variation accumulates, so sets pinch and open like grain.
- Spacing opens outward from the source, and smoothing builds up with age.
- **Mutations** are inherited by later echoes:
  - swale (a spacing jump);
  - buckle, which the migration amplifies;
  - neck cutoff, which leaves an oxbow;
  - chute (a break that widens);
  - fan hinge;
  - split into daughter trains.

  After K echoes, a train carries on as a new generation with re-rolled parameters.
- **Where trains stop:**
  - at other lines, and at other trains (so sets truncate each other);
  - at the shard voids and the inner quiet zone of knots;
  - when the train closes into a tight ring.

  Cut ends feather back, and trains thin out at the end.
- **Planes:** below 0.5 the Version 8 brushed planes are only 1–3 isolated facets that cross the lines, with a small capped share of ink. From 0.5 to 1 they blend back to all planes.
- **Over:** Density goes to 1.5; Continue, Slash and Surprise to 2 (over 1.3 gives two surprises); Mutate to 1.5.
- **Recipes:** a recipe without `planes` (Version 8) is byte-identical. Density 0 hash `7df7ab2d4579`, Version 8 at 0.7 `3459b012fb50`, at 1 `015d6c1e8680`. Pasting a Version 8 recipe on the page runs it on that path and says so.
- Outside Version 8, the crosshatched disc surprise is gone; the review read it as a stamp.

## Page (Version 9)

- Two new sub-dials, Planes (default 0.15) and Mutate (default 1).
- Cover defaults to 0.45, as Ian asked.
- The dials that go over 1 are labelled "Past 1 is over".

## Known gaps

- At max, the grown field uses about 25–30 m, not the ink limit, because a field needs lines to grow from. Empty halves stay empty unless Continue adds ribbons.
- Scallop fronts can still read as topo at Mutate over.
- Every surprise is now a thorn star, which risks repetition.
