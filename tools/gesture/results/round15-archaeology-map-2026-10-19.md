# Round 15, phase 0b — archaeology map of four past-keep families (2026-10-19)

Made by a Sol 6.1 Codex agent (read-only); the lead spot-checked the
registration lines. Paths: **K** = `tools/gesture/gesture/kit/`,
**S** = `axibridge/sources/_gesture_studies/studies/`, **R** =
`tools/gesture/results/`. Params: `[min,max]=default`.

## 1. Hand Drift and the danced chain

- voice `drift` (K/voices_base.py:68): `hands` refs(hand, 1–6) = [matisse, shikasta, lichtenberg]; `blend` mixture|interp; `plateau` [0,.6]=.12; `length` [.2,12]=6; `joins` smooth|chain.
- voice `hand` (voices_base.py:61): `hand`, `length`, `joins`.
- modulator `timing` (modulators_base.py:65): `tempo` ref(tempo)=staccato; `amount` [0,2]=1; `wrist_nib`; `mass_width` [1,30]=9; `pen`; `jitter_gain`; `q_mass`.
- voice `dance` (voices_corpus.py:75): `trail` ref(dance_trail)=levitation; `seconds` [1,60]=15; `t0`; `cut` phrase|none; `effectors` all|hands|feet|….
- modulators `measure_pair` (measure_pairs.py:409: `chart` kappa|route|phase|atlas|ledger, `split`, `cells`) and `measure_next` (measure_next.py:1000: `grain`, `cells`, `split`, `page` diptych|margin|triptych).

Studies (S): `hand_drift` uses the older Hand Drift engine, not a kit recipe; for composition use `drift`. `danced_chain`: `{"seed":7000,"parts":[{"voice":{"id":"drift","joins":"chain"},"modulators":[{"id":"timing","tempo":"staccato"}]}],"renderer":{"id":"nib","style":"e"}}`. `dance_atlas`: dance mantis 20 s + `measure_pair` atlas, renderer `measure_wire`. `dance_triptych`: dance mantis + `measure_next` triptych.

Calling: `drift` and `dance` fit any box. drift carries `voice`; timing adds `r, phi, M, tremor, dance_t` (keeps `W`): render with `nib`. Atlas modulators subdivide and refit **their supplied box** and add chart marks for `measure_wire`. Needs hands matisse/shikasta/lichtenberg, tempo staccato, trail mantis.
Keep evidence: danced chain "save the methods of 2 and 4" (R/round9-review:7); atlas "love this as well" (round10-review:10); triptych "cool" (round11-review:12).

## 2. Swell and bold gestures

- renderer `swell` (swell_ink.py:411): `profile` bell|lens|drop|press|turn|momentum|sag|necklace = drop; `size` [.5,40]=7; `k_head` [.05,.98]=.75; `tail` [0,120]=18; `tail_w` [.1,6]=1.6; `pen`; `thr`.
- renderer `swell_dots` (swell_ink.py:659): `rule` inflection|turns|beat|count|decel|fullstop|pauses; `shape_L` disc|ring|split|comma|wound; `line` wire|none|swell; `size`; `swell_size`; `phrase`; `space`.
- arranger `swell_place` (swell_ink.py:753): `boxes` fractional, `inks`.
- modulator `prosody` (prosody_modulators.py:307): `density` [.05,10]=1; `gap`; `unit` pulse|segment; `span`; `primary`; `W`; `M`.

Studies: `bold_swell` = hand shikasta 0.9 + prosody (density .4, gap 60, span 8, primary .5) + swell (pen .6, size 22, k_head .8, tail 55, tail_w 2.6), seed 7601. `swell_answer` = dev_chorus (radius 14, black,red) over roadrunner wire + shikasta swell. `swell_sentence` = drift_tokens chain + prosody segment + swell_dots fullstop/ring/swell.
Calling: `part.run(box)`: hand → prosody → swell. Renderers follow the placed geometry without refitting; swell reads `emphasis`, else `clip(r−1,0,1)`. Extra bold recipes: R/swell-bold.recipe.json keys `b2-thirds`, `b3-press-sweep` (meander69, 7620), `b4-turn-knots` (marden, 7630). Ian: "very nice, very promising" (round11-review:22).

