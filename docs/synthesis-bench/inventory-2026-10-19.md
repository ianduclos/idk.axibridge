# Synthesis bench — technique inventory (2026-10-19)

Made by a Sol 6.1 Codex agent (read-only survey) for the synthesis bench: the
one bench that groups and synthesizes most of the gesture techniques, where Ian
composes and edits the substructure. The lead spot-checked the registration
count (122) and sampled file:line references. Paths are relative to
`tools/gesture/gesture/kit/` unless stated. The `arch` study was being built
while this was written; it is not in the 28-study baseline.

**122 decorator registrations:** 32 voices, 27 modulators, 24 renderers, 26 arrangers, 13 devices. No files written.

The original **28 studies** are indexed below. A new, untracked `arch` study appeared during concurrent work; it is excluded from that baseline.

**Reading key**

- Technique locations are relative to `tools/gesture/gesture/kit/`.
- Review references `r8`–`r11` mean `tools/gesture/results/roundN-review-2026-10-17.md`; `r12`–`r13` end `2026-10-18.md`; `r14`–`r15` end `2026-10-19.md`. `p13` = `round13-phase2-2026-10-18.md`.
- Verdicts: **K** keeper, **L** liked, **M** meh, **D** dud. **~** means the quote concerns a sheet/thread/variant, rather than independent approval of the component.
- Inputs: **H** `hand`, **T** `tempo`, **D** `dance_trail`, **RS** `river_stems`, **RL** `river_loops`, **RB** `river_braid`, **DS** `drive_signal`, **TD** `typed_drawing`.
- Outputs: **G** geometry; **I** Ink; **Q** = `r,phi,W,M`; **μ** mark metadata; **S** `_score.Score` plus `ctx.note("score",…)`. Otherwise **no Score or ctx.note**. Existing channels generally pass through; default Q channels are omitted.
- Runtime: **F** <1s, **M** 1–10s, **S** >10s; variant-dependent timings are explained in §5.

**Study index:** `s1 annotated_page`; `s2 bold_swell`; `s3 brood_gallery`; `s4 chorus`; `s5 conversation`; `s6 dance_atlas`; `s7 dance_triptych`; `s8 danced_chain`; `s9 drawing_and_measure`; `s10 found_ground`; `s11 hand_drift`; `s12 leaf_miner`; `s13 ledger_straight`; `s14 limb_signs`; `s15 limb_signs_levitation`; `s16 margin_chart`; `s17 merged_shadow`; `s18 morphing_belt`; `s19 numbered_atlas`; `s20 rechain`; `s21 river_taxonomy`; `s22 sampler`; `s23 shape_atlas`; `s24 specimen_plate`; `s25 swell_answer`; `s26 swell_sentence`; `s27 three_voices`; `s28 two_voices`.

Study cells identify **direct recipe references**. `hand_drift` has its own engine; `sampler` chooses registrations dynamically, so neither supplies a fixed additional mapping.

**1. Technique inventory**

**Voices**

