// Orientation coherence: the ONE place stored (machine-frame mm) <-> displayed
// (current-view) param conversions happen. Params stay stored in machine
// frame forever (resolve/save/plot never see this module); the frontend
// display layer maps at render time, driven by declarative json_schema_extra
// tags (viewRotate / viewAngle / viewSize / viewOrient / viewAxis).
//
// Pure, dependency-free — no DOM, no imports — so it's testable standalone
// under node (see tests/test_view_coherence.py).
//
// Sign convention (derived from canvas.js's portrait display transform
// `translate(H 0) rotate(90)` — the display adds 90deg CW to everything;
// `rotate` params are CW on paper, per assets.py's `_rotated`):
//   displayed = (stored + 90) mod period
//   stored    = (displayed - 90 + period) mod period
// Landscape is the identity map. Sanity anchor: stored 270 in portrait must
// display as 0 (the historical band-aid this pass replaces).

export function rotToDisplay(v, period, portrait) {
  if (!portrait) return v;
  return ((v + 90) % period + period) % period;
}

export function rotToStored(v, period, portrait) {
  if (!portrait) return v;
  return ((v - 90) % period + period) % period;
}

// Aspect factor for a viewSize-tagged mm field (stored = extent along
// machine x). In portrait the on-paper VISUAL width is the doc's
// machine-frame HEIGHT, so displayed = stored * f, stored = displayed / f.
//
// `schema` is a JSON Schema (properties map); `values` is the live params
// object; `assets` is S.state.assets ([{name, width, height, frames}, ...]
// — see assets.py AssetStore.info()). Returns null when the image/asset
// isn't known (no image chosen, or it went missing) — callers fall back to
// showing the raw stored value with a relabeled title.
export function sizeFactor(values, schema, assets) {
  const props = (schema && schema.properties) || {};
  const imageKey = Object.keys(props).find((k) => {
    const p = props[k];
    const s = p.format ? p : ((p.anyOf || []).find((a) => a.format) || {});
    return p.format === "asset" || s.format === "asset";
  });
  if (!imageKey) return null;
  const name = values ? values[imageKey] : null;
  if (!name) return null;
  const asset = (assets || []).find((a) => (a.name ?? a) === name);
  if (!asset || !asset.width || !asset.height) return null;

  const rotateKey = Object.keys(props).find((k) => props[k].viewRotate);
  const rotate = rotateKey && values ? Number(values[rotateKey]) || 0 : 0;
  const [iw, ih] = [asset.width, asset.height];
  const [rw, rh] = (rotate === 90 || rotate === 270) ? [ih, iw] : [iw, ih];
  if (!rw) return null;
  return rh / rw;
}

// For every viewRotate/viewAngle-tagged property in `schema`, replace the
// value already seeded into `params` (module defaults, in machine frame)
// with its stored equivalent for the CURRENT displayed default — i.e. what
// reads "0" to the user on first open stays whatever machine-frame value
// that actually is. Generalizes the old single-field "portrait defaults to
// rotate=270" band-aid to every tagged field. Mutates and returns `params`.
export function applyViewDefaults(schema, params, portrait) {
  if (!portrait || !schema) return params;
  const props = schema.properties || {};
  for (const [key, spec] of Object.entries(props)) {
    if (!(key in params)) continue;
    if (spec.viewRotate) {
      params[key] = rotToStored(Number(params[key]), 360, portrait);
    } else if (spec.viewAngle) {
      params[key] = rotToStored(Number(params[key]), spec.viewAngle, portrait);
    }
  }
  return params;
}
