// Auto-generated controls from a Pydantic JSON Schema.
//
// This is the other half of the "declared parameter schema" contract: every
// module/backend ships its Params schema, and this renders it. Supported
// field shapes: number/integer (slider+spinbox when bounded), boolean,
// string, enum, and `format: "asset"` strings (a select over the project's
// uploaded image assets). `title` labels the control, `description` becomes
// a tooltip.

import { api } from "./api.js";
import { S, actions } from "./main.js";
import { rotToDisplay, rotToStored, sizeFactor } from "./viewmap.js";

// Advanced-field <details> groups collapse on every re-render by default
// (fresh DOM, no `open` attribute). Persist open/closed state across
// re-renders per the house pattern (see compose.js `expandedSteps`): callers
// pass a stable opts.stateKey to namespace groups as `${stateKey}:${group}`.
// Without a stateKey, groups fall back to the old behavior (always closed).
const openGroups = new Set();

// Orientation coherence: every viewAxis/viewAngle/viewSize-tagged field gets
// a {show(v), store(v), mapBounds(min,max), mapTitle(t), step} transform
// derived from its tag, portrait-gated on the project's CURRENT view (the
// mechanism this generalizes — S.state.project.view — is the same one the
// old ad-hoc viewAxis code read). null in landscape or for untagged fields.
function fieldViewTransform(key, spec, values, schema) {
  if (spec.viewAxis) {
    // vector rule: machine (dx,dy) -> screen (-dy,dx); canvas y is down, so
    // only the field whose ORIGINAL axis letter is y negates for display —
    // the paired x field keeps its stored sign (label swap only, below).
    const isY = /\b(y)\b/.test(spec.title || key);
    return {
      mapTitle: (t) => t.replace(/\b([xy])\b/, (m) => (m === "x" ? "y" : "x")),
      show: isY ? (v) => -v : null,
      store: isY ? (v) => -v : null,
      mapBounds: isY
        ? (min, max) => [min === undefined ? min : -max, max === undefined ? max : -min]
        : null,
    };
  }
  if (spec.viewAngle) {
    const period = spec.viewAngle;
    return {
      show: (v) => rotToDisplay(v, period, true),
      store: (v) => rotToStored(v, period, true),
    };
  }
  if (spec.viewSize) {
    const f = sizeFactor(values, schema, S.state?.assets || []);
    if (f == null) {
      // aspect unknown (no image chosen / asset missing): show the raw
      // stored value, but relabel the title so it stays honest.
      return { mapTitle: (t) => t.replace(/\bWidth\b/, "Height") };
    }
    return {
      show: (v) => Math.round(v * f * 10) / 10, // quantize DISPLAYED to 0.1mm
      store: (v) => v / f,                       // store keeps full precision
      mapBounds: (min, max) => [min === undefined ? min : min * f, max === undefined ? max : max * f],
      step: 0.1,
    };
  }
  return null;
}

