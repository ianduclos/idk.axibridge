// The bottom timeline bar: scrub + jump-to-ends + jump-to-checkpoints +
// next/previous frame steppers + a button that opens the render popup. Lives
// between #canvas-wrap and #canvas-status (index.html) — the strip that
// already reports on the drawing, so a strip that positions it belongs
// beside it.
//
// Play/pause deliberately stays in the Plot tab's Animation panel (Ian's Q7
// ruling, docs/plans/timeline-v2.md §2b — supersedes that doc's S4 bullet
// putting playback here). This bar only POSITIONS the master timeline.
//
// Visible only when the project has anything that follows it — the strict
// predicate below (a `follow_master` tween, or any `frame_follow` layer) —
// so a static project never pays for a control it can't use. Static markup
// in index.html, not appended by a tab body, so it survives project
// reloads the same way #layers-dock does.

import { S, actions } from "./main.js";
import { stepFrame, renderRasterPreview, frameGrid } from "./plot.js";

const $ = (id) => document.getElementById(id);

// ---- S5: cached-frame ticks --------------------------------------------------
//
// Frame INDICES (against the CURRENT grid — F6's frameGrid()) whose geometry
// has been fetched at least once this session, purely to light a tick — never
// consulted to decide whether to fetch. A hint, not a cache guarantee: the
// server's tween/gencache caches evict randomly under a point budget
// (session.py's TWEEN_CACHE_BUDGET_POINTS, gencache.py's docstring), so a lit
// tick can still be a miss by the time you land on it again. Recorded at the
// three places that know their t on completion (S5): this module's own
// `scrub` below, plot.js's previewScrub._run, and plot.js's
// renderRasterPreview loop — the latter two call recordFetchedFrame directly.
// Cleared on the next refreshProject after a mutating call (main.js) — a
// project edit can change what geometry lives at a given t, so a tick from
// before the edit is no longer honest.
const fetchedFrames = new Set();

export function recordFetchedFrame(i) {
  if (i == null) return;
  fetchedFrames.add(i);
  const tick = $("tl-ticks")?.children[i];
  if (tick) tick.classList.add("fetched");
}

export function clearFetchedFrames() {
  fetchedFrames.clear();
  renderGrid();
}

// Q4(a): the bar spans 0..1; the frame grid's [tFrom, tTo] sub-range is
// shaded, and one tick is drawn at each of the n grid positions inside it.
function renderGrid() {
  const shade = $("tl-shade");
  const ticksWrap = $("tl-ticks");
  if (!shade || !ticksWrap) return;
  const { n, tFrom, tTo } = frameGrid();
  const from = Math.max(0, Math.min(1, tFrom));
  const to = Math.max(0, Math.min(1, tTo));
  shade.style.left = `${from * 100}%`;
  shade.style.width = `${Math.max(0, (to - from) * 100)}%`;

  ticksWrap.innerHTML = "";
  for (let k = 0; k < n; k++) {
    const t = n <= 1 ? tFrom : tFrom + (tTo - tFrom) * k / (n - 1);
    const tick = document.createElement("div");
    tick.className = "tick" + (fetchedFrames.has(k) ? " fetched" : "");
    tick.style.left = `${Math.max(0, Math.min(100, t * 100))}%`;
    tick.title = `frame ${k + 1}/${n} (t=${t.toFixed(3)})`;
    ticksWrap.appendChild(tick);
  }
}

// Q3(b)/Q4(a): snap a raw slider value to the frame grid, phase-locked to
// tFrom with the grid's own step — so a value outside [tFrom, tTo] still
// lands on a consistent lattice rather than free-floating there (the step
// keeps counting past the n real frames, it just has none left to light).
// frameIndex is a real grid frame (0..n-1, tick-lightable) only when the
// snapped t falls inside [tFrom, tTo]; null outside it.
function snapToGrid(v) {
  const { n, tFrom, tTo } = frameGrid();
  const clamp = (x) => Math.max(0, Math.min(1, x));
  if (n <= 1 || tTo === tFrom) return { t: clamp(v), frameIndex: null };
  const step = (tTo - tFrom) / (n - 1);
  const k = Math.round((v - tFrom) / step);
  const t = clamp(tFrom + k * step);
  const frameIndex = (k >= 0 && k <= n - 1) ? k : null;
  return { t, frameIndex };
}

// Real keyboard state, not the input event's own (a range's `input` event
// carries no shiftKey, and the synthetic events this module's shift-fine-drag
// cousin in main.js dispatches don't either) — tracked here so the drag
// handler below can tell snap-by-default from the ⇧ escape at the moment
// each `input` tick actually fires.
let shiftHeld = false;
document.addEventListener("keydown", (e) => { if (e.key === "Shift") shiftHeld = true; });
document.addEventListener("keyup", (e) => { if (e.key === "Shift") shiftHeld = false; });
window.addEventListener("blur", () => { shiftHeld = false; });

