# Territory v5 research 2: procedures from precedents

Scope: what artists *do* (decision rules, sequencing, revision), turned into checkable machine rules. Not a look-alike list. Source depth varies and is flagged. Where a source only supports a general claim, the rule is my extrapolation, marked "(extrapolated)".

**The references (3.15.04, 3.15.39).** I could not identify the artist and did not find them by search; I won't guess a name. What is legible procedurally: painted or monoprinted grounds where *white paper is the ray or slat, removed from ink* (subtractive marks), tube and horn forms with a lattice or blue-checked interior visible through the mouth, spiky burst outlines in the one black line, and one heavy, rendered form set against loose flat ground. Ian's own read, "a bit rigid, but maybe it can do something," fits: the transferable part is authority contrast (one rigid register against soft ones) and apertures with a foreign inside, not the rays or bursts.

## 1. Harold Cohen / early AARON (strongest, primary source)
**Why:** the only precedent that states drawing as decision rules, and Ian already cites it.
**Procedure:** Cohen's ["What Is an Image?"](https://aaronshome.com/aaron/publications/whatisanimage.pdf) (IJCAI 1979) lists three primitives: figure/ground, open/closed, inside/outside. The first development of any figure decides, by frequency, that it will be closed, open, or "uncommitted": a line or complex is drawn and only later decided whether to close. Some closed forms are never outlined; "the definition of the occupied space" waits for later space-filling moves. Forms come from a repetition protocol ("go a given distance, change direction, repeat"); an overriding avoidance protocol "guarantees the territorial integrity of existing figures"; and the program knows the current intention but "will not know what shape will result." A current development can also be "stacked" to do something not originally envisaged.
**Rule:** every stroke is born with a *commitment state* in {closed, open, uncommitted}, drawn from a set frequency. Uncommitted strokes may close at a later pass or never. Check: log the state per stroke; at least 30% of strokes end open, and at least 1 per cell resolves late.
**Warning:** copying the surface gives cartoon amoebae and rounded blobs (the disliked family). Cohen's coherence comes from avoidance plus repeated intention, not from the closed outline.

