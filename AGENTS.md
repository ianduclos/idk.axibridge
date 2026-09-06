# AGENTS.md

**Read `CLAUDE.md` at this root — it is the single authoritative operating
context for this repo** (run/test commands, invariants, where things live,
hardware notes). This file is deliberately a pointer, not a copy: a copy
drifts, and a stale invariant is worse than none (this file once claimed the
frontend had no build step months after it got one).

Also load-bearing before structural changes: `ARCHITECTURE.md` (design
rationale, resolve order, caching) and `docs/MODULES.md` (module authoring).
Current state lives in `STATUS.md`; mid-flight work in `HANDOFF.md`.

## Agent protocol

- The primary agent keeps the driver's seat: owns direction, artistic judgement,
  architecture, shared contracts, integration and final acceptance.
- Use **Sol or Terra for bounded, low-stakes coding and mechanical support**
  when there is useful independent work. Give each agent explicit file ownership,
  deliverables and limits; avoid concurrent changes to the same contract or file.
- Keep the team small (at most three supporting agents). Do not launch agents
  merely to fill slots; do not delegate the central design decision by default.
  Supporting agents must not delegate further without an explicit assignment.
- For aesthetic drawing reviews, use a bounded **Sol** second eye through
  `.agents/skills/drawing-review/SKILL.md`. Review whole iteration populations,
  close views and recorded exchanges, including weak and ambiguous cases.
- Calibrate reviewers with neutral labels and altered variants before revealing
  mechanisms and prior preferences. Separate visible evidence from attribution;
  judge the reasoning, not agreement with the lead. No beauty scores.
- The primary inspects results, retains meaningful disagreements, verifies the
  integrated work and remains responsible for what is delivered. Agent reports
  are evidence, not automatic approval.
