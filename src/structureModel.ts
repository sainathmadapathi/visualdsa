import type { NodeRec, Structure, TraceEvent, Value } from './types';

/**
 * Layouts for the learner's data structures. Pure functions of one recorded snapshot: linked lists
 * as chains, trees by in-order position and depth, tries and n-ary trees by their children, graphs
 * by a deterministic force layout, and recursion as the tree of calls made so far.
 */

export interface PlacedNode extends NodeRec { x: number; y: number; role: 'list' | 'tree' | 'nary' | 'other' }
export interface SceneEdge { key: string; from: number; to: number; field: string; label?: string; kind: 'next' | 'prev' | 'child' | 'extra'; d: string }
export interface Scene { width: number; height: number; nodes: PlacedNode[]; edges: SceneEdge[]; ends: { key: string; x: number; y: number }[]; kinds: Set<PlacedNode['role']> }

export const LIST_W = 58, LIST_H = 36, TREE_D = 40;
const PAD = 26, BADGE = 30;

const half = (role: PlacedNode['role']) => role === 'list' ? { w: LIST_W / 2, h: LIST_H / 2 } : { w: TREE_D / 2, h: TREE_D / 2 };

/** Every node of one snapshot placed: lists in rows by chain, trees and tries below them. */
export function sceneOf(structure: Structure): Scene {
  const all = structure.nodes || [];
  const byId = new Map(all.map(n => [n.id, n]));
  const isTree = (n: NodeRec) => 'left' in n.links || 'right' in n.links;
  const isList = (n: NodeRec) => !isTree(n) && 'next' in n.links;
  const kidOf = new Set(all.flatMap(n => n.kids.map(k => k[1])));
  const isNary = (n: NodeRec) => !isTree(n) && !isList(n) && (n.kids.length > 0 || kidOf.has(n.id));
  const placed = new Map<number, PlacedNode>();
  let top = PAD + BADGE;
  let width = 0;
  const place = (n: NodeRec, x: number, y: number, role: PlacedNode['role']) => { placed.set(n.id, { ...n, x, y, role }); width = Math.max(width, x + PAD + LIST_W); };
  const ends: Scene['ends'] = [];

  // Linked lists: one row per chain, starting at nodes nothing points to (a pure cycle, where every node is
  // pointed to, starts at its first node in recorded order).
  const lists = all.filter(isList);
  if (lists.length) {
    const incoming = new Set(lists.map(n => n.links.next).filter((t): t is number => t != null && byId.has(t)));
    const starts = [...lists.filter(n => !incoming.has(n.id)), ...lists].map(n => n.id);
    const seen = new Set<number>();
    let row = 0;
    for (const start of starts) {
      if (seen.has(start)) continue;
      let at: number | null | undefined = start, i = 0;
      while (at != null && byId.has(at) && !seen.has(at) && isList(byId.get(at)!)) {
        seen.add(at);
        place(byId.get(at)!, PAD + i * (LIST_W + 34), top + row * (LIST_H + 26 + BADGE), 'list');
        at = byId.get(at)!.links.next;
        i++;
      }
      if (at == null && i > 0) ends.push({ key: `end-${start}`, x: PAD + i * (LIST_W + 34) - 6, y: top + row * (LIST_H + 26 + BADGE) + LIST_H / 2 });
      row++;
    }
    top += row * (LIST_H + 26 + BADGE) + 6;
  }

  // Binary trees: x by in-order position, y by depth.
  const trees = all.filter(isTree);
  if (trees.length) {
    const childOf = new Set(trees.flatMap(n => [n.links.left, n.links.right]).filter((t): t is number => t != null));
    const roots = [...trees.filter(n => !childOf.has(n.id)), ...trees];
    const order = new Map<number, { index: number; depth: number }>();
    let index = 0, deepest = 0;
    const walk = (id: number | null | undefined, depth: number) => {
      if (id == null || order.has(id) || !byId.has(id) || !isTree(byId.get(id)!)) return;
      order.set(id, { index: -1, depth });
      walk(byId.get(id)!.links.left, depth + 1);
      order.get(id)!.index = index++;
      deepest = Math.max(deepest, depth);
      walk(byId.get(id)!.links.right, depth + 1);
    };
    for (const root of roots) walk(root.id, 0);
    const gap = 46;
    for (const [id, at] of order) place(byId.get(id)!, PAD + at.index * gap, top + at.depth * 66, 'tree');
    top += (deepest + 1) * 66 + BADGE;
  }

  // Tries and n-ary trees: leaves side by side, each parent centred over its children.
  const nary = all.filter(isNary);
  if (nary.length) {
    const roots = [...nary.filter(n => !kidOf.has(n.id)), ...nary];
    let next = 0, deepest = 0;
    const done = new Set<number>();
    const lay = (id: number, depth: number): number => {
      const n = byId.get(id)!;
      done.add(id);
      deepest = Math.max(deepest, depth);
      const xs = n.kids.filter(([, k]) => byId.has(k) && !done.has(k)).map(([, k]) => lay(k, depth + 1));
      const x = xs.length ? (xs[0] + xs[xs.length - 1]) / 2 : PAD + next++ * 50;
      place(n, x, top + depth * 72, 'nary');
      return x;
    };
    for (const root of roots) if (!done.has(root.id)) lay(root.id, 0);
    top += (deepest + 1) * 72 + BADGE;
  }

  const rest = all.filter(n => !placed.has(n.id));
  rest.forEach((n, i) => place(n, PAD + i * (LIST_W + 30), top, 'other'));
  if (rest.length) top += LIST_H + BADGE;

  // Edges: next arrows (straight to the right neighbour, arcs otherwise), prev arcs below, children, other links dashed.
  const edges: SceneEdge[] = [];
  const keys = new Map<string, number>();  // Two list attributes both have a child 0: each edge keeps its own key.
  const centre = (n: PlacedNode) => ({ cx: n.x + half(n.role).w, cy: n.y + half(n.role).h });
  for (const n of placed.values()) {
    const a = centre(n);
    const edge = (to: number, field: string, kind: SceneEdge['kind'], label?: string) => {
      const target = placed.get(to);
      if (!target) return;
      const b = centre(target);
      let d: string;
      if (kind === 'next' || kind === 'prev') {
        const forward = target.role === 'list' && Math.abs(target.y - n.y) < 2 && target.x > n.x && target.x - n.x < LIST_W + 40;
        if (forward && kind === 'next') d = `M ${n.x + LIST_W} ${a.cy} L ${target.x - 3} ${b.cy}`;
        else {
          const lift = kind === 'prev' ? LIST_H / 2 + 12 + Math.min(40, Math.abs(b.cx - a.cx) / 6) : -(LIST_H / 2 + 14 + Math.min(46, Math.abs(b.cx - a.cx) / 5));
          const y1 = a.cy + (kind === 'prev' ? LIST_H / 2 : -LIST_H / 2), y2 = b.cy + (kind === 'prev' ? LIST_H / 2 : -LIST_H / 2);
          d = `M ${a.cx} ${y1} C ${a.cx} ${y1 + lift} ${b.cx} ${y2 + lift} ${b.cx} ${y2 + (kind === 'prev' ? 3 : -3)}`;
        }
      } else {
        const r = target.role === 'list' ? LIST_H / 2 : TREE_D / 2;
        const dx = b.cx - a.cx, dy = b.cy - a.cy, len = Math.max(1, Math.hypot(dx, dy));
        d = `M ${a.cx + dx / len * r} ${a.cy + dy / len * r} L ${b.cx - dx / len * (r + 3)} ${b.cy - dy / len * (r + 3)}`;
      }
      const key = `${n.id}-${field}-${label ?? ''}`, repeat = keys.get(key) ?? 0;
      keys.set(key, repeat + 1);
      edges.push({ key: repeat ? `${key}~${repeat}` : key, from: n.id, to, field, label, kind, d });
    };
    for (const [field, to] of Object.entries(n.links)) {
      if (to == null) continue;
      if (field === 'next' && n.role === 'list') edge(to, field, 'next');
      else if (field === 'prev' && n.role === 'list') edge(to, field, 'prev');
      else if ((field === 'left' || field === 'right') && n.role === 'tree') edge(to, field, 'child');
      else edge(to, field, 'extra');
    }
    for (const [label, to] of n.kids) edge(to, 'kid', n.role === 'nary' ? 'child' : 'extra', String(label));
  }
  const nodes = [...placed.values()];
  return { width: Math.max(width, ...nodes.map(n => n.x + PAD + LIST_W)), height: top + 4, nodes, edges, ends, kinds: new Set(nodes.map(n => n.role)) };
}

