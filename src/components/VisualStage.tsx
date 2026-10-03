import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import gsap from 'gsap';
import { ArrowRight, BookOpenCheck, Braces, CircleAlert, CornerDownLeft, Eye, GitCompareArrows, Layers, LogIn, Pencil, Repeat2, Search, Sparkles, Target, TriangleAlert } from 'lucide-react';
import ScrollRegion from './ScrollRegion';
import { reducedMotion } from '../motion';
import type { Divergence, Structure, TraceEvent, Value } from '../types';
import { categoryOf, focusAt, ghostIndex, goalRowFor, gridPointerNames, lineLens, pointerNames, pointerRange, pointersAt, py, returnedLane, ribbon, stepChange, wrongAt } from '../visualModel';
import type { Category, Focus, GoalState, Pointer, StepChange } from '../visualModel';
import { showCalls } from '../structureModel';
import { BitStrip, CallTree, GraphView, HeapTree, MatrixGrid, NodeCanvas, QueueView, StackView } from './StructureViews';

const empty: StepChange = { written: {}, old: {}, swapped: {}, added: {}, changed: {}, removed: {}, variables: {} };
const palette = ['#f3a25f', '#c9a2f5', '#78d4c6', '#f590b4', '#e9d27c', '#9cc3ff'];
const json = (value: unknown) => JSON.stringify(value);
const isSequence = (s: Structure) => s.type === 'array' || s.type === 'string';
const icons: Record<Category, typeof Eye> = { read: Eye, write: Pencil, compare: GitCompareArrows, lookup: Search, insert: Braces, loop: Repeat2, call: LogIn, return: CornerDownLeft, error: TriangleAlert, state: Sparkles };
const verbs: Record<Category, string> = { read: 'Read', write: 'Write', compare: 'Compare', lookup: 'Lookup', insert: 'Store', loop: 'Loop', call: 'Call', return: 'Return', error: 'Stopped', state: 'Update' };

export interface StageProps {
  events: TraceEvent[]; step: number; onSeek?: (step: number) => void;
  goal: GoalState | null; divergence: Divergence | null | undefined;
  /** The line to summarise; defaults to the current step's line. */
  focusLine?: number | null; lines?: Record<string, number>; code?: string;
}