export function renderForm(container, schema, values, onChange, opts = {}) {
  container.innerHTML = "";
  const portrait = S.state?.project?.view === "portrait";
  // fields tagged json_schema_extra={"group": "..."} collapse into a <details>
  // appended after the plain fields (keeps ten near-identical forms uncrammed)
  const groups = new Map();
  const props = schema.properties || {};
  // a viewSize field's display factor depends on the schema's image/rotate
  // fields — when either changes, the form is re-rendered so the width
  // control re-derives its aspect mapping (values is live, so state survives).
  const hasViewSize = Object.values(props).some((p) => p.viewSize);
  const rerenderSelf = () => renderForm(container, schema, values, onChange, opts);
  for (const [key, spec] of Object.entries(props)) {
    if (spec.hidden) continue; // declared but not user-facing (e.g. hardware identity)
    // pydantic emits {anyOf:[...]} for optionals; take the first concrete type
    const s = spec.type ? spec : (spec.anyOf || []).find((a) => a.type) || spec;
    const field = document.createElement("div");
    field.className = "field";
    if (spec.description) field.title = spec.description;
    const vt = portrait ? fieldViewTransform(key, spec, values, schema) : null;

    const label = document.createElement("label");
    const name = document.createElement("span");
    let title = spec.title || key;
    if (vt?.mapTitle) title = vt.mapTitle(title);
    name.textContent = title;
    label.appendChild(name);
    field.appendChild(label);

    const ctl = document.createElement("div");
    ctl.className = "ctl";
    const val = values[key];
    const set = (v) => { values[key] = v; onChange(key, v); };

    if (spec.format === "asset" || s.format === "asset") {
      const sel = document.createElement("select");
      const fill = (selected) => {
        sel.innerHTML = "";
        const assets = S.state?.assets || [];
        const names = assets.map((a) => a.name ?? a);
        const none = document.createElement("option");
        none.value = ""; none.textContent = "— none —";
        if (selected === "" || selected == null) none.selected = true;
        sel.appendChild(none);
        for (const a of assets) {
          const name = a.name ?? a;
          const o = document.createElement("option");
          o.value = name;
          // frame sequences arrive as one entry (name = "clip#", frames = N)
          o.textContent = a.frames > 1 ? `${name} (${a.frames} frames)` : name;
          if (name === selected) o.selected = true;
          sel.appendChild(o);
        }
        if (selected && !names.includes(selected)) { // asset went missing: show it, don't silently drop
          const o = document.createElement("option");
          o.value = selected; o.textContent = `${selected} (missing)`; o.selected = true;
          sel.appendChild(o);
        }
      };
      fill(val);
      sel.onchange = () => {
        set(sel.value);
        if (hasViewSize) rerenderSelf(); // a viewSize field's aspect factor tracks this
      };
      ctl.appendChild(sel);
      // inline upload: new assets land in the dropdown (and get picked)
      // immediately. Multi-select or a single video imports a frame SEQUENCE
      // (POST /api/assets/sequence); one image keeps the plain single path.
      const file = document.createElement("input");
      file.type = "file"; file.multiple = true;
      file.accept = "image/png,image/jpeg,video/mp4,video/quicktime,video/webm,video/x-matroska,video/x-msvideo";
      file.hidden = true;
      const up = document.createElement("button");
      up.textContent = "⤒"; up.title = "upload an image, several images, or a video (frame sequence)";
      up.onclick = (e) => { e.preventDefault(); file.click(); };
      file.onchange = async () => {
        const fs = [...file.files];
        if (!fs.length) return;
        const isVideo = fs.length === 1 && /\.(mp4|mov|webm|mkv|avi|m4v)$/i.test(fs[0].name);
        const isSequence = fs.length > 1 || isVideo;
        // sequence import emits gen-progress SSE — same bar the generators use
        if (isSequence) actions.setSeqProgress(true);
        try {
          let r;
          if (isSequence) {
            const fd = new FormData();
            for (const f of fs) fd.append("files", f);
            r = await api.upload("/api/assets/sequence", fd);
          } else {
            const fd = new FormData();
            fd.append("file", fs[0]);
            r = await api.upload("/api/assets", fd);
          }
          S.state.assets = r.assets;
          fill(r.name);
          set(r.name);
          file.value = "";
          if (hasViewSize) { rerenderSelf(); return; } // container's DOM (incl. `file`) is now stale
        } catch (err) { actions.oops(err); }
        finally { if (isSequence) actions.setSeqProgress(false); }
        file.value = "";
      };
      ctl.appendChild(up);
      ctl.appendChild(file);
    } else if (s.enum) {
      const sel = document.createElement("select");
      const rotateDisplayOrder = portrait && spec.viewRotate ? s.enum : null;
      for (const opt of (rotateDisplayOrder || s.enum)) {
        const o = document.createElement("option");
        if (rotateDisplayOrder) {
          // `opt` IS the displayed value (enum already lists 0/90/180/270);
          // option.value is the stored equivalent it maps back to on select.
          const stored = rotToStored(opt, 360, true);
          o.value = stored;
          o.textContent = opt;
          if (stored === val) o.selected = true;
        } else {
          o.value = opt;
          o.textContent = (portrait && spec.viewOrient) ? swapOrient(String(opt)) : opt;
          if (opt === val) o.selected = true;
        }
        sel.appendChild(o);
      }
      sel.onchange = () => {
        set(s.type === "integer" || s.type === "number" ? Number(sel.value) : sel.value);
        if (hasViewSize && spec.viewRotate) rerenderSelf(); // width's aspect factor tracks rotate
      };
      ctl.appendChild(sel);
    } else if (s.type === "boolean") {
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = !!val;
      cb.onchange = () => set(cb.checked);
      ctl.appendChild(cb);
    } else if (s.type === "number" || s.type === "integer") {
      const min = s.minimum ?? s.exclusiveMinimum;
      const max = s.maximum ?? s.exclusiveMaximum;
      // viewAxis/viewAngle/viewSize-tagged fields route through the field's
      // transform: show() for machine-frame -> displayed, store() back.
      // Untagged (and landscape) fields get the identity — same as before.
      const show = vt?.show || ((v) => v);
      const store = vt?.store || ((v) => v);
      let dmin = min, dmax = max;
      if (vt?.mapBounds) [dmin, dmax] = vt.mapBounds(min, max);
      const num = document.createElement("input");
      num.type = "number";
      num.value = show(val);
      if (dmin !== undefined) num.min = dmin;
      if (dmax !== undefined) num.max = dmax;
      const step = vt?.step ?? (s.type === "integer" ? 1 : stepFor(min, max));
      num.step = step;
      let range = null;
      if (dmin !== undefined && dmax !== undefined) {
        range = document.createElement("input");
        range.type = "range";
        // step="any": a discrete step grid is anchored at `min`, so any
        // stored value off that grid (or off by float error) snaps the THUMB
        // while the number box keeps the true value — the worst case being a
        // 0.35 on a 0..1 field parking visually at 0. Instead the slider is
        // continuous and WE quantize drag output to the step's decimals.
        range.min = num.min; range.max = num.max;
        range.step = "any";
        range.value = show(val);
        const quant = (v) => (step === 1 ? Math.round(v)
          : Number(v.toFixed(step === 0.01 ? 2 : 1)));
        // live number readout while dragging; commit ONCE on release — a
        // mid-drag commit re-renders the panel and kills the drag. Forms
        // may pass opts.onLive(key, value) to observe mid-drag values (live
        // preview); it updates `values` but never fires the commit callback.
        range.oninput = () => {
          const q = quant(Number(range.value));
          num.value = q;
          if (opts.onLive) {
            const v = store(q);
            values[key] = v;
            opts.onLive(key, v);
          }
        };
        range.onchange = () => {
          const q = quant(Number(range.value));
          num.value = q;
          range.value = q;
          set(store(q));
        };
        ctl.appendChild(range);
      }
      num.onchange = () => {
        let v = Number(num.value);
        if (num.min !== "") v = Math.max(v, Number(num.min));
        if (num.max !== "") v = Math.min(v, Number(num.max));
        num.value = v;
        if (range) range.value = v;
        set(store(v));
      };
      ctl.appendChild(num);
    } else if (spec.format === "textarea" || s.format === "textarea") {
      const ta = document.createElement("textarea");
      ta.value = val ?? "";
      ta.rows = 3;
      ta.onchange = () => set(ta.value);
      ctl.appendChild(ta);
    } else { // string and anything else
      const inp = document.createElement("input");
      inp.type = "text";
      inp.value = val ?? "";
      inp.onchange = () => set(inp.value);
      ctl.appendChild(inp);
    }
    field.appendChild(ctl);
    if (spec.group) {
      if (!groups.has(spec.group)) {
        const det = document.createElement("details");
        det.className = "form-group";
        const sum = document.createElement("summary");
        sum.textContent = spec.group;
        det.appendChild(sum);
        if (opts.stateKey) {
          const gkey = `${opts.stateKey}:${spec.group}`;
          det.open = openGroups.has(gkey);
          det.addEventListener("toggle", () => {
            if (det.open) openGroups.add(gkey);
            else openGroups.delete(gkey);
          });
        }
        groups.set(spec.group, det);
      }
      groups.get(spec.group).appendChild(field);
    } else {
      container.appendChild(field);
    }
  }
  for (const det of groups.values()) container.appendChild(det);
}

function stepFor(min, max) {
  if (min === undefined || max === undefined) return "any";
  const span = max - min;
  if (span <= 2) return 0.01;
  if (span <= 20) return 0.1;
  return 1;
}

// viewOrient: swap the two words in an option's visible label only — the
// stored enum value (option.value) never changes. "both" passes through.
function swapOrient(s) {
  if (s === "horizontal") return "vertical";
  if (s === "vertical") return "horizontal";
  return s;
}
