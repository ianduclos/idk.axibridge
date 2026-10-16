# Typography as a source of hands: Arabic letterpress and vintage print (research, 2026-10-16)

**Scope.** Ian's brief, after two clarifications: the **letterpress and
vintage-print look in Arabic script**. That covers 19th–early-20th-century
movable type (Bulaq, Beirut, the European presses) and the 1950s–90s display
lettering of film posters, cassette J-cards, LP sleeves, book covers and
Letraset sheets. Latin wood type and stripe faces are reduced to a contrast
appendix (§9). Arabic *calligraphy* belongs to the parallel agent
(`calligraphy-arabic.md`).

**Rules followed.** Web research and metadata or API queries only; **nothing
downloaded**. Every download needs Ian's go, so each candidate carries a
size. Per Ian, **licence is not a selection filter**: this is private
research, the source images are never used or published, and only line
statistics are learned from them. Rights are recorded as information
(CSV `licence` column, §7); **tiers rank usefulness**: clean lettering,
resolution, genre coverage, contiguous/inline/outline lines. The
sacred-text respect rule still applies (§6). Scans live in the gitignored
`.local/`; only the manifest is committed.

Candidate manifest: `typography-candidates.csv` (66 rows; ids below).
"Unverified" means seen in a search result, not opened.

## 1. Arabic letterpress: history that matters for line-making

1. **1514**: *Kitab Salat al-Sawa'i*, the first Arabic book in movable type.
   Its colophon says Fano; scholars argue it was printed in Venice by Gregorio
   de' Gregori. It is liturgical, so it is excluded (AL13).
2. **1584–1595, the Medici Oriental Press, Rome**, with types by Robert
   Granjon: Avicenna's *Canon* (1593, AL02) and al-Tusi's Euclid (1594,
   AL01). The Euclid is the most "Ian" document in this survey: Naskh type and
   Euclid's construction diagrams on the same page.
3. **Leiden in the 1610s–20s**: Erpenius' types (AL03). European-cut Arabic
   breaks the connected script into sorts for the first time.
4. **1706**: Aleppo, the first movable-type press in an Arabic-speaking
   country (Athanasius Dabbas). **Müteferrika, Istanbul, 1720s**: the
   commonly cited date of 1729 was not confirmed by these searches.
5. **The Bulaq press, Cairo**: founded 1820, opened 1821, first book 1822
   (Wikipedia). It is the long arc of Arabic Naskh type, and the material
   here runs from AL11 (1830) through AL04 (1844), AL05 (1872) and AL07
   (1872).
6. **1905: Bulaq/Amiriya issued a new Naskh type.** Hosny (TUGboat 33:1)
   argues it balances calligraphic Naskh against the limits of typesetting,
   and keeps many of the letterforms that other revivals drop. **Amiri (AF01)
   is its digital revival**, and AL08 (1906) and AL09 (1914) are books set in
   that era's type. Together they make the cleanest **medium pair** in the
   project: the same design as a digital outline and as a letterpress
   impression.
7. **The American Press, Beirut (19th c.)**: the Smith–Van Dyck type
   lineage (Auji, *Printing Arab Modernity*, 2016). Most of its output is
   scripture (excluded). AL10 (1881, public health) is a secular witness to
   the Beirut cut.
8. **1908–1993, the machine age**: Linotype, Monotype, photocomposition and
   early digital (Nemeth, *Arabic Type-Making in the Machine Age*, Brill 2017,
   not open access). **From 1976, Letraset Arabic dry transfer.** Boutros
   Advertisers Naskh (1977) married Naskh to straight linking strokes so it
   could sit beside Helvetica. Shehab and Nawar call dry transfer one of the
   last big experiments in Arabic type before digital.

**What makes Arabic letterpress a hand** (all of it measurable):

1. **Joins become seams.** Movable type cuts a connected script into sorts
   that butt-join at a fixed baseline height. Contiguous baseline strokes are
   kept, but with a constant connection thickness and occasional
   misregistration at the joins.
2. **Ligature and stacking compromises.** The vertical stacking of
   calligraphy is flattened or reduced to a fixed ligature set, and kashida
   extension is mechanised. Measured as fewer vertical excursions and longer
   straight baseline runs than in the hand.
