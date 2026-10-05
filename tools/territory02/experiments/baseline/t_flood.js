function flood(F, level, seed) {
  const mask = new Uint8Array(N);
  if (F[seed] <= level) return mask;
  const st = [seed]; mask[seed] = 1;
  while (st.length) {
    const c = st.pop(), i = c % GW, j = (c / GW) | 0;
    const nb = [i > 0 ? c - 1 : -1, i < GW - 1 ? c + 1 : -1, j > 0 ? c - GW : -1, j < GH - 1 ? c + GW : -1];
    for (const q of nb) if (q >= 0 && !mask[q] && F[q] > level) { mask[q] = 1; st.push(q); }
  }
  return mask;
}
