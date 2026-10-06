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
  LINK_WRITE: 'write', HEAP_PUSH: 'insert', HEAP_POP: 'insert', HEAP_BUILD: 'write', QUEUE_PUSH: 'insert', QUEUE_POP: 'insert', BIT_OP: 'compare',
};
export const categoryOf = (type: string): Category => categories[type] || 'state';

const json = (value: unknown) => JSON.stringify(value);
const isIdentifier = (text?: string) => !!text && /^[A-Za-z]\w*$/.test(text);
const sameFrame = (a?: TraceEvent, b?: TraceEvent) => !!a && !!b && json(a.state.callstack) === json(b.state.callstack);

/** Variables that index each sequence: the names the code used inside its brackets. A name that never indexed it
 * is not its pointer, whatever it is called. */
export function pointerNames(events: TraceEvent[]): Record<string, string[]> {
  const names: Record<string, string[]> = {};
  const used: Record<string, Set<string>> = {};
  const add = (structure: string, name: string) => { (names[structure] ||= []).includes(name) || names[structure].push(name); };
  for (const event of events) {
    const read = event.type === 'ARRAY_ACCESS' && event.meta.structure && isIdentifier(event.meta.index) ? [event.meta.structure, event.meta.index!] : null;
    const failed = event.meta.access && isIdentifier(event.meta.access.index) ? [event.meta.access.structure, event.meta.access.index] : null;
    for (const [structure, name] of [read, failed].filter(Boolean) as string[][]) { (used[name] ||= new Set()).add(structure); add(structure, name); }
  }
  // Left-hand names sit on top, as in most textbook drawings; others keep their first-use order.
  const rank = (name: string) => { const i = ['i', 'left', 'lo', 'low', 'start', 'slow', 'write'].indexOf(name); return i < 0 ? 100 : i; };
  for (const list of Object.values(names)) list.sort((a, b) => rank(a) - rank(b));
  return names;
}

/** Variables that index each grid, by the same rule: names the code put in its row brackets (grid[r]) and in
 * its column brackets (grid[r][c], read or written). A name that never indexed the grid is not its pointer. */