/** Which links changed since the previous snapshot of the same frame, and which nodes are new. */
export function nodeChanges(previous: Structure | undefined, current: Structure) {
  const before = new Map((previous?.nodes || []).map(n => [n.id, n]));
  const relinked = new Set<string>(), fresh = new Set<number>(), relabelled = new Set<number>();
  if (!previous) return { relinked, fresh, relabelled };
  for (const n of current.nodes || []) {
    const old = before.get(n.id);
    if (!old) { fresh.add(n.id); continue; }
    if (JSON.stringify(old.label) !== JSON.stringify(n.label)) relabelled.add(n.id);
    for (const [field, to] of Object.entries(n.links)) if (old.links[field] !== to && to != null) relinked.add(`${n.id}-${field}-`);
  }
  return { relinked, fresh, relabelled };
}

/** Nodes some variable has pointed at, at this step or before it: the part of the structure the code has walked. */
export function walkedNodes(events: TraceEvent[], step: number) {
  const walked = new Set<number>();
  for (let i = 0; i <= step && i < events.length; i++) for (const s of events[i].state.structures) if (s.type === 'nodes') for (const id of Object.values(s.refs || {})) if (id != null) walked.add(id);
  return walked;
}

/** A deterministic force layout (same graph, same picture), in a w × h box. */
const layouts = new Map<string, { x: number; y: number }[]>();
export function graphLayout(count: number, edges: [number, number, Value][], w: number, h: number) {
  const key = `${count}|${w}|${h}|${edges.map(e => `${e[0]}-${e[1]}`).join(',')}`;
  const cached = layouts.get(key);
  if (cached) return cached;
  const cx = w / 2, cy = h / 2, radius = Math.min(w, h) / 2 - 30;
  const pos = Array.from({ length: count }, (_, i) => ({ x: cx + radius * Math.cos(2 * Math.PI * i / Math.max(count, 1) - Math.PI / 2), y: cy + radius * Math.sin(2 * Math.PI * i / Math.max(count, 1) - Math.PI / 2) }));
  if (count > 2 && edges.length) {
    const k = Math.sqrt((w * h) / count) * 0.62;
    let heat = Math.min(w, h) / 8;
    for (let round = 0; round < 260; round++) {
      const shift = pos.map(() => ({ x: 0, y: 0 }));
      for (let i = 0; i < count; i++) for (let j = i + 1; j < count; j++) {
        const dx = pos[i].x - pos[j].x, dy = pos[i].y - pos[j].y, d = Math.max(0.01, Math.hypot(dx, dy)), f = k * k / d;
        shift[i].x += dx / d * f; shift[i].y += dy / d * f; shift[j].x -= dx / d * f; shift[j].y -= dy / d * f;
      }
      for (const [a, b] of edges) {
        if (a === b || !pos[a] || !pos[b]) continue;
        const dx = pos[a].x - pos[b].x, dy = pos[a].y - pos[b].y, d = Math.max(0.01, Math.hypot(dx, dy)), f = d * d / k;
        shift[a].x -= dx / d * f; shift[a].y -= dy / d * f; shift[b].x += dx / d * f; shift[b].y += dy / d * f;
      }
      pos.forEach((p, i) => {
        const d = Math.max(0.01, Math.hypot(shift[i].x, shift[i].y)), step = Math.min(d, heat);
        p.x = Math.max(26, Math.min(w - 26, p.x + shift[i].x / d * step));
        p.y = Math.max(26, Math.min(h - 26, p.y + shift[i].y / d * step));
      });
      heat *= 0.97;
    }
  }
  if (layouts.size > 64) layouts.clear();
  layouts.set(key, pos);
  return pos;
}

