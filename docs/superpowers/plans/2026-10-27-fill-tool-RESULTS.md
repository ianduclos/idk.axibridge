# Fill tool — results and decisions

Implemented on `codex/fill-tool` from `8d62de5`, after Ian accepted Pen v2 and Hand and authorized their local integration. This branch remains separate from main; no push or hardware action is part of delivery.

## Delivered behavior

Fill captures the enclosed face under the pointer from the existing resolved drawing, including effects, visibility, nested placement, occlusion and the current timeline time. The hover shows holes. Exact faces support a quick single click; repaired faces require a visible preview before confirmation. The result is a frozen ordinary Pen layer in paper coordinates, with editable anchors and no automatic fill effect.

The latest result has Detail refitting while Fill retains ownership. None, Hatch, Offset, Offset v2 and Cymatic use ordinary effect controls, including outline. Leaving the tool, selection changes, undo and unrelated edits end raw-boundary ownership. Drag union, subtraction and source-linked fills remain future work. [Usage and limits](../../FILL-TOOL.md).

## Verification status

The production fix `8186bce` passed its scoped re-review: an atomic optional expected revision protects newer edits, and per-client/disconnect cancellation stops obsolete searches. Independent original probes preserved external geometry and cancelled all abandoned searches; the following project read fell from 4.51 s to 0.041 s.

Focused checks: **145 server/regression tests**, **68 source/built Fill browser tests**, typecheck/build and diffcheck passed. Earlier drawing/Pen regression run: 147 passed. Isolated visual checks at 1440×900 and 1100×740 retained holes and Hatch; these are provisional software evidence.

**Final full-suite verification remains incomplete.** At `60c0942`, the full suite finished with **2,584 passed, three skipped, one failed in 1465.26 s**. The single Gesture Studies setup failure lost a 409 response body during navigation. `f9a7c58` removes redundant reload and a legacy broad error filter, observing existing live sync instead; its exact regression passed and all eight bench UI tests passed in 103.37 s. A fresh scoped review approved that test-only change.

The subsequent full run at `f9a7c58` reported `tests/test_gallery_ui.py::test_gallery_browses_filters_and_remembers_search` failing, then stalled near 33% and did not respond to normal SIGINT. At Ian's wrap-up request, only that owned test process tree (21 processes) was terminated; the run ended143 and did not produce a traceback. The Gallery failure's cause is unproven and must be diagnosed before acceptance/merge. Logs: `/tmp/axibridge-fill-final-f9a7c58.log`; stopped process inventory `/tmp/axibridge-fill-stopped-test-processes.json`. No production change followed the clean final review.

The three skips in the completed run were the native spawn test because port2942 already had the real app backend, and two explicitly opt-in slow Gesture Studies control tests (`shape_atlas`, `ledger_straight`). Existing NumPy warnings and Vite size advisory remain.

## Harness corrections and handoff

The original Pen/Hand baseline had 2,444 passed, three skipped and two browser failures. One uncaptured HTTP409 had no retained body, so cancellation attribution is unproven; the other raced library-card readiness. The reviewed test-only correction ignores only exact `detail.code=render_cancelled` responses and retains malformed/read-failed/genuine conflicts and JavaScript errors.

The first Fill full run also exposed a lifecycle gap: a bare TestClient inherited a closed singleton event-bus loop from an earlier app lifespan. `60c0942` runs the real lifespan and detaches only its own closed loop. The reproduced ordering case passed63 checks; lifecycle-adjacent run passed59; scoped task review approved.

**Native activation is pending.** The original live project/backend were not replaced; a recovery checkpoint and full read-only snapshot are retained in the ignored plan workspace. Recheck current state, checkpoint again, use the normal launcher with simulator/no auto-connect, restore kept content/history, compare sources, and verify the live backend before user acceptance. The Pi receives print jobs only. No hardware or machine motion occurred.

Ian explicitly requested wrap-up and GitHub publication. Publish Fill as a draft with this incomplete gate disclosed; do not merge. Main contains only the previously accepted Pen/Hand integration and existing history. Keep the feature worktree and its ignored recovery ledger for continuation.

## Rulings made by the primary

Copied exhaustively from the execution ledger in decision order, including costs if wrong.

1. Add pure POST /api/geometry/face/fit accepting bounded raw rings and detail, returning subpaths via fit_face; Task 3 uses it for latest-result Detail refits — the agreed live-refit behavior must validate topology without re-reading changed page geometry — costs one small API endpoint and validation surface if wrong.