// ---- master timeline scrub ---------------------------------------------------
//
// One /compose/resolved?t= request in flight at a time; the latest slider
// value always wins (coalesce, no timer). Moved verbatim from compose.js,
// where it drove the old Compose-tab #timeline-panel — same no-PATCH
// discipline: pure UI state, never touches the project or undo history.
const scrub = {
  inflight: false, pending: false, pendingFrameIndex: null,
  // frameIndex: the grid frame `v` was snapped to (S5), or null for a ⇧
  // continuous drag / a value off the grid — only a real frame index gets
  // its tick recorded on completion.
  request(v, frameIndex = null) {
    S.masterT = v;  // shared: every refreshResolved() now stays on this frame
    this.pending = true;
    this.pendingFrameIndex = frameIndex;
    if (!this.inflight) this._run();
  },
  async _run() {
    if (!this.pending) return;
    this.pending = false;
    const frameIndex = this.pendingFrameIndex;
    this.pendingFrameIndex = null;
    this.inflight = true;
    try {
      // per-tick: geometry only. plan_job()/flatten_to_document() per layer
      // is too expensive to pay on every slider frame; the change handler
      // wired in initTimelineBar() runs one full refresh (stats+plan) on
      // release. scrub:true — per Ian's ruling (§2c "Trays"), a timeline
      // interaction may still switch out of a live sheet preview, unlike an
      // ordinary param edit (8a's stickiness is for edits, not scrubbing).
      await actions.refreshResolved(undefined, { plan: false, stats: false, scrub: true });
      recordFetchedFrame(frameIndex); // S5: this bar's own scrub completion
    } catch (e) {
      actions.oops(e);
    } finally {
      this.inflight = false;
      if (this.pending) this._run();  // moved meanwhile: run once more
    }
  },
};

function setReadout(t) {
  const val = $("tl-t-val");
  if (val) val.textContent = `t = ${Number(t).toFixed(3)}`;
}

function setFrameReadout(i, n) {
  const el = $("tl-frame-val");
  if (el) el.textContent = `frame ${i + 1}/${n}`;
}

// A discrete jump (both ends, a checkpoint, a keyframe pick) isn't a drag —
// there's no mouseup to run a deferred full refresh, so it asks for
// stats+plan right away instead of riding `scrub` above.
async function jumpTo(t) {
  t = Math.max(0, Math.min(1, t));
  const el = $("tl-scrub");
  if (el) el.value = String(t);
  setReadout(t);
  try { await actions.refreshResolved(t, { scrub: true }); } catch (e) { actions.oops(e); }
}

// This tween's keyframe ids (S1's `keys`-or-[a,b] normalization, mirrored
// frontend-side — session.py's `_chain_keys` is the backend twin, compose.js
// has its own copy as `chainKeyIds` for the same reason: no shared module
// between the two, so both read the same two fields the same way) mapped to
// the master-timeline t each one sits at — isometrically spaced, mapped
// through the tween's own window. Declines (returns []) for a curve that
// reaches an interior key mid-window rather than at a fixed t (a ping-pong
// tween reaches B mid-window; only linear/cosine land every key at a fixed
// point in the window).
function chainKeyPositions(p) {
  if (p.time_curve && p.time_curve !== "linear" && p.time_curve !== "cosine") return [];
  const keys = (Array.isArray(p.keys) && p.keys.length > 2) ? p.keys : [p.a, p.b].filter(Boolean);
  if (keys.length < 2) return [];
  const wf = p.window_from ?? 0, wt = p.window_to ?? 1;
  return keys.map((id, k) => ({ id, k, t: wf + (wt - wf) * (k / (keys.length - 1)) }));
}

// Selecting a keyframe (any key of a follow_master tween — the classic A/B,
// or any key of a chain grown past it) jumps the master timeline to where
// that keyframe shows, so clicking it to edit also previews it in the
// animation. No-op for a layer that isn't a following tween's keyframe, or
// when the bar is hidden.
export function jumpTimelineToKeyframe(layerId) {
  if ($("timeline-bar")?.hidden) return;
  for (const l of S.state?.project?.layers || []) {
    if (l.source.type !== "tween") continue;
    const p = l.source.params || {};
    if (!p.follow_master) continue;
    const pos = chainKeyPositions(p).find((k) => k.id === layerId);
    if (!pos) continue;
    jumpTo(pos.t);
    return;
  }
}

// A chain's checkpoints (TweenParams.keys, S2): one jump button per key,
// when a following tween carries more than the classic two. Degrades to
// nothing for today's plain A/B tweens (no `keys`, or `keys.length <= 2` —
// the bar's own start/end buttons already cover those) and for a mid-chain
// ping-pong, same reason jumpTimelineToKeyframe declines one.
function chainCheckpoints() {
  const layers = S.state?.project?.layers || [];
  for (const l of layers) {
    if (l.source.type !== "tween") continue;
    const p = l.source.params || {};
    if (!p.follow_master) continue;
    const keys = Array.isArray(p.keys) ? p.keys : [];
    if (keys.length <= 2) continue;
    const positions = chainKeyPositions(p);
    if (!positions.length) continue;
    return positions.map((pos) => ({
      ...pos,
      name: layers.find((x) => x.id === pos.id)?.name || `key ${pos.k + 1}`,
    }));
  }
  return [];
}

