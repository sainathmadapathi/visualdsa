import { useId, useMemo } from 'react';
import type { CSSProperties } from 'react';
import { ArrowDownToLine, ArrowRightLeft, Binary, Grid3x3, Layers, ListOrdered, Network, Share2, Triangle, Waypoints } from 'lucide-react';
import ScrollRegion from './ScrollRegion';
import type { Structure, TraceEvent, Value } from '../types';
import { py } from '../visualModel';
import { LIST_W, TREE_D, bitWidth, bitsOf, callLabel, callTree, graphLayout, heapPosition, layoutCalls, nodeChanges, sceneOf } from '../structureModel';

const palette = ['#f28845', '#c9a2f5', '#f6e6d2', '#8fd6c4', '#f590b4', '#e9d27c', '#9cc3ff', '#ff9b85'];  // The posters' ember, lilac and cream first.
const colorOf = (name: string) => palette[[...name].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) % palette.length];
const json = (value: unknown) => JSON.stringify(value);
const text = (value: Value) => value === null ? 'None' : typeof value === 'string' ? value : py(value);
const numberOf = (value: Value | undefined) => typeof value === 'number' && Number.isInteger(value) ? value : null;
const variable = (event: TraceEvent, names: string[], limit: number) => {
  for (const name of names) {
    const found = numberOf(event.state.variables.find(v => v.id === name)?.value);
    if (found !== null && found >= 0 && found < limit) return { name, value: found };
  }
  return null;
};