| Kind | Id | File:line | Does | Inputs / calls | Outputs | Time | Round | Artist verdict | Study |
|---|---|---|---|---|---|---|---|---|---|
| V | drift | voices_base.py:68 | Changes hands along one line | H | G,voice | ? | 8→9 | K “one of the best” r8:18 | s1,8,9,16,17,19,20,24,28 |
| V | morph_handover | voices_handover.py:314 | Hands exchange individual features | H | G,src_*,stage,voice,handover_u | ? | 13 | K “really good. keep” r13:17 | — |
| V | revisit_glyph | voices_revisit.py:183 | Held limb writes other limbs’ movement | D | G,dance_*,glyph,Q | ? | 12 | K “super nice. keeper” r12:28 | s14,15 |
| V | river_zoom | voices_rzoom.py:371 | Magnifies real river along itself | RS | G,zoom,u_km;μ | ? | 14 | K “Amazing results” r14:26 | — |
| V | oehlen_found_river | arrangers_oehlen_found.py:577 | Tight far-view river fragment | RS | G;μ | ? | 12 | K~ “absolute gold” r12:8 | s10 |
| V | series_travel | voices_series.py:139 | Routes changing hands across sheets | H | G,voice,series_u | ? | 12 | K~ “amazing” r12:25 | — |
| V | dance | voices_corpus.py:75 | Draws actual effector trails | D | G,dance_t/speed/acc | ? | 9 | K~ “amazing … would save” r9:11 | s6,7,27 |
| V | belt | voices_belt.py:71 | Tightens detrended hand curvature | H; grow helper | G;μ | ? | 12 | L “loving this kinda stuff” r12:30 | s18 |
| V | trail_brood | voices_trails.py:80 | Larvae branch from mother gallery | H | G,voice,age | ? | 11 | L “super nice” r11:20 | s3 |
| V | diagram | voices_machine_diagram.py:563 | Draws regenerated line’s measurements | H; grow,hand_drawn | G,r,voice,machine;μ | F–M/S | 9 | L “would print this as is” r9:18 | s23 |
| V | gmorph | voices_gmorph.py:313 | Schedules grammar-feature changes | H | G,u,r optional;μ | ? | 13 | L “more what i wanted” r13:20; mixed r13:37 | — |
| V | mutual | voices_mutual.py:1076 | Four regimes exchange event cues | H,RS; local quake files | G,tick,neg,r;μ | ? | 13 | L “Really like this” r13:29 | — |
| V | accrue_walk | voices_accrue.py:327 | History changes subsequent gesture | H | G,acc_*;μ | ? | 13 | L~ “love love the last one” r13:31 | — |
| V | stages_line | arrangers_stages.py:446 | Encounter-driven continuous line | H; grow helper | G,Q,src,series_u;μ | ? | 13 | L~ “it's nice” r13:35 | — |
| V | river_approach | voices_rnear.py:498 | Approaches river through scales/hands | RS,H,RL | G,zoom,src,stem_u,voice | ? | 14 | L “nice as well” r14:34 | — |
| V | lcorp_zoom | voices_lcorp.py:495 | Zooms hand, relay, dance or river | H/D/RS | G,zoom,u_src,voice; S relay-only | ? | 15 | L relay “good”; general “more difference” r15:20 | — |
| V | oehlen_conduct | voices_oehlen_conduct.py:577 | Source cues enlarged learned performance | D,H | G,cw,role,r;μ | ? | 12 | L~ process “have to explore” r12:18 | — |
| V | oehlen_conduct_ensemble | voices_oehlen_conduct.py:897 | Cues alternate multiple performers | D,H | G,cw,role,voice,r;μ | ? | 12 | L~ process “have to explore” r12:18 | — |
| V | river_braid | voices_rivers.py:314 | Threads split around learned islands | H,RB | G,voice,thread,emphasis | ? | 11 | M “idk” r11:29 | — |
| V | oehlen_conduct_tree | voices_oehlen_conduct.py:746 | Dance cues branching tree program | D,H | G,cw,role,r;μ | ? | 12 | M “meh” r12:53 | — |
| V | oehlen_intuit_sheet | voices_oehlen_intuit.py:207 | Replays authored intuition-session sheet | TD | G;μ | ? | 12 | D~ “not great” r12:51 | — |
| V | script_solid | script_solid.py:571 | Builds abstract joined script rows | H | G,Q,voice;μ | ? | 11 | M~ “not interested … too similar to real” r11:34 | — |
| V | hand | voices_base.py:61 | One learned grammar throughout | H | G,voice | ? | 8→9 | not reviewed independently | s1,2,4,5,10,12,13,21,25,27,28 |
| V | drift_tokens | prosody_voices.py:47 | Drift with token-event channels | H | G,voice,token,tok_turn | ? | 9 | not reviewed | s4,26 |
| V | machine | voices_machine.py:394 | Machine grammar re-speaks hand | H; grow helper | G,voice,machine | F–M | 9 | not reviewed independently | — |
| V | measure_next_duet | measure_next.py:1270 | Two offset whole hand-lines | H; grow helper | G,voice | ? | 11 | not reviewed | — |
| V | river_loops | voices_rivers.py:192 | Attaches or abandons learned oxbows | H,RL | G,voice,loop,r | ? | 11 | not reviewed | — |
| V | trail_sheet | voices_trails.py:38 | Generates learned whole-sheet topology | H | G,voice | ? | 11 | not reviewed independently | — |
| V | series_stretch | voices_series.py:161 | Placeholder receiving travelling-line stretch | series_row | No standalone marks | ? | 12 | not reviewed | — |
| V | passage | voices_passage.py:427 | Unequal sections exchange source features | H; accrue/gmorph/handover helpers | G,src_*,voice,section,n_sources;μ | ? | 13 phase 2 | M~ “more dynamic though” p13:40 | — |
| V | cgram_free | arrangers_cgram.py:123 | Recreates seed-3966 free line | H; accrue helper | G;μ | ? | 14 | not reviewed independently | — |
| V | cproc_score | arrangers_cproc.py:116 | Placeholder for procedural composer | cproc | No standalone marks | ? | 14 | not reviewed | — |

`src_*` = corner/bend/turn/length ownership. `acc_*` = curl, habit, press, spin, rel, recall, s, knot.

**Modulators**

