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

  // Linked lists: one row per chain, starting at nodes nothing points to (cycles start at their smallest node).
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
      edges.push({ key: `${n.id}-${field}-${label ?? ''}`, from: n.id, to, field, label, kind, d });
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

export interface PlacedCall { node: CallNode; x: number; y: number; w: number; parent: PlacedCall | null }
const short = (value: Value): string => {
  const text = JSON.stringify(value) ?? 'None';
  return (text === 'null' ? 'None' : text.replace(/^"(.*)"$/, '$1')).slice(0, 14);
};
export const callLabel = (node: CallNode) => `${node.fn.split('.').pop()}(${Object.values(node.args).map(short).join(', ')})`;
/** Tidy layout: each subtree as wide as its label or its children, parents centred above. */
export function layoutCalls(roots: CallNode[], limit = 90) {
  const out: PlacedCall[] = [];
  const widthOf = (n: CallNode) => Math.max(46, Math.min(150, callLabel(n).length * 6.4 + 18));
  const span = new Map<CallNode, number>();
  let budget = limit;
  const measure = (n: CallNode): number => {
    budget--;
    const kids = n.children.filter(() => budget > 0);
    const inner = kids.map(measure).reduce((a, b) => a + b + 10, -10);
    const total = Math.max(widthOf(n), kids.length ? inner : 0);
    span.set(n, total);
    return total;
  };
  let x = 0;
  const place = (n: CallNode, left: number, depth: number, parent: PlacedCall | null) => {
    const total = span.get(n);
    if (total === undefined) return;
    const me: PlacedCall = { node: n, x: left + total / 2, y: depth * 58, w: widthOf(n), parent };
    out.push(me);
    const kids = n.children.filter(k => span.has(k));
    const inner = kids.reduce((a, k) => a + span.get(k)! + 10, -10);
    let at = left + (total - inner) / 2;
    for (const k of kids) { place(k, at, depth + 1, me); at += span.get(k)! + 10; }
  };
  for (const root of roots) { if (budget <= 0) break; measure(root); place(root, x, 0, null); x += (span.get(root) ?? 0) + 18; }
  return { placed: out, width: x, height: Math.max(0, ...out.map(p => p.y)) + 40, hidden: Math.max(0, -budget) };
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