const json = (value: unknown) => JSON.stringify(value);
/** Island maps, as [land, water]. */
const ISLANDS: [Value, Value][] = [['1', '0'], ['#', '.'], [1, 0]];
/** Tables of computed values are never maps, whatever they hold. */
const TABLES = /^(dp|dist|distance|distances|memo|table|cost|costs|best|ways|count|counts|paths|f|t|lcs|ans|res)$/i;
export type MapRole = 'land' | 'water' | 'mark';
/**
 * Whether a grid is an island map, and each value's role in it. Conservative by rule: the grid's first recorded
 * snapshot (`first`, when it has the same shape; otherwise this one) holds exactly the two values of one
 * land/water pair — the characters '1'/'0' or '#'/'.', or the integers 1/0 — and the grid has no table name
 * (dp, dist, memo…). A character map stays a map while every cell is one character, and any other character
 * the code writes is a mark; an integer map stays a map only while 0 and 1 are its only values. Anything else
 * (booleans, [[1, 2], [3, 0]], distances) is a table, drawn by value.
 */
export function islandMap(name: string, rows: Value[][], first: Value[][] = rows): ((value: Value) => MapRole) | null {
  if (TABLES.test(name.split('.').pop() || '')) return null;
  const sameShape = first.length === rows.length && first.every((row, r) => row.length === rows[r].length);
  const basis = new Set((sameShape ? first : rows).flat().map(json));
  const pair = ISLANDS.find(([land, water]) => basis.size === 2 && basis.has(json(land)) && basis.has(json(water)));
  if (!pair) return null;
  const [land, water] = pair.map(json);
  const now = rows.flat();
  if (typeof pair[0] === 'number' ? now.some(v => json(v) !== land && json(v) !== water) : now.some(v => typeof v !== 'string' || v.length !== 1)) return null;
  return value => json(value) === land ? 'land' : json(value) === water ? 'water' : 'mark';
}