| Kind | Id | File:line | Does | Inputs / calls | Outputs | Time | Round | Artist verdict | Study |
|---|---|---|---|---|---|---|---|---|---|
| M | measure_pair | measure_pairs.py:409 | Pairs drawing with indexed measurement | marks; optional H redraw | G,r=0;μ | F/S | 10 | K~ “amazing. keep as is” r10:8 | s6,13,16,19 |
| M | measure_shadow | measure_pairs.py:615 | Unions drawing and measured shadow | geometry/curvature | G,r=0;μ | ? | 10 | K “love all the different options” r10:12 | s17 |
| M | measure_atlas | measure_pairs.py:666 | Rearranges measured shape specimens | marks; optional H redraw | G,r=0;μ | F/S | 10 | K~ “amazing. keep as is” r10:8 | — |
| M | measure_next | measure_next.py:1000 | Extended plates, cuts and triptychs | marks; optional H redraw | G,r=0,mn_specimen on rechain;μ | F/S | 11 | K~ “love” r11:9 | s7,10,21,24 |
| M | timing | modulators_base.py:65 | Dance tempo controls weight/tremor | T | G,r,M,phi,tremor,dance_t | ? | 8→9 | K~ “save the methods” r9:7 | s1,5,8 |
| M | measure_next_rechain | measure_next.py:1165 | Reorders specimens into new line | marks | G,mn_specimen;μ | ? | 11 | L “super nice” r11:9 | s20 |
| M | lcorp_aware | modulators_lcorp.py:268 | Depth cuts or sympathetic twisting | marks,zoom | G;μ | ? | 15 | L sympathy “very very good” r15:24 | — |
| M | lcorp_style | modulators_lcorp.py:98 | Applies fine bends to retained course | H/RS | G;μ | ? | 15 | L “very interesting” r15:22 | — |
| M | annotate | voices_machine_diagram.py:607 | Adds measurement beside/over marks | marks; optional H | G,r,voice,machine;μ | ? | 9 | L~ “handy for a project” r9:15 | s9 |
| M | handover | voices_machine.py:515 | Machines take selected line stretches | marks; machine helpers | G,machine,voice;μ | ? | 9 | L “very occasional stairs” r9:20 | s9 |
| M | prosody | prosody_modulators.py:307 | Selects stresses from line events | geometry/token/voice/dance channels | emphasis,r,W,M;μ | ? | 9 | L~ “when you start mixing it up” r9:22 | s2,4,25,26 |
| M | own_tempo | voices_corpus.py:125 | Uses source dance’s own clock | dance_speed/acc | G,r,M | ? | 9 | L~ “amazing … would save” r9:11 | s27 |
| M | accrue_ink | modulators_accrue.py:58 | Accumulated state becomes nib/mass | acc_curl/spin/knot | Q | ? | 13 | L~ “love love the last one” r13:31 | — |
| M | drive_phi | modulators_drive.py:294 | Driver turns nib angle | DS | phi,drv_phi,drvm_phi;μ | ? | 12 | L~ uncapped “interesting morphological evolutions” r12:38 | — |
| M | drive_width | modulators_drive.py:202 | Driver swells width | DS | dw/W/M,drv_width,drvm_width;μ | ? | 12 | D~ “not a fan” r12:36 | — |
| M | drive_regime | modulators_drive.py:265 | Driver selects wire/nib/mass | DS | r,W,M,drv_regime,drvm_regime;μ | ? | 12 | D~ “not a fan” r12:36 | — |
| M | drive_pen | modulators_drive.py:329 | Driver selects pen runs | DS | pen_i,drv_pen,drvm_pen;μ | ? | 12 | D~ “not a fan” r12:36 | — |
| M | drive_knots | modulators_drive.py:361 | Driver pauses become knots | DS | knot,emphasis,drv_knots,drvm_knots;μ | ? | 12 | D~ “not a fan” r12:36 | — |
| M | drive_tremor | modulators_drive.py:412 | Driver noise displaces line | DS | G,tremor,drv_tremor,drvm_tremor;μ | ? | 12 | D~ “not a fan” r12:36 | — |
| M | wire | modulators_base.py:36 | Forces dry line | marks | r=0 | ? | 9 | not reviewed | s28 |
| M | constant | modulators_base.py:47 | Assigns constant channels | marks | selected Q | ? | 9 | not reviewed | s28 |
| M | field | modulators_base.py:128 | Spatial field selects regime | sheet coordinates | r | ? | 8→9 | not reviewed independently | s28 |
| M | dev_rare_machine | dev_rare.py:87 | Rare event-triggered machine interruptions | line events; handover helper | G,machine;μ | ? | 10 | not reviewed | — |
| M | measure_answer | measure_pairs.py:722 | Second hand answers measured turning | marks,H | G,r=0;μ | ? | 10 | not reviewed: favorable record is paraphrase | — |
| M | measure_next_rehand | measure_next.py:1195 | Re-speaks specimens through changing hands | marks,H | G,voice;μ | ? | 11 | not reviewed | — |
| M | revisit_notate | modulators_revisit.py:174 | Writes body-event sign instructions | dance channels/figures | μ:revisit_events | ? | 12 | not reviewed | — |
| M | lcorp_zoom_mod | modulators_lcorp.py:46 | Zooms existing line along itself | marks | G,zoom;μ | ? | 15 | not reviewed | — |

**Renderers**

All output **I**, without persistent channel changes, Score or ctx.note.