/** Linked lists, binary trees and tries: the learner's own nodes, re-laid out at every step. */
export function NodeCanvas({ structure, previous }: { structure: Structure; previous?: Structure }) {
  const scene = useMemo(() => sceneOf(structure), [structure]);
  const change = useMemo(() => nodeChanges(previous, structure), [previous, structure]);
  const marker = useId().replace(/:/g, '');
  const refs = structure.refs || {};
  const pointed = new Map<number, string[]>();
  const empty: string[] = [];
  for (const [name, id] of Object.entries(refs)) {
    if (id === null) empty.push(name);
    else (pointed.get(id) || pointed.set(id, []).get(id)!).push(name);
  }
  const kind = scene.kinds.has('list') && scene.kinds.size === 1 ? (scene.nodes.some(n => n.links.prev != null) ? 'doubly linked list' : 'linked list')
    : scene.kinds.has('tree') && scene.kinds.size === 1 ? 'binary tree' : scene.kinds.has('nary') && scene.kinds.size === 1 ? 'tree · trie' : 'nodes';
  const labelOf = (d: string) => { const n = d.match(/-?\d+(\.\d+)?/g)?.map(Number) || []; return n.length >= 4 ? { x: (n[0] + n[n.length - 2]) / 2, y: (n[1] + n[n.length - 1]) / 2 } : null; };
  const placed = new Map(scene.nodes.map(n => [n.id, n]));
  // Pointers are their own layer, keyed by name, so a pointer glides from node to node as the code moves it.
  const badges: { name: string; x: number; y: number }[] = [];
  for (const [id, names] of pointed) {
    const n = placed.get(id);
    if (!n) continue;
    const widths = names.map(name => 16 + name.length * 7.2);
    let left = Math.max(2, n.x + (n.role === 'list' ? LIST_W : TREE_D) / 2 - (widths.reduce((a, b) => a + b, 0) + (names.length - 1) * 4) / 2);
    names.forEach((name, k) => { badges.push({ name, x: left + widths[k] / 2, y: n.y }); left += widths[k] + 4; });
  }
  // In a tree or trie, the way down from the root to each pointed node is lit, as on the poster.
  const up = new Map<number, { key: string; from: number }>();
  for (const e of scene.edges) if (e.kind === 'child') up.set(e.to, { key: e.key, from: e.from });
  const lit = new Set<string>();
  for (const id of pointed.keys()) {
    if (placed.get(id)?.role === 'list') continue;
    for (let at = id, guard = 0; up.has(at) && guard < 80; guard++) { lit.add(up.get(at)!.key); at = up.get(at)!.from; }
  }
  const letter = new Map<number, string>();
  for (const e of scene.edges) if (e.field === 'kid' && e.label !== undefined && placed.get(e.to)?.role === 'nary' && placed.get(e.to)?.label === null) letter.set(e.to, e.label);
  const halos = [...pointed.entries()].flatMap(([id, names]) => { const n = placed.get(id); return n && n.role !== 'list' ? [{ name: names[0], x: n.x + TREE_D / 2, y: n.y + TREE_D / 2 }] : []; });
  return <section className="nodes-view" aria-label={`${kind}: ${scene.nodes.length} nodes`}>
    <div className="lane-head"><span>{kind === 'binary tree' ? <Network size={13}/> : kind.startsWith('tree') ? <Waypoints size={13}/> : <Share2 size={13}/>} {kind}</span><code>{scene.nodes.length} node{scene.nodes.length === 1 ? '' : 's'}</code></div>
    <ScrollRegion className="nodes-scroll" label={`${kind}, ${scene.nodes.length} nodes (scrollable)`}>
      <div className="nodes-stage" style={{ width: scene.width, height: scene.height }}>
        <svg className="nodes-edges" width={scene.width} height={scene.height} aria-hidden="true">
          <defs>
            <marker id={`a-${marker}`} viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="10" markerHeight="10" markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M0 1 L9 5 L0 9 z"/></marker>
            <marker id={`h-${marker}`} viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="10" markerHeight="10" markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path className="hot" d="M0 1 L9 5 L0 9 z"/></marker>
          </defs>
          {scene.edges.map(e => {
            const hot = change.relinked.has(`${e.from}-${e.field}-`);
            return <path key={e.key} d={e.d} className={`edge edge-${e.kind} ${hot ? 'is-new' : ''} ${lit.has(e.key) ? 'is-lit' : ''}`} markerEnd={e.kind === 'child' && e.field !== 'kid' ? undefined : `url(#${hot ? 'h' : 'a'}-${marker})`}/>;
          })}
          {scene.edges.filter(e => e.label && !letter.has(e.to)).map(e => { const at = labelOf(e.d); return at && <text key={`t${e.key}`} x={at.x} y={at.y - 4} className="edge-label">{e.label}</text>; })}
        </svg>
        {halos.map(h => <span key={`halo-${h.name}`} className="node-halo" style={{ transform: `translate(${h.x}px, ${h.y}px)`, '--c': colorOf(h.name) } as CSSProperties} aria-hidden="true"/>)}
        {scene.nodes.map(n => {
          const names = pointed.get(n.id) || [];
          const state = [change.fresh.has(n.id) && 'is-fresh', change.relabelled.has(n.id) && 'is-written', names.length > 0 && 'is-pointed'].filter(Boolean).join(' ');
          const flag = Object.entries(n.attrs).find(([, v]) => v === true);
          return <div key={n.id} className={`node node-${n.role} ${state}`} style={{ transform: `translate(${n.x}px, ${n.y}px)`, ...(names.length ? { '--c': colorOf(names[0]) } : {}) } as CSSProperties} title={`${n.cls}${Object.keys(n.attrs).length ? ' · ' + Object.entries(n.attrs).map(([k, v]) => `${k}=${text(v)}`).join(', ') : ''}`}>
            <span className="node-val">{n.label === null ? (letter.get(n.id) ?? (n.role === 'nary' ? '•' : n.cls.slice(0, 1))) : text(n.label)}</span>
            {n.role === 'list' && <span className="node-next" aria-hidden="true"/>}
            {flag && <span className="node-flag" title={flag[0]}>{flag[0].length <= 6 ? flag[0] : '✓'}</span>}
          </div>;
        })}
        {badges.map(b => <span key={`ptr-${b.name}`} className="node-badge" style={{ transform: `translate(${b.x}px, ${b.y}px)`, '--c': colorOf(b.name) } as CSSProperties}><b>{b.name}</b></span>)}
        {scene.ends.map(end => <span key={end.key} className="node-null" style={{ transform: `translate(${end.x}px, ${end.y - 9}px)` }}>None</span>)}
      </div>
    </ScrollRegion>
    {empty.length > 0 && <p className="node-empty">{empty.map(name => <b key={name} style={{ '--c': colorOf(name) } as CSSProperties}>{name}</b>)}<span>→ None</span></p>}
  </section>;
}