const SEEN = /^(vis|visited|seen|used|explored|marked|done)$/i;
/** Cells of a grid that the program's other structures name, by exact coordinates only: an (r, c) pair of
 * in-bounds integers in a visited set or in a queue, stack or heap, and the true cells of a same-shaped visited
 * grid. A longer tuple — (dist, r, c) or (r, c, dist) — is ambiguous and marks nothing. */
export function gridMarks(structures: Structure[], grid: string, [height, width]: [number, number]) {
  const cell = (v: Value) => Array.isArray(v) && v.length === 2 && v.every(x => typeof x === 'number' && Number.isInteger(x) && x >= 0) && (v[0] as number) < height && (v[1] as number) < width ? `${v[0]},${v[1]}` : null;
  const visited = new Set<string>(), queued = new Set<string>();
  for (const s of structures) {
    const name = s.id.split('.').pop()!;
    if (s.type === 'hashset' && SEEN.test(name)) (s.values || []).forEach(v => { const k = cell(v); if (k) visited.add(k); });
    if (s.type === 'array' && (s.kind === 'queue' || s.kind === 'stack' || s.kind === 'heap')) (s.values || []).forEach(v => { const k = cell(v); if (k) queued.add(k); });
    if (s.type === 'matrix' && s.id !== grid && SEEN.test(name) && s.shape?.[0] === height && s.shape?.[1] === width) (s.rows || []).forEach((r, i) => r.forEach((v, j) => { if (v === true || v === 1) visited.add(`${i},${j}`); }));
  }
  return { visited, queued };
}

/** What the program's own structures say about each node of a graph, each under the structure's own name:
 * members of a visited set or of a queue, stack or heap (plain node ids only; a tuple such as (node, dist) is
 * ambiguous and marks nothing), and, when the nodes are numbered 0..n-1, per-node arrays of length n: the
 * true entries of a visited array, the values of one dist-like array (shown below the nodes), colours. */