| Kind | Id | File:line | Does | Inputs / calls | Time | Round | Artist verdict | Study |
|---|---|---|---|---|---|---|---|---|
| R | trail_gallery | voices_trails.py:164 | Age-widened mine and terminal chamber | age/geometry; bead helpers | ? | 11 | K leaf miner “super good, keep” r11:20 | s3,12 |
| R | arch_ink | renderers_arch.py:14 | Dispatches wire/nib/swell per mark | metadata; nib,swell | ? | 15 | K~ “all are excellent” r15:8 | arch in flight |
| R | oehlen_found_ink | arrangers_oehlen_found.py:952 | Uses each mark’s pen/colour | metadata | ? | 12 | K~ “absolute gold” r12:8 | s10 |
| R | revisit_nib | renderers_revisit.py:89 | Nib with mark-specific colour | Q; nib | ? | 12 | K~ “super nice. keeper” r12:28 | s14,15 |
| R | nib | renderers_base.py:42 | Broad-nib and mass inking | Q | ? | 6–9 | K~ “save the methods” r9:7 | s1,4,5,8,27,28 |
| R | measure_wire | measure_pairs.py:794 | Finer pen for analytic marks | measure_role | ? | 10 | K~ “keep as is” r10:8 | s6,7,13,16,17,19,20,21,24 |
| R | swell | swell_ink.py:411 | Smoothly grows round line-built masses | emphasis/r; bead helpers | ? | 11 | L bold “very nice, very promising” r11:22 | s2,25 |
| R | swell_dots | swell_ink.py:659 | Rule-placed shape/size vocabulary | geometry/events/emphasis | ? | 11 | L “from time to time” r11:24 | s26 |
| R | dev_beads | dev_beads.py:168 | Round beads at stresses | emphasis/r; optional nib | ? | 10 | L “slightly better” r10:24 | s4 |
| R | oehlen_conduct_ink | renderers_oehlen_conduct.py:29 | Splits passes by width channel | cw | ? | 12 | L~ process “have to explore” r12:18 | — |
| R | stages_ink | arrangers_stages.py:559 | Wets line into nib and pools | Q,pools; bead helpers | ? | 13 | L~ “it's nice” r13:35 | — |
| R | drive_ink | renderers_drive.py:52 | Sweeps width, pens and knots | dw,pen_i,knot/Q; nib | ? | 12 | D~ “not a fan” r12:36 | — |
| R | oehlen_intuit_pens | voices_oehlen_intuit.py:236 | Session-specific pen/colour replay | metadata | ? | 12 | D~ “not great” r12:51 | — |
| R | script_solid_nib | script_solid.py:679 | Solid joined nib with counters | Q,script metadata | ? | 11 | M~ “keep it a separate thing” r11:35 | — |
| R | script_solid_bar | script_solid.py:698 | Carves white script from black slugs | script geometry/rows | ? | 11 | M~ “keep it a separate thing” r11:35 | — |
| R | wire | renderers_base.py:25 | One polyline per mark | geometry | ? | 9 | not reviewed independently | s1,4,5,9,18,23,25,27,28 |
| R | restate | prosody_renderers.py:111 | Rewrites stressed stretches repeatedly | emphasis/r | ? | 9 | not reviewed independently | s4 |
| R | coil | prosody_renderers.py:182 | Offset rings or spiral mass | emphasis/r | ? | 9 | not reviewed independently | — |
| R | revisit_signs | renderers_revisit.py:42 | Materializes recorded signs/junctions | revisit_events; signs helpers | ? | 12 | not reviewed | — |
| R | stages_layer | arrangers_stages.py:591 | Wires event layers | geometry | ? | 13 | not reviewed | — |
| R | rzoom_ink | renderers_rzoom.py:50 | Width/colour by zoom bands | zoom | ? | 14 | not reviewed independently; constant width requested r14:26 | — |
| R | cproc_ink | arrangers_cproc.py:1149 | Metadata pens plus optional nib | metadata,Q; nib | ? | 14 | not reviewed independently | — |
| R | lcorp_ink | renderers_lcorp.py:17 | Constant-width source/part colours | voice/part | ? | 15 | not reviewed | — |
| R | meas_ink | renderers_meas.py:9 | Named ink at constant width | geometry | ? | 15 | not reviewed | — |

**Arrangers**

Composer input abbreviations: **C** = `found_play,hand,oehlen_found_river,diagram,machine,belt,gmorph,passage,morph_handover,mutual,accrue_walk,river_loops`. **P** = `hand,trail_sheet,diagram,morph_handover,mutual,revisit_glyph,passage,belt,oehlen_found_river,river_braid,river_loops`, plus accrue helpers. **J** = `hand,belt,gmorph,passage,morph_handover,oehlen_found_river,diagram,river_braid,river_loops,river_zoom,revisit_glyph`. **G** = cgram’s recipe players at `arrangers_cgram.py:78`: H-based voices plus `cgram_free,passage,gmorph,belt,revisit_glyph,river_loops,mutual,morph_handover,diagram,oehlen_found_river`.

