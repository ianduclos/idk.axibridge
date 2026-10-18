# Gesture bank — the process

How the gesture bank is worked on, end to end: from scans of other people's
lines to pieces you can keep in AxiBridge. Ian, 2026-10-17: "for once we have a
real workflow going on … document the whole process too, this is important."

This file is the map. Detail lives in the files it links; the plan and ledger
are in [IDEAS-gesture-bank.md](IDEAS-gesture-bank.md).

---

## 1. What it is

A bank of line "hands" learned from scans (artists, calligraphy, print, dance,
physics and earth lines), measured as curvature along arc length, regrown as
grammars, and combined into drawings for the AxiDraw. The aim is not imitation:
distinct grammars that are "interesting and coherent yet strange in themselves",
set side by side, with lines that turn into nibs and masses and back.

---

## 2. The loop

The working method that settled over rounds 8–10:

1. **Explore in parallel.** A round is 3–7 explorations run by separate agents
   at once, each a self-contained brief: one idea, its corpus, one real risk
   ("be dragged by curiosity, go on limbs"). Each produces images, numbers and a
   short write-up. Duds are kept as evidence.
2. **Lead review.** The lead (the main Claude session) checks every agent's
   diff, runs the suites, looks at every headline image, forms its own read,
   writes the round summary and commits.
3. **Review page.** All images of the round go on one private claude.ai
   artifact, grouped by exploration, each with the lead's read and a **notes
   box** whose text is saved in the page's database (collection `notes`,
   doc id = image name, `exp-<thread>` or `round`).
4. **Ian annotates.** He writes notes on the images he cares about.
5. **Compare first.** The lead reads the notes back and, before acting, says
   how Ian's reads compared to its own: where they agreed, where it was wrong
   and why. The comparison is committed as `results/roundN-review-*.md`.
6. **Ian orients.** He says what to keep, what to develop, what to drop. Kept
   work becomes a **study** (a saved piece in the app) or a technique in the
   **kit**; the next round builds on it.

Images are the medium of judgement. Nothing is plotted unless Ian asks.

---

## 3. The parts

| Part | What it is | Where |
|---|---|---|
| Corpora | scans + manifests (rights recorded as information, not a filter; each download approved by Ian) | `.local/gesture/corpus/` (local), `docs/research/gesture-corpus/*.md|csv` |
| Extraction | scan → strokes with width (`extract_hybrid` is the default) | `tools/gesture/gesture/extract_hybrid.py` |
| Measurement | the 74-feature panel; standard preprocessing (σ ≥ 7 line widths + medium projection) for comparing hands | `panel.py`, `medium.py` |
| Hands | learned line grammars (clothoid segments, plans, chains) | `grammar.py`; saved in the library |
| Regimes | one line becoming nib and mass (r(s) from 0 to 2), from fields, timing, prosody | `regime.py`, `regime_field.py`, `gesture_timing.py` |
| Kit | saved library + combinable techniques + recipes | `tools/gesture/gesture/kit/` ([contract](../tools/gesture/gesture/kit/README.md), [spec](superpowers/specs/2026-10-17-gesture-kit.md)) |
| Library | every learned hand, tempo, dance trail, shape set, corpus index, with provenance and policy | `tools/gesture/library/<kind>/<id>/` |
| Hand Drift bench | the first app bench: one line drifting through hands | `axibridge/sources/hand_drift.py` ([plan](superpowers/plans/2026-10-17-hand-drift-bench.md)) |
| Gesture Studies | saved pieces with their own controls, one bench with its own dropdown (28 built-in; forks in a machine-level store) | `axibridge/sources/gesture_studies.py`, `_gesture_studies/`, `gesture_studies_store.py`, `gesture_studies_api.py` ([spec](superpowers/specs/2026-10-17-gesture-studies.md)) |

### The kit in one paragraph

Four kinds of technique, each a drop-in file that registers itself: **voices**
draw centrelines (a hand, a drift, the dance itself, a machine, a chart);
**modulators** write per-point channels (regime, nib angle, width, emphasis)
from a field, a tempo, prosody, a handover; **renderers** ink (wire, nib
styles, restatement, coils); **arrangers** place parts on a sheet (single,
grid, scatter, page, conversation, call and response). A **recipe** is JSON
naming the techniques and their params; `kit.run(recipe)` is deterministic and
`kit.preview` saves the recipe beside every image, so anything kept can be
rebuilt or recombined.