2. Use Sol 6.1 for bounded implementation and task reviews; retain primary integration and final acceptance. Whole-branch review uses the most capable reviewer per the execution skill — costs a broader review seat, keeps central architecture with primary.

3. fit_face validates topology and bounded boundary deviation, rather than requiring the fitted polygon to cover every point of the original — valid curve fits can move inward within tolerance; Task 2 checks clicked-point containment separately — costs a clear refusal for clicks closer to the boundary than the fit error, instead of globally rejecting curved fills.

4. exclude targets reachable within Gap along existing linework before nearest gap connector selection — avoid dense bent-line shortcuts as well as exact retraces while preserving true ring closure — costs bounded graph traversal and may refuse a gap on a shape whose whole existing route is shorter than Gap.

5. increase helper raw capacity to 20,000 segments, noded capacity to 50,000, with STRtree bbox candidate preflight capped at 250,000 pairs before native union — current real drawing exceeds initial cap; bounded intersection work is safer than raw count alone — costs explicit rejection of some drawings with heavily overlapping bboxes plus a spatial-index pass. Review before Task 3.

6. densify fill-boundary edges to at most0.5mm before shared fitting, preserve original vertices, cap expanded samples20k, retain existing topology and error checks — rounded square sparse fit bulged1.93mm between samples at Detail1 — costs additional bounded fitting work and possible sample-limit refusals; avoids changing legacy pen fitter behavior.

7. Gap0 single-click intent waits for/reuses the exact face preview and commits only if click point/options/revision/master_t/lifecycle stay current; Gap>0 retains already-visible-preview requirement — F1 one-click creation governs ordinary exact faces, while repaired faces need prior visible review per anti-goal — costs a short asynchronous create delay and an extra review click only for an unpreviewed repaired face.

8. add backwards-compatible expected_revision on ordinary regenerate, checked under existing Session lock, and use captured pre-fit revision from Fill — local state can lag SSE and checking after write cannot protect external edits — costs one optional API field/conflict path; omitted clients keep existing behavior.

9. use per-client fill-preview replacement scopes plus disconnect cancellation before Session lock acquisition; retain mutation cancellation and other-client/render isolation — aborting fetch alone leaves obsolete synchronous work queued — costs narrow async request coordination and cancellation bookkeeping; wrong isolation could cancel another reader, covered by targeted tests.

10. correct only Fill API test fixture to run actual app lifespan and clear its own closed loop reference after teardown; verify against preceding lifecycle tests before fresh full rerun — isolated tests never started lifespan, hiding cross-test state — costs real per-test startup/shutdown and test-only cleanup of singleton state; production contracts remain unchanged. This is bounded integrated-test repair, not another production final-review fix wave.

11. remove redundant navigation and legacy broad409errorfilter from the single GestureStudies test setup; observe the existing external-edit SSE row update before resuming — avoid destroying response evidence during a test unrelated to navigation while retaining strict errors and recipe assertions — costs dependence on the already-shipped live-sync contract; if wrong, setup wait fails visibly. Test-only bounded worker repair, production unchanged.

12. honor explicit wrapup/publication by pushing the reviewed branch as a draft with failed/incomplete verification prominent, rather than treating it as accepted — user requested publication to close the session; publishing a draft preserves the work without merging — costs a draft requiring follow-up diagnosis; final readiness is explicitly withheld.

## Known limits and deferred judgments

1. Conservative geometry budgets can refuse complicated drawings: 20,000 raw segments, 50,000 noded segments, 250,000 bounding-box candidate pairs before each union, two million gap comparisons, 20,000 ring vertices/expanded fitting samples and 2,000 output anchors. Refusal is explicit; boundaries are not silently simplified.
2. Gap repair closes eligible dangling endpoints by nearest bounded connections. Some dense or locally connected shapes remain open rather than risk shortcuts. Fitting preserves ring/hole topology and bounds boundary deviation; a click too close to a fitted boundary can be refused.
3. Raw rings are transient. Saved projects contain normal Pen geometry and ordinary effects; old fills remain editable with Pen but do not regain Fill Detail ownership.
4. Existing invalid-escape/NumPy warnings and the Vite chunk-size advisory remain unrelated maintenance. A historical TDZ browser failure lacks enough retained evidence to assign a cause; later serial runs passed.
5. Native interaction, artistic preference and physical plotting require Ian's check. The Pi only receives resolved plot jobs and needs no app deployment or checkout sync.