/** Grids and DP tables: the cell just read, cells just written, row/column pointers, visited and queued cells. */
export function MatrixGrid({ structure, previous, event }: { structure: Structure; previous?: Structure; event: TraceEvent }) {
  const rows = structure.rows || [];
  const [height, width] = structure.shape || [rows.length, rows[0]?.length ?? 0];
  const shownCols = rows[0]?.length ?? 0;
  const cell = shownCols <= 7 ? 40 : shownCols <= 12 ? 32 : shownCols <= 18 ? 26 : 22;
  const hot = structure.hot?.[0];
  const before = previous?.rows;
  const written = new Set<string>();
  if (before) rows.forEach((row, r) => row.forEach((value, c) => { if (json(before[r]?.[c]) !== json(value)) written.add(`${r},${c}`); }));
  const row = variable(event, ['i', 'r', 'row', 'ni', 'nr', 'x'], rows.length);
  const col = variable(event, ['j', 'c', 'col', 'nj', 'nc', 'y'], shownCols);
  const pair = (value: Value) => Array.isArray(value) && value.length === 2 && value.every(v => typeof v === 'number') ? `${value[0]},${value[1]}` : null;
  const visited = new Set<string>(), queued = new Set<string>();
  for (const s of event.state.structures) {
    if (s.type === 'hashset' && /^(vis|visited|seen|used|explored|done)$/i.test(s.id.split('.').pop()!)) (s.values || []).forEach(v => { const k = pair(v); if (k) visited.add(k); });
    if ((s.type === 'array') && (s.kind === 'queue' || s.kind === 'stack' || s.kind === 'heap')) (s.values || []).forEach(v => { const k = pair(Array.isArray(v) && v.length === 3 ? v.slice(-2) as Value : v); if (k) queued.add(k); });
    if (s.type === 'matrix' && s.id !== structure.id && /^(vis|visited|seen|used)$/i.test(s.id.split('.').pop()!)) (s.rows || []).forEach((r, i) => r.forEach((v, j) => { if (v === true || v === 1) visited.add(`${i},${j}`); }));
  }
  const numbers = rows.flat().filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
  // A map (land and water, open and wall, visited marks) is drawn by meaning; a table of numbers by size.
  const table = /^(dp|dist|distance|distances|memo|table|cost|costs|best|ways|count|counts|paths|f|t|lcs|ans|res)$/i.test(structure.id.split('.').pop() || '');
  const map = !table && rows.flat().every(v => typeof v === 'boolean' || (typeof v === 'string' && v.length === 1) || (typeof v === 'number' && Number.isInteger(v) && v >= -1 && v <= 3))
    && new Set(rows.flat().map(json)).size <= 4;
  const role = (v: Value) => v === 0 || v === '0' || v === false || v === '.' || v === 'W' || v === ' ' ? 'water' : v === 1 || v === '1' || v === true || v === 'L' || v === '#' ? 'land' : v === -1 ? 'void' : 'mark';
  const scale = !map && numbers.length === rows.flat().length && numbers.length > 0 ? Math.max(1, ...numbers.map(Math.abs)) : 0;
  return <section className="matrix-view" aria-label={`${structure.id}: ${height} × ${width}`}>
    <div className="lane-head"><span><Grid3x3 size={13}/> {structure.id}</span><code>{height} × {width}{height > rows.length || width > shownCols ? ' · showing 24 × 24' : ''}</code></div>
    <ScrollRegion className="matrix-scroll" label={`${structure.id}, ${height} by ${width} grid (scrollable)`}>
      <div className="matrix-grid" style={{ gridTemplateColumns: `24px repeat(${shownCols}, ${cell}px)`, '--cell': `${cell}px` } as CSSProperties}>
        <span className="matrix-corner"/>
        {Array.from({ length: shownCols }, (_, c) => <span key={`h${c}`} className={`matrix-head ${col?.value === c ? 'is-pointer' : ''}`} style={col?.value === c ? { '--c': colorOf(col.name) } as CSSProperties : undefined}>{col?.value === c ? col.name : c}</span>)}
        {rows.map((values, r) => [
          <span key={`r${r}`} className={`matrix-head matrix-row-head ${row?.value === r ? 'is-pointer' : ''}`} style={row?.value === r ? { '--c': colorOf(row.name) } as CSSProperties : undefined}>{row?.value === r ? row.name : r}</span>,
          ...values.map((value, c) => {
            const key = `${r},${c}`;
            const state = [hot && hot[0] === r && hot[1] === c && 'is-hot', written.has(key) && 'is-written', visited.has(key) && 'is-visited', queued.has(key) && 'is-queued',
              (row?.value === r || col?.value === c) && 'is-cross', map ? `is-${role(value)}` : '', !map && (value === -1 || value === null) ? 'is-void' : ''].filter(Boolean).join(' ');
            const heat = scale && typeof value === 'number' && value !== -1 ? Math.abs(value) / scale : 0;
            return <span key={key} className={`matrix-cell ${state}`} style={heat ? { '--heat': heat.toFixed(3) } as CSSProperties : undefined} title={`${structure.id}[${r}][${c}] = ${text(value)}`}>
              <span key={written.has(key) ? `w${event.id}` : 'v'}>{value === true ? 'T' : value === false ? 'F' : text(value)}</span>
            </span>;
          }),
        ])}
      </div>
    </ScrollRegion>
  </section>;
}

