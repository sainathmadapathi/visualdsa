import type { Divergence, Run, Structure, TraceEvent, Value } from './types';

/**
 * Pure decisions behind the visual stage. Every visual cue is derived from the recorded
 * trace: nothing here simulates execution or guesses at intent.
 */

export type Category = 'read' | 'write' | 'compare' | 'lookup' | 'insert' | 'loop' | 'call' | 'return' | 'error' | 'state';
const categories: Record<string, Category> = {
  ARRAY_ACCESS: 'read', HASHMAP_LOOKUP: 'lookup', ARRAY_WRITE: 'write', HASHMAP_INSERT: 'insert', HASHMAP_DELETE: 'insert',
  STACK_PUSH: 'insert', STACK_POP: 'insert', COMPARE: 'compare', LOOP_START: 'loop', LOOP_END: 'loop',
  RECURSION_CALL: 'call', RECURSION_RETURN: 'call', RETURN: 'return', ERROR: 'error', POINTER_MOVE: 'state', STATE_CHANGE: 'state',
};
export const categoryOf = (type: string): Category => categories[type] || 'state';

const json = (value: unknown) => JSON.stringify(value);
const isIdentifier = (text?: string) => !!text && /^[A-Za-z]\w*$/.test(text);
const sequences = (event?: TraceEvent) => (event?.state.structures || []).filter(s => s.type === 'array' || s.type === 'string');
const sameFrame = (a?: TraceEvent, b?: TraceEvent) => !!a && !!b && json(a.state.callstack) === json(b.state.callstack);

/** Variables that index each sequence: names the code used inside its brackets, plus classic pointer names. */
export function pointerNames(events: TraceEvent[]): Record<string, string[]> {
  const names: Record<string, string[]> = {};
  const used: Record<string, Set<string>> = {};
  const add = (structure: string, name: string) => { (names[structure] ||= []).includes(name) || names[structure].push(name); };
  for (const event of events) {
    const read = event.type === 'ARRAY_ACCESS' && event.meta.structure && isIdentifier(event.meta.index) ? [event.meta.structure, event.meta.index!] : null;
    const failed = event.meta.access && isIdentifier(event.meta.access.index) ? [event.meta.access.structure, event.meta.access.index] : null;
    for (const [structure, name] of [read, failed].filter(Boolean) as string[][]) { (used[name] ||= new Set()).add(structure); add(structure, name); }
  }
  // Classic pointer names the code never used as an index keep the tracer's placement.
  for (const event of events) for (const s of sequences(event)) for (const name of Object.keys(s.pointers || {})) if (!used[name]) add(s.id, name);
  // Left-hand names sit on top, as in most textbook drawings; others keep their first-use order.
  const rank = (name: string) => { const i = ['i', 'left', 'lo', 'low', 'start', 'slow', 'write'].indexOf(name); return i < 0 ? 100 : i; };
  for (const list of Object.values(names)) list.sort((a, b) => rank(a) - rank(b));
  return names;
}

export interface Pointer { name: string; index: number; outside: 'before' | 'after' | null }
/** Where each pointer sits at this step. Positions outside the sequence are shown at its edge, marked. */
export function pointersAt(event: TraceEvent | undefined, structure: Structure, names: string[]): Pointer[] {
  const length = structure.length ?? structure.values?.length ?? 0;
  return names.flatMap(name => {
    const variable = event?.state.variables.find(v => v.id === name);
    const value = variable?.value;
    if (typeof value !== 'number' || !Number.isInteger(value)) return [];
    return [{ name, index: Math.max(-1, Math.min(value, length)), outside: value < 0 ? 'before' as const : value >= length ? 'after' as const : null }];
  });
}

/** Two pointers on one sequence define a range worth shading (a window, a search interval). */
export function pointerRange(pointers: Pointer[]): [number, number] | null {
  const pairs = [['left', 'right'], ['lo', 'hi'], ['low', 'high'], ['start', 'end'], ['slow', 'fast'], ['i', 'j']];
  for (const [a, b] of pairs) {
    const left = pointers.find(p => p.name === a), right = pointers.find(p => p.name === b);
    if (left && right && !left.outside && !right.outside) return [Math.min(left.index, right.index), Math.max(left.index, right.index)];
  }
  return null;
}

