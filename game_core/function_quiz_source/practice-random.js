const KEY = 'goodssaem-practice-variants-v1';

// Draw on opening a problem, never on render. Exclude the immediately preceding
// variant, including after a reload, without retry loops or changing saved work.
export function createVariantPicker({ storage, random = Math.random } = {}) {
  try { storage ??= globalThis.localStorage; } catch { /* Storage may be disabled. */ }
  let previous = {};
  return (key, count) => {
    if (!Number.isInteger(count) || count < 2) throw new Error('At least two practice variants are required.');
    try {
      const saved = JSON.parse(storage?.getItem(KEY));
      if (saved && typeof saved === 'object' && !Array.isArray(saved)) previous = { ...previous, ...saved };
    } catch { /* In-memory draws still avoid immediate repetition. */ }
    const old = previous[key], exclude = Number.isInteger(old) && old >= 0 && old < count;
    let next = Math.min(count - (exclude ? 2 : 1), Math.max(0, Math.floor(random() * (count - (exclude ? 1 : 0)))));
    if (exclude && next >= old) next++;
    previous[key] = next;
    try { storage?.setItem(KEY, JSON.stringify(previous)); } catch { /* Keep playing without persistence. */ }
    return next;
  };
}

export function shuffled(items, random = Math.random) {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}
export const signed = n => n < 0 ? `− ${Math.abs(n)}` : `+ ${n}`;
export const shifted = (variable, n) => `${variable} ${signed(-n)}`;
export const linearText = (a, b) => `${a === 1 ? '' : a === -1 ? '−' : a}x ${signed(b)}`;
export const setText = values => `{${[...new Set(values)].sort((a, b) => a - b).join(', ')}}`;