/** A graph from an adjacency list, matrix or edge list, coloured by the program's own visited/dist/queue state. */
export function GraphView({ structure, event }: { structure: Structure; event: TraceEvent }) {
  const labels = structure.labels || [], edges = structure.edges || [];
  const count = labels.length;
  const w = 460, h = Math.max(220, Math.min(380, 120 + count * 16));
  const pos = graphLayout(count, edges, w, h);
  const marker = useId().replace(/:/g, '');
  const index = (value: Value) => labels.findIndex(l => json(l) === json(value));
  const visited = new Set<number>(), frontier = new Set<number>();
  const dist: Record<number, Value> = {}, color: Record<number, Value> = {};
  for (const s of event.state.structures) {
    const name = s.id.split('.').pop()!.toLowerCase();
    if (s.type === 'array' && (s.values || []).length === count && count > 0) {
      if (/^(vis|visited|seen|used|explored|marked|done)$/.test(name)) (s.values || []).forEach((v, i) => { if (v === true || v === 1) visited.add(i); });
      if (/^(dist|distance|distances|d|level|levels|depth|cost|time|parent)$/.test(name)) (s.values || []).forEach((v, i) => { dist[i] = v; });
      if (/^(color|colors|colour|side|group)$/.test(name)) (s.values || []).forEach((v, i) => { color[i] = v; });
    }
    if (s.type === 'hashset' && /^(vis|visited|seen|used|explored)$/.test(name)) (s.values || []).forEach(v => { const i = index(v); if (i >= 0) visited.add(i); });
    if (s.type === 'array' && (s.kind === 'queue' || s.kind === 'stack' || s.kind === 'heap' || /^(q|queue|stack|st|frontier)$/.test(name))) (s.values || []).forEach(v => {
      const i = index(Array.isArray(v) ? v[v.length - 1] as Value : v);
      if (i >= 0) frontier.add(i);
    });
  }
  const find = (names: string[]) => { for (const n of names) { const v = event.state.variables.find(x => x.id === n)?.value; const i = v === undefined ? -1 : index(v); if (i >= 0) return { name: n, i }; } return null; };
  const current = find(['node', 'u', 'curr', 'cur', 'vertex', 'src', 'start', 'source']);
  const neighbour = find(['v', 'nb', 'neighbor', 'neighbour', 'nei', 'adjnode', 'adjNode', 'child', 'it', 'nxt', 'to']);
  const dashed = (value: Value) => value === null || (typeof value === 'number' && Math.abs(value) >= 1e9) || value === 'inf' || value === 'Infinity';
  return <section className="graph-view" aria-label={`${structure.id}: graph of ${count} nodes`}>
    <div className="lane-head"><span><Network size={13}/> {structure.id}</span><code>graph · {count} nodes · {edges.length} edges{structure.directed ? ' · directed' : ''}</code></div>
    <svg className="graph-svg" viewBox={`0 0 ${w} ${h}`} style={{ maxWidth: w }} aria-hidden="true">
      <defs><marker id={`g-${marker}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 1 L9 5 L0 9 z"/></marker></defs>
      {edges.map(([a, b, weight], k) => {
        if (!pos[a] || !pos[b] || a === b) return null;
        const dx = pos[b].x - pos[a].x, dy = pos[b].y - pos[a].y, len = Math.max(1, Math.hypot(dx, dy)), r = 17;
        const live = current && neighbour && ((current.i === a && neighbour.i === b) || (!structure.directed && current.i === b && neighbour.i === a));
        return <g key={k} className={`gedge ${live ? 'is-live' : ''} ${visited.has(a) && visited.has(b) ? 'is-seen' : ''}`}>
          <line x1={pos[a].x + dx / len * r} y1={pos[a].y + dy / len * r} x2={pos[b].x - dx / len * (r + (structure.directed ? 4 : 0))} y2={pos[b].y - dy / len * (r + (structure.directed ? 4 : 0))} markerEnd={structure.directed ? `url(#g-${marker})` : undefined}/>
          {weight !== null && weight !== undefined && <text x={(pos[a].x + pos[b].x) / 2} y={(pos[a].y + pos[b].y) / 2 - 5}>{text(weight)}</text>}
        </g>;
      })}
      {current && pos[current.i] && <circle key={`ripple-${current.i}`} className="gripple" cx={pos[current.i].x} cy={pos[current.i].y} r="18"/>}
      {labels.map((label, i) => pos[i] && <g key={i} className={`gnode ${visited.has(i) ? 'is-visited' : ''} ${frontier.has(i) ? 'is-frontier' : ''} ${current?.i === i ? 'is-current' : ''} ${neighbour?.i === i ? 'is-next' : ''} ${color[i] !== undefined ? `tint-${String(color[i]).replace(/[^\w-]/g, '')}` : ''}`} style={{ transform: `translate(${pos[i].x}px, ${pos[i].y}px)` }}>
        {frontier.has(i) && <circle className="gring" r="23"/>}
        <circle className="gbody" r="17"/><text className="gnode-label" y="5">{text(label)}</text>
        {dist[i] !== undefined && <text className="gnode-dist" y="33">{dashed(dist[i]) ? '∞' : text(dist[i])}</text>}
        {(current?.i === i || (neighbour?.i === i && current?.i !== i)) && <Pill name={current?.i === i ? current.name : neighbour!.name} next={current?.i !== i}/>}
      </g>)}
    </svg>
    <div className="graph-legend"><span className="is-current">current</span><span className="is-frontier">in queue/stack</span><span className="is-visited">visited</span>{Object.keys(dist).length > 0 && <span>dist below</span>}</div>
  </section>;
}

