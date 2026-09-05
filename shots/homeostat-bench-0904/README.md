# Homeostat — first bench session, 2026-09-04

Ian's own bench runs on the day the module shipped (`55da3b8`), kept because
they are the first evidence of what it actually does and the matplotlib contact
sheet did not show it.

What they establish, and what the module's own docs did not predict:

- **The knot.** Tight polygonal rosettes — closed orbits where the pen curls
  into a near-regular heptagon and retraces it — appear wherever `turn_bias`
  dominates `wander` in the rerolled hand. They are the strongest thing in the
  frame, they read as "the system was in trouble here" and nothing in the design
  put them there. They are an emergent signature of one region of genome space.
- **The travel.** Long, almost empty sweeps between knots. The contrast between
  a knot and a travel is doing most of the compositional work.
- **The seam is invisible.** A reroll changes the hand and marks nothing. In
  `01` and `02` the eye finds the knots, not the transitions — which is the
  opposite of the design's claim that "the seam lands where the system was in
  trouble, which is a reason the sheet can show".
- **Walls still attract a biased hand** (`04`, top and right edges). True
  reflection cut wall-pinning to 0.5-2.6% of points, but a hand with a strong
  turn bias still tracks a boundary once it arrives.

NOT reproducible as-is: the bench does not record the seed and params that made
a given picture, so these four cannot be regenerated exactly. That gap is worth
closing before the next session.