| Kind | Id | File:line | Does | Inputs / calls | Outputs | Time | Round | Artist verdict | Study |
|---|---|---|---|---|---|---|---|---|---|
| A | arch | arrangers_arch.py:619 | Revives keeps in new compositional roles | C;drift,timing,prosody,revisit_glyph | G,Q,neg,bold,src_core;μ,S | ? | 15 | K “amazing keep this” r15:8 | arch in flight |
| A | listen | arrangers_listen.py:1059 | Composes explicit listening relations | H,RS;hand,river_zoom | G;μ,S | ? | 15 | K “keep note … techniques” r15:10 | — |
| A | ccolour | arrangers_ccolour.py:698 | Composes through pen ownership/lending | C | G,neg,bold;μ | ? | 14 | K “weird yet cohesive and elegant” r14:9 | — |
| A | oehlen_found | arrangers_oehlen_found.py:651 | Pastes, negotiates, covers, crosses | parts | G,neg;μ | ? | 12 | K “absolute gold” r12:8 | s10 |
| A | rules | arrangers_rules.py:596 | Breakable ground/weight/exit rules | parts | G,neg,bold;μ | ? | 13 | K “keeper” r13:9 | — |
| A | dev_chorus | dev_chorus.py:54 | Multiple answering voices/pens | parts;answer_mark | G,emphasis,r,W,M;μ | ? | 10 | K “absolutely love … keep” r11:14 | s4,25 |
| A | poly_page | poly_sheets.py:562 | Rows, glosses and annotation | parts | G;μ | ? | 9 | K~ P2 kept; no direct quote r9:23 | s1 |
| A | series_row | arrangers_series.py:71 | Hands travelling-line stretches to parts | parts;series_stretch | G,age;μ | ? | 12 | K~ “amazing” r12:25 | — |
| A | contagion | arrangers_contagion.py:619 | Contact carries another grammar away | parts;river/chart helpers | G,catch;μ | ? | 13 | L “I like it a lot” r13:15 | — |
| A | call_response | prosody_arrangers.py:106 | Stresses answer preceding silence | parts;prosody helpers | emphasis,r,W,M;μ | ? | 9 | L “mixing it up” r9:22 | — |
| A | poly_converse | poly_converse.py:118 | Previous unit determines next reply | parts;hand probes | G,Q;μ | ? | 9 | L “can be developed further” r9:24 | s5 |
| A | stages_row | arrangers_stages.py:478 | Event layers change travelling line | stages_line,parts,H/RS | G,Q,src,series_u;μ | ? | 13 | L “I like this one” r13:35 | — |
| A | lcorp_lens | arrangers_lcorp.py:119 | Spatial field opens neighbouring lines | parts;lcorp helpers,lcorp_aware | G,zoom,u_src,voice;S | ? | 15 | L “i like this haha” r15:21 | — |
| A | cproc | arrangers_cproc.py:1133 | Plans and executes composition acts | P | G;μ:private score/log | F–S | 14 | L “like the direction” r14:16 | — |
| A | cimpro | arrangers_cimpro.py:589 | Perceives sheet, chooses next move | J | G;μ | ? | 14 | M “jumbled mess”; composition liked r14:21 | — |
| A | cgram | arrangers_cgram.py:1187 | Executes compositional grammar sentences | G | G;μ | ? | 14 | M general; K uniform “maybe keep” r14:25 | — |
| A | found_play | arrangers_found_play.py:198 | Rules, contagion and answering combined | parts,H;rules/contagion helpers | G,neg,bold;μ | ? | 13 phase 2 | M~ “more dynamic though” p13:40 | — |
| A | drive_beside | arrangers_drive.py:120 | Straightens drawing beside driver traces | parts,drive metadata | G,driver channels;μ | ? | 12 | D~ “not a fan” r12:36 | — |
| A | script_solid_page | script_solid.py:747 | Writes beside/around drawing | parts;script_solid helper | G,phi;μ | ? | 11 | M~ “separate thing” r11:35 | — |
| A | script_solid_stack | script_solid.py:814 | Stacks authored script bands | parts | G;μ | ? | 11 | M~ “separate thing” r11:35 | — |
| A | single | arrangers_base.py:19 | Overlays parts in same box | parts | G | ? | 9 | not reviewed independently | s2,3,6–9,12–21,24,26–28 |
| A | grid | arrangers_base.py:42 | Cells with common physical scale | parts | G | ? | 9 | not reviewed independently | s23 |
| A | poly_scatter | poly_sheets.py:453 | Scatters independent units/annotations | parts | G;μ | ? | 9 | not reviewed: “potential” is paraphrase r9:23 | — |
| A | swell_place | swell_ink.py:753 | Places parts in authored boxes | parts | G | ? | 11 | not reviewed | — |
| A | trail_specimen | voices_trails.py:260 | Common-scale specimen grid/bar | grid | G;μ | ? | 11 | not reviewed independently | — |
| A | meas_boxes | arrangers_meas.py:54 | Places boxes, measures cross/near | parts | G;S | ? | 15 | not reviewed independently | — |

**Devices**

Every device outputs **I**, writes **no channels, Score or ctx.note**, and belongs to **round 15**. None occurs in the original 28 study recipes.

| Kind | Id | File:line | Does | Inputs | Time | Artist verdict |
|---|---|---|---|---|---|---|
| D | meas_ledger | devices_meas_ledger.py:22 | Process/source/ink-length ledger | ordered marks,provenance; optional H redraw | ? | K “spectacular” r15:16 |
| D | meas_arcs | devices_meas_arcs.py:61 | Diagrams relations or their sites | Score/log-derived score,layer marks | ? | K “spectacular” r15:16 |
| D | meas_inventory | devices_meas_inventory.py:20 | Common-scale numbered process atlas | ordered source units | ? | K~ “amazing” r15:17 |
| D | meas_air | devices_meas_air.py:35 | Draws ordered pen-up flights | ink/line/step endpoints | ? | K~ “amazing”; optional r15:17–19 |
| D | scale_ruler | devices_measg1.py:55 | Measures true projected millimetres | drawing/region bounds | ? | K~ “love love love this” r15:17 |
| D | density_isoline | devices_measg1.py:238 | Contours blurred ink coverage | finished inks and widths | ? | K~ “love love love this” r15:17 |
| D | heading_rose | devices_measg1.py:267 | Length-weighted axial heading histogram | mark segments | ? | K~ “love love love this” r15:17 |
| D | arc_ticks | devices_measg2.py:119 | Ticks cumulative plotted distance | ink arclength,clearance | ? | K~ “great” r15:18 |
| D | survey_marks | devices_measg2.py:193 | Bounds, centroid, principal axis | length-weighted ink geometry | ? | K~ “great” r15:18 |
| D | misfit_grid | devices_measg2.py:371 | Density gradient displaces grid | finished ink density/clearance | ? | K~ “it's fun. keep” r15:18 |
| D | meas_stations | devices_meas_stations.py:55 | Source-clock ticks/variable scale bar | u_km/dance_t,optional zoom | ? | not reviewed separately |
| D | meas_turning | devices_meas_turning.py:39 | Accumulated-turning comparison fan | mark curvature/arclength | ? | not reviewed separately |
| D | meas_roll | devices_meas_roll.py:36 | Drawn-length roll grouped by source | ordered source units | ? | not reviewed separately |