/** A pointer's name as a pill above its graph node. */
function Pill({ name, next }: { name: string; next: boolean }) {
  const w = 20 + name.length * 6.8;
  return <g className={`gpill ${next ? 'is-next' : ''}`} transform="translate(0 -31)"><rect x={-w / 2} y="-9" width={w} height="16" rx="8"/><text y="3">{name}</text></g>;
}

/** Offsets that keep each queued item the same element as it moves toward the front. */
function queueOffsets(events: TraceEvent[], id: string) {
  const offsets: number[] = [];
  let offset = 0, last: Value[] | null = null;
  for (const e of events) {
    const now = e.state.structures.find(s => s.id === id)?.values || null;
    if (last && now) {
      // How many left the front: the rest of the old queue must still lead the new one.
      for (let k = 0; k <= last.length; k++) {
        const rest = last.slice(k);
        if (json(now.slice(0, rest.length)) === json(rest)) { offset += k; break; }
      }
    }
    if (now) last = now;
    offsets.push(offset);
  }
  return offsets;
}

/** A stack drawn upright: the top is the last item; pushes drop in, pops lift out. */
export function StackView({ structure, previous, stamp }: { structure: Structure; previous?: Structure; stamp: number }) {
  const values = (structure.values || []).slice(-14);
  const hidden = (structure.values || []).length - values.length;
  const was = previous?.values || [];
  const popped = was.length > (structure.values || []).length ? was.slice((structure.values || []).length).reverse() : [];
  return <section className="stack-view" aria-label={`${structure.id}: stack of ${(structure.values || []).length}`}>
    <div className="lane-head"><span><Layers size={13}/> {structure.id}</span><code>stack · {(structure.values || []).length}</code></div>
    <div className="stack-well">
      {popped.map((v, i) => <div key={`p${stamp}-${i}`} className="stack-item is-popped">{text(v)}</div>)}
      {[...values].reverse().map((v, i) => {
        const index = values.length - 1 - i + hidden;
        const fresh = previous && index >= was.length;
        return <div key={`${index}-${fresh ? stamp : json(v)}`} className={`stack-item ${i === 0 ? 'is-top' : ''} ${fresh ? 'is-pushed' : ''}`}>{text(v)}{i === 0 && <small>top</small>}</div>;
      })}
      {!values.length && <div className="stack-empty">empty</div>}
      {hidden > 0 && <div className="stack-more">+{hidden} below</div>}
    </div>
  </section>;
}

