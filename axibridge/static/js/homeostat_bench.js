// Homeostat owns its control hierarchy; the common host knows no field names.
export function homeostatFormSchema(schema) {
  const groups = {
    'Viability': ['measure', 'target', 'tolerance', 'patience'],
    'Hand and coupling': ['variety', 'escalation', 'pens', 'unit'],
    'Frame and seed': ['width', 'height', 'seed'],
    'Fine tuning': ['step_len', 'memory', 'lift_on_reroll'],
  };
  const properties = {};
  for (const [group, keys] of Object.entries(groups)) {
    for (const key of keys) if (schema.properties[key]) properties[key] = {
      ...schema.properties[key], group, groupOpen: group === 'Viability',
    };
  }
  for (const [key, spec] of Object.entries(schema.properties)) {
    if (!properties[key]) properties[key] = spec;
  }
  return { ...schema, properties };
}