**2. Families and candidate common controls**

Membership overlaps where a technique serves two roles. Keepers retain the qualifications above.

| # | Family / members | Keepers | Shared controls |
|---|---|---|---|
| F1 | Grammar lines: hand,drift,drift_tokens,belt,gmorph,morph_handover,passage,accrue_walk,cgram_free,measure_next_duet; lcorp_zoom/mod/style | drift,morph_handover | source(s),seed,length,feature ownership,schedule,scale,joining |
| F2 | Found paths: dance,river_loops/braid/zoom/approach,oehlen_found_river,trail_sheet/brood | dance,river_zoom,found river recipe | source/window,effector,zoom,detail,branch count,spacing |
| F3 | Structured/session voices: series_travel/stretch,stages_line,oehlen_conduct/tree/ensemble,oehlen_intuit_sheet,script_solid,machine | series method | duration,route,rows/sheets,cues,players,blank,pen vocabulary |
| F4 | Regime channels: wire,constant,field,timing,own_tempo,prosody,handover,dev_rare_machine,drive_*,accrue_ink,revisit_notate | danced timing recipe | thresholds,gain,smoothing,event spacing,width,angle,minimum run |
| F5 | Inking: **all renderer rows** | nib/measurement/found/revisit recipes;trail_gallery | physical pen,width/mass,stress threshold,fill spacing,colour,roundness |
| F6 | Placement: single,grid,poly_scatter/page,trail_specimen,swell_place,script_solid_page/stack,series_row,stages_row,meas_boxes | poly_page,series_row | boxes,common scale,gaps,rows,margins,cropping |
| F7 | Conversation/awareness: call_response,dev_chorus,poly_converse,mutual,lcorp_aware,revisit_glyph | chorus,revisit | listener/source,radius,delay,answer/refusal probability,depth,gap,sympathy gain |
| F8 | Ground negotiation: oehlen_found,rules,contagion,found_play | oehlen_found,rules | contact reach,ride/carry length,weight,break permissions,covers,history window |
| F9 | Composers: cproc,cimpro,cgram,ccolour,arch,listen,lcorp_lens | ccolour,arch,listen | frame,density,acts/order,source pool,scale ladder,blank,palette,relation budget |
| F10 | Analytic companions: diagram,annotate,measure_pair/shadow/atlas/answer/next/rechain/rehand,drive_beside; seven meas_* devices | pair/shadow/next;ledger/arcs/inventory/air | cut law,ordering,normalisation,layout,indexing,source colour,placement |
| F11 | General measurement: scale_ruler,density_isoline,heading_rose,arc_ticks,survey_marks,misfit_grid | praised general-device sheets | region,physical interval,bins,blur,clearance,strength,labels |

**3. Relations already implemented**

Locations below identify operations, including implicit and derivative relationships. **Y** = persisted `_score.Score`; **N** = geometry/channels/private logs only.