## 3. Limb signs and the chorus

- voice `revisit_glyph` (voices_revisit.py:183): `trail`; `host` lhand|rhand|lfoot|rfoot|head; `with_` none|others|…; `seconds`; `still`; `min_hold_s`; `fig`; `max_glyphs` [0,80]=12.
- arranger `dev_chorus` (dev_chorus.py:54): `answer_to` previous|all|leader|none; `listen_by` space|time; `radius`; `answer`; `layout` single|rows; `inks`; `voices`.

Studies: `limb_signs` = revisit_glyph particles, host rfoot with head, 60 s, still .2, min_hold .25, max_glyphs 5, frame 150×210, renderer `revisit_nib` black,red, seed 1201. `limb_signs_levitation` = levitation, lhand with lfoot, 240×180. `chorus` = dev_chorus 4 voices (drift_tokens nib; drift_tokens bubble+hokusai restate 8 contour; meander69 dev_beads cluster; shikasta dev_beads line none), seed 7100.
Calling: glyphs fit into any box and carry `r/phi/W/M`, `glyph`, dance channels; `revisit_nib` keeps per-mark colours. dev_chorus is an arranger, not a part: call it with `ctx.with_box(box)` and its parts; it uses `p.run(box)` and `prosody_arrangers.answer_mark` (replies only for marks with prosody meta).
Ian: limb signs "super nice. keeper" (round12-review:28); chorus "very nice actually … multiple pens" (round10-review:15).

## 4. Handover, accrue (3966), belt, gmorph

- voice `morph_handover` (voices_handover.py:314): `hands` 2 refs = [meander69, fly_open]; `order` "bend,turn,corner,length"; `windows`; `R_mm` [10,1000]=110; `rows` [1,12]; `route`; `K`; `mode` features|tokens|average.
- voice `accrue_walk` (voices_accrue.py:327): `hand`=river_belt; `length` [.3,60]=9; `scale`; `K`; `habit` leaky|loops; `c_max`; `grow`; `exhaust`.
- voice `belt` (voices_belt.py:71): `hand`=river_belt; `length`; `joins`; `gain` [0,4]=1.8; `gain_end`; `pull`; `drift_mm`; `read_box`.
- voice `gmorph` (voices_gmorph.py:313): `hand`; `length`; schedules `span/turn/corners/sign/gain/pull` as [u, value, …].
- modulator `accrue_ink` (modulators_accrue.py:58): `curl_on`, `curl_r`, `spin_floor`, `spin_full`, `W`, `M`, `phi0`, `smooth`.

Study: `morphing_belt` = belt gain_end 1.8, frame 280×60, seed 12407, wire .35 (its saved gain does not ramp: equal gains). No handover/accrue/gmorph study. Accrue 3966 (R/accrue-3-variants.recipe.json[2]): `{"frame":[297,105],"seed":3966,"margin":6,"parts":[{"voice":{"id":"accrue_walk"},"modulators":[{"id":"accrue_ink"}]}],"renderer":{"id":"nib"}}`. Exemplars: R/handover-1-piece.recipe.json, R/gmorph-piece.recipe.json.
Calling: handover and accrue grow directly against `ctx.box` (steered, not clipped) and record no `meta.fit`; belt and gmorph fit into the box. Handover carries `src_*`, `stage`, `voice`, `handover_u` (wire is enough); accrue carries `acc_*`, `voice` (`accrue_ink` turns it into nib channels); gmorph carries `u` and optional scheduled `r`.
Ian: handover "this is really good. keep" (round13-review:17); accrue 3966 "love love the last one" (:31); belt "line that morphs gesture type" (round12-review:30).

## Pitfalls

- Pass the box to **both** stages: `p.run(box)` or `p.modulate(p.voice(box), box)` (core.py:691).
- Automatic margin follows renderer reach: changing a renderer can change fitted geometry and prosody.
- The exact accrue opening helper (voices_passage.py:49) only translates recorded geometry; it needs width ≥ 285 mm, height > 93 mm.
- Process-global registries and library caches: treat cached entries as read-only.
- Handover/accrue proposal searches can be slow; the full swell experiment took ≈ 90 s.
- `handover` (voices_machine.py:515) is a separate **modulator**, not an alias of `morph_handover`.
