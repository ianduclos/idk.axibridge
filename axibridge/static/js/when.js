// `when`: does a control act right now? One dialect for every bench that dims
// a control that does nothing and says why (Gesture Studies' study controls,
// study bench v3; the synthesis bench's relation params). A condition is
// {key, is | not | in: [...]}, or {all: [...]} / {any: [...]} of those, with
// an optional `say` (the reason, in words); `key` names a sibling control.
// It is advice for the bench only: what is drawn is the same either way.

// Values compared by content (key order and number spelling do not matter).
export function canon(v) {
  if (Array.isArray(v)) return `[${v.map(canon).join(',')}]`;
  if (v && typeof v === 'object') return `{${Object.keys(v).sort().map(k => `${JSON.stringify(k)}:${canon(v[k])}`).join(',')}}`;
  return JSON.stringify(v);
}

function labelOf(v) {
  if (v === true) return 'on';
  if (v === false) return 'off';
  if (Array.isArray(v)) return v.join(', ');
  return String(v);
}

// Does `w` hold, reading sibling values through `read(key)`? No condition: always.
export function holds(w, read) {
  if (!w) return true;
  if (w.all) return w.all.every(x => holds(x, read));
  if (w.any) return w.any.some(x => holds(x, read));
  const v = read(w.key);
  if ('is' in w) return canon(v) === canon(w.is);
  if ('not' in w) return canon(v) !== canon(w.not);
  return (w.in || []).some(x => canon(x) === canon(v));
}

// Why a dimmed control does nothing: its `say`, else "acts when <name> is …"
// (`nameOf(key)`: the named control's label).
export function reasonOf(w, nameOf) {
  if (w.say) return w.say;
  const part = x => {
    if (x.all) return x.all.map(part).join(' and ');
    if (x.any) return x.any.map(part).join(', or ');
    const name = nameOf(x.key) || x.key;
    if ('is' in x) return `${name} is ${labelOf(x.is)}`;
    if ('not' in x) return `${name} is not ${labelOf(x.not)}`;
    return `${name} is ${x.in.map(labelOf).join(' or ')}`;
  };
  return `acts when ${part(w)}`;
}
