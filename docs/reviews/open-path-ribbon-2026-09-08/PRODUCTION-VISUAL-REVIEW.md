# Production ribbon visual review

This was a non-blind second-eye review: I knew the smoothing mechanism and the decision under review. I inspected the full production sheet and enlarged crops of all nine cells. The browser could not open the local HTML under its URL policy, so the close views came directly from the supplied PNG.

## Decision

Preserve **Accepted smoothing** as the default. Offer **More softening** and **Uneven softening** as optional moves. I see no objectionable new crossing in either option, and the corner masking remains legible. More softening changes the character enough to be useful; uneven smoothing is subtler and carries one local risk described below.

## Reading

1. **Straight / Accepted** has the strongest sequence of unequal events: a small dark intake, a broad open crest, a long low lens, then a hard little diamond. The diamond is an awkward feature worth protecting. It stops the profile from becoming one fluent exhalation and makes the long quiet passage before it feel consequential.

2. **Straight / More** turns that diamond into a low capsule and fattens the approach to the first crest. The result is calmer and more continuous, but it loses the useful snap between the long lens and the final line. This is a credible optional register, not a better default.

3. **Corner / Accepted** makes the small event after the corner read as a separate knot or hitch. In **More** and **Uneven**, it becomes a longer folded continuation of the corner. That relation is attractive: the bend appears to send material down the new arm. It also explains more of the drawing, so retaining the sharper default leaves more unresolved.

4. **Loop / Accepted** is the strongest argument for the default. The two narrow, pointed upper-left lobes are almost uncomfortably sharp beside the larger lower bell. Removing them would lose the abrupt change of authority and the peculiar empty wedges between those passages. More smoothing converts that interruption into a single soft pod; readable, but tidier and less surprising.

5. **Loop / Uneven** gives the upper-left pod a shallow sequence of flank bends. At full-sheet scale these create a slight stutter; enlarged, they can read as buckling or contour noise because the rest of the family remains very smooth. This is the only visible feature I would watch closely. It does not cross itself or overshoot the local envelope in this sheet.

## Weak and uncertain cases

6. **Straight / Uneven** is nearly indistinguishable from More smoothing. Its differences do not yet redirect attention or offer a clearly different compositional move.

7. **Corner / Uneven** is also weak as evidence for unevenness: the changed flank cadence is too slight to matter beside the corner itself. The option may still prove useful across a broader seed population; these two cells do not demonstrate that range.

## Focused next check

Plot or render only the upper-left loop passage and the small post-corner event at final physical scale, comparing accepted, more, and uneven smoothing. Those two sites expose the actual trade: preserving sharp punctuation versus allowing a crest to extend through a turn. The screen preview cannot establish whether the uneven loop stutter survives as useful phrasing on paper or collapses into pen-density noise.


## Lead follow-up after Ian's clarification

Ian clarified that unevenness belongs independently to each rising/falling
flank of each crest. The final implementation now assigns separate seeded
radius targets at flank midpoints and smoothly interpolates through peaks and
troughs. The production sheet was regenerated, and the lead inspected it plus
`production-flank-close.png`. The optional uneven loop retains the shallow
buckling observed above; no new crossing is visible in this fixture. The accepted
fixed-radius default is unchanged. This is a lead follow-up, not a second blind
review, and paper acceptance remains open.