| # | Kind; implementation locations | Reads from other material → response | Score |
|---|---|---|---|
| R1 | grow/ride/ignore: arrangers_oehlen_found.py:174,222,236,279,776,923 | Ground points,tangents,ends → entry,offset ride,bridge,release | N |
| R2 | cover/cut/tint/cross: arrangers_oehlen_found.py:459,797,852,866,900 | Existing ink,late path,cover polygons → targeted terminations,masked/tinted pieces,late crossings | N |
| R3 | R4 listen/ride: arrangers_rules.py:138 | Found curvature,tangents,proximity → aligned riding or straight-line exception | N |
| R4 | R3 entry;R2 become/exit: arrangers_rules.py:252,343,372 | Found endpoint and signed turning → origin,continuation,amplified exit motif | N |
| R5 | R1 weight;R5 cover: arrangers_rules.py:490,455,535,729 | Ground regions,ride duration,density → bold/hair weight,carry,cover position | N |
| R6 | catch/contagion/shed: arrangers_contagion.py:71,118,293,418,444,482,532,667,713 | Contact plus river/chart grammar → carried bends,ticks,ruled runs,immunity,release | N |
| R7 | answer/refuse: arrangers_found_play.py:389,448,453 | Recent line’s endpoint,tangent,tail → joining answer or declined call | N |
| R8 | catch another hand/ignore: arrangers_found_play.py:455,473,495,502 | Earlier line’s geometry,named hand,scale → fresh carried grammar; unheeded crossings logged | N |
| R9 | chart translation: arrangers_found_play.py:68,100 | Chart needles’ heights,widths,spacing → carried chart vocabulary | N |
| R10 | borrow/reverse/contact/spill/refuse: arrangers_ccolour.py:478,539,586 | Ride/carry/answer tags,infections,nearest object,container → borrowed/reversed/stained pen runs | N |
| R11 | answer: arrangers_arch.py:309,329,562 | First swell’s spatial emphasis → second swell stresses its silence | Y |
| R12 | contain/translate: arrangers_arch.py:342,354,386,573,576 | Container depth and selected core hand/pen → passer changes grammar/ink | Y |
| R13 | surface: arrangers_arch.py:439,584 | Host geometry and surrounding crowding → limb figure surfaces in clear stretch | Y |
| R14 | cross/intrude/ride/echo/contact/spill: arrangers_arch.py:519,556,586,605 | Planned acts and colour-event logs → structural relation interpretation | Y, partial |
| R15 | imitate/exaggerate/translate: arrangers_listen.py:462,489,561 | Source gesture,listener grammar,occupancy → spliced responding passage | Y |
| R16 | refuse: arrangers_listen.py:565,594,982 | Source halo → boundary detour or endpoint truncation | Y detours; truncation unrecorded |
| R17 | echo/calm/nest/bind: arrangers_listen.py:599,631,636,651,656,695,699,724 | Gesture,crook,endpoints → decaying copies,flattening,nesting,ligature | Y |
| R18 | mask/ignore: arrangers_listen.py:728,829,865,867 | Multi-layer overlap and polygon/order → selective cutting/crossing | Y |
| R19 | weave/yield: arrangers_listen.py:869,905 | Pairwise intersections,over-line width → alternating or later-line gaps | Y, aggregated per pair |
| R20 | sympathy/depth: modulators_lcorp.py:149,177,218,276 | Other pass’s wiggle,geometry,zoom → sympathetic displacement or farther-pass cuts | N standalone |
| R21 | exaggerate/mask/intermingle: arrangers_lcorp.py:139,194,203,207,210 | Spatial field and other passes → opening,depth,sympathy | Y; counterpart incomplete |
| R22 | ride/catch/wet/cross: arrangers_stages.py:174,212,327,458 | Event-layer geometry,curvature,hand,nib → source takeover,width/angle change | N |
| R23 | answer/suppress: prosody_arrangers.py:47,119; dev_chorus.py:69 | Previous/all previous emphasis in space or shared time → reselected stresses | N |
| R24 | call/answer/ride/wrap/refuse/ignore/wake/lift: voices_mutual.py:142,153,431,553,708,788,858,919,955 | Stop/turn/arrival/burst events and paper geometry → four regimes’ responses | N |
| R25 | negotiate/catch: arrangers_cgram.py:402,439 | Existing ground,named players,grammar statistics → responding line | N |
| R26 | reserve/contain/spill/cover/cross/answer/trail: arrangers_cgram.py:283,627,662,702,717,799,823,849,887,921 | Existing regions,ink,endpoints → displaced/clipped placements and continuations | N |
| R27 | stop/contaminate/zoom/repeat/counter/intrude: arrangers_cgram.py:1001,1023,1070,1095,1117,1135 | Other ink,earlier segment/move/core → stopping,borrowing,scaled rhyme,opposition | N |
| R28 | perceive/decide: arrangers_cimpro.py:241,377 | All existing geometry/widths → density,core,blank,balance,next move | N |
| R29 | catch/answer/weight: arrangers_cimpro.py:475,676 | Found matter,last two hands,ride codes → carried grammar/weight,calls | N |
| R30 | thicken/traverse/intrude/counter/cover/cross/answer/trail/reserve: arrangers_cimpro.py:803,907,936,957,1016,1053,1087,1106,1122,1225 | Perceived cores,blanks,calls,covers → next intervention | N |
| R31 | catch/negotiate/answer: arrangers_cproc.py:543,692,714 | Found/made geometry,last unlike hands,end tangents → borrowed grammar/reply | N |
| R32 | place/traverse/trail/reink/intrude/cover/cross: arrangers_cproc.py:509,898,950,968,1017,1078 | Existing ink,patches,planned cores/blanks → subsequent acts | N; private `Score` |
| R33 | echo/contrast/continue/avoid: poly_converse.py:159,218 | Previous hand,busyness,weight,end/tangent,occupied boxes → next unit | N |
| R34 | underline/bracket/encircle/point/echo/tether: poly_sheets.py:289,407 | Target bounds,path,endpoints,nearest other voice → warped annotation route | N |
| R35 | avoid/gloss: poly_sheets.py:469,650 | Earlier boxes/body rows → scatter/gloss eligibility | N |
| R36 | meet/junction: modulators_revisit.py:134; renderers_revisit.py:19,49 | Other effector position/time and mark/arclength → meeting signs/junction masses | N |
| R37 | learned attach/branch;brood: voices_trails.py:45,109 | Prior topology or mother tangent/position → joins,larval orientation/length | N |
| R38 | source-part translation: voices_machine.py:400; voices_machine_diagram.py:579 | Another part’s **seed**, regenerated source → machine/chart; not actual-layer reading | N |
| R39 | retrace: voices_oehlen_conduct.py:550,728 | Primary line and widths → drifting split/rejoined second pass | N |
| R40 | common scale/bands: arrangers_base.py:48; renderers_rzoom.py:60 | All bounds/max zoom → shared grid scale/inking thresholds | N |
| R41 | measure/shadow/atlas/answer: measure_pairs.py:433,631,681,737; voices_machine_diagram.py:615 | Input curvature,events,shape → derivative analytic/answer layers | N |
| R42 | specimen/rechain/rehand: measure_next.py:1041,1173,1204 | Input cuts/specimens/channels → reordered or re-spoken drawing | N |
| R43 | driver pairing: arrangers_drive.py:60,135 | Input geometry and recorded signals → straightened line/trace companion | N |
| R44 | wrap/avoid: script_solid.py:334,351,747 | Drawing obstacle geometry → available writing intervals | N |
| R45 | stretch/reassign: arrangers_series.py:79,85,92 | Part-zero geometry/channels → later parts’ stretches | N |
| R46 | measured cross/near: arrangers_meas.py:27,46,51 | Finished part intersections/distances → observational relations | Y |
| R47 | relay handover: voices_lcorp.py:541,549 | Voice-channel transitions → virtual hand-layer succession | Y |
| R48 | measurement devices: _devices.py:120; device rows above | Finished marks/inks/process/Score → separate readings | N; preserve incoming Score |