### Studies — keeping pieces without overcooking the instrument

A study is a frozen recipe plus the 3–8 controls that matter for it, with a
version and a parent. Built-in studies ship in the app; "Save as new study"
forks one into a machine-level store; kept layers embed the whole recipe so
they never change. Hand controls list every hand in the frozen library, so new
hands appear in every study after a refreeze. One generator, "Gesture
Studies", holds them all, with its own study dropdown. A multi-pen study (the
chorus) keeps as a group with one layer per voice, each on its own pen; the
Sampler's seed picks a whole unbred combination from the kit.

### Research vs app

Research code (`tools/gesture/`, its own venv `.local/gesture/.venv`) keeps
moving. The app never reads it: what the app needs is **frozen** into
`axibridge/sources/_hand_drift/` and `_gesture_studies/` by freeze scripts
(`tools/hand_drift/freeze.py`, `tools/gesture_studies/freeze.py`), always from
the committed HEAD, with parity tests proving the frozen copy draws exactly
what the research draws.

---

## 4. How to

**Run a round.** Write one brief per exploration that stands on its own: the
kit contract to read, the relevant results, Ian's latest notes and principles
(quote him), the exploration, one risk, and the hard rules below. Each agent
may only CREATE its own files (`kit/<prefix>_*.py`, `experiments/<name>.py`,
`tests/test_<name>.py`, `results/<name>-<date>.md`, new library folders,
`.local/gesture/out/<name>/`) — that is what lets 4–7 agents share one
checkout. Launch them in the background together; review each as it lands.

**Make the review page.** Copy the previous round's page
(`round9-review.html` pattern: one section per exploration, lead pick tags, a
saved notes box per image, the db capability), publish the round's images as
files beside it, probe the notes store once, and record the URL in
`HANDOFF.md`. Read the notes back with ArtifactData before commenting.

**Add a hand.** Extract the corpus, learn a grammar, save it with
`kit.library.save(...)` in its own folder with provenance and policy, measure
how distinct and how self-consistent it is. To get it into the app, rerun
`tools/gesture_studies/freeze.py`.

**Add a technique.** One file under `kit/` registering a voice, modulator,
renderer or arranger with a param spec; tests; an image made through
`kit.run` + `kit.preview`.

**Keep a piece.** In the app, the Gesture Studies bench's "Keep as layer"
makes a layer pinned to the library it was drawn with ("Keep as group" for the
chorus: one layer per voice, each on its own pen, one undo step). Resuming a
kept layer keeps it on its own library through every edit; "Update to current
library" moves it on purpose. "Save as new
study" forks a study into the machine-level store (records its parent). To
make a recipe a built-in study: add `axibridge/sources/_gesture_studies/studies/<id>/study.json`
(the recipe, 3–8 bounded controls, notes on why), rerun
`tools/gesture_studies/freeze.py` with the research venv (it freezes the kit
from HEAD and every generative library entry, and checks parity), run
`tests/test_gesture_studies.py`.

**Bring new hands into the app.** Learn and save them in the library, commit,
rerun `tools/gesture_studies/freeze.py`: every study's hand controls list them,
and they enter the Sampler's sample space. Kept layers stay pinned to the
snapshot they were made from, edits included, until "Update to current
library".

---

## 5. Rules that bind

- **Images only.** Research is judged from images; don't stage plots or touch
  the live app unless Ian asks.
- **Arabic calligraphy:** Qur'anic and devotional text is measure-only, never a
  generation source (the library's policy gate and `calligraphy.require_generative`
  enforce it); never output legible Arabic. A sheet that opens with a
  devotional invocation is measure-only.
- **Abstract script is never legible in any script**, Latin included; a page
  with an Arabic look gets a human reader's check before it is kept.
- **Licences** are recorded, not used as a filter (private research); every
  download still needs Ian's go (name, source, size). No CAPTCHAs.
