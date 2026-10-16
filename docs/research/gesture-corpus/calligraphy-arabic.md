# Arabic-script calligraphy as hands (research, 2026-10-16)

Ian asked whether the genres of Arabic-script calligraphy can serve as hands
for the gesture bank. This note covers the genres seen as line geometry, a
candidate harvest (`calligraphy-arabic-candidates.csv`, 131 rows), a policy on
sacred text, and pipeline notes. Research used web search and museum API
metadata only. **Nothing was downloaded.** Each download still needs Ian's go.

Markers: **†** = general knowledge, not source-checked in this session.
"verify" = metadata did not settle it. Licence is recorded as information
only. It is not a selection filter: this is private research, scans stay in a
gitignored folder, and only line statistics are used (coordinator's
clarification, 2026-10-16).

## Short answer

1. **Best hands for "contiguous lines"**: **shikasta** (G14), **diwani**
   (G12) and **nasta'liq siyah mashq** (G13 exercises). They have the longest
   connected ribbons and the least lifting. **Maghribi** (G15) is the
   plotter-native one, because its stroke width is close to uniform.
   **Square Kufic** (G4) is the geometric extreme and needs no scans: it can
   be synthesised from grid rules.
2. **Best training data**: exercise sheets (mashq, karalama, pen trials) and
   model books. The standout is Hashem al-Baghdadi's *Qawa'id al-khatt
   al-'Arabi* (1961, NYU, believed PD). It covers ruq'a, naskh, thuluth,
   farsi, diwani and jali diwani with nuqta measures.
3. **Policy**: never train on or output Qur'anic text. Devotional
   non-Qur'anic text is measure-only. Generated output is framed as
   calligraphy-derived asemic line studies, never as "Arabic" (E1–E6).

## 1. Genres as a line-maker sees them

The common physics: almost every genre is written with a **broad-cut reed
qalam** held at a roughly constant nib angle. Stroke width is therefore a
function of stroke direction, w(θ) ≈ W·|sin(θ − φ)| + w₀. That is a
2-parameter width model per sheet. Proportion comes from **al-khatt
al-mansub** ("proportioned script"), traditionally credited to Ibn Muqla and
refined by Ibn al-Bawwab. The nib makes a **rhombic dot (nuqta)**, which is
the unit length. The **alif** is N nuqtas tall, N varying by script. A circle
with the alif as its diameter sizes the other letters. The attribution is
disputed and no autograph of Ibn Muqla survives. Words break into **"parts of
words"** at the six non-connecting letters (ا د ذ ر ز و): each part is one
pen-down ribbon plus dots added afterwards. Writing runs right to left.

