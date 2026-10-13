# MCP server + live sync — review record (2026-10-12/13)

Preserved from the subagent-driven execution ledger (gitignored scratch, deleted after this copy).
Spec: `docs/superpowers/specs/2026-10-12-mcp-server-design.md` · Plan: `docs/superpowers/plans/2026-10-12-mcp-server.md` · Usage: `docs/MCP.md`.

Merged to main as `069e11b`; full suite on the merged result: 1,954 passed.

## Parked for Ian (first follow-ups)

1. focus deferral latches on focus alone (focusin clears fieldCommitted; a focused field blocks sync until blur, docs say "uncommitted edit")
2. call_api can PUT /api/settings host/port on live (rewrites next launch's bind)

## Rulings made during execution

1. move test_client_id_does_not_need_a_secure_context from Task 1 to Task 2 (append it to tests/test_live_sync.py there) — global rule "never commit broken state" beats the plan's leave-it-failing note — cost if wrong: none, same test lands one commit later.
2. fix both plan-mandated Importants now, plus Minor 1 (ApiClient: catch httpx.TransportError + non-JSON 2xx → ToolError) — spec: sandbox must be isolated, every failure readable; later tasks all route through Targets — cost if wrong: small extra code in the foundation
3. Task 4 note text '{i}: error — {e[:300]}' instead of brief's '{i}: {e}' — brief's own test asserts '2: error' in text (captions live in the image) — cost if wrong: none
4. Task 5 review Minor 3 (unchecked layer_id in paths) elevated to Important — "../plot/start?" as a layer_id turns an unprompted tool's request into POST /api/plot/start, breaking the spec's motion-only-through-prompted-tools rule; fix centrally in ApiClient.request (refuse paths containing '..', '?', '#', '\\', or percent-escapes; query goes via params) — cost if wrong: a legit id containing those chars is refused (axibridge ids are hex)
5. fix both (read edit_rev before and after the plan, refuse if moved; suggested call names plot_target) plus docstring accuracy (jog is a pen-up move; go_home goes to the design origin 0,0, not necessarily the physical home corner, and pi_ssh has no goto) and unused import — spec guarantee "what gets plotted is what was previewed" — cost if wrong: none
6. Task 7 seeding adapted to the locked Sandbox (start(timeout, seed, seed_root) seeds under Sandbox._lock) — brief predated Task 3 fix — cost if wrong: none
7. fix both + Minor 1 (repo check uses cwd OR command, path-component match), Minor 2 (frontend staleness ignores dotfiles/editor temp files), Minor 4 (fresh-start seed failure stops the sandbox; KeyError on projects_root handled) — false stale warnings on every session would erode trust in the warning; all small — cost if wrong: none
8. Task 8 normalize() splits query/fragment by hand, not urlsplit — urlsplit parses '//api/machine/jog' as host+path, refused only by accident — cost if wrong: none
9. block non-GET /api/limits on live in call_api (soft-limit widening silently weakens later approved motion) and handle malformed-JSON bodies as ToolError — reviewer Minor 1/2; /api/connect + backend/select left allowed (pyaxidraw connect only raises the pen: safe direction; settings PUT too broad to block) — cost if wrong: an agent can't adjust limits on live without Ian doing it in the UI
10. Task 11 literal scan treats whole {placeholders} as path parts (brief's regex broke on f"/api/layers/{layer['id']}") — cost if wrong: none
11. revise Task 8 ruling — refuse non-GET /api/settings whose body contains projects_root on both targets (reviewer's point holds: the key specifically breaks sandbox isolation) — cost if wrong: an agent can't move the projects root, Ian does it in the UI
12. park, surface to Ian as first follow-up (fix: only `input` marks dirty) — no second fix wave per process; cost if wrong: Ian's window stays stale while a field has focus during MCP co-creation
13. park, surface — cost if wrong: an agent could misconfigure the next app launch
14. keep this workspace until wrapup copies parked follow-ups into HANDOFF.md (skill says delete after final review; deleting now would drop the deferred-minor list) — cost if wrong: a gitignored folder lingers

## Deferred minor findings (triaged by the final review as leave-for-now unless fixed in the fix wave)

- Task 1: minor (deferred): middleware misses event when handler raises unhandled after checkpoint (app.py:70-73) — try/finally would announce
- Task 1: minor (deferred): live-sync tests monkeypatch bus.emit; real SSE path untested
- Task 1: minor (deferred): test_reads_and_refused_requests doesn't assert 409/404 status codes
- Task 2: minor (deferred): pointerHeld can stick true if pointerup never arrives (native context menu, drag out of window) — clear on blur/contextmenu; FINAL REVIEW: consider fixing, it silently stalls live sync
- Task 2: minor (deferred): secure-context test is a source grep; "Review Focus 1" comment lacks context
- Task 2: minor (deferred): long mutations (generate) defer external refreshes for their duration (acceptable per spec)
- Task 3: minor (deferred): state fetches full /api/state + resolved stats (heavy); decorator would break async tools (note "tools must be sync"); warning held back when a tool raises; harness leaks temp dirs/process on failure paths; unknown-target test asserts only is_error; _free_port TOCTOU
- Task 3: minor (deferred): a slow sandbox start (≤45 s) holds Targets._lock and blocks concurrent live calls
- Task 4: minor (deferred): see() silently drops unknown layer_ids (typo → blank "0 layers")
- Task 4: minor (deferred): try_effects with bad layer_id returns success of all-error tiles — raise when all fail; layer_id not URL-quoted
- Task 4: minor (deferred): filled paths drawn as outlines; captions clipped; F541 f-string in test_mcp_look; joint="curve" on huge polylines unbenchmarked
- Task 5: minor (deferred): edit_layer params+patch = two undo steps, partial apply on PATCH failure, undocumented; _history loses done-count on unexpected error; save_project reports no name/folder; project status fails if /api/recovery fails
- Task 5: minor (deferred): ids containing '/' can still reach sibling routes under the same prefix (no dangerous endpoint reachable); a per-id segment regex would close it
- Task 6: minor (deferred): suggested call quotes target without escaping
- Task 7: minor (deferred): diagnose(target=sandbox) boots the sandbox; logs test lacks positive-match assertion; stale check globs under Targets lock (cost unmeasured)
- Task 7: minor (deferred): is_here uses substring on command (a foreign server mentioning the repo path passes); reset stops a running sandbox before validating the seed name; swallowed stale-check errors leave no log trace
- Task 8: minor (deferred): no test pins that the normalised path is what's sent; case/';' spellings 404 today but lack regression tests; %-encoded legit paths (asset names with spaces) unreachable via call_api (fails closed) — document
- Task 8: minor (deferred): no test for malformed-JSON fallback
- Task 9: minor (deferred): goto/boot/tab-click PwErrors unwrapped (raw multi-line); steps list unbounded (cap ~20); ms ignored for non-wait steps; empty selector not validated; thin tests (unknown-tab passes for any error; fill/press/wait uncovered)
- Task 10: minor (deferred): MCP.md plot bullet reads as fragment; call_api calibration-on-both-targets wording ambiguous; control chars not listed; wiring test parses "running at " string
- Task 11: minor (deferred): tautological first assert in test_the_mcp_notices (plan-mandated); no test of once-per-change wrapper; unused os/tmp_path; /api/pens* skip broad; self-check re-globs per call