/** The animated stage: everything shown is a recorded snapshot of the learner's own run. */
export default function VisualStage({ events, step, onSeek, goal, divergence, focusLine, lines, code = '' }: StageProps) {
  const event = events[step];
  // Change animations play only when stepping forward by one; jumps show the state directly.
  // Track the previous *distinct* step so unrelated re-renders never cut an animation short.
  const seen = useRef({ step: -1, previous: -1, events });
  if (seen.current.step !== step || seen.current.events !== events) seen.current = { step, previous: seen.current.events === events ? seen.current.step : -1, events };
  const forward = seen.current.previous === step - 1;
  const change = forward && event ? stepChange(events[step - 1], event) : empty;
  const focus = focusAt(events, step);
  const names = useMemo(() => pointerNames(events), [events]);
  const colors = useMemo(() => {
    const all = [...new Set(Object.values(names).flat())];
    return Object.fromEntries(all.map((name, i) => [name, palette[i % palette.length]]));
  }, [names]);
  const returnName = useMemo(() => returnedLane(events), [events]);
  const grids = useMemo(() => gridPointerNames(events), [events]);
  // Each grid's first recorded snapshot decides whether it is an island map (see islandMap).
  const firstRows = useMemo(() => {
    const first: Record<string, Value[][]> = {};
    for (const e of events) for (const s of e.state.structures) if (s.type === 'matrix' && !(s.id in first)) first[s.id] = s.rows || [];
    return first;
  }, [events]);
  const calls = useMemo(() => showCalls(events), [events]);
  if (!event) return null;
  const wrong = wrongAt(divergence, step);
  // The step before, for views that animate what changed (re-links, new nodes, writes, pushes and pops).
  const before = forward ? events[step - 1] : undefined;
  const previous = (id: string) => before?.state.structures.find(s => s.id === id);
  const rank = (s: Structure) => s.type === 'nodes' ? 0 : s.type === 'graph' ? 1 : s.type === 'matrix' ? 2 : 3;
  const structures = [...event.state.structures].sort((a, b) => rank(a) - rank(b));
  // A bit operation stays in view while its line is still running.
  let bits: TraceEvent | undefined;
  for (let i = step; i >= 0 && i >= step - 3 && events[i].line === event.line; i--) if (events[i].type === 'BIT_OP') { bits = events[i]; break; }
  const failed = event.type === 'ERROR' ? event.meta.access : undefined;

  return <div className="stage" data-category={categoryOf(event.type)}>
    {goal && <GoalBar goal={goal} step={step} total={events.length}/>}
    <div className="stage-structures">
      {structures.map(s => s.type === 'nodes' ? <NodeCanvas key={s.id} structure={s} previous={previous(s.id)}/>
        : s.type === 'graph' ? <GraphView key={s.id} structure={s} event={event} events={events} step={step}/>
        : s.type === 'matrix' ? <MatrixGrid key={s.id} structure={s} previous={previous(s.id)} event={event} pointers={grids[s.id]} first={firstRows[s.id]}/>
        : isSequence(s) && s.kind === 'stack' ? <StackView key={s.id} structure={s} previous={previous(s.id)} stamp={event.id}/>
        : isSequence(s) && s.kind === 'queue' ? <QueueView key={s.id} structure={s} events={events} step={step}/>
        : isSequence(s)
        ? <div key={s.id} className="lane-group"><ArrayLane structure={s} pointers={pointersAt(event, s, names[s.id] || [])} reserved={(names[s.id] || []).length} colors={colors} change={change} focus={focus} stamp={event.id}
            wrong={divergence?.elements?.name === s.id ? wrong.map(w => w.position) : []}
            goalRow={goalRowFor(goal, s.id, returnName)}
            ghost={failed && failed.structure === s.id && failed.kind === 'sequence' ? failed : null}/>
          {s.kind === 'heap' && <HeapTree structure={s} previous={previous(s.id)}/>}</div>
        : <MapTable key={s.id} structure={s} change={change} focus={focus} stamp={event.id} missing={failed && failed.structure === s.id && failed.kind === 'dict' ? failed.key : undefined}/>)}
    </div>
    {calls && <CallTree events={events} step={step} onSeek={onSeek}/>}
    <VariableTape event={event} change={change} pointers={new Set(Object.values(names).flat())} colors={colors}/>
    {event.state.callstack.length > 1 && !calls && <div className="stage-frames" aria-label="Call stack">{event.state.callstack.map((frame, i) => <span key={i} style={{ '--depth': i } as CSSProperties}>{frame}</span>)}</div>}
    <Narration event={event} step={step} total={events.length} focus={focus} bits={bits}/>
    <StageAlert event={event} step={step} last={step === events.length - 1} divergence={divergence} wrong={wrong} goal={goal} onSeek={onSeek}/>
    <LineLens events={events} lines={lines} code={code} line={focusLine && /^(?!def\s|#)\S/.test((code.split('\n')[focusLine - 1] || '').trim()) ? focusLine : event.line} current={event.line} onSeek={onSeek}/>
    <ExecutionRibbon events={events} divergence={divergence} step={step} onSeek={onSeek}/>
  </div>;
}

function GoalBar({ goal, step, total }: { goal: GoalState; step: number; total: number }) {
  const state = !goal.returned ? 'running' : goal.result === null && goal.expected !== null && !goal.matches ? 'pending' : goal.matches ? 'match' : 'differs';
  return <div className={`goal-bar goal-${state}`} role="status">
    <div><span className="stage-label"><Target size={12}/> GOAL FOR THIS INPUT</span><code>{py(goal.expected)}</code></div>
    <ArrowRight size={15} aria-hidden="true"/>
    <div><span className="stage-label">YOUR RESULT</span>
      {state === 'running' ? <span className="goal-running">running · step {step + 1}/{total}</span>
        : state === 'pending' ? <span className="goal-note">nothing returned yet</span>
        : <code>{py(goal.result)}<b>{state === 'match' ? ' ✓ matches' : ' ✗ differs'}</b></code>}</div>
  </div>;
}

function ArrayLane({ structure, pointers, reserved = pointers.length, colors, change, focus, stamp, wrong, goalRow, ghost }: {
  structure: Structure; pointers: Pointer[]; reserved?: number; colors: Record<string, string>; change: StepChange; focus: Focus; stamp: number;
  wrong: number[]; goalRow: Value[] | null; ghost: { key: Value; index: string; size: number } | null;
}) {
  const values = (structure.values || []).slice(0, 40);
  const track = useRef<HTMLDivElement>(null);
  const tokens = useRef<Record<number, HTMLSpanElement | null>>({});
  const [width, setWidth] = useState(520);
  useLayoutEffect(() => {
    const node = track.current?.parentElement;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const ghostAt = ghost ? ghostIndex(ghost) : null;
  const slots = values.length + (ghostAt !== null && ghostAt >= values.length ? 1 : 0) + (ghostAt !== null && ghostAt < 0 ? 1 : 0);
  const shift = ghostAt !== null && ghostAt < 0 ? 1 : 0;
  const pitch = Math.max(30, Math.min(68, (width - 16) / Math.max(slots, 1)));
  const cell = Math.round(pitch * 0.84);
  const x = (index: number) => (index + shift) * pitch;
  const swapped = change.swapped[structure.id];
  const written = new Set(change.written[structure.id] || []);
  const reads = new Set(focus.reads[structure.id] || []);
  const compared = new Set(focus.compared[structure.id] || []);
  // A long sequence shows its first cells only: a pointer past them has no cell to point at, so it is named, not drawn.
  const shown = values.length, length = structure.length ?? shown;
  const beyond = length > shown ? pointers.filter(p => p.index >= shown) : [];
  const placed = pointers.filter(p => !beyond.includes(p));
  const range = pointerRange(pointers);
  const band = range && range[0] < shown ? [range[0], Math.min(range[1], shown - 1)] : null;
  // At a wrong return the goal row takes the space under the cells; the pointers have done their work.
  const above = placed.slice(0, 1), below = goalRow ? [] : placed.slice(1);
  const top = reserved > 0 ? 52 : 8;
  const bottom = Math.max(goalRow ? 40 : 6, reserved > 1 ? 22 + (reserved - 1) * 26 : 6) + (ghostAt !== null ? 36 : 0);

  // A swap: both values leave the row, one over and one under, and land in each other's slot.
  useLayoutEffect(() => {
    if (!swapped || reducedMotion()) return;
    const [a, b] = swapped;
    return swapMotion(tokens.current[a], tokens.current[b], (b - a) * pitch, cell * 1.05);
  }, [stamp]);  // eslint-disable-line react-hooks/exhaustive-deps

  return <section className="lane" aria-label={`${structure.id}: ${values.map(v => py(v)).join(', ')}`}>
    <div className="lane-head"><span><Layers size={13}/> {structure.id}</span><code>{structure.type === 'string' ? 'string' : 'list'} · {structure.length ?? values.length}</code></div>
    <ScrollRegion className="lane-scroll" label={`${structure.id}, ${structure.type === 'string' ? 'string' : 'list'} of ${structure.length ?? values.length} (scrollable)`}>
      <div ref={track} className="lane-track" style={{ width: slots * pitch, height: top + cell + bottom, '--top': `${top}px`, '--cell': `${cell}px`, '--pitch': `${pitch}px` } as CSSProperties}>
        {band && <div className="lane-band" style={{ left: x(band[0]) - 5, width: (band[1] - band[0]) * pitch + cell + 10 }} aria-hidden="true"/>}
        {values.map((value, i) => {
          const isSwap = !!swapped && (swapped[0] === i || swapped[1] === i);
          const state = [wrong.includes(i) && 'is-wrong', isSwap && 'is-swapped', !isSwap && written.has(i) && 'is-written', reads.has(i) && 'is-read', compared.has(i) && 'is-compared', goalRow && (json(goalRow[i]) === json(value) ? 'goal-ok' : 'goal-bad')].filter(Boolean).join(' ');
          return <div key={i} className={`cell ${state}`} style={{ left: x(i), width: cell, height: cell }}>
            <span className="cell-index">{i}</span>
            {(reads.has(i) || compared.has(i)) && <span className="cell-ring" key={`r${stamp}`}/>}
            {goalRow && i < goalRow.length && <span className="cell-goal">{py(goalRow[i])}</span>}
          </div>;
        })}
        {values.map((value, i) => {
          const isSwap = !!swapped && (swapped[0] === i || swapped[1] === i);
          const fresh = written.has(i) && !isSwap;
          const label = value === ' ' ? '␣' : py(value).replace(/^'(.*)'$/, '$1');
          // Long values (True, [2, 3]) shrink to fit their tile rather than spill over it.
          return <span key={fresh ? `w${i}-${stamp}` : `t${i}-${json(value)}`} ref={node => { tokens.current[i] = node; }} className={`cell-token ${fresh ? 'is-written' : ''}`} style={{ left: x(i), width: cell, height: cell, ...(label.length > 3 ? { fontSize: Math.max(9, Math.round(cell * 1.3 / label.length)) } : {}) }} aria-hidden="true">
            {label}
            {change.old[structure.id]?.[i] !== undefined && fresh && <span className="cell-ghost">{py(change.old[structure.id][i])}</span>}
          </span>;
        })}
        {ghostAt !== null && <div className="cell cell-missing" style={{ left: x(Math.max(-1, Math.min(ghostAt, values.length))), width: cell, height: cell }}>
          <span className="cell-index">{ghostAt}</span><span className="cell-token">?</span>
          <span className="cell-missing-note">{structure.id}[{ghost!.index}] · no position {ghostAt}</span>
        </div>}
        {above.map(p => <PointerMark key={p.name} pointer={p} x={x(p.index) + cell / 2} color={colors[p.name]} row={-1}/>)}
        {below.map((p, row) => <PointerMark key={p.name} pointer={p} x={x(p.index) + cell / 2} color={colors[p.name]} row={row}/>)}
      </div>
    </ScrollRegion>
    {length > shown && <p className="stage-note">Showing the first {shown} of {length} elements.{beyond.length > 0 && ` Beyond them: ${beyond.map(p => `${p.name} → ${p.outside === 'after' ? 'past the end' : `index ${p.index}`}`).join(', ')}.`}</p>}
  </section>;
}

/** A swap's motion: each value rises (or dips) out of the row, crosses, and settles into the other slot. The
 * returned cleanup reverts both tokens, so whether the motion finished or was cut short (fast playback, the
 * case tour, quick steps), every token ends at its resting place with no transform left behind. */
function swapMotion(a: HTMLElement | null | undefined, b: HTMLElement | null | undefined, dx: number, lift: number) {
  const ctx = gsap.context(() => {
    const arc = (node: HTMLElement | null | undefined, from: number, dy: number) => node && gsap.timeline()
      .fromTo(node, { x: from, y: 0, scale: 1 }, { x: from / 2, y: dy, scale: 1.12, duration: 0.34, ease: 'power2.out' })
      .to(node, { x: 0, y: 0, scale: 1, duration: 0.34, ease: 'power2.in' });
    arc(a, dx, -lift);
    arc(b, -dx, lift);
  });
  return () => ctx.revert();
}

function PointerMark({ pointer, x, color, row }: { pointer: Pointer; x: number; color: string; row: number }) {
  const up = row < 0;
  return <div className={`ptr ${up ? 'ptr-up' : 'ptr-down'} ${pointer.outside ? 'ptr-outside' : ''}`} style={{ transform: `translateX(${x}px)`, '--c': color, '--stem': `${up ? 16 : 14 + row * 24}px` } as CSSProperties}>
    <span className="ptr-stem"/><span className="ptr-label">{pointer.name}{pointer.outside && <small> {pointer.outside === 'after' ? 'past end' : 'before start'}</small>}</span>
  </div>;
}

function MapTable({ structure, change, focus, stamp, missing }: { structure: Structure; change: StepChange; focus: Focus; stamp: number; missing?: Value }) {
  const set = structure.type === 'hashset';
  const entries = structure.entries || (structure.values || []).map(key => ({ key, value: null as Value }));
  const added = new Set(change.added[structure.id] || []), changed = new Set(change.changed[structure.id] || []);
  const lookup = focus.lookup?.structure === structure.id ? focus.lookup : null;
  return <section className={`table ${set ? 'table-set' : ''}`} aria-label={`${structure.id}: ${entries.length} entries`}>
    <div className="lane-head"><span><Braces size={13}/> {structure.id}</span><code>{set ? 'set' : 'dict'} · {entries.length}</code></div>
    {lookup && <div className={`probe ${lookup.found ? 'probe-found' : 'probe-miss'}`} key={`p${stamp}`}><Search size={12}/> looking for <code>{py(lookup.key)}</code> {lookup.found ? '✓ found' : '✗ not here'}</div>}
    <div className="table-rows">
      {entries.length === 0 && <div className="table-empty">empty</div>}
      {entries.map(entry => {
        const key = json(entry.key);
        const hit = lookup?.found && json(lookup.key) === key;
        return <div key={key} className={`row ${added.has(key) ? 'is-added' : ''} ${changed.has(key) ? 'is-changed' : ''} ${hit ? 'is-hit' : ''}`}>
          <code className="row-key">{py(entry.key)}</code>{!set && <><ArrowRight size={11}/><code className="row-value" key={changed.has(key) ? `c${stamp}` : 'v'}>{py(entry.value)}</code></>}
        </div>;
      })}
      {/* A key this step deleted: marked removed in every motion setting, and animated away when motion is on. */}
      {(change.removed[structure.id] || []).map(entry => <div key={`gone-${json(entry.key)}-${stamp}`} className="row is-removed"><code className="row-key">{py(entry.key)}</code><span>removed</span></div>)}
      {missing !== undefined && <div className="row row-missing"><code className="row-key">{py(missing)}</code><span>missing key</span></div>}
    </div>
  </section>;
}

function VariableTape({ event, change, pointers, colors }: { event: TraceEvent; change: StepChange; pointers: Set<string>; colors: Record<string, string> }) {
  if (!event.state.variables.length) return null;
  return <div className="tape" aria-label="Variables">{event.state.variables.map(v => {
    const changed = v.id in change.variables;
    return <div key={v.id} className={`chip ${changed ? 'is-changed' : ''}`} style={pointers.has(v.id) ? { '--c': colors[v.id] } as CSSProperties : undefined}>
      <code>{v.id}</code><span key={changed ? `v${event.id}` : 'v'}>{py(v.value)}</span>
      {changed && change.variables[v.id] !== undefined && <small>was {py(change.variables[v.id])}</small>}
    </div>;
  })}</div>;
}

function StageAlert({ event, step, last, divergence, wrong, goal, onSeek }: { event: TraceEvent; step: number; last: boolean; divergence: Divergence | null | undefined; wrong: { position: number; value: Value; goal: Value }[]; goal: GoalState | null; onSeek?: (step: number) => void }) {
  const go = (target: number | null | undefined, label: ReactNode) => target !== null && target !== undefined && onSeek ? <button onClick={() => onSeek(target)}>{label}</button> : null;
  const cycle = divergence?.cycle;
  let alert: ReactNode = null, tone = 'warn';
  if (event.type === 'ERROR' && cycle) {
    tone = 'bad';
    alert = <><Repeat2 size={16}/><div><strong>Infinite loop, proven</strong><p>The while loop on line {cycle.line} reached exactly the same state twice. Nothing changed between those iterations, so it would never finish.</p><span className="alert-actions">{go(cycle.first, `Step ${(cycle.first ?? 0) + 1}`)}{go(cycle.repeat, `Step ${(cycle.repeat ?? 0) + 1} · same state`)}</span></div></>;
  } else if (cycle && (step === cycle.first || step === cycle.repeat)) {
    alert = <><Repeat2 size={16}/><div><strong>{step === cycle.repeat ? `Same state as step ${(cycle.first ?? 0) + 1}` : `This state comes back at step ${(cycle.repeat ?? 0) + 1}`}</strong><p>Compare the variables: every value is identical, so the loop is going in circles.</p></div></>;
  } else if (event.type === 'ERROR') {
    tone = 'bad';
    const access = event.meta.access;
    alert = <><TriangleAlert size={16}/><div><strong>{access ? access.kind === 'dict' ? `Key ${py(access.key)} is not in ${access.structure}` : `${access.structure}[${access.index}] is outside the list` : 'Execution stopped'}</strong><p>{access?.kind === 'sequence' ? `${access.index} = ${py(access.key)}, but ${access.structure} only has positions 0 to ${access.size - 1}.` : event.detail}</p></div></>;
  } else if (wrong.length) {
    tone = 'bad';
    alert = <><CircleAlert size={16}/><div><strong>This write stays wrong to the end</strong><p>{wrong.map(w => `Position ${w.position} gets ${py(w.value)}${w.goal !== null ? ` — the goal has ${py(w.goal)} there` : ' — the goal does not include it'}.`).join(' ')} It is never changed afterwards. The cause may be earlier.</p></div></>;
  } else if (divergence && !divergence.cycle && (divergence.step === step || (divergence.step === null && last))) {
    tone = divergence.kind === 'Nothing returned yet' ? 'warn' : 'bad';
    alert = <><CircleAlert size={16}/><div><strong>{divergence.kind}</strong><p>{divergence.message}</p></div></>;
  } else if (goal?.returned && goal.matches && step === goal.returnStep) {  // The program's own return: a design problem's last operation.
    tone = 'good';
    alert = <><BookOpenCheck size={16}/><div><strong>On target for this input</strong><p>Your result matches the goal. Run all tests to check other inputs.</p></div></>;
  }
  return alert ? <div className={`stage-alert alert-${tone}`} key={`${step}-${tone}`} role={tone === 'bad' ? 'alert' : 'status'}>{alert}</div> : null;
}

function Narration({ event, step, total, focus, bits }: { event: TraceEvent; step: number; total: number; focus: Focus; bits?: TraceEvent }) {
  const category = categoryOf(event.type);
  const Icon = icons[category];
  return <div className={`narration cat-${category}`} key={event.id}>
    <div className="narration-top"><span><Icon size={14}/> {verbs[category]}</span><code>line {event.line} · step {step + 1}/{total}</code></div>
    {bits ? <><h3>{event.type === 'BIT_OP' ? event.detail : event.explanation?.what ?? event.detail}</h3><BitStrip event={bits}/></>
      : focus.compare
      ? <div className="compare-visual"><code>{py(focus.compare.left)}</code><span>{focus.compare.expression.replace(/^.*?\s(==|!=|<=|>=|<|>|not in|in|is not|is)\s.*$/, '$1')}</span><code>{py(focus.compare.right)}</code><b className={focus.compare.result ? 'is-true' : 'is-false'}>{focus.compare.result ? 'True' : 'False'}</b><small>{focus.compare.expression}</small></div>
      : <h3>{event.explanation?.what ?? event.detail}</h3>}
    {event.explanation?.why && <p>{event.explanation.why}</p>}
  </div>;
}

function LineLens({ events, lines, code, line, current, onSeek }: { events: TraceEvent[]; lines?: Record<string, number>; code: string; line: number; current: number; onSeek?: (step: number) => void }) {
  const lens = useMemo(() => lineLens({ events, lines }, code, line), [events, lines, code, line]);
  if (!lens.source) return null;
  const summary = lens.iterations ? `${lens.iterations} iteration${lens.iterations === 1 ? '' : 's'}` : lens.ran === null ? '' : lens.ran ? `ran ${lens.ran}×` : 'never ran';
  return <div className={`lens ${lens.ran === 0 && !/^def\s/.test(lens.source) ? 'lens-idle' : ''}`} aria-label={`What line ${line} did`}>
    <div className="lens-head"><span className="stage-label">LINE {line}{line === current ? ' · NOW' : ' · YOUR CURSOR'}</span><code>{lens.source}</code>{summary && <b>{summary}</b>}</div>
    {lens.samples.length > 0 && <div className="lens-samples">{lens.samples.map((s, i) => <button key={s.step} onClick={() => onSeek?.(s.step)} title={`Go to step ${s.step + 1}`}>{i > 0 && <ArrowRight size={10}/>}{s.label}</button>)}{lens.more > 0 && <span>+{lens.more} more</span>}</div>}
    {lens.note && <p>{lens.note}</p>}
  </div>;
}

function ExecutionRibbon({ events, divergence, step, onSeek }: { events: TraceEvent[]; divergence: Divergence | null | undefined; step: number; onSeek?: (step: number) => void }) {
  const model = useMemo(() => ribbon({ events, divergence: divergence ?? null }), [events, divergence]);
  const total = Math.max(1, events.length);
  return <div className="ribbon" aria-label="Execution overview">
    <div className="ribbon-track" onClick={e => { const r = e.currentTarget.getBoundingClientRect(); onSeek?.(Math.min(total - 1, Math.floor((e.clientX - r.left) / r.width * total))); }}>
      {model.ticks.map((category, i) => <i key={i} className={`tick cat-${category}`} style={{ left: `${i / total * 100}%`, width: `${100 / total}%` }}/>)}
      {model.markers.map((m, i) => <button key={i} className={`marker marker-${m.kind}`} style={{ left: `${(m.step + 0.5) / total * 100}%` }} title={`Step ${m.step + 1}: ${m.label}`} aria-label={`Step ${m.step + 1}: ${m.label}`} onClick={e => { e.stopPropagation(); onSeek?.(m.step); }}/>)}
      <span className="ribbon-now" style={{ left: `${(step + 0.5) / total * 100}%` }}/>
    </div>
    <div className="ribbon-legend">{(['read', 'write', 'compare', 'lookup', 'insert', 'loop', 'return'] as Category[]).map(c => <span key={c} className={`cat-${c}`}>{verbs[c].toLowerCase()}</span>)}</div>
  </div>;
}

/** Pre-run view: the input itself, before any code has run. */
export function InputStage({ structures, variables }: { structures: Structure[]; variables: { id: string; value: Value }[] }) {
  const snapshot: TraceEvent = { id: 0, type: 'STATE_CHANGE', line: 0, source: '', detail: '', meta: {}, state: { structures, variables, callstack: [] }, explanation: { what: '', why: '' } };
  return <div className="stage stage-input">
    <div className="stage-structures">{structures.map(s => s.type === 'nodes' ? <NodeCanvas key={s.id} structure={s}/>
      : s.type === 'matrix' ? <MatrixGrid key={s.id} structure={s} event={snapshot}/>
      : s.type === 'graph' ? <GraphView key={s.id} structure={s} event={snapshot}/>
      : isSequence(s)
      ? <ArrayLane key={s.id} structure={s} pointers={[]} colors={{}} change={empty} focus={{ reads: {}, compared: {}, lookup: null, compare: null }} stamp={0} wrong={[]} goalRow={null} ghost={null}/>
      : <MapTable key={s.id} structure={s} change={empty} focus={{ reads: {}, compared: {}, lookup: null, compare: null }} stamp={0}/>)}</div>
    {variables.length > 0 && <div className="tape">{variables.map(v => <div key={v.id} className="chip"><code>{v.id}</code><span>{py(v.value)}</span></div>)}</div>}
  </div>;
}