Internal source dependencies also include `revisit_glyph` reading other limbs (`voices_revisit.py:123,137`), braided neighbouring gaps (`voices_rivers.py:338,362`), and duet placement from the first line’s bounds (`measure_next.py:1283`). Passage’s recall reads **its own past**, rather than another layer (`voices_passage.py:394`).

**4. Gaps and overlaps**

1. **Repeated mechanisms:** `hand/drift/drift_tokens` share growth; `belt/gmorph/morph_handover/passage/accrue` offer different ways to change gesture type. `river_zoom/lcorp_zoom/lcorp_zoom_mod/lcorp_lens` overlap in scaling. Measurement exists as diagram voices, append-and-refit modulators, and finished-sheet devices. Numerous wire/colour renderers differ mainly in metadata conventions.
2. **Whole-sheet ownership:** `mutual`, all four round-14 composers, `arch`, `listen`, series/stages and script pages own order, frame, blank or evolving paper state. They are not interchangeable parts. `belt` measures through an authored `read_box` (`voices_belt.py:84`); zoom variants refit results; `mutual` additionally reads `.local` quake files (`voices_mutual.py:68,512`).
3. **Score coverage is observational and incomplete.** Only five files persist relations. `_score.py:41` appends dictionaries, not executable operations. Arch collapses carry/reverse into ride and answer into echo (`arrangers_arch.py:605`), omitting underlying found-play events. Standalone awareness discards its log; lens records rule→line without the actual counterpart.
4. **Identity/order remain incompatible:** part, mark, line, object and virtual Score layer differ. Nested score writers overwrite the shared `"score"` note (`core.py:662`). Recent-line eligibility, event clocks, density decisions and masks require ordered history, not merely pairwise edges.
5. **Keep the distinctions:** `handover` is machine interruption; `morph_handover` exchanges source features. A lead-labelled “dud” is not an artist rejection: crowded rules, mutual soup, accrue runaway and uniform cgram were liked.

**5. Composition-relevant numbers**

| # | Recorded quantity | Source under `tools/gesture/results/` |
|---|---|---|
| N1 | Measurement pairs: **<1s/sheet** machine; **20–37s** hand-redrawn. Input example **1555mm,28 specimens** | measure_pairs-2026-10-17.md:44,58 |
| N2 | Next-measurement sheets: **<1s** normally; **10–31s** straight rules; **49–118s** fully redrawn | measure_next-2026-10-17.md:131 |
| N3 | Machine/diagram sheets **0.2–1.5s**; hand κ chart **~5s**; atlas+ledger **~60s** | voices_machine-2026-10-17.md:74 |
| N4 | cproc **0.6–19s/sheet** | cproc-2026-10-18.md:17 |
| N5 | Arch **2–6 made lines**; ccolour **1–12 made lines**, excluding other roles | arch-2026-10-19.md:16; ccolour-2026-10-18.md:14 |
| N6 | Listen,40 seeds: **3.7–9.7mm ink/cm²**; representative **6.8**, versus **15–18** comparison sheets | listen-2026-10-19.md:7,126 |
| N7 | River zoom: **one continuous line,1.3–2.4m**; example **1.56m** | rzoom-2026-10-18.md:11,32 |
| N8 | Found-ground late line **1374mm,6 rides,11% riding**; contagion example **1495mm** | oehlen_found-2026-10-17.md:73; contagion-2026-10-18.md:40 |
| N9 | Metamorphosis **one ~5.4m line across seven A5 sheets**; stages uses five sheets | series-2026-10-17.md:62; round13-2026-10-18.md:29 |
| N10 | Merged-shadow variants use **54.5–84.4%** of unmerged ink; contour device **51 paths**; arc ticks **92/92 retained** over **1479.2868mm input ink** | measure_pairs-2026-10-17.md:46; measg1-2026-10-19.md:5; measg2-2026-10-19.md:15 |

These timings describe recorded **sheet variants**, not intrinsic module benchmarks; no generation-time estimate has been inferred for the `?` entries.