## 2. Cy Twombly
**Why:** revision as visible content; weight from accumulation and correction, not fill.
**Procedure:** sources are secondary and thin ([Getty](https://www.getty.edu/art/exhibitions/twombly/explore.html), [LRB "Drawing Out Twombly"](https://lareviewofbooks.org/article/drawing-out-twombly/), [ARTDEX](https://www.artdex.com/in-contemplation-of-lines-and-scribbles-cy-twomblys-beautiful-writing/)). Reported habits: graphite loops, crossing-out, erasure and smudge that stays on the sheet as a record of the earlier state; the famous quote "childlike but not childish... has to be felt." Erasure and rewriting are both left as marks.
**Rule (extrapolated):** a "cancel" pass. Some restated strokes are not near the target; they cross a previous stroke at a steep angle (>40 degrees) and stop, as a strike-through. Check: 1 to 3 cancels per cell, never parallel to what they cancel.
**Warning:** looping cursive scribble and "writing" texture (asemic handwriting). Cancels should be rare and directed, not a fill.

## 3. Willem de Kooning (closed-eye drawings; tracing overlays)
**Why:** two procedures for pentimenti, one blind, one archival.
**Procedure:** [Hyperallergic on the closed-eye drawings](https://hyperallergic.com/flying-blind-de-koonings-closed-eye-drawings/): 24 charcoal drawings made with eyes closed, pad held flat, often starting "by the feet... more often by the center of the body," showing little revision. [ARTnews "De Kooning Paints a Picture"](https://www.artnews.com/art-news/news/de-kooning-paints-a-picture-2123/) and [Tate on Women Singing II](https://www.tate.org.uk/research/in-focus/women-singing-ii/process-and-memory): before changing a painting he traced whole sections onto transparent paper, tested changes on overlays, and returned to a canvas holding two states of one area (overlay and underlay).
**Rule:** two-state rule. A restated stretch is drawn against a *frozen snapshot* of the earlier state (not a fresh jittered copy), and where the snapshot and current state disagree by >5 mm, both are kept. Check: each restated bundle traces to a stored snapshot index.
**Warning:** de Kooning's lush charcoal gradients and figure fragments. Blind drawing also means *no correction*; do not mix the two, or the searching reads as fur.

## 4. Picasso, The Bull (1945-46)
**Why:** the reverse of accumulation: states that remove until a contour survives.
**Procedure:** [Norton Simon "States of Mind"](https://www.nortonsimon.org/exhibitions/2010-2019/states-of-mind) (page blocked on fetch; content from search summary), [MoMA state VII](https://www.moma.org/collection/works/62986), [Lavin, "Picasso's Bulls" (IAS)](https://publications.ias.edu/sites/default/files/Lavin_OP_ArtWithoutHistory_1987.pdf): eleven states from one stone, from shaded and realistic down to a few lines, each print a reworking, "he had to pass through all of the intermediary stages" (Mourlot).
**Rule:** a reduction pass. After the sediment is built, one late pass *removes* the middle strokes of a bundle and keeps the first and last (oldest, newest). Check: heaviest bundles lose >=40% of strokes before output; the outermost strokes are never removed.
**Warning:** the tidy end-state is a minimal contour drawing, the exact clean line Ian did not ask for. Take the discarding, not the simplification.

## 5. Vera Molnar (Interruptions, Desordres, 1% de desordre)
**Why:** the cleanest procedure for shaped negative space from deletion.
**Procedure:** [Right Click Save interview](https://www.rightclicksave.com/article/an-interview-with-vera-molnar); [DAM (Des)Ordres](https://dam.org/museum/artists_ui/artists/molnar-vera/des-ordres/). Interruptions (from 1969): random sections in which lines are erased, "voids shaped both by the missing elements and those nearby." Randomness as "artificial intuition," and she selects among outputs ("You need to draw boundaries somewhere"). Her "imaginary machine" checks what each change did.
**Rule:** interruption by *gap coordination*: when a stroke is cut, neighbouring strokes within 15 mm are cut over an overlapping span (not the same span), so the void has a shape. Check: the void's convex-hull solidity is between 0.5 and 0.85 (neither slit nor disc).
**Warning:** a grid with holes. Her order is the rigid frame; here the frame is the contour graph, not a lattice.

## 6. Henri Michaux (mescaline drawings)
**Why:** lines that turn into something else at the rhythm level, drawn *from memory of a rhythm*.
**Procedure:** [Miserable Miracle text](https://doorofperception.com/wp-content/uploads/Henri-Michaux-Miserable-Miracle.pdf), [Studio International](https://www.studiointernational.com/index.php/henri-michaux-the-mescaline-drawings-courtauld-gallery-london): he could not draw during the acute phase; he drew from the "vibratory motion" that persisted for days, at speed, pages "more palpable than legible," half writing and half drawing.
**Rule (extrapolated):** a *rhythm carrier*. One stroke inherits a single oscillation (wavelength 3 to 8 mm) from the previous stroke and keeps its phase across a junction, so a border continues as a tremor-thread then fades. Check: autocorrelation peak persists >30 mm across a register change.
**Warning:** tremor-line "calligraphy" on every stroke. One carrier per cell.

## 7. Louise Bourgeois (Insomnia drawings; spirals)
**Why:** repetition as working-through; direction of travel changes control.
**Procedure:** [Art UK](https://artuk.org/discover/stories/a-voyage-with-no-destination-louise-bourgeoiss-1960s-drawings), [Artsy](https://www.artsy.net/article/artsy-editorial-louise-bourgeoiss-drawings-reveal-creative-process): one line begets another "in a loosely systematic style"; she reported less control drawing a spiral outside-in than inside-out.
**Rule (extrapolated):** direction sets discipline. Passes travelling *toward* a knot centre run loose and lose accuracy, those leaving it run tight. Check: knots show asymmetric jitter by direction (variance ratio >1.5).
**Warning:** obsessive-pattern filler and spirals as a motif (already flagged in earlier reviews).

## 8. Philip Guston (late drawings)
**Why:** a line that becomes a cloud, a sun or hair, and correction by wiping.
**Procedure:** [Hyperallergic, Guston's Line](https://hyperallergic.com/philip-gustons-line/): "all he relied on was a line," no rendering or shading, the line becomes a rounded shape or short strokes become hair, and when dissatisfied he wiped or scraped and drew something else. [Brooklyn Rail](https://brooklynrail.org/2008/07/artseen/philip-guston-works-on-paper/): varying line weight, clusters of lines.
**Rule:** job change by *count*, not by renderer: the same line spec becomes a contour at n=1, a mass at n>=4 (dense short returns), a thread at n=0 (a lone tail). Check: a stroke has at least 2 different local pass counts along its length.
**Warning:** cartoon-object figuration and thick outline style.

## 9. Julie Mehretu
**Why:** layered structure erased or sanded so what survives is uneven.
**Procedure:** [Art21](https://art21.org/read/julie-mehretu-to-be-felt-as-much-as-read/): "the more the information is layered in a way that's hard to decipher what is what. And that's intentional"; "the erasure itself became the action." [Art Story](https://www.theartstory.org/artist/mehretu-julie/): layers separated by clear acrylic, begins with an architectural structure, adds, subtracts, erases.
**Rule:** *structure then loss*. Start from a rigid scaffold layer (long chords), then drop cells of it where later layers are dense. Only remnants that touch a later stroke survive. Check: >=60% of chord length is removed, and every surviving remnant terminates on or crosses a later stroke.
**Warning:** confetti of marks, architectural plan drawing, atmospheric dust. Scaffold must stay sparse and unpainterly.

## Others considered
- **Albert Oehlen** ([Two Coats of Paint](https://twocoatsofpaint.com/2015/07/albert-oehlens-genius.html)): self-imposed constraints, changing material to prevent routine ("gives an insecurity to the work that is very helpful"), stopping before "agonizingly chewed-over." Rule: **stop early** on a per-cell budget. Little sequencing detail found.
- **Anders Hoff / inconvergent** ([site](https://inconvergent.net/), [sand-spline](https://github.com/inconvergent/sand-spline)): displacement of many points by small noise, differential growth. Useful mainly as a warning: uniform per-point noise is exactly the "one handwriting everywhere" failure.
- **Mark Tobey** ([Art Story](https://www.theartstory.org/artist/tobey-mark/)): "multiple focus," several centres in one all-over net. Rule: two competing foci per sheet, unequal. Weak procedural evidence beyond that.
- **Not covered:** Mitchell, Winters, Marden, Nake, Mohr; no usable procedural sources found in the time spent.

## The five rules, ranked

1. **Every stroke carries a commitment state (closed / open / uncommitted) and closure may be decided late** (Cohen). Maps to: **pass-state machine**, with an added "uncommitted" state; and **fraying net on one lobe** (a lobe decided as held only late). Check: 30%+ open, 1+ late resolve per cell. It is the only rule with primary-source procedure and it directly prevents blobs.
2. **Restate against a stored earlier state, keeping both where they disagree, capped at 2 to 3 fronts per cell** (de Kooning overlays). Maps to: **sediment / palimpsest**. Check: each bundle has a snapshot index; not more than a third of bundles evenly spaced.
3. **Remove before you finish: a reduction pass drops middle strokes of a bundle and keeps oldest and newest** (Picasso's states, Mehretu's erasure, Oehlen's early stop). Maps to: **event scarcity budget** and **silent winner**. Check: heaviest bundles lose >=40%; weight ratio heaviest:lightest >=5:1. This is what turns tree rings into a sling.
4. **Gap coordination: cuts in one stroke are answered by overlapping-but-offset cuts in neighbours** (Molnar), with the void's edge marked by cusp hooks only at T-ends. Maps to: **aperture / pushing void** and **cusp hooks**. Check: void solidity 0.5 to 0.85; hooks on <=30% of ends.
5. **The same line changes job by local pass count** (Guston), and carries a rhythm across the change (Michaux). Maps to: **line that changes jobs**, **good continuation at junctions**, **contest register field**. Check: 2+ pass-count regimes per stroke; rhythm autocorrelation persists across junctions. One shared carrier per cell only.

Also worth a cheap try: Twombly-style **cancels** (rule 2 above) as a single directed stroke per cell; it is the one procedure that adds "searching" with almost no ink.

## Confidence
High: Cohen (primary text read). Medium: de Kooning, Picasso, Molnar, Mehretu (secondary or interview summaries). Low: Twombly, Michaux, Bourgeois, Guston, Tobey as *procedure* (mostly descriptions of results); the rules attached to those are mine.