| # | Genre | Geometry (curvature, corners, baseline) | Width | Continuity | Surviving PD corpus | Fit |
|---|---|---|---|---|---|---|
| G1 | Early (Abbasid) Kufic | Low, wide, horizontal; hard right-angle corners; long extended horizontals (mashq-stretching); flat baseline | broad nib, heavy | short discrete letter-blocks | almost only **Qur'ans** on parchment | poor (E1) |
| G2 | Eastern / "broken" Kufic (New Style)† | Tall thin verticals, sharp oblique strokes, angular hooks | high contrast | short | mostly Qur'ans | poor (E1) |
| G3 | Foliated / floriated Kufic | Kufic stems ending in leaf/palmette loops | — | ornamental, mostly carved/painted | ceramics, tiraz, architecture; **secular aphorism bowls** (Samanid slipware) | B, as a secular Kufic stand-in |
| G4 | **Square Kufic** (banna'i) | Pure grid: orthogonal segments only, stroke = one grid cell, letters on gridlines, right-angle rotations (Sakkal) | constant | long orthogonal meanders | architecture photos (C); clean modern grid drawings (Fabris, Sakkal) | **synthesise**; geometric pole |
| G5 | Naskh | Small, round, compact; short tails; flat baseline; many dots | moderate contrast | short parts-of-words | secular texts exist (science, Kalila wa Dimna) | B: short strokes |
| G6 | Thuluth (+ jali) | Large curved tails sweeping below the line, tall alifs with wedge heads, stacked composition | high contrast | medium; **long tails** are the best curves | Ottoman muraqqa (mostly hadith), tughras, levhas | B; tails and tughra loops are A material |
| G7 | Muhaqqaq | Long straight horizontals, shallow sub-linear bowls, straight descending tails† | high | long horizontals | large Qur'ans | poor (E1) |
| G8 | Rayhani | Small muhaqqaq† | — | — | Qur'ans | poor (E1) |
| G9 | Tawqi' | Chancery; compact; joins letters that normally do not connect† | — | more connected | rare as single sheets | gap |
| G10 | Riqa' (classical) | Small tawqi'; Ottoman diploma (icazet) script† | — | connected | ijaza diplomas (Walters W.674) | B |
| G11 | Ruq'a | Ottoman everyday hand (19th c.†): short, unflourished, flat; letters sit on the line | low–moderate | short | modern; **Baghdadi** model book | B (short strokes) |
| G12 | **Diwani** (+ jali diwani) | Ottoman chancery (Ibrahim Munif, late 15th c.); dense interlocking letters, lines that **rise at the left end**†, no vowels in plain diwani; jali fills gaps with ornament dots | moderate | **very long, tightly ligatured** | fermans, berats, letters (secular) | **A** |
| G13 | Ta'liq / **Nasta'liq** | Persian "hanging" script: each word steps down right→left, **long horizontal sweeps** and deep round bowls, short discrete hooks between† | high, very fine hairlines | mixed: long sweeps plus short pieces | album poetry (secular); **siyah mashq** exercise sheets | **A** |
| G14 | **Shikasta** | "Broken" nasta'liq (17th–18th c.; Shafi'a, Taleqani†): extreme connection across normally non-joining letters, fast loops, steep slants | high | **longest contiguous ribbons of any genre** | albums, chancery documents, siyah mashq (secular) | **A** |
| G15 | **Maghribi** (mabsut, mujawhar, …) | Large descending bowls with sweeping loops, horizontal baseline; the hand forms one or two letters at a time | **low contrast, near-uniform width** (mabsut "very little contrast") | long sub-linear bowls | Qur'ans (E1) plus **secular documents** (treaty, histories) | **A, plotter-native** |
| G16 | Sini | Chinese-brush Arabic (14th c. on): round brush, pressure-tapered strokes, not broad-nib | brush taper, not angle | rounded, fluid | modern only (Haji Noor Deen); no PD found | B; different width model |
| G17 | Ghubar | "Dust" micro-script (pigeon post†); used to fill outlines of compositions | — | tiny | Met 665823 composition | B, texture only |
| G18 | Tughra | Thuluth/diwani-derived monogram: three tall parallel verticals and two large nested elliptical loops sweeping left | high | **very long sweeps** | Met, CMA, Commons (secular: a sultan's name) | A for its loops |

**Long continuous strokes**: shikasta > diwani > nasta'liq sweeps ≈ maghribi
bowls > thuluth tails/tughra loops. **Short and discrete**: naskh, ruq'a,
ghubar, Kufic letter-blocks. Siyah mashq sheets are the densest
long-stroke material: letters repeated in every direction until the page is
black.

## 2. Sources

| # | Source | Rows | Licence (info) | Access notes |
|---|---|---|---|---|
| S1 | The Met Open Access (Islamic Art) | 36 (+1 Qur'an coverage row) | CC0 | `v1.1/search` works; `/v1/objects` sits behind Incapsula, so I paced it at 1 request/1.2 s and got 511 of 557 objects. 401 are PD with an image; 63 of those are titled Qur'an. DP/DT photos ≈4000 px, legacy `sf` scans ≈1200 px |
| S2 | Cleveland Museum of Art | 13 | CC0 | Open API with pixel sizes: print JPG 3400 px (~7 MB), full TIFF ~90 MB |
| S3 | Art Institute of Chicago | 8 | CC0 for PD works | API open; IIIF delivery size unverified (Cloudflare challenge to curl) |
| S4 | The Digital Walters | 10 | CC0 (confirmed on site) | TEI per manuscript, so folios map to image files; `sap` JPG ~1.1 MB, master TIFF ~300 MB |
| S5 | Wikimedia Commons | 40 | mostly PD-Art / CC0 tags, some CC BY-SA | API rate-limits bursts; upstreams include GAP, reed.edu, auction houses and Telegram (weak provenance noted per row) |
| S6 | Smithsonian NMAA (Freer\|Sackler) | 8 | CC0 when marked Open Access | api.si.edu DEMO_KEY ran out after ~8 calls and asia.si.edu returns 403 to scripts. Rows come from search hits; get a free key to enumerate |
| S7 | Library of Congress, *Selections of Arabic, Persian and Ottoman Calligraphy* (~355 sheets) | 3 | "PD or no known restrictions" | **Richest PD exercise source** (siyah mashq incl. Mir 'Imad, Ottoman karalama/mufradat), but loc.gov blocks scripts (Cloudflare). Needs a manual browse |
| S8 | Harvard Art Museums | 1 | non-commercial (verify) | API key needed; not queried |
| S9 | NYU Arabic Collections Online | 1 (Baghdadi) | "believed PD" | 141-page model book, PDF 98 MB (hi) / 10.5 MB (lo) |
| S10 | IRCICA print (Şevki meşk facsimile; competition catalogues, 64–94 plates each) | 2 | © IRCICA | must be bought and scanned. Competition plates are genre-labelled by construction |
| S11 | Web archives: ketebe.org, sakkal.com, reed.edu, auction houses, galleries (Massoudy, Haji Noor Deen) | 8 | © various | source-level rows; harvest per work |
| S12 | Chester Beatty | 1 | CC, variant unverified | <10% of Arabic collection online |
| S13 | Qatar Digital Library | 1 | per item PD/CC | chancery letters; IIIF |
| S14 | Bodleian / British Library / Princeton | 0 | Bodleian CC BY-NC 4.0; BL PDM (voluntary); Princeton per item | not enumerated: few calligraphy *sheets* and mostly codices. Low priority |

Tiers (by usefulness, not licence): **A 53 / B 67 / C 11**. A = clean ink on
plain ground, one genre, at least ~2000 px or an exercise sheet. B =
decorated, illuminated or low-res, or of uncertain content. C = skip, or a
coverage record of excluded Qur'anic material. The `text_status` column
carries the sacred-text status the policy below acts on.

**Gaps**: no PD Sini; little ruq'a and classical tawqi'/riqa' outside the
Baghdadi and Şevki model books; Kufic, muhaqqaq and rayhani survive almost
only in Qur'ans, so they stay uncovered by design (E1).

## 3. Ethics and policy (respect, independent of licence)

What the sources say:

- **Museums** openly photograph, licence (CC0) and publish Qur'an folios
  (Met, Cleveland, AIC). *Studying and reproducing* Qur'anic calligraphy is
  normal institutional practice.
- **Distorting or repurposing verses is the sensitive part.** Jordan's Iftaa'
  Board, Resolution 31 (1993), rules that drawings that form figures out of
  Qur'anic verses "degrade" them and are impermissible, and that good
  intentions do not excuse it, since calligraphers wrote verses to dignify
  them. Malaysia's Mufti office (Al-Kafi 1537): verses must be dignified and
  "free from anything that may lead to … degrading". A Hanafi Q&A reports
  that some scholars allow verse art and others dislike it "due to there
  being a danger of disrespect". Jordan's 2025 fatwa 3969 permits wall verses
  given clean materials and no risk of disrespect or tampering. No single
  ruling binds everyone, but every source agrees that tampering is the line.
- **Accidental resemblance has caused real offence.** In 1997 Nike recalled
  shoes whose flame logo resembled "Allah" in Arabic script (CAIR agreement,
  apology, donation). Lagerfeld apologised in **1994** (not 2007) for Qur'an
  passages used as decoration on Chanel dresses.
- **Pseudo-script has a history.** Pseudo-Kufic (now "pseudo-Arabic") in
  medieval and Renaissance European art used Arabic-like script as exotic or
  sacral ornament, often on garment hems and haloes (Moore, NGA/CASVA;
  Britannica). Scholarship is split between reading it as Orientalist
  "atmosphere" and treating Arabic-like writing as carrying meaning beyond
  "real vs fake". Thomas Milo's "Eurabic" critique concerns imitations that
  ignore script grammar. The counter-tradition is **hurufiyya**: Arab
  artists such as Madiha Umar (1949) and Shakir Hassan Al Said (One Dimension
  group, 1971) abstracted letters as form. The difference lies in authorship,
  knowledge and framing, not in legibility.

Recommended policy (Ian's decision; E1 and E3 are the load-bearing ones):

- **E1. Qur'anic text: exclude entirely.** It is not used for training, as a
  token source, or for statistics. Rationale: a hand learned from it gets
  recombined into new marks, which is exactly the "tampering/distortion" the
  rulings name. Avoiding it costs little, because secular corpora exist for
  every genre that matters here. Accept the Kufic/muhaqqaq/rayhani gap. Use
  Samanid aphorism slipware and tiraz for secular Kufic.
- **E2. Devotional but non-Qur'anic text (hadith, prayers, hilye, basmala,
  divine names): measure-only.** Aggregate statistics such as pen angle,
  nuqta size and the width-vs-direction fit are allowed. Never use it as a
  token or segment bank, and never as a generator source. Flag rows in
  `text_status`. A reader checks "verify" rows before use.
- **E3. Never output legible Arabic.** The generator works below the
  word level, using strokes and ribbons, not glyph sequences. Before any
  public showing, a **reader of Arabic/Persian** checks outputs for
  accidental words, especially the *Allah* and *Muhammad* ligature shapes
  (the Nike lesson). This cannot be automated reliably on generated strokes.
- **E4. Framing.** Call outputs "line studies after the shikasta / diwani …
  hand" and credit the masters and genres. Never present them as "Arabic
  calligraphy", "Islamic art" or text, and avoid exotic titles. This places
  the work in a hurufiyya-adjacent, informed lineage rather than a
  pseudo-Kufic one.
- **E5. Physical sheets.** A widely held practice† is that paper bearing
  sacred text is not discarded casually. E1 and E2 make this moot for
  outputs. Any printed reference sheets of devotional pages should be kept
  or disposed of respectfully.
- **E6. Before exhibiting**, show a selection to a practising calligrapher or
  Muslim reader. This costs little and catches what the policy misses.

### Adopted policy (Ian, 2026-10-16)

1. **Qur'anic text: measurement only.** Qur'anic folios may be used for
   statistics (the panel, curvature, tremor measurements). They are never a
   source of strokes, tokens or segments for generation, restyle or
   juxtaposition. (This replaces E1's full exclusion.)
2. **E2–E4 as drafted:** other devotional text is measure-only; never
   output legible Arabic, and have a reader check anything shown publicly;
   call outputs "line studies after the X hand", never "Arabic calligraphy".
3. **Abstraction by design.** Ian: "the output process should abstract
   anyways". Generation draws from line statistics, never from letterforms,
   so outputs are non-textual by construction. E3's reader check stays as
   the safety net.
4. In manifests, tag each item's `content_type` (qur'an / devotional /
   poetry / exercise / document / …) so training code can enforce (1)–(2)
   mechanically.

## 4. Technical notes for the pipeline

- **T1. Ribbons, not lines.** A broad-nib stroke is a filled ribbon. Extract
  the medial axis plus a width profile, i.e. the "filled blade" mode from
  `hands-to-collect.md`. Heavy strokes give skeleton spurs at wedge-shaped
  terminals and joins, so prune spurs by width.
- **T2. Fit the nib.** Scatter local width against tangent direction and fit
  W and φ per sheet. This gives each genre and hand a signature, and it
  checks the centreline extraction for free (a bad skeleton breaks the
  sinusoid).
- **T3. The nuqta is the ruler.** Detect rhombic dots as a separate class
  (small, convex, about four-sided). Their size is the pen width, which
  normalises scale across scans of any resolution. Keep dots out of κ(s)
  statistics; model them as a separate placement process.
- **T4. Grounds.** Gold and coloured inks, cloud bands (abri), gold-flecked
  and marbled paper (Met 453983) and illuminated borders all need colour
  segmentation that keeps black ink only. **Ruled frames (jadval)** are long
  perfect straight lines and must be masked, or they poison the
  straight-segment and corner statistics. Siyah mashq sheets are written at
  every rotation and cross themselves heavily. κ(s) is rotation-invariant,
  but crossings need the junction logic.
- **T5. Constant-width plotter.** Width is the dominant visual cue here.
  Hatching is ruled out. The options, in recommended order:
  (a) **nib-sweep envelope**: drag a segment of length W at angle φ along
  the generated centreline and plot the two envelope edges. That is one
  contiguous closed outline per stroke, with thick/thin produced
  automatically by the 2-parameter model. (b) Offset or multi-pass parallels
  (`fat_tube`). (c) Centreline only, which loses the cue. This bears on the
  open "thickness gap" decision in `IDEAS-gesture-bank.md`. Calligraphy is
  the strongest case for (a).
- **T6. Maghribi** has near-uniform width. It is the clean test of
  centreline-only, and the genre where the plotter needs no width trick.
- **T7. Square Kufic** is not a hand but a rule system (Sakkal): one cell per
  stroke, letters on gridlines, 90° rotations. Generate it directly as a
  "regime" partner for juxtaposition and skip scans. The Fabris and banna'i
  drawings (wc-35..37) are only for checking proportions.
- **T8. Stroke order and direction.** Main body (rasm) right to left, dots
  and marks after. Parts-of-words are the natural stroke units. Direction
  priors differ from Latin hands, which matters for the lognormal
  kinematics.

## 5. Recommended first harvest (for Ian's approval)

34 images, about **126 MB**, plus the Baghdadi PDF (**98 MB** hi-res, or
10.5 MB lo-res first). Total ≈ **225 MB**, or ≈ 137 MB with the lo-res PDF.
All rows are `secular` or `secular (verify)`. Ordered by expected value:

| # | id | what | why | MB |
|---|---|---|---|---|
| H1 | aic-131868 | Calligraphic exercise with letter measurements (Turkey) | the nuqta proportion system drawn out: ground truth for T3 | 1.5 |
| H2 | nyu-baghdadi | Baghdadi, *Qawa'id al-khatt al-'Arabi* (1961) | isolated letters for 6+ genres; the only good ruq'a/diwani model | 98.3 |
| H3 | met-716305 | Siyah mashq, Muhammad Shah Qajar | dense nasta'liq exercise | 3.5 |
| H4 | met-716307 | Siyah mashq, Asadullah Shirazi | ditto | 3.5 |
| H5 | met-716304 | Exercise, Fath 'Ali Shah | ditto | 3.5 |
| H6 | wal-W672-5b | Ottoman karalama | Ottoman naskh/thuluth exercise | 1.1 |
| H7 | wal-W672-6a | Ottoman karalama | ditto | 1.1 |
| H8 | wal-W668-66b | Nasta'liq pen trials | exercise | 1.1 |
| H9 | wal-W668-74b | Nasta'liq pen trials, Mir 'Imad | master's exercise | 1.1 |
| H10 | cma-1983.1115.a | Quatrains + calligraphic exercises, Sultan Muhammad Khandan | exercise, 3400 px | 7 |
| H11 | wc-12 | Shikasta siyah mashq, Golestaneh | longest-ribbon genre, exercise | 3.0 |
| H12 | wc-13 | Shikasta siyah mashq, Golestan Palace 1506 | ditto | 1.8 |
| H13 | met-716315 | Shikasta album leaf, Mirza Kuchak (Visal) | shikasta | 4.9 |
| H14 | met-450714 | Taleqani, 1763 | shikasta master | 3.5 |
| H15 | wc-10 | Taleqani, 1770 | ditto, 4656×7472 | 4.2 |
| H16 | wc-15 | Plea for Tax Relief (Harvard 1958.212) | secular chancery shikasta | 4.1 |
| H17 | wc-17 | Sa'di verses in shikasta, Mirza Kuchak | shikasta | 9.1 |
| H18 | wc-19 | Pandnama 01, Mir 'Imad | secular nasta'liq, 4057×6712 | 15.1 |
| H19 | wc-22 | Tuhfat al-Vozara 01, Mir 'Imad | secular nasta'liq | 1.6 |
| H20 | wc-24 | Quatrain of Kamal al-Din Isma'il, Mir 'Imad | nasta'liq | 2.6 |
| H21 | met-450713 | Verses in nasta'liq, Mir 'Imad 1608 | nasta'liq | 3.6 |
| H22 | aic-108853 | Qit'a, 'Abd Allah al-Hasani | nasta'liq | 1.5 |
| H23 | wc-05 | Ahmed III letter (Swedish National Archives) | secular diwani, 4988×8886 | 3.8 |
| H24 | wc-39 | Page of calligraphy (Met 453274), Turkey 1664 | diwani | 3.3 |
| H25 | wc-06 | 16th-c. ferman with tughra (LACMA/GAP) | diwani + tughra loops | 10.6 |
| H26 | met-449533 | Tughra of Süleyman | the longest sweeps in the set (mask gold) | 3.5 |
| H27 | wc-30 | Moroccan–American treaty 1787 | secular maghribi | 0.5 |
| H28 | wc-33 | Rawd al-Qirtas (Leiden), 989 H | secular maghribi | 0.8 |
| H29 | wc-32 | BnF arabe 6805, 1751 | maghribi | 0.7 |
| H30 | cma-1977.91.a | Dioscorides text page, 1224 | secular naskh (short-stroke contrast) | 7 |
| H31 | cma-1945.383.b | al-Jazari text page, 1315 | secular naskh | 7 |
| H32 | met-665823 | Ghubari composition | micro-script texture | 3.5 |
| H33 | wc-35 | Square Kufic grid drawing (Fabris) | grid-rule check for T7 | 2.9 |
| H34 | wc-37 | Banna'i drawing, Qeysarie gate | ditto | 0.9 |
| H35 | met-451802 | Samanid bowl with Arabic inscription | secular Kufic stand-in (B) | 3.5 |

Not in this round, but worth a manual session: **S7** (LoC: browse the ~355
sheets by hand for siyah mashq and karalama) and **S10** (buy the IRCICA
Şevki meşk facsimile: the canonical Ottoman thuluth+naskh exercise book).

## URLs used

- Met API: https://collectionapi.metmuseum.org/public/collection/v1.1/search · objects at `/v1/objects/{id}` (pages listed per row)
- Cleveland API: https://openaccess-api.clevelandart.org/api/artworks/
- AIC API: https://api.artic.edu/api/v1/artworks/search
- Smithsonian API: https://api.si.edu/openaccess/api/v1.0/search ; Mir 'Ali objects https://asia.si.edu/object/F1956.12/ , https://asia.si.edu/object/F1939.50b , https://asia.si.edu/object/S1986.94/ , https://asia.si.edu/object/S1986.92/
- Digital Walters: https://thedigitalwalters.org/Data/WaltersManuscripts/ManuscriptDescriptions/W672_tei.xml (also W668, W670, W674); CC0 statement https://thedigitalwalters.org/01_ACCESS_WALTERS_MANUSCRIPTS.html ; https://art.thewalters.org/object/W.672
- Commons API: https://commons.wikimedia.org/w/api.php (categories: Berlin Muraqqa of Hafiz Osman, Mustafa Râkim, Diwani style, Shekasteh Nasta'liq, Mir Emad Hassani, Chalipa, Square Kufic, Maghrebi script)
- LoC: https://www.loc.gov/collections/selections-of-arabic-persian-and-ottoman-calligraphy/ ; essay https://www.loc.gov/collections/selections-of-arabic-persian-and-ottoman-calligraphy/articles-and-essays/ottoman-calligraphers-and-their-works/ ; https://www.loc.gov/item/2019714504/ ; https://www.loc.gov/resource/amedscd.2019714505/ ; blog https://blogs.loc.gov/international-collections/2021/04/on-the-wings-of-a-flight-of-geese-arabic-persian-and-ottoman-calligraphy-sheets-at-the-library-of-congress-part-2/ , https://blogs.loc.gov/international-collections/2021/05/written-in-istanbul-arabic-persian-and-ottoman-calligraphy-sheets-at-the-library-of-congress-part-3/
- Harvard siyah mashq: https://harvardartmuseums.org/collections/object/212747
- NYU ACO Baghdadi: https://sites.dlib.nyu.edu/viewer/node/4619 ; Wikipedia https://en.wikipedia.org/wiki/Hashem_Muhammad_al-Baghdadi
- IRCICA: https://shop.ircica.org/tr/shop/1691 ; https://ircica.org/publications/arts-handicrafts/catalogue-of-winners-plates-in-the-fourth-international-calligraphy-competition-in-the-name-of-sheikh-hamdullah
- Sakkal square Kufic: https://sakkal.com/articles/principles_of_square_kufic.html , https://sakkal.com/instrctn/sq_kufi_hashem.html , https://design.tutsplus.com/tutorials/creative-arabic-calligraphy-square-kufic--cms-23012
- Ketebe: https://ketebe.org/en/artist/mohamed-zakariya-3269 ; Zakariya profile https://archive.aramcoworld.com/issue/199201/the.world.of.mohamed.zakariya.htm
- Haji Noor Deen: https://islamic-art.smb.museum/en/story/chinese_arabic_calligraphy ; Massoudy: https://ocula.com/artists/hassan-massoudy/
- Ibn Muqla / proportioned script: https://en.wikipedia.org/wiki/Ibn_Muqla , https://education.asianart.org/resources/the-history-of-islamic-calligraphy/ , https://ajis.org/index.php/ajiss/article/view/912
- Diwani: https://en.wikipedia.org/wiki/Diwani , https://islamicartsmagazine.com/magazine/view/diwani_style_-_a_calligraphic_variety_of_arabic_script/
- Maghribi: https://www.calligraphyqalam.com/styles/maghribi/ , https://callfront.inha.fr/s/callfront/page/maghribi-script-belaid-hamidi
- Met resources: https://www.metmuseum.org/art/metpublications/How_to_Read_Islamic_Calligraphy , https://metmuseum.org/press/exhibitions/2019/the-decorated-word
- Rulings: https://www.aliftaa.jo/decision-en/415/Resolution-No31-Ruling-on-Drawings-Designed-by-a-Talented-Fr , https://aliftaa.jo/en-fatwas/3969/rss.aspx , https://muftiwp.gov.my/en/artikel/al-kafi-li-al-fatawi/4009-al-kafi-1537-the-ruling-of-writing-verses-of-al-quran-in-certain-shapes-and-designs , https://islamqa.org/?p=170986
- Incidents: https://www.deseret.com/1997/6/24/19319663/nike-will-recall-shoes-to-appease-muslims/ , https://gulfnews.com/world/gulf/saudi/dress-laced-with-verses-from-quran-sparks-row-1.1276389
- Pseudo-script: https://en.wikipedia.org/wiki/Pseudo-Kufic , https://nga.gov/research/casva/publications/center-report/center-44/research-reports/kathryn-blair-moore.html , https://eb.com/story/beautiful-gibberish-fake-arabic-in-medieval-and-renaissance-art , https://languagehat.com/centuries-of-fake-arabic/ , https://www.cambridge.org/core/books/hidden-language-of-graphic-signs/script-pseudoscript-and-pseudopseudoscript-in-the-work-of-filippo-lippi/3DDF979C21379C8798BE849125CC476F
- Hurufiyya: https://en.wikipedia.org/wiki/Shakir_Hassan_Al_Said , https://awarewomenartists.com/en/artiste/madiha-umar/ , https://greyartmuseum.nyu.edu/2019/10/press-releasetaking-shape-abstraction-from-the-arab-world-1950s-1980s/
- Licences: Chester Beatty https://cbl.access.preservica.com/home/arabic-manuscripts-on-microfilm ; QDL https://qdl.qa/en/copyright-ethical-terms-reuse ; Bodleian https://digital.bodleian.ox.ac.uk/terms/ ; Princeton https://www.princeton.edu/news/2009/03/16/new-digital-library-islamic-manuscripts-online