export interface StepChange {
  written: Record<string, number[]>; old: Record<string, Record<number, Value>>; swapped: Record<string, [number, number]>;
  added: Record<string, string[]>; changed: Record<string, string[]>; removed: Record<string, { key: Value; value: Value }[]>;
  variables: Record<string, Value | undefined>;
}
const entriesOf = (s?: Structure) => s ? (s.entries || (s.values || []).map(key => ({ key, value: null as Value }))) : [];
/** What this step changed, compared with the step before it in the same frame. */
export function stepChange(previous: TraceEvent | undefined, current: TraceEvent): StepChange {
  const change: StepChange = { written: {}, old: {}, swapped: {}, added: {}, changed: {}, removed: {}, variables: {} };
  if (!sameFrame(previous, current)) return change;
  const before = Object.fromEntries(previous!.state.structures.map(s => [s.id, s]));
  for (const s of current.state.structures) {
    const old = before[s.id];
    if (s.type === 'array' || s.type === 'string') {
      const now = s.values || [], was = old?.values || [];
      const indices = now.map((_, i) => i).filter(i => i >= was.length || json(now[i]) !== json(was[i]));
      if (!old || !indices.length) continue;
      change.written[s.id] = indices;
      change.old[s.id] = Object.fromEntries(indices.filter(i => i < was.length).map(i => [i, was[i]]));
      const [a, b] = indices;
      if (indices.length === 2 && b < was.length && json(now[a]) === json(was[b]) && json(now[b]) === json(was[a])) change.swapped[s.id] = [a, b];
    } else {
      const was = new Map(entriesOf(old).map(e => [json(e.key), e])), now = new Map(entriesOf(s).map(e => [json(e.key), e]));
      if (!old) continue;
      change.added[s.id] = [...now.keys()].filter(k => !was.has(k));
      change.changed[s.id] = [...now.keys()].filter(k => was.has(k) && json(was.get(k)!.value) !== json(now.get(k)!.value));
      change.removed[s.id] = [...was.entries()].filter(([k]) => !now.has(k)).map(([, e]) => e);
    }
  }
  const was = new Map(previous!.state.variables.map(v => [v.id, v.value]));
  for (const v of current.state.variables) if (!was.has(v.id) || json(was.get(v.id)) !== json(v.value)) change.variables[v.id] = was.get(v.id);
  return change;
}

export interface Focus {
  reads: Record<string, number[]>; compared: Record<string, number[]>;
  lookup: { structure: string; key: Value; found: boolean } | null;
  compare: { expression: string; left: Value; right: Value; result: boolean } | null;
}
const position = (key: Value, length: number) => typeof key === 'number' ? (key < 0 ? length + key : key) : -1;
/** What this step looked at: the read, the lookup, or the comparison and the cells that fed it. */
export function focusAt(events: TraceEvent[], step: number): Focus {
  const event = events[step];
  const focus: Focus = { reads: {}, compared: {}, lookup: null, compare: null };
  if (!event) return focus;
  const lengthOf = (name: string) => event.state.structures.find(s => s.id === name)?.length ?? 0;
  if (event.type === 'ARRAY_ACCESS' && event.meta.structure) focus.reads[event.meta.structure] = [position(event.meta.key ?? null, lengthOf(event.meta.structure))];
  if (event.type === 'HASHMAP_LOOKUP') {
    const structure = event.meta.structure || /\bin\s+([A-Za-z]\w*)\s*$/.exec(event.meta.expression || '')?.[1];
    if (structure) focus.lookup = { structure, key: event.meta.structure ? event.meta.key ?? null : event.meta.left ?? null, found: event.meta.structure ? true : !!event.meta.found };
  }
  if (event.type === 'COMPARE' && event.meta.expression) {
    focus.compare = { expression: event.meta.expression, left: event.meta.left ?? null, right: event.meta.right ?? null, result: !!event.meta.result };
    // The reads that fed this comparison happened just before it, on the same line.
    for (let i = step - 1; i >= 0 && events[i].line === event.line && events[i].type === 'ARRAY_ACCESS'; i--) {
      const read = events[i];
      if (read.meta.structure) (focus.compared[read.meta.structure] ||= []).push(position(read.meta.key ?? null, lengthOf(read.meta.structure)));
    }
  }
  return focus;
}

/** The step's own wrong-answer evidence: writes whose values stayed wrong to the end. */
export const wrongAt = (divergence: Divergence | null | undefined, step: number) => (divergence?.elements?.wrong || []).filter(w => w.step === step);