- **Taste** (from Ian's notes; details in the review files):
  - contiguous lines, never hatching;
  - distinct grammars kept whole, never averaged;
  - transitions and less obvious sign-like shapes matter most;
  - surprise comes from combination, for example two voices on one surface,
    or a drawing beside its own measurement;
  - systematic structure only as an accessory or an occasional event;
  - masses as round beads and knots, not elongated capsules;
  - digest sources conceptually, never copy their forms.
- **Determinism:** seeds derive from the recipe seed and part index only; never
  `hash()` or set order (a `max(set(...))` tie once made sheets differ between
  processes).
- **Processes:** worker pools only as context managers; agents check that none
  of theirs survive (22 orphans once piled up from earlier runs).
- **Freeze from HEAD**, never from files another agent may be editing.

---

## 6. History

| When | What | Where |
|---|---|---|
| 2026-10-16 | Brainstorm, research passes, staged plan | [IDEAS-gesture-bank.md](IDEAS-gesture-bank.md) |
| Stage 0–2 | Corpora (Matisse, Hokusai, Ingres), nulls, extraction bake-off, panel; medium confound found and projected out | ledger in IDEAS; `results/medium-invariance-2026-10-16.md` |
| Stage 3, rounds 2–4 | Grammars v2–v6 (contiguous lines, corner budget), topology, restyle, tremor, composite; Arabic calligraphy and print corpora (policy adopted) | `results/grammar-v*.md`, `round3/4-2026-10-16.md` |
| Rounds 5–7 | Broad-nib model, regimes (line → nib → mass), signs as line events, wet edges, nib inking at real pens, path ordering | `round6/7-2026-10-16.md` |
| Round 8 | Seven threads joining line styles with gesture/shape corpora; first review page; Ian: hybrid/drift is "the closest to the idea I had in mind" | `round8-2026-10-16.md`, `round8-review-2026-10-17.md` |
| 2026-10-17 | Hand Drift bench in the app | [plan](superpowers/plans/2026-10-17-hand-drift-bench.md) |
| 2026-10-17 | Gesture kit: library + techniques + recipes | [spec](superpowers/specs/2026-10-17-gesture-kit.md) |
| Round 9 | Corpus voices, machine/diagram voices, prosody, polyphonic sheets, built into the kit; Ian: "save the methods" of the two-voice and danced-chain recipes | `round9-2026-10-17.md`, `round9-review-2026-10-17.md` |
| Round 10 + Studies | Gesture Studies bench in the app (8 studies, Hand Drift first; new hands flow in on refreeze); explorations: drawing + its measurement (numbered atlas, merged shadow), developments (beads, rare machine events, chorus), combination search (proxy AUC 0.87 / 0.61) | `round10-2026-10-17.md`, [studies spec](superpowers/specs/2026-10-17-gesture-studies.md) |
| Studies v2 | Seven studies from the round-10 review (numbered atlas, dance atlas, margin chart, merged shadow, chorus kept as a pen-per-voice group, sampler, ledger with straight lines); edits stay pinned; exact clothoid memos (~1.45×) | [studies spec](superpowers/specs/2026-10-17-gesture-studies.md) "Studies v2" |
| Round 11 | Emphasis on hands: 20 new hands (rivers at three zooms + a braid voice; leaf-miner, beetle, slime, borer, oak-net, grazer and particle-track trails; two fly hands from mosca-draw's simulated walks; six per-dancer hands, barely distinguishable); smooth swelling into round mass (drop/press/lens), deliberate dot shapes, bold single gestures; solid abstract script (joining decides it; weight window 0.25–0.42 band cover); measurement versions (taxonomy plate, specimens re-chained into a second drawing); refreeze to 44 hands; ten new corpora approved for download | `round11-2026-10-17.md`, review page in `HANDOFF.md` |

| Round 13 | Interlocking regimes (rules, mutual, contagion) and lines that change hands (gmorph, handover, accrue, stages); Ian kept rules, liked the dense "duds"; phase 2 built two studies as kit techniques (`found_play`, `passage`) with Sol 6.1 agents. Ian: correct "but more dynamic", so not frozen; next is full compositions | `round13-2026-10-18.md`, `round13-review-2026-10-18.md`, `round13-phase2-2026-10-18.md` |
| Round 12 | New pathways against calcification: sources as drivers (stork/mosquito steering a river line), a seven-sheet series, mass from fabric stains, a Codex-run outsider thread, round 7 revisited; Ian's seed "Oehlen works on paper, go deep" as research → approved downloads → found ground, conduction and an intuition-steered session; ≤ 5 images per thread; keeps → 24 studies | `round12-2026-10-18.md`, review page in `HANDOFF.md` |

### Turns in direction (Ian's words)

- "Contiguous lines … def not hatching. Think Oehlen's trees or some of the
  computer paintings." (rounds 2–3)
- "Lines, nibs, and shapes … the most interesting thing would be for them to be
  able to become one or the other in space." (round 6)
- "The less obvious shapes, how they seem to communicate something." (round 6)
- "Not on paper, image is enough." / "Told you we're not plotting." (round 8)
- "How different the grammars are, but how they are interesting and coherent
  yet strange in themselves." (round 8 review)
- "These feel like pieces … save these, each with its own relevant parameters,
  still able to have dynamism, and develop on top." (round 9 review)
- "Curiously I dig the unbred ones more. It's like these are collapsing into a
  style." (round 10 review)
- "An experimental approach, this is the most important" and "return more
  emphasis to the different hands." (round 11 brief)
- "Perhaps the new hands are a bit meh … more interested in using these
  kinematics to drive other stuff." / Abstract script: "too similar to real …
  keep it a separate thing." (round 11 review)
- "Albert Oehlen works on paper, go deep." / "Some radical alternative approach,
  session self steered by intuition." / Rivers as found material only "like a
  far away view of the river, tight zigzag curves." (round 12 seed)
- "The real sources blending into each other in a line … make the
  vocabularies more malleable." (round 13 review)
- "Would have thought they were more dynamic though … Grabbing the techniques
  that work and making full compositions which are different every time." /
  The Amazon river: "love it, but it's starting to be overused." (round 13
  phase 2)

---

## 7. Lessons

- Fidelity metrics and Ian's taste diverge: he picked a "failure" (chain-context
  joins) as one of the best, and passed over the lead's systematic picks. The
  notes-first comparison exists to surface this every round.
- Blending grammars collapses them; drifting between them or setting them side
  by side keeps them alive.
- Parallel agents in one checkout work when each only adds its own files;
  shared contracts (the kit README) must exist before the round starts. An
  app build can run beside research agents if it freezes from HEAD.
- A taste proxy is a candidate generator, not a judge: it caught the obvious
  dislikes (capsules) but could not tell the multi-voice sheets Ian liked from
  the ones he passed over. In the round-10 review he liked most of the proxy's
  bottom picks too, and preferred unbred samples: breeding toward a score
  collapses variety into one style. Sample widely; let Ian pick.
- A new corpus becomes a hand only at the right scale: rivers are distinct at
  the zoom where they fall into the human band, trails only from a coarse
  centre-line (plain extraction gave nothing on bark and fossils). Measure
  distinctness against the whole library before claiming a hand is new.
- Not every source is a hand: six dancers measured as two families, because
  the instruction outweighs the dancer. A negative result like that is worth
  keeping.
- Weight is not solidity: abstract script reads as writing when it is joined;
  more ink past half the band closes the counters and turns blocky.
- Smooth and round are compatible only if the slow part of a swell stays at
  line width; a symmetric swell turns into a sausage past one head diameter.
- Legibility slips in sideways: small-arch hands drift toward Latin cursive
  ("Don…", "bit"), and OCR misses what the eye catches. Check every script
  page by eye, in Latin as well as Arabic.
- An app build can change shared research modules while research agents run,
  if every change is default-preserving and parity-checked (the clothoid memos
  were bit-identical on every fixture).
- A pathway can saturate while still producing "correct" results: by round 11
  new hands measured as distinct yet read to Ian as "a bit meh". When a pathway
  keeps passing the numbers and stops moving him, change the pathway, not the
  parameters (see §8).
- A sound statistic is not a taste signal (round 12). Drivers passed a clean
  control test, but to Ian they read as "the aesthetic we already achieved". What he
  had been asking for all along turned out to be **regimes that interact**: a
  line captured by another regime, becoming it, ignoring it, and going on
  (Oehlen found ground, "absolute gold"). Rank by the relation between regimes.
- Legibility is a proxy too (round 13). The lead ranked tidy single-cause proofs first
  and showed the dense versions (mutual's soup, accrue's runaway, rules' crowded sheet)
  as duds; Ian liked those and called the rules thread a keeper. He rewards richness of
  interaction, many relations at once and a line passing through several real sources,
  over one readable relation. Show the "too much" versions as candidates, not as duds.
- A fixed composition with a varying line collapses into a template (round 13
  phase 2). Both studies did what they were built to do, and Ian found them not
  dynamic. Density of events inside one layout is not dynamics. The
  composition itself (frame, layers, scale contrasts, blank) has to vary
  and decide, so the test is a population of compositions, not one piece.
  A diagnostic can be a picture: the colour map of what each line was doing was
  the one image he commented on as a drawing.
- An artist seed done as research → his approval of references → several
  directions plus one free session found the round's best work. The free
  "intuition" session was bold but thin. The procedure-reading threads paid off.

---

## 8. Development method — notes

How the work is actually run, what keeps it healthy, and how to tell when it is
calcifying. Written at the end of rounds 8–11 (2026-10-17).

### Roles

- **Ian** sets direction in a sentence or two, annotates review pages, and
  decides what is kept. He reacts to images, not to descriptions.
- **The lead** (the main Claude session) turns that into briefs, runs the
  explorations as parallel agents, reviews every diff and headline image, writes
  its own read *before* seeing his, commits, publishes the review page, and
  compares his notes with its reads first. It owns the contracts (kit README,
  specs) and the records (round summaries, review records, this file).
- **Exploration agents** (Opus, background) each own one idea, one risk and
  only their own files. App builds are a separate agent that freezes from HEAD.
- **Study builds** (making a kept technique into a study, building it, freezing
  it) go to **Sol 6.1 (Codex) agents** (Ian, 2026-10-18: "for the study builds
  use sol 6.1 subagents"). Each gets a self-contained brief naming the files it
  owns. The lead reviews the diff and images and commits.
- **Sessions**: one long session per run, then a wrap-up and a plan; the next
  run starts fresh from `HANDOFF.md` and the plan file (stale context is the
  main failure source in long sessions).

### Cadence of one run

1. Plan file for the run (direction, threads, risks, what to keep) — written
   at the end of the previous run.
2. Build what was kept (studies, refreeze) beside the new explorations.
3. Lead review → round summary → review page.
4. Ian annotates → review record (notes vs reads, divergences, pattern).
5. Method notes and history updated here; wrap-up; next plan.

### What keeps it healthy

- The notes-first comparison: each round the lead has been wrong in a new way
  (systematic picks, capsules, the proxy, new hands), and the record makes the
  correction stick.
- Wide sampling over optimisation; duds kept as evidence.
- Recipes beside every image, so anything Ian names can be rebuilt.
- Small, explicit contracts before parallel work; freezing from HEAD.
- Policy and taste rules written down once (§5) instead of re-argued per round.

### Signs of calcification (check at every plan)

- A pathway keeps meeting its own metrics while Ian's notes go flat ("we've
  done better", "meh", "¯\_(ツ)_/¯").
- The same defaults keep reappearing: the matisse → shikasta → lichtenberg route,
  seed 7000, one A4 sheet, ink-on-paper preview, kit recipes as the only medium.
- Briefs reuse the lead's vocabulary and the same exploration shapes (one corpus
  → one hand → one sheet), so outcomes converge.
- The lead's read and Ian's agree only on what the previous round already
  established.
- Review pages grow (40+ images) while the number of things Ian keeps shrinks.

### Ways to break it

- Change the unit: a series, a sequence, a large multi-sheet piece, a timeline
  instead of one sheet.
- Change the role of a source: driver instead of grammar (kinematics steering
  weight, rhythm, pen changes).
- Change who seeds the round: Ian brings a sketch, photo or word; or a second
  model (Codex / Gemini agents) explores with its own taste.
- Constraint rounds: one technique only, no kit, or revisit an old round's duds
  with today's tools.
- Fewer images, more depth: one finished piece per thread instead of a
  population sheet.