/** A queue left to right: the front leaves on the left, new items join at the back. */
export function QueueView({ structure, events, step }: { structure: Structure; events: TraceEvent[]; step: number }) {
  const offsets = useMemo(() => queueOffsets(events, structure.id), [events, structure.id]);
  const offset = offsets[step] ?? 0;
  const values = (structure.values || []).slice(0, 16);
  return <section className="queue-view" aria-label={`${structure.id}: queue of ${(structure.values || []).length}`}>
    <div className="lane-head"><span><ArrowRightLeft size={13}/> {structure.id}</span><code>queue · {(structure.values || []).length}</code></div>
    <ScrollRegion className="queue-track" label={`${structure.id}, queue of ${(structure.values || []).length} (scrollable)`}>
      <div className="queue-tube" style={{ width: Math.max(2, values.length) * 66 + 14 }}>
        <div className="queue-items" style={{ width: Math.max(1, values.length) * 66 }}>
          {values.map((v, i) => <div key={offset + i} className={`queue-item ${i === 0 ? 'is-front' : ''} ${(offset + i) % 3 === 1 ? 'is-alt' : ''}`} style={{ transform: `translateX(${i * 66}px)` }}>{text(v)}</div>)}
          {!values.length && <div className="stack-empty">empty</div>}
        </div>
      </div>
      <div className="queue-ends" style={{ width: Math.max(2, values.length) * 66 + 14 }}><span>front</span><i className="queue-flow" aria-hidden="true"/><span>back</span></div>
    </ScrollRegion>
    {(structure.values || []).length > 16 && <p className="stage-note">Showing the first 16 of {(structure.values || []).length}.</p>}
  </section>;
}

/** A heap's array drawn as the tree it encodes: parent i, children 2i+1 and 2i+2. */
export function HeapTree({ structure, previous }: { structure: Structure; previous?: Structure }) {
  const values = (structure.values || []).slice(0, 31);
  const w = 440;
  const depth = values.length ? Math.floor(Math.log2(values.length)) + 1 : 1;
  const was = previous?.values || [];
  return <div className="heap-tree" aria-label="The heap as a tree">
    <span className="stage-label"><Triangle size={11}/> AS A TREE · parent i → children 2i+1, 2i+2</span>
    <svg viewBox={`0 0 ${w} ${depth * 54 + 14}`} style={{ maxWidth: w }}>
      {values.map((_, i) => i > 0 && <line key={`l${i}`} x1={heapPosition(Math.floor((i - 1) / 2), w).x} y1={heapPosition(Math.floor((i - 1) / 2), w).y} x2={heapPosition(i, w).x} y2={heapPosition(i, w).y}/>)}
      {values.map((v, i) => { const p = heapPosition(i, w); const changed = json(was[i]) !== json(v) && previous; return <g key={i} className={`heap-node ${i === 0 ? 'is-root' : ''} ${changed ? 'is-written' : ''}`} transform={`translate(${p.x} ${p.y})`}>
        <circle r="15"/><text y="4">{text(v)}</text><text className="heap-index" y="27">{i}</text>
      </g>; })}
    </svg>
  </div>;
}

