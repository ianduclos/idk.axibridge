# Meander 3, advice after round 1 (Fable, 29 September 2026)

## 1. Decoding the review

- **v6 vs new.** R05, R12 are v6 (seeds 10, 22). R03 is seed 22 at accents 0, bridges 0; R15 at defaults. R03 ties R12; R15 ranks below both: CP1 (χ, calm hand, pre-smooth) costs nothing on the target seed; accents + bridges are what R15 added, and they lost. **Do not trigger the round kill; keep CP1.**
- **Frays are the tangle zone.** Zones measure 59–114 mm at defaults (seeds 10, 16, 24, 40), mostly two per sheet, up to 8 strands revived. Seeds 22, 3, 7 (R03/12/15, R07, R13) have no zone: the cells called "closest to the target". Search patches (2–3, 2–6 passes) add the same texture.
- **"Arcs at every bend" is mostly the band.** Seed 7 (R13) has 0 accents; R03 and R12 have none, yet the reviewer sees "4 leaning arcs" there. Those are M2 strands (K up to 8 at ~0.9 mm): the calm hand exposed the band as ruled parallels. Accents (1–2 per sheet, 3–5 members) add to it.
- **"Second river runs beside"** (R13, R11, R07, R17 = seeds 7, 40, 3, 31): all single-trunk. The "river" is the S0 = 4 banded minor that never touches the trunk. Trunk 2 fired only in R08 and R09/R18; R09 is "the most integrated". Firing at 0.5: 8/40, the low edge of the target.
- **Beans.** R11 (seed 40) has no bridges: the egg is a 99 mm minor, ends 68 mm apart, pre-smoothed into a drafted oval. R13's ovals: 150–170 mm chains, 53–61 mm gaps. R05 is v6: the pear is what Ian said "comes close", not a defect.
- **Sameness.** Seed 10: `fillet13e1, fillet13e1`. Hooks fire on every k = 0 cut end at one curvature.

## 2. Changes for round 2, ranked

- **F1 — one small knot.** `tg.left` 2 → 1. Zone half-length `(18 + 30u + 20A)` → `(10 + 12u + 6A)` mm (25–55 mm full). Keep it ≥ 25 mm from either terminal, else drop it. Revive only `k < 4`. Per-zone `lam` 8–30 mm. Long-tangle mode unchanged; it is the one zone.
- **F2 — strand cap outside χ.** `K = min(K, χ < 0.5 ? 5 : 8)`. Leave `steady` at 0.45: the calm line is still a hand.
- **F3 — bridges: one stroke, one or two places, none into the chaos.** `nB = round(bd·(1 + 2u))` (1–2 at 0.5). χ exclusion 0.7 → 0.4. Within 40 mm of a chosen bridge: dead, not rarity 0.3. Second bridge differs in kind. Continuations ≤ 35 mm (seed 19 made 59). Echoes: p 0.65 → 0.3, ≤ 1 per bridge, ≤ 2 per sheet.
- **F4 — accents 3–4 members, only by the chaos.** `cnt = 3 + floor(2u)`; drop pass 2 (the "far" site); hard cap 2 per sheet.
- **F5 — the band must meet the trunk.** In the M2 `ms` selection, S0 = 4 only when `near(c.present, trunk.present, 6) > 0`, else 1.4. Trunk 2: `smooth(0.3, 0.9)` → `smooth(0.25, 0.85)` (~0.38 at 0.5); `crossAt` inside the middle 60 % of the sheet, else retry.
- **F6 — beans.** Bean test: host arms 15 → 40 mm, area 30–400 → 30–1200 mm². Pre-smooth `smoothPts(P, 14)` → 6 passes (σ ≈ 5 → 3.5 mm), so a near-closed minor keeps its wander. Leave seed 10's pear alone.
- **F7 — search.** `want` 1–2 spots, passes ≤ 4, `halfMm` clamp 6–25.
- **F8 — hooks.** p 0.5 on k = 0 cut ends, spacing 25 → 45 mm, curvature 0.35 → 0.2 + 0.25u, none on history traces.

## 3. Keep unchanged

χ field and centring, calm-hand blend, pre-smooth (existence), search gating and share cap; accent construction (gap set, lean, broken outer arc); bridge construction (Hermite, hand, corridor, before history); trunk-2 geometry, sprouts, neck rule; stream numbers; dials at 0.5. Re-shoot the same 18 cells and recipes so pairs compare like with like; add closes of seeds 7 and 40.

Smoke acceptance: zone `mm` 25–55, ≤ 1 per sheet; bridges ≤ 2, distinct kinds; banded minors touch the trunk 40/40; seeds 22 and 10 keep junction and pear.
