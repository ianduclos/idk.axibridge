# Hand effect — results, rulings and deferred items

Built 2026-10-22 on branch `hand-effect` (2af8c1b..b99cb9d) from [the plan](2026-10-22-hand-effect.md). Full suite at head: 2446 passed, 3 skipped, 0 failed. Contact sheets were rendered for Ian outside the repo; nothing has been tried by hand in the app yet.

## Decisions

- Ruling 1: trim the hand-engine ceiling matrix to 2 seeds once _clamp has its own unit test (Pi runtime) — cost if wrong: thinner coverage of hand×fixture combos
- Ruling 2: bend_mm lower bound 3 (plan said 1) — token-generation cost scales with L/bend (matisse 2 m at bend 5 = 0.7 s Mac, several s on Pi) — cost if wrong: finest tremor scale unavailable
- Ruling 3: keep the hand pin whenever the hand id is unchanged, including preset/defaults apply (differs from Gesture Studies, which re-pins on preset apply) — spec says kept layers keep their pin across refreezes — cost if wrong: Ian may want presets to refresh to the newest hand version
- Task 3: minor (deferred): with Ruling 3 there is no way to refresh a layer to the newest version of the same hand without switching hands; two Hand steps on one hand share the first pin
- Ian (2026-10-22): keep stray 2x/5x ceiling semantics as built (Settled 5 confirmed by Ian)

## Deferred minor findings

- Task 1: minor (deferred): np.unwrap ±π choice on exact retraces is float-noise dependent (possible Mac/Pi divergence)
- Task 2: minor (deferred, pre-existing all effects): stored step with invalid params raises ValidationError in compose._apply_effect_stack (hand-edited files only)
- Task 3: minor (deferred): with Ruling 3 there is no way to refresh a layer to the newest version of the same hand without switching hands; two Hand steps on one hand share the first pin
- Final fix wave: re-review all ADDRESSED. Minor (deferred): heading memo budget counts only one of two arrays (~2x soft bound); _rng_key assumes PCG64 dict state

## Open, Ian's call

- A local-feature-size limit (prototyped by the final reviewer) would keep small shapes recognisable at large wander strays; it changes the line's character.
- Refreshing a layer to the newest version of the same hand: switch the hand away and back.