/** Every call made so far, as a tree: returned calls show their value, the running path glows. */
export function CallTree({ events, step, onSeek }: { events: TraceEvent[]; step: number; onSeek?: (step: number) => void }) {
  const tree = useMemo(() => callTree(events, step), [events, step]);
  const layout = useMemo(() => layoutCalls(tree.roots), [tree]);
  if (!layout.placed.length) return null;
  const pad = 16;
  return <section className="calls-view" aria-label={`Calls: ${tree.count}`}>
    <div className="lane-head"><span><ListOrdered size={13}/> calls</span><code>{tree.count} call{tree.count === 1 ? '' : 's'} so far{layout.hidden ? ` · showing ${90}` : ''}</code></div>
    <ScrollRegion className="calls-scroll" label={`Calls so far: ${tree.count} (scrollable)`}>
      <div className="calls-stage" style={{ width: layout.width + pad * 2, height: layout.height + pad }}>
        <svg width={layout.width + pad * 2} height={layout.height + pad} aria-hidden="true">
          {layout.placed.filter(p => p.parent).map(p => <path key={`e${p.node.id}`} className={tree.path.has(p.node.id) ? 'is-path' : ''} d={`M ${p.parent!.x + pad} ${p.parent!.y + pad + 28} C ${p.parent!.x + pad} ${p.y + pad - 6} ${p.x + pad} ${p.parent!.y + pad + 34} ${p.x + pad} ${p.y + pad}`}/>)}
        </svg>
        {layout.placed.map(p => <button key={p.node.id} className={`call ${p.node.id === tree.active ? 'is-active' : tree.path.has(p.node.id) ? 'is-path' : p.node.done ? 'is-done' : ''}`}
          style={{ width: p.w, transform: `translate(${p.x + pad - p.w / 2}px, ${p.y + pad}px)` }} onClick={() => onSeek?.(p.node.step)} title={`${callLabel(p.node)}${p.node.done ? ` returned ${text(p.node.value ?? null)}` : ' is running'} · step ${p.node.step + 1}`}>
          <span>{callLabel(p.node)}</span>{p.node.done && <b>→ {text(p.node.value ?? null).slice(0, 12)}</b>}
        </button>)}
      </div>
    </ScrollRegion>
  </section>;
}

/** A bit operation, bit by bit: both operands and the result, with the bits that are set. */
export function BitStrip({ event }: { event: TraceEvent }) {
  const { left, right, result, op } = event.meta;
  if (typeof left !== 'number' || typeof right !== 'number' || typeof result !== 'number') return null;
  const shift = op === '<<' || op === '>>';
  const width = bitWidth(left, shift ? 0 : right, result);
  const rows: [string, number][] = shift ? [[`${left}`, left], [`${op} ${right}`, NaN], [`= ${result}`, result]] : [[`${left}`, left], [`${op} ${right}`, right], [`= ${result}`, result]];
  return <div className="bit-strip" aria-label={`${left} ${op} ${right} = ${result}`}>
    <span className="stage-label"><Binary size={11}/> BIT BY BIT · {width}-bit</span>
    {rows.map(([label, value], r) => <div key={r} className={`bit-row ${r === 2 ? 'is-result' : ''}`}><code>{label}</code>
      {Number.isNaN(value) ? <span className="bit-shift"><ArrowDownToLine size={12}/> shift by {right}</span> : [...bitsOf(value, width)].map((b, i) => <i key={i} className={b === '1' ? 'is-one' : ''}>{b}</i>)}
    </div>)}
  </div>;
}