function renderCheckpoints() {
  const wrap = $("tl-checkpoints");
  if (!wrap) return;
  const points = chainCheckpoints();
  wrap.hidden = points.length === 0;
  wrap.innerHTML = "";
  for (const pt of points) {
    const b = document.createElement("button");
    b.textContent = String(pt.k + 1);
    b.title = `jump to checkpoint ${pt.k + 1}: ${pt.name} (t=${pt.t.toFixed(3)})`;
    b.onclick = () => jumpTo(pt.t);
    wrap.appendChild(b);
  }
}

// Show the bar when there's anything for it to drive: a follow_master tween,
// or a frame_follow clip layer — the strict predicate (F5 in
// docs/plans/timeline-v2.md; the old #timeline-panel used a looser one that
// also counted a tween not yet following, driving a nudge hint — that hint
// is rehomed onto the tween's own Timeline fold now, see compose.js).
//
// Also resyncs the scrub position/readout from S.masterT, unless the slider
// itself currently holds focus (a drag in progress) — same "don't fight a
// typist" idiom main.js's zoom box uses.
export function renderTimelineBar() {
  const bar = $("timeline-bar");
  if (!bar) return;
  const layers = S.state?.project?.layers || [];
  const hasFollow = layers.some(
    (l) => (l.source.type === "tween" && (l.source.params || {}).follow_master)
        || l.frame_follow);
  bar.hidden = !hasFollow;
  if (!hasFollow) return;
  const el = $("tl-scrub");
  const t = S.masterT ?? 0;
  if (el && document.activeElement !== el) el.value = String(t);
  setReadout(t);
  renderCheckpoints();
  renderGrid(); // S5: the grid can have moved (frames/t-from/t-to, or a fresh project)
}

// Wired once (idempotent, like main.js's initLayersDock): the bar is static
// markup in index.html, not rebuilt by a tab body, so it survives project
// reloads without re-registering handlers.
export function initTimelineBar() {
  const bar = $("timeline-bar");
  if (!bar || bar.dataset.tlInit) return;
  bar.dataset.tlInit = "1";

  const el = $("tl-scrub");
  // Q3(b): snap to the frame grid by default; ⇧ held during the drag escapes
  // to continuous (shiftHeld tracks real keyboard state — see above, since
  // neither this event nor main.js's own shift-fine-drag carries shiftKey).
  el.oninput = () => {
    const raw = Number(el.value);
    if (shiftHeld) {
      setReadout(raw);
      scrub.request(raw, null);
      return;
    }
    const { t, frameIndex } = snapToGrid(raw);
    el.value = String(t);           // thumb snaps visibly, not just the readout
    setReadout(t);
    scrub.request(t, frameIndex);
  };
  // Drag release: one full refresh (stats + plan) so the estimate and the
  // travel overlay recover from the plan/stats-skipping ticks above — same
  // pattern the old #master-t slider used.
  el.onchange = () => actions.refreshResolved(undefined, { scrub: true });

  // Arrow keys step one frame (Q3(b)) when the bar's own slider has focus —
  // plain, not ⇧+arrow, which main.js's global fine-nudge already owns for
  // every range input. Reuses plot.js's stepFrame (F6), same as the
  // prev/next buttons below, rather than a second copy of the stepping math.
  el.onkeydown = (e) => {
    if (e.shiftKey) return;
    const dir = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1 }[e.key];
    if (!dir) return;
    e.preventDefault();
    const { i, n, t } = stepFrame(dir);
    el.value = String(t);
    setFrameReadout(i, n);
    setReadout(t);
  };

  $("tl-start").onclick = () => jumpTo(0);
  $("tl-end").onclick = () => jumpTo(1);

  // Frame steppers reuse plot.js's own frame-grid math (F6: an exported
  // accessor rather than a second copy of animT/pullAnimControls). Clamped
  // at the ends rather than wrapping (plot.js's own "Frame →" wraps) — this
  // bar already has explicit jump-to-start/end buttons for that.
  $("tl-prev").onclick = () => {
    const { i, n, t } = stepFrame(-1);
    el.value = String(t);
    setFrameReadout(i, n);
    setReadout(t);
  };
  $("tl-next").onclick = () => {
    const { i, n, t } = stepFrame(1);
    el.value = String(t);
    setFrameReadout(i, n);
    setReadout(t);
  };

  $("tl-render").onclick = () => { renderRasterPreview(); };

  renderTimelineBar();
}