export interface LineSummary { line: number; source: string; ran: number | null; iterations: number; samples: { step: number; label: string }[]; more: number; note: string }
/** Python-style display, matching what learners write. */
export function py(value: Value | undefined): string {
  if (value === undefined) return '—';
  if (value === null) return 'None';
  if (typeof value === 'boolean') return value ? 'True' : 'False';
  if (typeof value === 'string') return `'${value}'`;
  if (typeof value === 'number') return String(value);
  if (Array.isArray(value)) return `[${value.map(py).join(', ')}]`;
  return `{${Object.entries(value).map(([k, v]) => `${py(k)}: ${py(v)}`).join(', ')}}`;
}
const describe = py;
const keyLabel = (key: string) => py(JSON.parse(key) as Value);
/** What one source line did across the whole run: how often it ran and the values it produced. */
export function lineLens(run: Pick<Run, 'events' | 'lines'>, code: string, line: number): LineSummary {
  const source = (code.split('\n')[line - 1] || '').trim();
  const ran = run.lines ? run.lines[String(line)] ?? 0 : null;
  const events = run.events.filter(e => e.line === line);
  const loops = events.filter(e => e.type === 'LOOP_START');
  const samples: { step: number; label: string }[] = [];
  const sample = (event: TraceEvent, label: string) => samples.push({ step: event.id, label });
  for (const event of events) {
    const previous = run.events[event.id - 1];
    const assigned = /^(.+?) updated\.$/.exec(event.detail)?.[1];
    if (event.type === 'LOOP_START') {
      const names = assigned ? assigned.split(', ') : [];
      const values = names.map(name => event.state.variables.find(v => v.id === name)).filter(Boolean).map(v => `${v!.id}=${describe(v!.value)}`);
      sample(event, values.length ? values.join(', ') : `iteration ${loops.indexOf(event) + 1}`);
    } else if (event.type === 'COMPARE' || (event.type === 'HASHMAP_LOOKUP' && event.meta.expression)) sample(event, event.meta.result ? 'True' : 'False');
    else if (event.type === 'RETURN') sample(event, `returned ${describe(event.meta.value ?? null)}`);
    else if ((event.type === 'STATE_CHANGE' || event.type === 'POINTER_MOVE') && assigned) {
      const values = assigned.split(', ').map(name => event.state.variables.find(v => v.id === name)).filter(Boolean);
      if (values.length) sample(event, values.map(v => `${v!.id} = ${describe(v!.value)}`).join(', '));
    } else if (event.type === 'ARRAY_WRITE' || event.type === 'HASHMAP_INSERT' || event.type === 'STACK_PUSH' || event.type === 'STACK_POP' || event.type === 'HASHMAP_DELETE') {
      const change = stepChange(previous, event);
      const parts = [
        ...Object.entries(change.swapped).map(([id, [a, b]]) => `swap ${id}[${a}]↔[${b}]`),
        ...Object.entries(change.written).filter(([id]) => !change.swapped[id]).flatMap(([id, indices]) => indices.map(i => `${id}[${i}] = ${describe(event.state.structures.find(s => s.id === id)?.values?.[i] ?? null)}`)),
        ...Object.entries(change.added).flatMap(([id, keys]) => keys.map(k => `${id} + ${keyLabel(k)}${event.state.structures.find(s => s.id === id)?.type === 'hashmap' ? ` → ${describe(event.state.structures.find(s => s.id === id)!.entries!.find(e => json(e.key) === k)!.value)}` : ''}`)),
        ...Object.entries(change.changed).flatMap(([id, keys]) => keys.map(k => `${id}[${keyLabel(k)}] → ${describe(event.state.structures.find(s => s.id === id)!.entries!.find(e => json(e.key) === k)!.value)}`)),
        ...Object.entries(change.removed).flatMap(([id, gone]) => gone.map(e => `${id} − ${describe(e.key)}`)),
      ];
      sample(event, parts.join(', ') || event.detail.replace(/\.$/, ''));
    } else if (event.type === 'ARRAY_ACCESS' && !events.some(e => e.type !== 'ARRAY_ACCESS' && e.type !== 'HASHMAP_LOOKUP')) sample(event, `read ${describe(event.meta.value ?? null)}`);
    else if (event.type === 'ERROR') sample(event, 'stopped here');
  }
  const header = /^def\s/.test(source);
  const code_line = !!source && !source.startsWith('#') && !header;
  const note = header ? 'Function header.' : ran === 0 && code_line ? 'This line never ran for this input.' : ran && !samples.length ? `Ran ${ran}× without a recorded state change.` : '';
  return { line, source, ran, iterations: loops.length, samples: samples.slice(0, 10), more: Math.max(0, samples.length - 10), note };
}