export function gridPointerNames(events: TraceEvent[]): Record<string, { rows: string[]; cols: string[] }> {
  const grids = events.flatMap(e => e.state.structures.filter(s => s.type === 'matrix').map(s => s.id)).filter((id, i, all) => all.indexOf(id) === i);
  const names: Record<string, { rows: string[]; cols: string[] }> = {};
  const add = (grid: string, axis: 'rows' | 'cols', name: string) => { const list = (names[grid] ||= { rows: [], cols: [] })[axis]; if (!list.includes(name)) list.push(name); };
  const used = (structure: string, index: string | undefined) => {
    if (!isIdentifier(index)) return;
    if (grids.includes(structure)) add(structure, 'rows', index!);
    else for (const grid of grids) if (structure.startsWith(`${grid}[`) && structure.endsWith(']')) add(grid, 'cols', index!);
  };
  for (const event of events) {
    if (event.type === 'ARRAY_ACCESS' && event.meta.structure) used(event.meta.structure, event.meta.index);
    if (event.meta.access) used(event.meta.access.structure, event.meta.access.index);
    // A write names its targets: several in meta.targets, a single one in its detail ("grid[r][c] updated.").
    const targets = event.type !== 'ARRAY_WRITE' ? [] : event.meta.targets?.length ? event.meta.targets : /^(.+?) updated\.$/.exec(event.detail)?.[1].split(', ') || [];
    for (const target of targets) for (const grid of grids) {
      const cell = target.startsWith(`${grid}[`) ? /^\[\s*([A-Za-z]\w*)\s*\](?:\[\s*([A-Za-z]\w*)\s*\])?$/.exec(target.slice(grid.length)) : null;
      if (cell) { add(grid, 'rows', cell[1]); if (cell[2]) add(grid, 'cols', cell[2]); }
    }
  }
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

/** The range between two pointers, when the run shows they bound one: see rangePairs. */
export function pointerRange(pointers: Pointer[], pair?: [string, string] | null): [number, number] | null {
  if (!pair) return null;
  const left = pointers.find(p => p.name === pair[0]), right = pointers.find(p => p.name === pair[1]);
  return left && right && !left.outside && !right.outside ? [Math.min(left.index, right.index), Math.max(left.index, right.index)] : null;
}

/** For each sequence, the two of its pointers that bound a range, from how they move: each only ever moves one way
 * within a call (a sliding window, pointers closing in, a search interval). A pointer that jumps back, as an inner
 * loop's index does each pass, bounds nothing. The first such pair by first use, whatever the names. */
export function rangePairs(events: TraceEvent[], names: Record<string, string[]>): Record<string, [string, string]> {
  const ways: Record<string, Set<number>> = {};
  let previous: TraceEvent | undefined;
  for (const event of events) {
    if (previous && sameFrame(previous, event)) {
      const was = new Map(previous.state.variables.map(v => [v.id, v.value]));
      for (const v of event.state.variables) {
        const before = was.get(v.id);
        if (typeof v.value === 'number' && typeof before === 'number' && v.value !== before) (ways[v.id] ||= new Set()).add(Math.sign(v.value - before));
      }
    }
    previous = event;
  }
  const steady = (name: string) => (ways[name]?.size ?? 0) <= 1;
  const pairs: Record<string, [string, string]> = {};
  for (const [lane, list] of Object.entries(names)) {
    for (let a = 0; a < list.length && !pairs[lane]; a++) for (let b = a + 1; b < list.length && !pairs[lane]; b++) {
      if (steady(list[a]) && steady(list[b]) && (ways[list[a]]?.size || ways[list[b]]?.size)) pairs[lane] = [list[a], list[b]];
    }
  }
  return pairs;
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

/**
 * Which values of a sequence moved in one step, as [to, from] pairs, and which earlier positions' values left it:
 * only when the step provably moved values rather than wrote new ones. Either the same values in a new order (a
 * sort, a reverse, a sift), or a length change (an insert, a removal, a push or pop at any end). Each value keeps
 * its own position when it can; otherwise it comes from the nearest earlier position holding the same value. A
 * value with no earlier position is new, not moved. Same-length steps that change the values are writes: see
 * copySources.
 */
export function valueMoves(before: Value[], after: Value[]): { moves: [number, number][]; gone: number[]; added: number[] } {
  const was = before.map(v => json(v)), now = after.map(v => json(v));
  const sorted = (keys: string[]) => [...keys].sort().join('\u0000');
  if (was.length === now.length && (sorted(was) !== sorted(now) || was.every((k, i) => k === now[i]))) return { moves: [], gone: [], added: [] };
  const used = new Set<number>(), from: (number | null)[] = now.map(() => null);
  now.forEach((k, i) => { if (was[i] === k) { from[i] = i; used.add(i); } });
  now.forEach((k, i) => {
    if (from[i] !== null) return;
    let best = -1;
    was.forEach((w, j) => { if (w === k && !used.has(j) && (best < 0 || Math.abs(j - i) < Math.abs(best - i))) best = j; });
    if (best >= 0) { from[i] = best; used.add(best); }
  });
  return { moves: from.flatMap((j, i) => j !== null && j !== i ? [[i, j] as [number, number]] : []), gone: was.flatMap((_, j) => used.has(j) ? [] : [j]), added: from.flatMap((j, i) => j === null ? [i] : []) };
}

/** Writes that copied another position of the same sequence (a[j + 1] = a[j]), as [to, from] pairs: the written
 * value equals a value the same line read from that position just before, in the same call. */
export function copySources(events: TraceEvent[], step: number, structure: string, written: number[]): [number, number][] {
  const event = events[step];
  const now = event?.state.structures.find(s => s.id === structure);
  if (!now?.values || !written.length) return [];
  const pairs: [number, number][] = [];
  for (const to of written) {
    for (let i = step - 1; i >= 0 && events[i].line === event.line && sameFrame(events[i], event); i--) {
      const read = events[i];
      if (read.type !== 'ARRAY_ACCESS' || read.meta.structure !== structure) continue;
      const at = position(read.meta.key ?? null, now.length ?? now.values.length);
      if (at >= 0 && at !== to && json(read.meta.value) === json(now.values[to])) { pairs.push([to, at]); break; }
    }
  }
  return pairs;
}

/** How a lane's values travel in a step, for the lane to animate: values that moved to a new position, writes
 * that copied a value from another position, values that left the lane (with where they were), new values that
 * joined it, and the positions a shorter lane gave up. Nothing travels between calls, or across a jump. */
export interface LaneMotion { moves: [number, number][]; copies: [number, number][]; gone: { from: number; value: Value }[]; added: number[]; vacated: number[] }
export function laneMotion(events: TraceEvent[], step: number, id: string, limit = 40): LaneMotion {
  const none: LaneMotion = { moves: [], copies: [], gone: [], added: [], vacated: [] };
  const previous = events[step - 1], current = events[step];
  if (!sameFrame(previous, current)) return none;
  const lane = (e: TraceEvent) => e.state.structures.find(s => s.id === id && (s.type === 'array' || s.type === 'string'))?.values;
  const was = lane(previous), now = lane(current);
  if (!was || !now) return none;
  // Matched on the whole lane, so a value entering or leaving past the cells on view still shifts the rest; only
  // the cells on view (the first `limit`) move.
  const { moves, gone, added } = valueMoves(was, now);
  const shown = (i: number) => i < limit;
  if (moves.length || gone.length || added.length) return {
    moves: moves.filter(([to, from]) => shown(to) && shown(from)), copies: [], gone: gone.filter(shown).map(from => ({ from, value: was[from] })),
    added: added.filter(shown), vacated: was.flatMap((_, i) => i >= now.length && shown(i) ? [i] : []),
  };
  const written = now.flatMap((v, i) => shown(i) && json(v) !== json(was[i]) ? [i] : []);
  return { ...none, copies: copySources(events, step, id, written) };
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
/** What one step did to the program's structures, as short phrases: swaps, writes, keys stored, changed and removed. */
function structureChanges(previous: TraceEvent | undefined, event: TraceEvent) {
  const change = stepChange(previous, event);
  const find = (id: string) => event.state.structures.find(s => s.id === id);
  const entry = (id: string, key: string) => find(id)?.entries?.find(e => json(e.key) === key)?.value ?? null;
  return [
    ...Object.entries(change.swapped).map(([id, [a, b]]) => `swap ${id}[${a}]↔[${b}]`),
    ...Object.entries(change.written).filter(([id]) => !change.swapped[id]).flatMap(([id, indices]) => indices.map(i => `${id}[${i}] = ${describe(find(id)?.values?.[i] ?? null)}`)),
    ...Object.entries(change.added).flatMap(([id, keys]) => keys.map(k => `${id} + ${keyLabel(k)}${find(id)?.type === 'hashmap' ? ` → ${describe(entry(id, k))}` : ''}`)),
    ...Object.entries(change.changed).flatMap(([id, keys]) => keys.map(k => `${id}[${keyLabel(k)}] → ${describe(entry(id, k))}`)),
    ...Object.entries(change.removed).flatMap(([id, gone]) => gone.map(e => `${id} − ${describe(e.key)}`)),
  ];
}
/** What one step changed, in the program's own names: structures, node links, node pointers and variables.
 * Compared within one frame only; a call or a return starts a different frame. */
export function changeLabels(previous: TraceEvent | undefined, event: TraceEvent): string[] {
  if (!previous || !sameFrame(previous, event)) return [];
  const parts = structureChanges(previous, event);
  for (const s of event.state.structures) {
    const old = s.type === 'nodes' ? previous.state.structures.find(x => x.id === s.id && x.type === 'nodes') : undefined;
    if (!old) continue;
    const label = (nodes: typeof s.nodes, id: number | null | undefined) => id == null ? 'None' : describe(nodes?.find(n => n.id === id)?.label ?? null);
    const before = new Map((old.nodes || []).map(n => [n.id, n]));
    for (const n of s.nodes || []) for (const [field, to] of Object.entries(n.links)) {
      const was = before.get(n.id)?.links[field];
      if (before.has(n.id) && was !== to) parts.push(`${label(s.nodes, n.id)}.${field} → ${label(s.nodes, to)}`);
    }
    for (const [name, id] of Object.entries(s.refs || {})) if (name in (old.refs || {}) && old.refs![name] !== id) parts.push(`${name} → ${id == null ? 'None' : `node ${label(s.nodes, id)}`}`);
  }
  const was = new Map(previous.state.variables.map(v => [v.id, v.value]));
  for (const v of event.state.variables) if (!was.has(v.id)) parts.push(`${v.id} = ${describe(v.value)}`);
    else if (json(was.get(v.id)) !== json(v.value)) parts.push(`${v.id}: ${describe(was.get(v.id))} → ${describe(v.value)}`);
  return parts;
}
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
      sample(event, structureChanges(previous, event).join(', ') || event.detail.replace(/\.$/, ''));
    } else if (event.type === 'LINK_WRITE') {
      // A re-link changes the nodes, not a variable: name the link it made (curr.next = prev → 4.next → 3).
      const links = changeLabels(previous, event).filter(part => /^\S+\.\w+ → /.test(part));
      sample(event, links.join(', ') || event.detail.replace(/\.$/, ''));
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

/** A design problem's trace: the class's own operations (Trie.insert, RecentCounter.ping) run at the top, not solve. */
/** A design problem's trace: a class's operations, each its own top-level call (the constructor first). A function's
 * trace (solve, or LeetCode's Solution.twoSum) is one top-level call throughout. */
export const isDesignTrace = (events: TraceEvent[]) => {
  const first = events.find(e => e.state.callstack.length > 0)?.state.callstack[0];
  return !!first && (first.endsWith('__init__') || events.some(e => e.state.callstack.length > 0 && e.state.callstack[0] !== first));
};
/** The step at which the program returned, or -1 when the trace does not show it. For solve, its own return.
 * A design problem returns once, after its last operation: every operation returns at the top level, so
 * the program has returned only at the last operation's return — never in a stopped or cut-off trace. */
export function programReturn(events: TraceEvent[], truncated = false): number {
  const top = (e: TraceEvent) => e.state.callstack.length === 1;
  if (!isDesignTrace(events)) return events.findIndex(e => e.type === 'RETURN' && top(e));
  if (truncated || events.some(e => e.type === 'ERROR')) return -1;
  let last = -1;
  events.forEach((e, i) => { if (e.type === 'RECURSION_CALL' && top(e)) last = i; });
  return last < 0 ? -1 : events.findIndex((e, i) => i > last && (e.type === 'RETURN' || e.type === 'RECURSION_RETURN') && top(e));
}
/** The lane solve returned by name: only a bare `return name` is that lane (`return res[::-1]` is not). */
export function returnedLane(events: TraceEvent[]): string | null {
  if (isDesignTrace(events)) return null;
  const at = programReturn(events);
  return at < 0 ? null : /^return\s+([A-Za-z_]\w*)\s*(#.*)?$/.exec(events[at].source.trim())?.[1] ?? null;
}

export interface GoalState { expected: Value; matches: boolean; returned: boolean; result: Value; returnStep: number | null; computed?: boolean }
/** The goal for this input and whether the program has returned yet, at this step: the same rule for live
 * previews and explicit runs. */
export function goalAt(run: Pick<Run, 'events' | 'goal' | 'preview' | 'expected' | 'passed' | 'result' | 'error' | 'truncated'>, step: number): GoalState | null {
  const goal = run.goal ?? (!run.preview && run.expected !== undefined && run.expected !== null ? { expected: run.expected, matches: run.passed } : null);
  if (!goal) return null;
  const returnStep = programReturn(run.events, run.truncated);
  const finished = returnStep >= 0 ? step >= returnStep : !run.error && step >= run.events.length - 1;
  return { expected: goal.expected, matches: goal.matches, returned: finished, result: run.result, returnStep: returnStep >= 0 ? returnStep : null, ...('computed' in goal && goal.computed ? { computed: true } : {}) };
}
/** The goal row under a lane: once the program has returned a list that differs, under the lane it returned by name. */
export const goalRowFor = (goal: GoalState | null, lane: string, returned: string | null): Value[] | null =>
  goal?.returned && Array.isArray(goal.expected) && !goal.matches && returned !== null && lane === returned ? goal.expected : null;

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

/** The work the run did, so far and in all: each kind counted from its recorded events. */
const WORK: [string, string[]][] = [['reads', ['ARRAY_ACCESS']], ['lookups', ['HASHMAP_LOOKUP']], ['comparisons', ['COMPARE']],
  ['writes', ['ARRAY_WRITE', 'LINK_WRITE', 'HASHMAP_INSERT', 'HASHMAP_DELETE', 'HEAP_BUILD']], ['pushes & pops', ['STACK_PUSH', 'STACK_POP', 'QUEUE_PUSH', 'QUEUE_POP', 'HEAP_PUSH', 'HEAP_POP']],
  ['loop passes', ['LOOP_START']], ['calls', ['RECURSION_CALL']]];
export function workDone(events: TraceEvent[], step: number) {
  return WORK.map(([label, types]) => {
    // A node built inside a call (ListNode(x)) is not a call of the algorithm.
    const counts = (e: TraceEvent) => types.includes(e.type) && !(e.type === 'RECURSION_CALL' && (e.meta.call?.depth ?? 1) > 1 && e.meta.call?.fn.endsWith('__init__'));
    let done = 0, total = 0;
    events.forEach((e, i) => { if (counts(e)) { total++; if (i <= step) done++; } });
    return { label, done, total };
  }).filter(w => w.total > (w.label === 'calls' ? 1 : 0));  // One call is the program itself, not work worth counting.
}

/** How often the code has read each position of one sequence so far: repeated reads are repeated work.
 * Counted only within one call (`frames`: the call running at each event) and while the sequence keeps its
 * length; a sequence of the same name in another call, or one that grew, is not provably the same list (null). */
export function readCounts(events: TraceEvent[], step: number, id: string, frames: (number | null)[]): Record<number, number> | null {
  const counts: Record<number, number> = {};
  let frame: number | null | undefined, length: number | undefined;
  for (let i = 0; i <= step && i < events.length; i++) {
    const e = events[i];
    if (e.type !== 'ARRAY_ACCESS' || e.meta.structure !== id) continue;
    const s = e.state.structures.find(x => x.id === id);
    const size = s?.length ?? s?.values?.length ?? 0;
    if (frame === undefined) { frame = frames[i]; length = size; } else if (frame !== frames[i] || length !== size) return null;
    const at = position(e.meta.key ?? null, size);
    if (at >= 0 && at < size) counts[at] = (counts[at] || 0) + 1;
  }
  return counts;
}

/** What each variable is, from the code's own text and the trace: an index into a sequence, a loop variable, a
 * counter or running total (an augmented assignment to it), or a value kept with max()/min(). Nothing is guessed:
 * a variable none of these describe gets no role. */
export function variableRoles(events: TraceEvent[], code: string, names: Record<string, string[]>) {
  const roles: Record<string, string> = {};
  const loops = new Set(events.filter(e => e.type === 'LOOP_START').flatMap(e => /^(.+?) updated\.$/.exec(e.detail)?.[1].split(', ') || []));
  const indexes: Record<string, string> = {};
  for (const [structure, list] of Object.entries(names)) for (const name of list) indexes[name] ??= structure;
  const literal = (name: string) => name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  for (const name of new Set(events.flatMap(e => e.state.variables.map(v => v.id)))) {
    const n = literal(name);
    const role = indexes[name] ? `${loops.has(name) ? 'loop index' : 'index'} into ${indexes[name]}`
      : loops.has(name) ? 'loop variable'
      : new RegExp(`(^|\\n)\\s*${n}\\s*[+-]=\\s*1\\s*(#.*)?$`, 'm').test(code) ? 'counter · += 1'
      : new RegExp(`(^|\\n)\\s*${n}\\s*[+-]=`, 'm').test(code) ? 'running total · +='
      : new RegExp(`(^|\\n)\\s*${n}\\s*=\\s*max\\(`, 'm').test(code) ? 'kept with max()'
      : new RegExp(`(^|\\n)\\s*${n}\\s*=\\s*min\\(`, 'm').test(code) ? 'kept with min()'
      : '';
    if (role) roles[name] = role;
  }
  return roles;
}

/** A node pointer's value as the memory panel shows it: the node it points at, by label, or None. Undefined when
 * the snapshot has no such pointer. */
export function nodeRef(event: TraceEvent, name: string): Value | undefined {
  const s = event.state.structures.find(x => x.type === 'nodes');
  if (!s?.refs || !(name in s.refs)) return undefined;
  const id = s.refs[name];
  return id == null ? null : `node ${describe(s.nodes?.find(n => n.id === id)?.label ?? null)}`;
}
const variableValue = (event: TraceEvent, name: string) => event.state.variables.find(v => v.id === name)?.value;
/** The values a variable (or, with `read`, a node pointer) held before this step, within the call running now:
 * oldest first, at most `limit`. */
export function valueTrail(events: TraceEvent[], frames: (number | null)[], step: number, name: string, limit = 3, read: (event: TraceEvent, name: string) => Value | undefined = variableValue) {
  const trail: Value[] = [];
  const frame = frames[step];
  let last: string | undefined = events[step] ? json(read(events[step], name)) : undefined;
  for (let i = step - 1; i >= 0 && trail.length < limit; i--) {
    if (frames[i] !== frame) continue;  // A call this one made: its variables are its own.
    const value = read(events[i], name);
    if (value === undefined) break;  // Not set yet before this point.
    if (json(value) !== last) { trail.unshift(value); last = json(value); }
    if (events[i].type === 'RECURSION_CALL' && events[i].meta.call?.id === frame) break;  // This call's start.
  }
  return trail;
}

/** A call as written: its function and argument values, in the order the function declares its parameters. */
const callText = (call: NonNullable<TraceEvent['meta']['call']>) => `${call.fn.split('.').pop()}(${(call.order ?? Object.keys(call.args)).filter(name => name in call.args).map(name => describe(call.args[name])).join(', ')})`;
export interface Phase { start: number; end: number; label: string; kind: 'setup' | 'pass' | 'after' | 'call' }
/**
 * The run in chapters, from its own structure: each pass of the outermost loop of the top-level call (the loop
 * with the least indented line), or, without one, each call the top-level call made (and the stretches between
 * them); a design problem's operations are its chapters. Null when that gives fewer than two or too many to read.
 */
export function phases(events: TraceEvent[], code: string, limit = 80): Phase[] | null {
  if (!events.length) return null;
  const lines = code.split('\n');
  const indent = (line: number) => (lines[line - 1] || '').match(/^\s*/)![0].replace(/\t/g, '    ').length;
  const top = (e: TraceEvent) => e.state.callstack.length === 1;
  const out: Phase[] = [];
  // A chapter that would end before it starts (a loop right after another) gives way to the one starting there.
  const open = (start: number, label: string, kind: Phase['kind']) => {
    while (out.length && out[out.length - 1].start >= start) out.pop();
    if (out.length) out[out.length - 1].end = start - 1;
    out.push({ start, end: events.length - 1, label, kind });
  };
  if (isDesignTrace(events)) {
    events.forEach((e, i) => { if (e.type === 'RECURSION_CALL' && e.meta.call?.depth === 1) open(i, callText(e.meta.call), 'call'); });
  } else {
    const loopLines = [...new Set(events.filter(e => e.type === 'LOOP_START' && top(e)).map(e => e.line))];
    const outer = loopLines.length ? Math.min(...loopLines.map(indent)) : null;
    if (outer !== null) {
      const passes: Record<number, number> = {};
      events.forEach((e, i) => {
        if (!top(e) || indent(e.line) !== outer || !loopLines.includes(e.line)) return;
        if (e.type === 'LOOP_START') {
          passes[e.line] = (passes[e.line] || 0) + 1;
          const names = /^(.+?) updated\.$/.exec(e.detail)?.[1].split(', ') || [];
          const values = names.map(name => e.state.variables.find(v => v.id === name)).filter(Boolean).map(v => `${v!.id} = ${describe(v!.value)}`);
          if (!out.length && i > 0) open(0, 'before the loop', 'setup');
          open(i, `pass ${passes[e.line]}${values.length ? ` · ${values.join(', ')}` : ''}`, 'pass');
        } else if (e.type === 'LOOP_END' && i < events.length - 1) open(i + 1, 'after the loop', 'after');
      });
    } else {
      // The shallowest level with more than one call: solve's own calls, or, when solve hands everything to one
      // helper (go(0, [])), the calls that helper makes.
      const calls = (depth: number) => events.filter(e => e.type === 'RECURSION_CALL' && e.meta.call?.depth === depth && !e.meta.call.fn.endsWith('__init__')).length;
      const deepest = Math.max(0, ...events.map(e => e.meta.call?.depth ?? 0));
      let level = 2;
      while (level < deepest && calls(level) < 2) level++;
      const root = events.find(e => e.type === 'RECURSION_CALL' && e.meta.call?.depth === 1)?.meta.call;
      events.forEach((e, i) => {
        const call = e.type === 'RECURSION_CALL' ? e.meta.call : undefined;
        if (call?.depth === level && !call.fn.endsWith('__init__')) {
          if (!out.length && i > 0) open(0, `${root ? root.fn : 'solve'} begins`, 'setup');
          open(i, callText(call), 'call');
        } else if (e.type === 'RECURSION_RETURN' && e.state.callstack.length === level && !e.state.callstack[level - 1].endsWith('__init__') && out.length && i < events.length - 1 && events[i + 1].type !== 'RECURSION_CALL') {
          open(i + 1, `back in ${e.state.callstack[level - 2] ?? 'solve'}`, 'after');  // The calling level, between the calls it made.
        }
      });
    }
  }
  return out.length >= 2 && out.length <= limit ? out : null;
}

/** Where a failed read pointed, relative to the sequence it read. */
export const ghostIndex = (access: { key: Value; size: number }) => typeof access.key === 'number' ? (access.key < 0 ? access.size + access.key : access.key) : null;