export function graphMarks(structures: Structure[], labels: Value[]) {
  const count = labels.length;
  const index = (value: Value) => labels.findIndex(l => json(l) === json(value));
  const numbered = labels.every((l, i) => l === i);
  const visited = new Set<number>(), frontier = new Set<number>(), color: Record<number, Value> = {};
  const names = { visited: [] as string[], frontier: [] as string[] };
  const note = (list: string[], name: string) => { if (!list.includes(name)) list.push(name); };
  const order = ['dist', 'distance', 'distances', 'd', 'level', 'levels', 'depth', 'cost', 'time', 'parent'];
  let below: { name: string; values: Value[] } | null = null, rank = order.length;
  for (const s of structures) {
    const name = s.id.split('.').pop()!.toLowerCase(), values = s.values || [];
    if (s.type === 'array' && numbered && count > 0 && values.length === count) {
      if (SEEN.test(name)) values.forEach((v, i) => { if (v === true || v === 1) { visited.add(i); note(names.visited, s.id); } });
      if (order.includes(name) && order.indexOf(name) < rank) { rank = order.indexOf(name); below = { name: s.id, values }; }
      if (/^(color|colors|colour|side|group)$/.test(name)) values.forEach((v, i) => { color[i] = v; });
    }
    if (s.type === 'hashset' && SEEN.test(name)) values.forEach(v => { const i = index(v); if (i >= 0) { visited.add(i); note(names.visited, s.id); } });
    if (s.type === 'array' && (s.kind === 'queue' || s.kind === 'stack' || s.kind === 'heap' || /^(q|queue|stack|st|frontier)$/.test(name))) values.forEach(v => {
      const i = v !== null && typeof v === 'object' ? -1 : index(v);
      if (i >= 0) { frontier.add(i); note(names.frontier, s.id); }
    });
  }
  return { visited, frontier, color, below: below as { name: string; values: Value[] } | null, names };
}

const NAME = /^[A-Za-z_]\w*$/;
const reads = (e: TraceEvent, structure: string) => (e.type === 'ARRAY_ACCESS' || e.type === 'HASHMAP_LOOKUP') && e.meta.structure === structure && !!e.meta.index && NAME.test(e.meta.index);
/** The variables the trace proves are walking a graph at this step: `current` is the name the code last used to
 * read a node's neighbours (graph[node]); `next` is the name it then took them in, after that read
 * (`for nei in graph[node]`, or graph[node][nei]). A name alone — start, src, node — proves nothing. */
