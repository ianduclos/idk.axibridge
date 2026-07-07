---
name: wrapup
description: End-of-session wrap-up for axibridge — verify the suite, settle docs/roadmap/memory debt, and commit in the house style. Use when the user says "wrap up", "/wrapup", or asks to close out the session.
---

# Wrap up an axibridge session

Work through these in order; stop and report instead of committing if any
verification fails.

## 1. Verify

- `.venv/bin/python -m pytest -q` — the hardware-free suite must be all
  green. Never "fix" a failure by switching interpreters; `.venv` is pinned.
- If the session touched `axibridge/static/**`, do a quick Playwright smoke
  against a throwaway server (`AXIBRIDGE_CONFIG_DIR=/tmp/... AXIBRIDGE_NO_AUTOCONNECT=1`,
  spare port). Use `wait_until="domcontentloaded"` — the SSE stream keeps
  `networkidle` from ever firing. Kill the server afterwards.

## 2. Sweep the tree

- `git status` — no stray logs, tmp files, screenshots, or `__pycache__`.
- Never stage `.Codex/settings.local.json` (personal allowlist; ignored).
- New files under `sources/` `effects/` `transforms/` must be drop-in
  complete: registered via decorator, every numeric param bounded.

## 3. Settle documentation debt

- `ROADMAP.md`: mark items the session shipped (keep the reasoning, note the
  date); record anything deliberately deferred *with the why*; add new user
  wishes verbatim enough to act on later.
- `docs/MODULES.md`: new module-authoring affordances (schema tags, helpers,
  progress hooks).
- `AGENTS.md`: only durable invariants and run/debug facts — not session
  history.

## 4. Memory

Persist to auto-memory only what the repo cannot tell a future session:
user preferences and corrections, hardware quirks, "why" behind decisions,
view/orientation gotchas. Update existing memory files over creating
near-duplicates; keep `MEMORY.md` index lines one per file.

## 5. Commit

One commit per session unless the work is clearly separable.

- Subject: lowercase, comma-separated feature list; optional `subsystem:`
  prefix (see `git log` for tone).
- Body: short bullets — what changed, why, and how it was verified.
- Trailer: `Co-Authored-By: Codex Fable 5 <noreply@anthropic.com>`
- Commit with the user's identity: `git -c user.name='Ian Duclos' -c user.email=ianduclos@gmail.com commit ...`

## 6. Report

End with: what shipped, what was deferred (and where it's recorded), any
loose ends with their location. Don't invent follow-ups; only mention ones
with a concrete artifact behind them.