3. **Ink squash and wear.** Acute corners round off, small counters fill
   (fa/qaf/waw heads), dots merge with letters, hairlines break on worn
   sorts, and inking varies along a line. This edge texture belongs to the
   same family as our tremor layer, with a different signature (§4.3).

## 2. Vintage Arabic display lettering, 1950s–1990s

What the material looks like (from the sources in §10):

1. **Film posters.** Early hand-painted posters were made by Greek and
   Armenian artists in Alexandria. Then came Egyptian studios (Hassan
   Gassour's, the first specialised poster company), running from the 1930s to
   the late 1990s. Titles are hand-lettered: bold Ruq'a, Diwani-flavoured
   swashes, geometric Kufi, often with **outline, inline or drop-shadow**
   treatment. The 1970s are known for unconventional lettering.
2. **Cassette J-cards (from the 1970s).** Hand-lettered or dry-transfer
   titles, plus a lot of early desktop-publishing (DTP) type from the late
   1980s. The Egyptian Cassette Archive credits individual designers and
   calligraphers.
3. **Book and magazine covers**: hand lettering, Letraset, and hot-metal
   headline type (the Arabic Design Archive / Arabic Book Cover Archive).
4. **Letraset sheets**: a whole display alphabet laid out once, clean, which
   makes them ideal shape data (AP07: the "Anti" 20 mm sheet, 1978).

**Where the images are** (full rows in the CSV; rights in §7):

| # | id | Source | What | Access | Tier |
|---|---|---|---|---|---|
| 1 | AP01 | Princeton DPUL `pudl0100` | 1,474 Egyptian posters + 768 lobby cards, 1935–2007 | IIIF; the catalogue JSON works; item pages block scripts, so use a browser | A |
| 2 | AP02 | Egyptian Cassette Archive (Amr Hamid) | 7k–20k tapes reported, 1960s–2000s | Instagram (~1080 px); ask Hamid for scans | A |
| 3 | AP03 | Syrian Cassette Archives | 4 J-card scans per tape; 1980s Egyptian and Lebanese compilations | Direct CDN JPEGs, ~100 KB (~1000 px) | A |
| 4 | AP04 | Arabic Design Archive / Arabic Book Cover Archive (Elhossieny) | 1,000–3,500+ covers, late 1930s–1990s | Instagram; no website confirmed | A |
| 5 | AP05 | Ian's own tapes, LPs and books | whatever he owns | own scans at 600–1200 ppi: the only true print-texture source | A |
| 6 | AP06 | Wikimedia Commons Egyptian posters | 46–76 files, 1940–1975 | API, direct files; often under 1000 px | B |
| 7 | AP07–08 | Shehab & Nawar, *A History of Arab Graphic Design* (2020) and its PGDA items | Letraset Arabic sheet (1978), posters, covers | Book plates; PGDA images ~1440 px | B |
| 8 | AP09–10 | Discogs; reissue labels (Habibi Funk, Sublime Frequencies, WeWantSounds) | cassette and LP covers by label and country | Login for full-size Discogs images; reissues may be redrawn | B |
| 9 | AP11–12 | Fonts In Use, Flickr; Abou Jaoude collection (Beirut, ~20,000 posters), QNL, BibAlex, AIF | leads | mostly offline or incidental | B/C |

## 3. Arabic typefaces with a print-era spirit

The fonts are the *clean* side of each pair. All the Google Fonts licences
were verified against `METADATA.pb` plus the `OFL.txt` in `google/fonts`.

| # | id | Face | Derives from | Calligraphic ↔ geometric | Broad-nib logic in outline? | Multi-line? | Use |
|---|---|---|---|---|---|---|---|
| 1 | AF01 | Amiri | 1905 Bulaq type | calligraphic | yes (thick/thin follow nib angle) | no | pair with AL08/AL09 |
| 2 | AF03 | Rakkas | 1950s–60s Egyptian poster Ruq'ah | calligraphic display | partly | no | pair with AP01 posters |
| 3 | AF04 | Lalezar | 1960s–70s Iranian Film-Farsi posters | bold lettering | weak | no | poster display |
| 4 | AF05 | Jomhuria | Iranian "Shablon" stencil | blocky | weak | stencil bridges | stencil rhythm |
| 5 | AF06 | Blaka Hollow (+solid) | blackletter × Kufi, reed pen | geometric | yes (reed-pen corners) | **double contour** | the Arabic outline/inline case |
| 6 | AF07 | Reem Kufi | Fatimid Kufi via Abdul Qadir | geometric | near-monoline | no | geometry pole |
| 7 | AF09 | Qahiri | manuscript Kufi, regularised | very geometric | monoline | no | geometry pole |
| 8 | AF02 | Amiri Typewriter | Arabic typewriters | mechanised | flattened | no | office-print hand |
| 9 | AF11 | Aref Ruqaa | classical Ruq'a | calligraphic | yes | no | the hand behind poster Ruq'ah |
| 10 | AF16 | Noto Kufi Arabic | simplified Kufi | geometric | no (wght 100 ≈ monoline) | no | centreline-extractor check |
| 11 | MF01–02 | Nadeem, Baghdad, Kufi Standard GK, Diwan Kufi, Al Tarikh, Beirut… | Diwan Software Mac Arabic fonts (name tables: 1987–2012) | mixed | mixed | no | **already installed**; 1990s DTP print look (look not yet inspected) |
| 12 | MF03 | DecoType Naskh | DecoType calligraphic engine | most calligraphic | yes | no | the hand-preserving extreme (installed) |

No open Arabic font found carries the **inline or triline stripe** look of
1970s posters. Blaka Hollow is the nearest. KACST and Arabeyes (AF23) list
shadow and outline cuts but were not inspected. Stripes therefore come from
the posters themselves (AP01, AP06) or from Latin faces as contrast (§9).
**No open single-stroke Arabic font exists** in any source searched
(GitHub, Golan Levin's single-line archive, the EMS collection), so Arabic
always needs skeletonising.

Shaping comes first: contextual forms and ligatures exist only after
HarfBuzz runs, so outlines of unshaped code points are meaningless. Python
options, named only and not installed: **`uharfbuzz`** (shaping; *not* in
`.local/gesture/.venv` yet), **`fontTools`** (outlines and variable
instancing; already there, 4.67.0), `freetype-py` (optional rasteriser).
`scikit-image` and `sknw` (skeletons) are already in the research venv.
Installing into `.local/gesture/.venv` touches nothing in the app's `.venv`
or `pyproject.toml`.

## 4. As a hand for this project

Letterforms are designed outlines, so their "hand" is an idealised one: a
**contrast class** to Matisse, Hokusai and Ingres, and a juxtaposition
partner ("a Hokusai tree in Qahiri's geometry", "a Matisse contour in Bulaq
1906 ink"). The hand lives in three separable layers:

1. **Outline geometry.** In connected Arabic, each *part-of-word* is one
   closed contour, so even a short string gives long contiguous closed
   strokes, which suits Ian's no-hatching direction. The panel will read κ(s)
   as piecewise-constant plateaus (lines and arcs) with sharp spikes, so the
   corner *angles* cluster on designed values (Kufi: 90° and 45°). Expect the
   corner rate to sit far above any drawing, at near-zero κ noise. The panel
   should separate type from hand trivially, which is fine for a contrast
   class.
2. **Centreline + width.** The skeleton of the filled shape gives a
   centreline; twice the distance transform along it gives width. For Naskh
   and Ruq'a, fit a **nib angle** α under the model w(θ) ≈ W·|sin(θ − α)|.
   The fit quality says how much broad-nib logic a typeface kept (expected
   order: DecoType > Amiri > Rakkas > Kufi ≈ 0). This feeds the
   thickness-gap question in `IDEAS-gesture-bank.md`.
3. **Multi-line structure** (hollow, inline, prism, stripe, shadow). These
   are contours nested at a near-constant normal distance: an "offset family"
   with a count, a spacing and a constancy. A **shadow** is different, a
   translated copy rather than an offset. Both are parallel contiguous lines,
   ideal for the plotter. They relate to the topology layer's double
   contours, so they could be learned as a relation rather than as strokes.
4. **Print texture** (scans only): edge displacement from a smoothed
   contour, or better, from the registered Amiri render for the 1905 pair.
   Report it as a roughness spectrum, corner-rounding radius and stroke gain
   (ink spread). Baird's defect model (1990; blur, threshold, jitter,
   speckle) and the Kanungo et al. degradation models are the standard
   vocabulary. The open question for the panel: does its tremor measure tell
   *print* noise (isotropic, ink-spread, corner-rounding) apart from *hand*
   tremor (along-stroke, bursty)? The AL08/AL09-vs-AF01 pair is a clean test.

## 5. Extraction route (sketch, no code)

**Fonts.** Shape a neutral string (§6) with HarfBuzz, take glyph outlines
through fontTools pens (the same route as `axibridge/sources/_fontglyph.py`)
and flatten them. That gives two views: (a) closed contours as closed strokes
for κ(s), corners and contour nesting, which yields the multi-line offset
families; (b) a high-resolution raster, then `skimage` skeletonize plus
`sknw`, spur pruning, and centreline strokes with a distance-transform
width. Instancing variable faces at their thinnest weight gives a
near-monoline cross-check of the skeleton (AF16).

**Scans.** Download single pages, never whole items: IA serves individual
files inside `_jp2.zip`, and Princeton serves IIIF. Then: Sauvola
binarisation, connected components, part-of-word blobs, and the same two
views as the fonts, plus the texture measures in §4.4. For the Bulaq 1905
pair, register blobs against the Amiri render of the same letters, so the
residual is pure print. For posters and cassettes, crop the title lettering
by hand (a few dozen crops), and drop photos and faces.

**Output to the existing contract**: `Stroke` with `closed=True` for
contours, `width` on centreline strokes, and the source and layer in `meta`.

## 6. Text content and respect

1. **No sacred text as a source or as a rendered string.** That means no
   Qur'anic text, no scripture or liturgy of any faith (Bibles, hymnals, the
   1514 Book of Hours), no hadith, Sufi or devotional titles, and no basmala.
   For scans: pick secular books (medicine, travel, lexicon, geometry), and
   skip front matter, because many Bulaq books open with a basmala and a
   religious preamble. AL13 lists the excluded items so nobody picks them by
   accident. The calligraphy agent will propose a Qur'anic-text policy; where
   the two policies differ, **the stricter one wins**.
2. **Rendering strings.** Use joining drills of repeated connecting letters
   (e.g. ببب، سسس، ههه), isolated forms, and abjad-order letter rows. Use
   random strings from a connecting-letter whitelist only if they are
   rejected against a wordlist (e.g. a Hunspell Arabic dictionary).
   Blacklist ﷲ (U+FDF2), ﷺ ﷻ ﷽ (U+FDFA, U+FDFB, U+FDFD), the sequences
   الله and لله, and divine and prophetic names.
3. **Pseudo-Arabic output.** Generated sheets in a learned Arabic-print hand
   will *look like* text. Don't caption them as Arabic or as meaningful, and
   have an Arabic reader check that no real words or phrases appeared
   (especially religious ones) before anything is shown publicly. Commons'
   "Faux Arabic" category is the orientalist trope to stay clear of.
4. **Posters and covers** show performers' faces and names. Crop the
   lettering only, never redistribute the crops, and keep everything in
   `.local/`.

## 7. Rights, recorded as information

1. Public domain or open: the Wellcome items (Public Domain Mark), the Toronto
   items (IA `NOT_IN_COPYRIGHT`), BIU Santé (Etalab Licence Ouverte), the
   Commons books (PD-old, PD-Ottoman), the Newberry (any lawful purpose) and
   Columbia ("no restrictions" on LW02).
2. Commons Egyptian posters are tagged PD-EG or PD-Egypt. Egyptian law
   protects collective works for publication + 50 years and applied art for
   + 25. The US status rests on the URAA (PD in Egypt by 1 Jan 1996). That is
   safest for posters before 1946 and contested for later ones.
3. In copyright: Princeton's posters (no statement retrievable), the cassette
   archives (Syrian site: "All Rights Reserved"), Arabic Design Archive covers,
   Discogs images, Letraset sheets and Ian's own items. All are acceptable
   under Ian's private-study ruling, kept local and never published.
4. Fonts: OFL 1.1 for every Google Fonts Arabic face and for Amiri
   Typewriter, whose `OFL.txt` contradicts GitHub's "NOASSERTION". AGPL-3.0
   for the Alif Type manuscript Kufics. GPL-2 for KACST and Arabeyes, not
   re-verified. The macOS Diwan and DecoType faces are Apple-licensed: read
   them locally, never copy them out. OFL binds the font software, not the
   drawings made from it.

## 8. Ranked first set for approval

1. **The Bulaq 1905 medium pair**: AF01 Amiri (0.43 MB), AL08 *Rihlat
   al-sayf* 1906 (20 pp ≈ 12 MB) and AL09 *Kitab al-Taj* 1914 (20 pp ≈ 4 MB).
   It separates print texture from design.
2. **Egyptian poster titles against their revival**: AP01 Princeton
   (about 30 posters from 1950–1985 with large title lettering, ≈ 15 MB;
   resolution unchecked) and AF03 Rakkas (0.15 MB).
3. **Cassettes**: AP03 Syrian Cassette Archives (about 40 scans ≈ 4 MB) and
   AP02 Egyptian Cassette Archive (about 40 images ≈ 5 MB; Instagram,
   manual).
4. **Covers**: AP04 Arabic Design Archive (about 40 covers ≈ 5 MB).
5. **Already on disk, 0 MB**: MF01 and MF02, the Diwan Mac Arabic faces
   (the 1990s DTP look).
6. **Multi-line structure**: AF06 Blaka Hollow + solid (0.13 MB), with Latin
   contrast LF01 Tilt Prism (1.05 MB) and LF02 Monoton (0.05 MB).
7. **The geometry pole**: AF09 Qahiri (0.04 MB), AF07 Reem Kufi (0.13 MB)
   and AF16 Noto Kufi Arabic (0.43 MB, the extractor check).
8. **Older letterpress textures**: AL04 Bulaq 1844 (20 pp ≈ 17 MB) and AL01
   Medici Euclid 1594 (20 pp ≈ 3 MB; type beside geometric diagrams).
9. **Hands behind the display faces**: AF11 Aref Ruqaa (0.11 MB), AF02 Amiri
   Typewriter (0.12 MB), AF04 Lalezar (0.29 MB) and AF05 Jomhuria (0.17 MB).
10. **Ian's own scans (AP05)**: these cost scanning time rather than
    downloads, and they are the only real source of print edges for the
    1960s–90s.

**Totals:** 12 font files ≈ 3.1 MB, plus about 270 images or pages ≈ 65 MB,
so **≈ 68 MB** of downloads. Add about 10 MB of Ian's own scans and the
installed macOS faces at 0 MB. Instagram (AP02, AP04) and Princeton (AP01)
need a browser rather than scripted fetches.

## 9. Appendix: Latin contrast (kept short)

1. **Wood type specimens, all public domain by age.** Page 1859 (LW01:
   high resolution; Tuscan, Clarendon, condensed gothic, shaded, outline),
   Page 1874 *chromatic* (LW02: layered type, i.e. multi-pen passes; low
   resolution), Tubbs and Holly (LW03, LW04), and ATF 1898 / BB&S 1907
   (LW05).
2. **Stripe and inline faces, OFL.** Tilt Prism and Monoton are literally
   parallel contiguous outlines. Faster One gives speed stripes; Bungee
   Inline and Shade show offset vs translated copy. Wood-type revivals
   (Holtwood, Rye, Sancreek, Ewert, Vast Shadow) are the clean partners for
   the specimen scans.
3. **Single-stroke fonts.** Hershey (via vpype) and CamBam stick are already
   on disk. Relief SingleLine and the EMS SVG fonts are OFL-derived. All are
   Latin-only.

## 10. Sources

- Bulaq Press — https://en.wikipedia.org/wiki/Bulaq_Press
- Hosny, Amiri, TUGboat 33:1 — https://tug.org/TUGboat/tb33-1/tb103hosny.pdf
- Amiri (typeface) — https://en.wikipedia.org/wiki/Amiri_(typeface)
- Yale, Early Arabic Printing — https://onlineexhibits.library.yale.edu/s/arabic-printing/page/printing_history_arabic_world
- Princeton, Early Arabic books — https://dpul.princeton.edu/early-arabic-books/about/introduction
- Notre Dame, Arabic's Gutenberg — https://sites.nd.edu/manuscript-studies/?p=3108
- Linda Hall, al-Tusi / Medici Euclid — https://www.lindahall.org/about/news/scientist-of-the-day/nasir-al-din-al-tusi-2/
- Nemeth 2017 (REF record) — https://results2021.ref.ac.uk/outputs/104cf7e3-ab6f-4701-833c-fc4095200f5b?page=1
- Auji 2016 — https://research.brighton.ac.uk/en/publications/hala-auji-printing-arab-modernity-book-culture-and-the-american-p/
- AbiFarès thesis (Leiden, open access) — https://scholarlypublications.universiteitleiden.nl/access/item:2887264/view
- Khatt Foundation, Typographia Arabica — https://www.khtt.net/en/id/4868
- Boutros Advertisers Naskh — https://en.wikipedia.org/wiki/Boutros_Advertisers_Naskh ; https://boutrosfonts.com/Full-of-character.html ; https://www.languagemagazine.com/?p=4666
- PGDA, A History of Arab Graphic Design — https://peoplesgdarchive.org/item/11814/A%20History%20of%20Arab%20Graphic%20Design
- Princeton film posters — https://libguides.princeton.edu/NEC_posters/exhibit ; https://dpul.princeton.edu/pudl0100
- Egyptian poster history — https://citylightsposters.com/blogs/articles/film-poster-making-in-egypt ; https://cairoscene.com/artsandculture/the-lost-art-of-the-afish-the-evolution-of-egyptian-film-posters ; https://arablit.org/2018/11/14/khatt-from-a-love-of-egyptian-pop-culture-and-arabic-typography/
- Lebanese film graphics (AIGA) — https://eyeondesign.aiga.org/the-bold-graphics-and-hidden-stories-behind-the-golden-age-of-lebanese-film/
- Letterform Archive lecture — https://letterformarchive.org/shop/explore-with-me-the-arabic-letterform-in-the-arabic-design-archive/
- Egyptian Cassette Archive — https://www.itsnicethat.com/articles/amr-hamid-the-egyptian-cassette-archive-graphic-design-200122 ; https://arabculturefund.org/Projects/7298
- Syrian Cassette Archives — https://syriancassettearchives.org/tapes/SMA_0326?lang=en
- Arabic Book Cover / Design Archive — https://www.printmag.com/post/building-an-arabic-book-cover-archive ; https://www.creativereview.co.uk/arabic-book-cover-archive/ ; https://arabculturefund.org/Projects/6822
- Abou Jaoude collection — https://www.middleeasteye.net/features/beiruts-movie-archivist-preserves-lebanons-celluloid-glory-years
- Arab Image Foundation — https://arabimagefoundation.org/about_en.html
- WeWantSounds, Sharayet El Disco — https://www.wewantsounds.com/sharayet-eldisco
- Commons, Egypt copyright rules — https://commons.wikimedia.org/wiki/Commons:Copyright_rules_by_territory/Egypt
- Google Fonts licences — https://github.com/google/fonts (per-family `METADATA.pb`, `OFL.txt`)
- Alif Type repositories — https://github.com/orgs/aliftype/repositories
- Single-line font archive (Levin) — https://github.com/golanlevin/p5-single-line-font-resources
- EMS SVG fonts — https://gitlab.com/oskay/svg-fonts ; Relief — https://github.com/isdat-type/Relief-SingleLine
- Hershey notice — https://web.mit.edu/ghostscript/src/gs6.01/doc/Hershey.htm
- Document defect models: Baird 1990 and Kanungo et al. TPAMI 2000 (via https://www.haralick.org/journals/i1209.pdf ; https://kanungo.com/ocr.html)
