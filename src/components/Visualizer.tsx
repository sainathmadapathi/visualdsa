import { useEffect, useRef } from 'react';
import gsap from 'gsap';
import { ArrowDown, ArrowRight, Braces, CircleHelp, Database, Eye, GitBranch, Layers, Sparkles } from 'lucide-react';
import { useLab } from '../store';
import type { Structure, Value } from '../types';

export const display = (value: Value | undefined): string => value === undefined ? '—' : typeof value === 'string' ? value : JSON.stringify(value);
export const eventLabel = (event: string) => event.toLowerCase().replaceAll('_', ' ');

function ArrayView({ structure }: { structure: Structure }) {
  const values = structure.values || [];
  const width = Math.max(330, Math.min(values.length, 12) * 62 + 35);
  const max = 40;
  const perRow = Math.min(12, Math.max(5, values.length));
  const height = Math.max(112, Math.ceil(Math.min(values.length, max) / perRow) * 95 + 20);
  return <div className="structure array-structure">
    <div className="structure-label"><span><Layers size={13} /> {structure.id}</span><code>{structure.type === 'string' ? 'string' : 'array'} · {structure.length ?? values.length} {structure.type === 'string' ? 'characters' : 'elements'}</code></div>
    <div className={`array-scroll ${values.length > 12 ? 'multi-row-array' : ''}`}><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${structure.id}: ${values.map(display).join(', ')}`}>
      {values.slice(0, max).map((v, i) => {
        const x = 12 + i % perRow * 62, y = 26 + Math.floor(i / perRow) * 95;
        const pointed = Object.entries(structure.pointers || {}).filter(([, index]) => index === i);
        const active = structure.highlights?.includes(i) || pointed.length > 0;
        return <g key={i} className="array-cell" data-active={active}>
          <text x={x + 25} y={y - 9} className="index-text" textAnchor="middle">{i}</text>
          <rect x={x} y={y} width="50" height="50" rx="9" className={active ? 'cell-active' : 'cell-normal'} />
          <text x={x + 25} y={y + 31} textAnchor="middle" className={`value-text ${active ? 'value-active' : ''}`}>{display(v).slice(0, 7)}</text>
          {pointed.length > 0 && <><path d={`M${x + 25},${y + 60} l-4,6 h8 Z`} fill="#537963"/><text x={x + 25} y={y + 82} textAnchor="middle" className="pointer-text">{pointed.map(([name]) => name).join(', ')}</text></>}
        </g>;
      })}
    </svg></div>
    {(structure.length ?? values.length) > max && <p className="small">Showing the first {max} elements. Snapshots retain up to 200; result checking uses the complete output.</p>}
  </div>;
}

function MapView({ structure }: { structure: Structure }) {
  const entries = structure.entries || (structure.values || []).map(key => ({ key, value: null }));
  return <div className="structure map-structure">
    <div className="structure-label"><span><Database size={13} /> {structure.id}</span><code>{structure.type === 'hashset' ? 'set' : 'dictionary'} · {entries.length} entries</code></div>
    {entries.length === 0 ? <div className="empty-map"><Braces size={24}/><span>No entries yet</span></div> : <div className="map-entries">{entries.map((entry, i) => <div className="map-entry" key={i}><code>{display(entry.key)}</code><ArrowRight size={12}/><code>{display(entry.value)}</code></div>)}</div>}
  </div>;
}

export default function Visualizer() {
  const { run, step, problem, args, code, runCode, source, live, previewBusy, previewMessage, playing } = useLab();
  const root = useRef<HTMLDivElement>(null);
  const event = run?.events[step];
  const structures: Structure[] = event?.state.structures || (problem?.params.flatMap((name, i) => {
    const value = args[i];
    return Array.isArray(value) || typeof value === 'string' ? [{ id: name, type: typeof value === 'string' ? 'string' as const : 'array' as const, values: typeof value === 'string' ? value.split('') : value, highlights: [], pointers: {} }] : [];
  }) || []);
  const vars = event?.state.variables || (problem?.params.flatMap((name, i) => !Array.isArray(args[i]) && typeof args[i] !== 'string' ? [{ id: name, value: args[i] }] : []) || []);
  useEffect(() => {
    if (!root.current || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const ctx = gsap.context(() => {
      gsap.fromTo('.array-cell[data-active="true"]', { y: 7, scale: 0.94, transformOrigin: '50% 50%' }, { y: 0, scale: 1, duration: 0.4, stagger: 0.04, ease: 'back.out(1.4)' });
      gsap.fromTo('.variable, .map-entry', { y: 5, opacity: 0.6 }, { y: 0, opacity: 1, duration: 0.3, stagger: 0.025 });
      gsap.fromTo('.event-copy', { opacity: 0.4, y: 6 }, { opacity: 1, y: 0, duration: 0.3 });
    }, root);
    return () => ctx.revert();
  }, [step, run]);
  return <div className={`visual-body ${playing ? 'trace-playing' : ''}`} ref={root}>
    <div className={`live-preview-status ${previewBusy ? 'is-tracing' : ''}`} role="status"><span className="signal-bars" aria-hidden="true"><i/><i/><i/></span><span>{source !== 'mine' ? 'Reference mode · run to explore' : previewBusy ? 'Tracing your latest edit…' : previewMessage || (live ? 'Live preview · updates as you type' : 'Live paused · run when you are ready')}</span></div>
    <div className="canvas-topline"><span className="live-indicator"/><span>{event ? source === 'mine' ? 'YOUR ACTUAL EXECUTION' : 'REFERENCE EXECUTION' : 'YOUR INPUT, VISUALLY'}</span><span className="canvas-line">{event ? `LINE ${event.line}` : 'READY TO EXPLORE'}</span></div>
    {runCode && runCode !== code && <div className="stale-warning">{live ? 'Previous trace · waiting for your latest edit.' : 'Your code changed. Run again to update this trace.'}</div>}
    <div className="structures">{structures.map(s => s.type === 'hashmap' || s.type === 'hashset' ? <MapView key={s.id} structure={s}/> : <ArrayView key={s.id} structure={s}/>)}
      {vars.length > 0 && <div className="variables"><span className="tiny-label">VARIABLES</span><div className="variable-chips">{vars.map(v => <div className="variable" key={v.id}><code>{v.id}</code><span>{display(v.value)}</span></div>)}</div></div>}
      {event?.state.callstack && event.state.callstack.length > 1 && <div className="stack-frames"><GitBranch size={14}/>{event.state.callstack.join(' → ')}</div>}
    </div>
    {!event ? <div className="pre-run-guide"><div className="guide-icon"><Eye size={22}/></div><h3>See your thinking in motion.</h3><p>{live ? 'Start typing. Pause for a moment.' : 'Write your approach, then run your code.'}<br/>{live ? 'Your code comes to life beside you.' : 'Every step leaves a trail you can explore.'}</p><div className="guide-flow"><span>Code</span><ArrowRight size={13}/><span>State</span><ArrowRight size={13}/><span>Understanding</span></div></div> : <div className={`event-card ${event.type === 'ERROR' ? 'event-error' : ''}`}>
      <div className="event-card-top"><span><GitBranch size={13}/>{eventLabel(event.type)}</span><code>step {step + 1}</code></div>
      <div className="event-copy"><h4>{event.explanation.what}</h4><p>{event.explanation.why}</p></div>
      {event.meta.expression && <div className="comparison"><code>{display(event.meta.left)}</code><span>{event.meta.found !== undefined && event.meta.found !== null ? 'lookup' : 'compare'}</span><code>{event.meta.found !== undefined && event.meta.found !== null ? event.meta.found ? 'found' : 'not found' : String(event.meta.result)}</code></div>}
    </div>}
    <div className="canvas-note"><CircleHelp size={12}/>{event ? 'Snapshots come from this program’s recorded execution.' : 'An index is a position. The first position is 0.'}{!event && <ArrowDown size={12}/>}</div>
    {!event && !structures.length && <div className="small"><Sparkles size={12}/> Your data structures appear as your code creates them.</div>}
  </div>;
}