export interface Ribbon { ticks: Category[]; markers: { step: number; kind: 'divergence' | 'wrong' | 'cycle' | 'origin'; label: string }[] }
/** The whole run at a glance, with the steps the evidence points at. */
export function ribbon(run: Pick<Run, 'events' | 'divergence'>): Ribbon {
  const markers: Ribbon['markers'] = [];
  const d = run.divergence;
  if (d?.cycle) {
    if (d.cycle.first !== null) markers.push({ step: d.cycle.first, kind: 'cycle', label: `Same state as step ${(d.cycle.repeat ?? d.cycle.first) + 1}` });
    if (d.cycle.repeat !== null) markers.push({ step: d.cycle.repeat, kind: 'cycle', label: `Repeats step ${d.cycle.first! + 1} exactly` });
  }
  for (const w of d?.elements?.wrong || []) markers.push({ step: w.step, kind: 'wrong', label: `Put ${describe(w.value)} at position ${w.position}${w.goal !== null ? `; the goal has ${describe(w.goal)}` : ''}` });
  if (d?.origin && !d.origin.unchanged) markers.push({ step: d.origin.step, kind: 'origin', label: `Last change to ${d.origin.name}` });
  if (d && d.step !== null && !d.cycle) markers.push({ step: d.step, kind: 'divergence', label: d.kind });
  return { ticks: run.events.map(e => categoryOf(e.type)), markers: markers.filter(m => m.step >= 0 && m.step < run.events.length) };
}

export interface GoalState { expected: Value; matches: boolean; returned: boolean; result: Value }
/** The goal for this input and whether the program has returned yet, at this step. */
export function goalAt(run: Pick<Run, 'events' | 'goal' | 'preview' | 'expected' | 'passed' | 'result' | 'error'>, step: number): GoalState | null {
  const goal = run.goal ?? (!run.preview && run.expected !== undefined && run.expected !== null ? { expected: run.expected, matches: run.passed } : null);
  if (!goal) return null;
  const returnStep = run.events.findIndex(e => e.type === 'RETURN' && e.state.callstack.length === 1);
  const finished = returnStep >= 0 ? step >= returnStep : !run.error && step >= run.events.length - 1;
  return { expected: goal.expected, matches: goal.matches, returned: finished, result: run.result };
}

/** A question that makes an edge case worth thinking about, chosen from the case's name. */
const casePrompts: [RegExp, string][] = [
  [/^example$/i, 'The case from the problem statement. Make it pass, then try to break it.'],
  [/your input/i, 'Your own input from Edit input. Predict the result before you watch it run.'],
  [/empty|both empty/i, 'Nothing to process: what should come back, and does your loop even start?'],
  [/single|one (value|item|element)|two (elements|characters|values)|one item/i, 'The smallest inputs: do your loop bounds and indices still hold?'],
  [/case matters|space/i, 'Exact characters: do uppercase letters and spaces change the answer?'],
  [/no pair|absent|no overlap|none|no zeroes|no repeat|nothing|falling/i, 'No valid answer exists: does your code return the right “nothing”?'],
  [/repeat|duplicate|same|equal|all one|three|one side/i, 'Repeated values: can your code tell equal values at different positions apart?'],
  [/negative|zero|mixed signs/i, 'Negatives and zero: does any assumption about positive numbers break?'],
  [/end|start|boundary|first|last|whole|longer|before|after|peak|dip/i, 'At the edges: do your indices reach the first and last positions?'],
  [/tie/i, 'A tie: which answer does the contract ask for?'],
];
export const casePrompt = (name: string) => casePrompts.find(([pattern]) => pattern.test(name))?.[1] ?? 'Predict the result before you watch it run.';

/** Where a failed read pointed, relative to the sequence it read. */
export const ghostIndex = (access: { key: Value; size: number }) => typeof access.key === 'number' ? (access.key < 0 ? access.size + access.key : access.key) : null;
