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

export function renderForm(container, schema, values, onChange) {
  container.innerHTML = "";
  const props = schema.properties || {};
  for (const [key, spec] of Object.entries(props)) {
    // pydantic emits {anyOf:[...]} for optionals; take the first concrete type
    const s = spec.type ? spec : (spec.anyOf || []).find((a) => a.type) || spec;
    const field = document.createElement("div");
    field.className = "field";
    if (spec.description) field.title = spec.description;

    const label = document.createElement("label");
    const name = document.createElement("span");
    let title = spec.title || key;
    // axis-tagged fields (paper-space x/y): swap the letter so the label
    // matches what the user SEES — the portrait view rotates the bed 90°
    if (spec.viewAxis && S.state?.project?.view === "portrait") {
      title = title.replace(/\b([xy])\b/, (m) => (m === "x" ? "y" : "x"));
    }
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
        const names = (S.state?.assets || []).map((a) => a.name ?? a);
        for (const opt of ["", ...names]) {
          const o = document.createElement("option");
          o.value = opt; o.textContent = opt || "— none —";
          if (opt === selected) o.selected = true;
          sel.appendChild(o);
        }
        if (selected && !names.includes(selected)) { // asset went missing: show it, don't silently drop
          const o = document.createElement("option");
          o.value = selected; o.textContent = `${selected} (missing)`; o.selected = true;
          sel.appendChild(o);
        }
      };
      fill(val);
      sel.onchange = () => set(sel.value);
      ctl.appendChild(sel);
      // inline upload: new images land in the dropdown (and get picked) immediately
      const file = document.createElement("input");
      file.type = "file"; file.accept = "image/png,image/jpeg"; file.hidden = true;
      const up = document.createElement("button");
      up.textContent = "⤒"; up.title = "upload a new image asset";
      up.onclick = (e) => { e.preventDefault(); file.click(); };
      file.onchange = async () => {
        if (!file.files[0]) return;
        const fd = new FormData();
        fd.append("file", file.files[0]);
        try {
          const r = await api.upload("/api/assets", fd);
          S.state.assets = r.assets;
          fill(r.name);
          set(r.name);
        } catch (err) { actions.oops(err); }
        file.value = "";
      };
      ctl.appendChild(up);
      ctl.appendChild(file);
    } else if (s.enum) {
      const sel = document.createElement("select");
      for (const opt of s.enum) {
        const o = document.createElement("option");
        o.value = opt; o.textContent = opt;
        if (opt === val) o.selected = true;
        sel.appendChild(o);
      }
      sel.onchange = () => set(s.type === "integer" || s.type === "number" ? Number(sel.value) : sel.value);
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
      const num = document.createElement("input");
      num.type = "number";
      num.value = val;
      if (min !== undefined) num.min = min;
      if (max !== undefined) num.max = max;
      num.step = s.type === "integer" ? 1 : stepFor(min, max);
      let range = null;
      if (min !== undefined && max !== undefined) {
        range = document.createElement("input");
        range.type = "range";
        range.min = min; range.max = max; range.value = val;
        range.step = num.step;
        range.oninput = () => { num.value = range.value; set(Number(range.value)); };
        ctl.appendChild(range);
      }
      num.onchange = () => {
        let v = Number(num.value);
        if (min !== undefined) v = Math.max(v, min);
        if (max !== undefined) v = Math.min(v, max);
        num.value = v;
        if (range) range.value = v;
        set(v);
      };
      ctl.appendChild(num);
    } else { // string and anything else
      const inp = document.createElement("input");
      inp.type = "text";
      inp.value = val ?? "";
      inp.onchange = () => set(inp.value);
      ctl.appendChild(inp);
    }
    field.appendChild(ctl);
    container.appendChild(field);
  }
}

function stepFor(min, max) {
  if (min === undefined || max === undefined) return "any";
  const span = max - min;
  if (span <= 2) return 0.01;
  if (span <= 20) return 0.1;
  return 1;
}