export function graphRoles(events: TraceEvent[], step: number, graph: string): { current: string | null; next: string | null } {
  const last = Math.min(step, events.length - 1);
  let at = last;
  while (at >= 0 && !reads(events[at], graph)) at--;
  if (at < 0) return { current: null, next: null };
  const current = events[at].meta.index!, row = `${graph}[${current}]`;
  for (let i = last; i > at; i--) {
    const e = events[i];
    if (reads(e, row)) return { current, next: e.meta.index! };
    const loop = e.type === 'LOOP_START' ? /^for\s+\(?\s*([A-Za-z_]\w*)[^:]*?\s+in\s+(.+?)\s*:/.exec(e.source) : null;
    if (loop && loop[2].replace(/\s+/g, '') === row) return { current, next: loop[1] };
  }
  return { current, next: null };
}

export interface CallNode { id: number; fn: string; args: Record<string, Value>; value?: Value; done: boolean; children: CallNode[]; step: number }
/** The calls made up to this step, as a tree: which are finished, with what, and which is running. */
export function callTree(events: TraceEvent[], step: number) {
  const roots: CallNode[] = [], stack: (CallNode | null)[] = [];
  let count = 0;
  for (let i = 0; i <= step && i < events.length; i++) {
    const e = events[i];
    if (e.type === 'RECURSION_CALL' && e.meta.call) {
      // Building a node inside another call (TrieNode(), ListNode(x)) is not a step of the algorithm.
      if (hiddenCall(e.meta.call)) { stack.push(null); continue; }
      const node: CallNode = { id: e.meta.call.id, fn: e.meta.call.fn, args: e.meta.call.args, done: false, children: [], step: i };
      const parent = [...stack].reverse().find(Boolean);
      (parent ? parent.children : roots).push(node);
      stack.push(node);
      count++;
    } else if (e.type === 'RECURSION_RETURN' && e.meta.ret && stack.length) {
      const node = stack.pop();
      if (node) { node.value = e.meta.ret.value; node.done = true; }
    }
  }
  const open = stack.filter((n): n is CallNode => !!n);
  return { roots, count, active: open.length ? open[open.length - 1].id : null, path: new Set(open.map(n => n.id)) };
}
/** Is a call tree worth drawing? Recursion, helpers, or a design problem's operations. */
export const showCalls = (events: TraceEvent[]) => {
  let deepest = 0, tops = 0;
  for (const e of events) if (e.type === 'RECURSION_CALL' && e.meta.call && !hiddenCall(e.meta.call)) { deepest = Math.max(deepest, e.meta.call.depth); if (e.meta.call.depth === 1) tops++; }
  return deepest > 1 || tops > 1;
};
function hiddenCall(call: { fn: string; depth: number }) { return call.depth > 1 && call.fn.endsWith('__init__'); }

/** One call of the whole recorded run: when it started, when it returned (null: not in the recorded trace), and
 * `key`, its function and arguments when the trace proves two calls asked exactly the same question. */
export interface CallRec extends CallNode { end: number | null; key: string | null; parent: number | null; children: CallRec[] }
/**
 * Every call the run made, as one tree. Drawn whole, the tree keeps its shape while the run plays: a step only
 * changes which calls have happened. `frames[i]` is the call running at event i (its own call and return events
 * included), so a value's history is read within one activation, never across two calls of the same function.
 */
export function callHistory(events: TraceEvent[]) {
  const roots: CallRec[] = [], all: CallRec[] = [], stack: (CallRec | null)[] = [], frames: (number | null)[] = [];
  const top = () => [...stack].reverse().find(Boolean) ?? null;
  for (let i = 0; i < events.length; i++) {
    const e = events[i];
    if (e.type === 'RECURSION_CALL' && e.meta.call) {
      if (hiddenCall(e.meta.call)) { stack.push(null); frames.push(top()?.id ?? null); continue; }
      const parent = top();
      const node: CallRec = { id: e.meta.call.id, fn: e.meta.call.fn, args: e.meta.call.args, done: false, children: [], step: i, end: null, key: callKey(e), parent: parent?.id ?? null };
      (parent ? parent.children : roots).push(node);
      stack.push(node);
      all.push(node);
      frames.push(node.id);
    } else if (e.type === 'RECURSION_RETURN' && e.meta.ret && stack.length) {
      frames.push(top()?.id ?? null);
      const node = stack.pop();
      if (node) { node.value = e.meta.ret.value; node.end = i; node.done = true; }
    } else frames.push(top()?.id ?? null);
  }
  const twins = new Map<string, CallRec[]>();
  for (const n of all) if (n.key) (twins.get(n.key) || twins.set(n.key, []).get(n.key)!).push(n);
  return { roots, all, frames, twins, byId: new Map(all.map(n => [n.id, n])) };
}
export type CallHistory = ReturnType<typeof callHistory>;

/** A call's question, when the trace can prove two calls asked the same one: every argument a plain value
 * (numbers, short text, short lists of them) or a node, named by its identity. Abbreviated lists ("…") and node
 * labels can't be told apart, so a call with them has no key and is never called a repeat. */
function callKey(e: TraceEvent) {
  const call = e.meta.call!;
  const refs = e.state.structures.find(s => s.type === 'nodes')?.refs || {};
  const plain = (v: Value, depth = 0): boolean => v === null || typeof v === 'number' || typeof v === 'boolean' || (typeof v === 'string' && v !== '…' && v.length < 400)
    || (Array.isArray(v) && depth < 2 && v.every(x => plain(x, depth + 1)));
  const args: Record<string, Value> = {};
  for (const [name, value] of Object.entries(call.args)) {
    if (name in refs) args[name] = { node: refs[name] };  // The callee's parameter holds this node.
    else if (plain(value)) args[name] = value;
    else return null;
  }
  return `${call.fn}(${JSON.stringify(args)})`;
}

export type CallState = 'ahead' | 'running' | 'waiting' | 'returned';
/** Where every call stands at this step: not made yet, running (the innermost open call), waiting for the calls
 * it made, or returned. `made` and `open` count calls so far and calls still on the stack. */
export function callStates(history: CallHistory, step: number) {
  const states = new Map<number, CallState>();
  let made = 0, open = 0;
  for (const n of history.all) {
    if (n.step > step) { states.set(n.id, 'ahead'); continue; }
    made++;
    if (n.end !== null && n.end <= step) states.set(n.id, 'returned');
    else { states.set(n.id, 'waiting'); open++; }
  }
  const active = history.frames[Math.min(step, history.frames.length - 1)] ?? null;
  if (active !== null && states.get(active) === 'waiting') states.set(active, 'running');
  return { states, active, made, open, total: history.all.length };
}

/** The earlier calls that asked exactly this call's question, and what the first of them had returned by `step`. */
export function earlierTwins(history: CallHistory, id: number, step: number) {
  const n = history.byId.get(id);
  const twins = n?.key ? history.twins.get(n.key)!.filter(t => t.step < n.step) : [];
  const answered = twins.find(t => t.end !== null && t.end <= step) ?? null;
  return { twins, answered };
}

export interface PlacedCall<T extends CallNode = CallNode> { node: T; x: number; y: number; w: number; parent: PlacedCall<T> | null }
const short = (value: Value): string => {
  const text = JSON.stringify(value) ?? 'None';
  return (text === 'null' ? 'None' : text.replace(/^"(.*)"$/, '$1')).slice(0, 14);
};
export const callLabel = (node: Pick<CallNode, 'fn' | 'args'>) => `${node.fn.split('.').pop()}(${Object.values(node.args).map(short).join(', ')})`;
/** Tidy layout: each subtree as wide as its label or its children, parents centred above. At most `limit`
 * calls are placed, the first ones made (in call order); `hidden` is exactly how many calls are not shown. */
export function layoutCalls<T extends CallNode>(roots: T[], limit = 90) {
  const out: PlacedCall<T>[] = [];
  const widthOf = (n: T) => Math.max(46, Math.min(150, callLabel(n).length * 6.4 + 18));
  // Which calls fit is decided first, in call order, so the limit is never exceeded by a wide family.
  const shown = new Set<T>();
  let total = 0;
  const kidsOf = (n: T) => n.children as T[];
  const choose = (n: T) => { total++; if (shown.size < limit) shown.add(n); kidsOf(n).forEach(choose); };
  roots.forEach(choose);
  const span = new Map<T, number>();
  const measure = (n: T): number => {
    const kids = kidsOf(n).filter(k => shown.has(k));
    const inner = kids.map(measure).reduce((a, b) => a + b + 10, -10);
    const width = Math.max(widthOf(n), kids.length ? inner : 0);
    span.set(n, width);
    return width;
  };
  let x = 0;
  const place = (n: T, left: number, depth: number, parent: PlacedCall<T> | null) => {
    const width = span.get(n)!;
    const me: PlacedCall<T> = { node: n, x: left + width / 2, y: depth * 58, w: widthOf(n), parent };
    out.push(me);
    const kids = kidsOf(n).filter(k => shown.has(k));
    const inner = kids.reduce((a, k) => a + span.get(k)! + 10, -10);
    let at = left + (width - inner) / 2;
    for (const k of kids) { place(k, at, depth + 1, me); at += span.get(k)! + 10; }
  };
  for (const root of roots.filter(r => shown.has(r))) { measure(root); place(root, x, 0, null); x += span.get(root)! + 18; }
  return { placed: out, width: x, height: Math.max(0, ...out.map(p => p.y)) + 40, hidden: total - out.length };
}

/** Where index i of a heap array sits in its binary tree, in a w-wide box. */
export const heapPosition = (i: number, w: number) => {
  const depth = Math.floor(Math.log2(i + 1)), first = 2 ** depth - 1;
  return { x: (i - first + 0.5) * w / 2 ** depth, y: 22 + depth * 54, depth };
};

/** n in binary: 8, 16 or 32 digits, two's complement for negatives. */
export function bitsOf(n: number, width: number) {
  const value = n < 0 ? (2 ** width + n) : n;
  return value.toString(2).padStart(width, '0').slice(-width);
}
export const bitWidth = (...values: number[]) => { const m = Math.max(...values.map(v => Math.abs(v))); return m < 256 && values.every(v => v >= 0) ? 8 : m < 32768 ? 16 : 32; };

/** Before any run: inputs judges write as lists, drawn as what the program will receive (nodes, grids). */
export function inputStructures(params: string[], args: Value[], kinds: Record<string, string>): Structure[] {
  const nodes: NodeRec[] = [], refs: Record<string, number | null> = {};
  let next = 1;
  const make = (label: Value): NodeRec => { const n: NodeRec = { id: next++, label, cls: 'ListNode', links: {}, kids: [], attrs: {} }; nodes.push(n); return n; };
  const chain = (values: Value[], doubly: boolean) => {
    let head: NodeRec | null = null, tail: NodeRec | null = null;
    for (const v of values) {
      const n = make(v);
      n.links.next = null;
      if (doubly) n.links.prev = tail ? tail.id : null;
      if (tail) tail.links.next = n.id; else head = n;
      tail = n;
    }
    return head;
  };
  const out: Structure[] = [];
  params.forEach((name, i) => {
    const value = args[i], kind = kinds[name];
    if (!Array.isArray(value)) return;
    if (kind === 'linkedlist' || kind === 'dll') refs[name] = chain(value, kind === 'dll')?.id ?? null;
    else if (kind === 'linkedlists') value.forEach((v, j) => { if (Array.isArray(v)) refs[`${name}[${j}]`] = chain(v, false)?.id ?? null; });
    else if (kind === 'tree') {
      if (!value.length || value[0] === null) { refs[name] = null; return; }
      const root = make(value[0]);
      root.cls = 'TreeNode';
      root.links = { left: null, right: null };
      refs[name] = root.id;
      const queue = [root];
      let k = 1;
      while (queue.length && k < value.length) {
        const parent = queue.shift()!;
        for (const side of ['left', 'right']) {
          if (k < value.length && value[k] !== null) { const child = make(value[k]); child.cls = 'TreeNode'; child.links = { left: null, right: null }; parent.links[side] = child.id; queue.push(child); }
          k++;
        }
      }
    } else if (kind === 'cycle') {
      return;  // A cycle position is drawn as the link it makes (below), not as a value.
    } else if (kind === 'graph') {
      // Adjacency lists, drawn as the graph the tracer will show; an undirected edge once.
      if (!value.every(row => Array.isArray(row) && row.every(x => typeof x === 'number' && x >= 0 && x < value.length))) return;
      const edges: [number, number, Value][] = [];
      (value as number[][]).forEach((row, u) => row.forEach(v => { if (u < v || !(value[v] as number[]).includes(u)) edges.push([u, v, null]); }));
      out.push({ id: name, type: 'graph', labels: value.map((_, i) => i), edges, directed: edges.some(([u, v]) => !(value[v] as number[]).includes(u)) });
    } else if (value.length && value.every(row => Array.isArray(row)) && value.every(row => (row as Value[]).length === (value[0] as Value[]).length) && (value[0] as Value[]).length > 0 && value.flat().every(x => x === null || typeof x !== 'object')) {
      out.push({ id: name, type: 'matrix', rows: value as Value[][], shape: [value.length, (value[0] as Value[]).length], hot: [] });
    }
  });
  // pos: the list's tail links back to node pos, as the code will receive it.
  params.forEach((name, i) => {
    const pos = args[i], list = params.find(p => kinds[p] === 'linkedlist' || kinds[p] === 'dll');
    if (kinds[name] !== 'cycle' || typeof pos !== 'number' || pos < 0 || !list || refs[list] == null) return;
    const chain: NodeRec[] = [];
    for (let at: number | null | undefined = refs[list]; at != null && chain.length < 200;) { const n = nodes.find(x => x.id === at)!; chain.push(n); at = n.links.next; }
    if (pos < chain.length) chain[chain.length - 1].links.next = chain[pos].id;
  });
  if (nodes.length || Object.keys(refs).length) out.unshift({ id: '@nodes', type: 'nodes', nodes, refs });
  return out;
}
