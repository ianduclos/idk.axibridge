// Bench identity is independent of time. Factories own domain interaction;
// the popup host knows only lifecycle callbacks and presentation.
const adapters = new Map();
export function registerBenchAdapter(id, version, adapter) {
  const key = `${id}:${version}`;
  if (adapters.has(key)) throw new Error(`Bench adapter already registered: ${key}`);
  adapters.set(key, adapter);
}
export function benchDescriptor(mod) {
  if (mod?.bench) return mod.bench;
  // Compatibility with older servers; use their effective axis, never infer
  // another one from the frontend schema.
  const caps = new Set(mod?.bench_capabilities || []);
  if (caps.has('intervene') && caps.has('branch'))
    return { adapter: 'second-reading', version: 1, modes: ['new', 'resume'] };
  return mod?.time_axis ? { adapter: 'process', version: 1, modes: ['new', 'watch'] } : null;
}
export function benchAdapter(mod, mode = 'new') {
  const spec = benchDescriptor(mod);
  if (!spec?.modes?.includes(mode)) return null;
  return adapters.get(`${spec.adapter}:${spec.version}`) || null;
}
export function benchUnavailableReason(mod, mode = 'new') {
  const spec = benchDescriptor(mod);
  if (!spec) return 'This generator does not declare a bench.';
  if (!spec.modes?.includes(mode)) return `This bench does not support ${mode}.`;
  return benchAdapter(mod, mode) ? '' : `Bench unavailable: ${spec.adapter} version ${spec.version}.`;
}
