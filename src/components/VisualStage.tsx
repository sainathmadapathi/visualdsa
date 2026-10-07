import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { ArrowRight, BookOpenCheck, Braces, CircleAlert, CornerDownLeft, Cpu, Eye, GitCompareArrows, Layers, LogIn, Pencil, Repeat2, Search, Sparkles, Target, TriangleAlert } from 'lucide-react';
import ScrollRegion from './ScrollRegion';
import { reducedMotion } from '../motion';
import { useFlip } from '../flip';
import type { Divergence, RunError, Structure, TraceEvent, Value } from '../types';
import { ErrorBody, explanationOf } from './ErrorCard';
import { categoryOf, changeLabels, focusAt, ghostIndex, goalRowFor, gridPointerNames, laneMotion, lineLens, nodeRef, phases, pointerNames, pointerRange, pointersAt, py, rangePairs, readCounts, returnedLane, ribbon, stepChange, valueTrail, variableRoles, workDone, wrongAt } from '../visualModel';
import type { Category, Focus, GoalState, LaneMotion, Pointer, StepChange } from '../visualModel';
import { callHistory, callLabel, showCalls, walkedNodes } from '../structureModel';
import type { CallHistory } from '../structureModel';
import { BitStrip, CallTree, GraphView, HeapTree, MatrixGrid, NodeCanvas, QueueView, StackView, colorOf } from './StructureViews';

const empty: StepChange = { written: {}, old: {}, swapped: {}, added: {}, changed: {}, removed: {}, variables: {} };
const still: LaneMotion = { moves: [], copies: [], gone: [], added: [], vacated: [] };
const palette = ['#f3a25f', '#c9a2f5', '#78d4c6', '#f590b4', '#e9d27c', '#9cc3ff'];
const json = (value: unknown) => JSON.stringify(value);
const isSequence = (s: Structure) => s.type === 'array' || s.type === 'string';
const icons: Record<Category, typeof Eye> = { read: Eye, write: Pencil, compare: GitCompareArrows, lookup: Search, insert: Braces, loop: Repeat2, call: LogIn, return: CornerDownLeft, error: TriangleAlert, state: Sparkles };
const verbs: Record<Category, string> = { read: 'Read', write: 'Write', compare: 'Compare', lookup: 'Lookup', insert: 'Store', loop: 'Loop', call: 'Call', return: 'Return', error: 'Stopped', state: 'Update' };

export interface StageProps {
  events: TraceEvent[]; step: number; onSeek?: (step: number) => void;
  goal: GoalState | null; divergence: Divergence | null | undefined;
  /** What stopped this run, if anything: shown in plain words at the step where it stopped. */
  error?: RunError | null;
  /** The line to summarise; defaults to the current step's line. */
  focusLine?: number | null; lines?: Record<string, number>; code?: string;
}

/** The animated stage: everything shown is a recorded snapshot of the learner's own run. */
export default function VisualStage({ events, step, onSeek, goal, divergence, focusLine, lines, code = '', error = null }: StageProps) {
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
  const ranges = useMemo(() => rangePairs(events, names), [events, names]);
  // The program's inputs (the entry call's parameters): only an input grid can be read as a map.
  const inputs = useMemo(() => new Set(events.find(e => e.type === 'RECURSION_CALL')?.meta.call?.order ?? []), [events]);
  const grids = useMemo(() => gridPointerNames(events), [events]);
  // Each grid's first recorded snapshot decides whether it is an island map (see islandMap).
  const firstRows = useMemo(() => {
    const first: Record<string, Value[][]> = {};
    for (const e of events) for (const s of e.state.structures) if (s.type === 'matrix' && !(s.id in first)) first[s.id] = s.rows || [];
    return first;
  }, [events]);
  const calls = useMemo(() => showCalls(events), [events]);
  const history = useMemo(() => callHistory(events), [events]);
  const roles = useMemo(() => variableRoles(events, code, names), [events, code, names]);
  // Lanes whose positions the run reads more than once: their read counts are shown from the start.
  const recounted = useMemo(() => {
    const ids = new Set(events.flatMap(e => e.type === 'ARRAY_ACCESS' && e.meta.structure ? [e.meta.structure] : []));
    return new Set([...ids].filter(id => Object.values(readCounts(events, events.length - 1, id, history.frames) || {}).some(n => n > 1)));
  }, [events, history]);
  const walked = useMemo(() => walkedNodes(events, step), [events, step]);
  // Tables the run looks keys up in keep a line for the probe, so a lookup step never shifts what is below.
  const probed = useMemo(() => new Set(events.flatMap((e, i) => e.type === 'HASHMAP_LOOKUP' ? [focusAt(events, i).lookup?.structure] : []).filter(Boolean)), [events]);
  if (!event) return null;
  const wrong = wrongAt(divergence, step);
  // The step before, for views that animate what changed (re-links, new nodes, writes, pushes and pops).
  const before = forward ? events[step - 1] : undefined;
  const previous = (id: string) => before?.state.structures.find(s => s.id === id);
  const rank = (s: Structure) => s.type === 'nodes' ? 0 : s.type === 'graph' ? 1 : s.type === 'matrix' ? 2 : 3;
  const structures = [...event.state.structures].sort((a, b) => rank(a) - rank(b));
  // How each sequence's values travelled in this step: only a step forward animates.
  const motions = Object.fromEntries(structures.filter(isSequence).map(s => [s.id, forward ? laneMotion(events, step, s.id) : still]));
  // A bit operation stays in view while its line is still running.
  let bits: TraceEvent | undefined;
  for (let i = step; i >= 0 && i >= step - 3 && events[i].line === event.line; i--) if (events[i].type === 'BIT_OP') { bits = events[i]; break; }
  const failed = event.type === 'ERROR' ? event.meta.access : undefined;

  return <div className="stage" data-category={categoryOf(event.type)}>
    {goal && <GoalBar key={json(goal.expected)} goal={goal} step={step} total={events.length}/>}
    <div className="stage-structures">
      {structures.map(s => s.type === 'nodes' ? <NodeCanvas key={s.id} structure={s} previous={previous(s.id)} walked={walked}/>
        : s.type === 'graph' ? <GraphView key={s.id} structure={s} event={event} events={events} step={step} animate={forward}/>
        : s.type === 'matrix' ? <MatrixGrid key={s.id} structure={s} previous={previous(s.id)} event={event} pointers={grids[s.id]} first={firstRows[s.id]} input={inputs.has(s.id)} events={events} step={step}/>
        : isSequence(s) && s.kind === 'stack' ? <StackView key={s.id} structure={s} previous={previous(s.id)} stamp={event.id}/>
        : isSequence(s) && s.kind === 'queue' ? <QueueView key={s.id} structure={s} events={events} step={step} animate={forward}/>
        : isSequence(s)
        ? <div key={s.id} className="lane-group"><ArrayLane structure={s} pointers={pointersAt(event, s, names[s.id] || [])} reserved={(names[s.id] || []).length} colors={colors} change={change} focus={focus} stamp={event.id}
            motion={motions[s.id]} range={ranges[s.id] ?? null}
            wrong={divergence?.elements?.name === s.id ? wrong.map(w => w.position) : []}
            goalRow={goalRowFor(goal, s.id, returnName)}
            ghost={failed && failed.structure === s.id && failed.kind === 'sequence' && failed.size !== null ? { key: failed.key, index: failed.index, size: failed.size } : null}
            reads={recounted.has(s.id) ? readCounts(events, step, s.id, history.frames) : null}
            legend={laneLegend(events, s.id, (names[s.id] || []).length > 0, recounted.has(s.id))}/>
          {s.kind === 'heap' && <HeapTree structure={s} previous={previous(s.id)} motion={motions[s.id]} stamp={event.id}/>}</div>
        : <MapTable key={s.id} structure={s} change={change} focus={focus} stamp={event.id} animate={forward} probed={probed.has(s.id)} missing={failed && failed.structure === s.id && failed.kind === 'dict' ? failed.key : undefined}/>)}
    </div>
    {calls && <CallTree events={events} step={step} onSeek={onSeek} animate={forward}/>}
    <MemoryPanel events={events} step={step} change={change} forward={forward} history={history} roles={roles} pointers={new Set(Object.values(names).flat())} colors={colors}/>
    {event.state.callstack.length > 1 && !calls && <div className="stage-frames" aria-label="Call stack">{event.state.callstack.map((frame, i) => <span key={i} style={{ '--depth': i } as CSSProperties}>{frame}</span>)}</div>}
    <Narration event={event} step={step} total={events.length} focus={focus} bits={bits} changes={changeLabels(events[step - 1], event)}/>
    <StageAlert event={event} step={step} last={step === events.length - 1} divergence={divergence} wrong={wrong} goal={goal} onSeek={onSeek} error={error}/>
    <LineLens events={events} lines={lines} code={code} line={focusLine && /^(?!def\s|#)\S/.test((code.split('\n')[focusLine - 1] || '').trim()) ? focusLine : event.line} current={event.line} onSeek={onSeek}/>
    <ExecutionRibbon events={events} divergence={divergence} step={step} onSeek={onSeek} code={code}/>
  </div>;
}

const text = (value: Value | undefined) => typeof value === 'string' ? value : py(value ?? null);

/** What a lane's marks mean, for the marks this run actually makes on it: a read that fed a comparison is one
 * made just before it on the same line, as focusAt marks it. */
function laneLegend(events: TraceEvent[], id: string, pointers: boolean, recounted: boolean) {
  const read = events.some(e => e.type === 'ARRAY_ACCESS' && e.meta.structure === id);
  const compared = events.some((e, i) => {
    if (e.type !== 'COMPARE') return false;
    for (let j = i - 1; j >= 0 && events[j].line === e.line && events[j].type === 'ARRAY_ACCESS'; j--) if (events[j].meta.structure === id) return true;
    return false;
  });
  const written = events.some(e => e.type === 'ARRAY_WRITE' && (e.meta.targets || [e.detail]).some(t => t.startsWith(`${id}[`)));
  return [pointers && 'pointer', read && 'read', compared && 'compared', written && 'written', recounted && 'count'].filter(Boolean) as string[];
}

/** The goal for this input is its answer, like the example's output in Understand: it stays hidden until the
 * learner's code has returned for this input (the verdict) or they ask to see it, so they can predict it first. */
function GoalBar({ goal, step, total }: { goal: GoalState; step: number; total: number }) {
  const [asked, setAsked] = useState(false);
  const state = !goal.returned ? (step >= total - 1 ? 'stopped' : 'running') : goal.result === null && goal.expected !== null && !goal.matches ? 'pending' : goal.matches ? 'match' : 'differs';
  // The bar never shrinks while one case is watched (it is keyed by the case's goal), so the verdict replacing the
  // taller prompt never shifts the stage below it.
  const bar = useRef<HTMLDivElement>(null), tallest = useRef(0);
  useLayoutEffect(() => { tallest.current = Math.max(tallest.current, bar.current?.offsetHeight ?? 0); });
  return <div ref={bar} className={`goal-bar goal-${state}`} role="status" style={tallest.current ? { minHeight: tallest.current } : undefined}>
    <div><span className="stage-label"><Target size={12}/> GOAL FOR THIS INPUT{goal.computed && <em className="computed-tag" title="Computed by a reference solution checked against this problem's page examples: not given by the page.">computed</em>}</span>
      {/* Returning nothing (the untouched starter) is no answer yet: the goal still waits for a prediction. */}
      {(goal.returned && state !== 'pending') || asked ? <code>{py(goal.expected)}</code>
        : <span className="goal-hidden">Predict it first: it appears when your code returns an answer. <button onClick={() => setAsked(true)}><Eye size={13}/> Show the goal</button></span>}</div>
    <ArrowRight size={15} aria-hidden="true"/>
    <div><span className="stage-label">YOUR RESULT</span>
      {state === 'running' ? <span className="goal-running">running · step {step + 1}/{total}</span>
        : state === 'stopped' ? <span className="goal-note">stopped before returning</span>
        : state === 'pending' ? <span className="goal-note">nothing returned yet</span>
        : <code>{py(goal.result)}<b>{state === 'match' ? ' ✓ matches' : ' ✗ differs'}</b></code>}</div>
  </div>;
}

const LEGEND: Record<string, string> = { pointer: 'a variable indexing it', read: 'read now', compared: 'feeds a comparison', written: 'just written (old value floats off)', count: '×n read n times so far' };
function ArrayLane({ structure, pointers, reserved = pointers.length, colors, change, focus, stamp, wrong, goalRow, ghost, reads: counts = null, legend = [], motion = still, range: bounds = null }: {
  structure: Structure; pointers: Pointer[]; reserved?: number; colors: Record<string, string>; change: StepChange; focus: Focus; stamp: number;
  wrong: number[]; goalRow: Value[] | null; ghost: { key: Value; index: string; size: number } | null;
  /** How often each position has been read so far, when the run reads some position more than once. */
  reads?: Record<number, number> | null; legend?: string[];
  /** How this step's values travelled: moved, copied from another position, gone, or new (see laneMotion). */
  motion?: LaneMotion;
  /** The two pointers that bound a range on this lane, if the run shows any (see rangePairs). */
  range?: [string, string] | null;
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
  // Positions a shorter lane just gave up keep their room while their values leave (only drawn with motion on).
  const vacated = motion.vacated.length && !reducedMotion() ? Math.max(...motion.vacated) + 1 - values.length : 0;
  const slots = values.length + Math.max(0, vacated) + (ghostAt !== null && ghostAt >= values.length ? 1 : 0) + (ghostAt !== null && ghostAt < 0 ? 1 : 0);
  const shift = ghostAt !== null && ghostAt < 0 ? 1 : 0;
  const pitch = Math.max(30, Math.min(68, (width - 16) / Math.max(slots, 1)));
  const cell = Math.round(pitch * 0.84);
  const x = (index: number) => (index + shift) * pitch;
  const swapped = change.swapped[structure.id];
  const written = new Set(change.written[structure.id] || []);
  const moved = new Map(motion.moves), copied = new Map(motion.copies), added = new Set(motion.added);
  const sources = new Set(motion.copies.map(([, from]) => from));
  // Values that moved or were inserted were not overwritten: nothing of theirs floats off.
  const shifted = motion.moves.length + motion.gone.length + motion.added.length > 0;
  const readNow = new Set(focus.reads[structure.id] || []);
  const hottest = Math.max(1, ...Object.values(counts || {}));
  const compared = new Set(focus.compared[structure.id] || []);
  // A long sequence shows its first cells only: a pointer past them has no cell to point at, so it is named, not drawn.
  const shown = values.length, length = structure.length ?? shown;
  const beyond = length > shown ? pointers.filter(p => p.index >= shown) : [];
  const placed = pointers.filter(p => !beyond.includes(p));
  const range = pointerRange(pointers, bounds);
  const band = range && range[0] < shown ? [range[0], Math.min(range[1], shown - 1)] : null;
  // At a wrong return the goal row takes the space under the cells; the pointers have done their work.
  const above = placed.slice(0, 1), below = goalRow ? [] : placed.slice(1);
  const top = reserved > 0 ? 52 : 8;
  const bottom = Math.max(goalRow ? 40 : 6, reserved > 1 ? 22 + (reserved - 1) * 26 : 6) + (ghostAt !== null ? 36 : 0);

  // Values travel to where this step put them: a swap's two values cross, one over and one under; a reordered
  // lane's values glide to their new places (rightward over, leftward under, so crossings stay readable); an
  // insert or removal slides the rest along; a copied value flies from the position it was read from.
  useLayoutEffect(() => {
    if (reducedMotion()) return;
    const runs: (Animation | undefined)[] = [];
    if (swapped) {
      const [a, b] = swapped;
      runs.push(...travel(tokens.current[a], (b - a) * pitch, -cell * 0.85, 680), ...travel(tokens.current[b], (a - b) * pitch, cell * 0.85, 680));
    } else {
      const reorder = !motion.added.length && !motion.gone.length;
      for (const [to, from] of motion.moves) runs.push(...travel(tokens.current[to], (from - to) * pitch, reorder ? Math.sign(to - from) * -cell * 0.55 : 0, 560));
      for (const [to, from] of motion.copies) runs.push(...travel(tokens.current[to], (from - to) * pitch, -cell * 0.8, 620));
    }
    return () => runs.forEach(run => run?.cancel());
  }, [stamp]);  // eslint-disable-line react-hooks/exhaustive-deps

  return <section className="lane" aria-label={`${structure.id}: ${values.map(v => py(v)).join(', ')}`}>
    <div className="lane-head"><span><Layers size={13}/> {structure.id}</span><code>{structure.type === 'string' ? 'string' : 'list'} · {structure.length ?? values.length}</code></div>
    <ScrollRegion className="lane-scroll" label={`${structure.id}, ${structure.type === 'string' ? 'string' : 'list'} of ${structure.length ?? values.length} (scrollable)`}>
      <div ref={track} className="lane-track" style={{ width: slots * pitch, height: top + cell + bottom, '--top': `${top}px`, '--cell': `${cell}px`, '--pitch': `${pitch}px` } as CSSProperties}>
        {band && <div className="lane-band" style={{ left: x(band[0]) - 5, width: (band[1] - band[0]) * pitch + cell + 10 }} aria-hidden="true"/>}
        {values.map((value, i) => {
          const isSwap = !!swapped && (swapped[0] === i || swapped[1] === i);
          const isMove = !isSwap && moved.has(i);
          const state = [wrong.includes(i) && 'is-wrong', isSwap && 'is-swapped', isMove && 'is-moved', !isSwap && !isMove && written.has(i) && 'is-written', readNow.has(i) && 'is-read', compared.has(i) && 'is-compared', sources.has(i) && 'is-source', goalRow && (json(goalRow[i]) === json(value) ? 'goal-ok' : 'goal-bad')].filter(Boolean).join(' ');
          const count = counts?.[i] ?? 0;
          return <div key={i} className={`cell ${state}`} style={{ left: x(i), width: cell, height: cell, ...(count > 1 ? { '--reads': Math.min(1, (count - 1) / Math.max(1, hottest - 1)) } : {}) } as CSSProperties}>
            <span className="cell-index">{i}</span>
            {count > 1 && <span className="cell-count" key={`c${count}`} title={`${structure.id}[${i}] read ${count} times so far`}>×{count}</span>}
            {(readNow.has(i) || compared.has(i) || sources.has(i)) && <span className="cell-ring" key={`r${stamp}`}/>}
            {goalRow && i < goalRow.length && <span className="cell-goal">{py(goalRow[i])}</span>}
          </div>;
        })}
        {motion.vacated.map(i => <div key={`v${i}-${stamp}`} className="cell is-vacated" style={{ left: x(i), width: cell, height: cell }} aria-hidden="true"/>)}
        {values.map((value, i) => {
          const isSwap = !!swapped && (swapped[0] === i || swapped[1] === i);
          const isMove = !isSwap && moved.has(i);
          const fresh = written.has(i) && !isSwap && !isMove;
          const label = tokenLabel(value);
          // Keyed by position and value: a token mounts (and enters) only when its value is new to the position,
          // and a later step that only re-styles it never replays the entrance.
          return <span key={`t${i}-${json(value)}`} ref={node => { tokens.current[i] = node; }} className={`cell-token ${isSwap || isMove ? 'is-moving' : ''} ${fresh ? 'is-written' : ''} ${fresh && added.has(i) ? 'is-inserted' : ''} ${copied.has(i) ? 'is-copied' : ''}`} style={tokenStyle(x(i), cell, label)} aria-hidden="true">
            {label}
            {change.old[structure.id]?.[i] !== undefined && fresh && !shifted && <span className="cell-ghost">{py(change.old[structure.id][i])}</span>}
          </span>;
        })}
        {motion.gone.map(({ from, value }) => { const label = tokenLabel(value); return <span key={`g${from}-${stamp}`} className="cell-token is-leaving" style={tokenStyle(x(from), cell, label)} aria-hidden="true">{label}</span>; })}
        {ghostAt !== null && <div className="cell cell-missing" style={{ left: x(Math.max(-1, Math.min(ghostAt, values.length))), width: cell, height: cell }}>
          <span className="cell-index">{ghostAt}</span><span className="cell-token">?</span>
          <span className="cell-missing-note">{structure.id}[{ghost!.index}] · no position {ghostAt}</span>
        </div>}
        {above.map(p => <PointerMark key={p.name} pointer={p} x={x(p.index) + cell / 2} color={colors[p.name]} row={-1}/>)}
        {below.map((p, row) => <PointerMark key={p.name} pointer={p} x={x(p.index) + cell / 2} color={colors[p.name]} row={row}/>)}
      </div>
    </ScrollRegion>
    {length > shown && <p className="stage-note">Showing the first {shown} of {length} elements.{beyond.length > 0 && ` Beyond them: ${beyond.map(p => `${p.name} → ${p.outside === 'after' ? 'past the end' : `index ${p.index}`}`).join(', ')}.`}</p>}
    {legend.length > 1 && <div className="view-legend" aria-hidden="true">{legend.map(item => <span key={item} className={`lg-${item}`}>{LEGEND[item]}</span>)}</div>}
  </section>;
}

const tokenLabel = (value: Value) => value === ' ' ? '␣' : py(value).replace(/^'(.*)'$/, '$1');
// Long values (True, [2, 3]) shrink to fit their tile rather than spill over it.
const tokenStyle = (left: number, cell: number, label: string): CSSProperties => ({ left, width: cell, height: cell, ...(label.length > 3 ? { fontSize: Math.max(9, Math.round(cell * 1.3 / label.length)) } : {}) });

/** A value's journey to its resting place: it starts `dx` away, glides home, and on the way rises (or dips) by
 * `lift` and back. The across and the up-and-down are separate animations on separate properties (translate and
 * transform), so the path is a true arc and never fights the token's own entrance or pop. Cancelling them (the
 * step changed: fast playback, the case tour, a jump) leaves the token exactly at rest. */
function travel(node: HTMLElement | null | undefined, dx: number, lift: number, duration: number): (Animation | undefined)[] {
  if (!node?.animate || (!dx && !lift)) return [];
  return [
    node.animate([{ translate: `${dx}px 0px` }, { translate: '0px 0px' }], { duration, easing: 'cubic-bezier(.45, .05, .25, 1)' }),
    lift ? node.animate([
      { transform: 'translateY(0px) scale(1)', easing: 'cubic-bezier(.1, .4, .6, 1)' },
      { transform: `translateY(${lift}px) scale(1.1)`, easing: 'cubic-bezier(.4, 0, .9, .6)' },
      { transform: 'translateY(0px) scale(1)' },
    ], { duration, composite: 'add' }) : undefined,
  ];
}

function PointerMark({ pointer, x, color, row }: { pointer: Pointer; x: number; color: string; row: number }) {
  const up = row < 0;
  return <div className={`ptr ${up ? 'ptr-up' : 'ptr-down'} ${pointer.outside ? 'ptr-outside' : ''}`} style={{ transform: `translateX(${x}px)`, '--c': color, '--stem': `${up ? 16 : 14 + row * 24}px` } as CSSProperties}>
    <span className="ptr-stem"/><span className="ptr-label">{pointer.name}{pointer.outside && <small> {pointer.outside === 'after' ? 'past end' : 'before start'}</small>}</span>
  </div>;
}

function MapTable({ structure, change, focus, stamp, animate = false, probed = false, missing }: { structure: Structure; change: StepChange; focus: Focus; stamp: number; animate?: boolean; probed?: boolean; missing?: Value }) {
  const rows = useRef<HTMLDivElement>(null);
  const stood = useFlip(rows, stamp, animate);
  const set = structure.type === 'hashset';
  const entries = structure.entries || (structure.values || []).map(key => ({ key, value: null as Value }));
  const added = new Set(change.added[structure.id] || []), changed = new Set(change.changed[structure.id] || []);
  const lookup = focus.lookup?.structure === structure.id ? focus.lookup : null;
  return <section className={`table ${set ? 'table-set' : ''}`} aria-label={`${structure.id}: ${entries.length} entries`}>
    <div className="lane-head"><span><Braces size={13}/> {structure.id}</span><code>{set ? 'set' : 'dict'} · {entries.length}</code></div>
    {(lookup || probed) && <div className="probe-slot">{lookup && <div className={`probe ${lookup.found ? 'probe-found' : 'probe-miss'}`} key={`p${stamp}`}><Search size={12}/> looking for <code>{py(lookup.key)}</code> {lookup.found ? '✓ found' : '✗ not here'}</div>}</div>}
    <div className="table-rows" ref={rows}>
      {entries.length === 0 && <div className="table-empty">empty</div>}
      {entries.map(entry => {
        const key = json(entry.key);
        const hit = lookup?.found && json(lookup.key) === key;
        return <div key={key} data-flip={key} className={`row ${added.has(key) ? 'is-added' : ''} ${changed.has(key) ? 'is-changed' : ''} ${hit ? 'is-hit' : ''}`}>
          <code className="row-key">{py(entry.key)}</code>{!set && <><ArrowRight size={11}/><code className="row-value" key={changed.has(key) ? `c${stamp}` : 'v'}>{py(entry.value)}</code></>}
        </div>;
      })}
      {/* A key this step deleted: marked removed in every motion setting, and animated away when motion is on, in the
          place it held (the rest close up around it) when the table showed it a step ago. */}
      {(change.removed[structure.id] || []).map(entry => {
        const at = animate ? stood(json(entry.key)) : undefined;
        return <div key={`gone-${json(entry.key)}-${stamp}`} className={`row is-removed ${at ? 'is-in-place' : ''}`} style={at ? { left: at[0], top: at[1] } : undefined}><code className="row-key">{py(entry.key)}</code><span>removed</span></div>;
      })}
      {missing !== undefined && <div className="row row-missing"><code className="row-key">{py(missing)}</code><span>missing key</span></div>}
    </div>
  </section>;
}

/**
 * What the program is holding at this step: each variable of the running call with what it is (from the code
 * and the trace, see variableRoles), its value and the values it held before in this call; and the work the run
 * has done so far out of all it does.
 */
function MemoryPanel({ events, step, change, forward, history, roles, pointers, colors }: { events: TraceEvent[]; step: number; change: StepChange; forward: boolean; history: CallHistory; roles: Record<string, string>; pointers: Set<string>; colors: Record<string, string> }) {
  const event = events[step];
  const work = useMemo(() => workDone(events, step), [events, step]);
  const call = history.byId.get(history.frames[step] ?? -1);
  // Variables that hold a node (curr, slow, root) are pointers into the node view, not values.
  const refs = Object.keys(event.state.structures.find(s => s.type === 'nodes')?.refs || {});
  if (!event.state.variables.length && !refs.length && !work.length) return null;
  const nested = !!call && (call.parent !== null || event.state.callstack.length > 1);
  const given = (name: string) => !!call && name in call.args;
  const roleOf = (name: string, value: Value) => {
    // A parameter of the running call is that, whatever the same name does in another function.
    if (given(name)) return nested ? 'argument of this call' : 'input';
    if (roles[name]) return roles[name];
    if (typeof value === 'boolean') return 'flag';
    const changes = valueTrail(events, history.frames, step, name, 99).length;
    return changes ? `changed ${changes}×` : 'set once';
  };
  const cards = [
    ...event.state.variables.map(v => ({ name: v.id, value: py(v.value), role: roleOf(v.id, v.value), changed: v.id in change.variables, trail: valueTrail(events, history.frames, step, v.id).map(py), color: pointers.has(v.id) ? colors[v.id] : undefined })),
    ...refs.map(name => ({ name, value: text(nodeRef(event, name)), role: given(name) ? (nested ? 'argument · a node' : 'input · a node') : 'points at a node',
      changed: forward && step > 0 && history.frames[step - 1] === history.frames[step] && py(nodeRef(events[step - 1], name)) !== py(nodeRef(event, name)),
      trail: valueTrail(events, history.frames, step, name, 3, nodeRef).map(text), color: colorOf(name) })),
  ];
  return <section className="memory" aria-label="What your code is holding">
    <div className="memory-head"><span className="stage-label"><Cpu size={12}/> WHAT YOUR CODE IS HOLDING</span>{call && <code>{nested ? 'inside ' : ''}{callLabel(call)}</code>}</div>
    {cards.length > 0 && <div className="memory-cards">{cards.map(c => <div key={c.name} className={`mem ${c.changed ? 'is-changed' : ''} ${c.color ? 'is-pointer' : ''}`} style={c.color ? { '--c': c.color } as CSSProperties : undefined}>
      <span className="mem-role">{c.role}</span>
      <div className="mem-main"><code>{c.name}</code><b key={c.changed ? `v${event.id}` : 'v'}>{c.value}</b></div>
      <span className="mem-trail">{c.trail.length ? <>was {c.trail.join(' → ')}</> : '\u00a0'}</span>
    </div>)}</div>}
    {work.length > 0 && <div className="work-row" aria-label="Work so far">{work.map(w => <span key={w.label} className="work" title={`${w.done} of the ${w.total} ${w.label} this run records`}>
      <i style={{ '--p': w.done / w.total } as CSSProperties}/><b>{w.done}</b><small>/{w.total}</small> {w.label}
    </span>)}</div>}
  </section>;
}

function StageAlert({ event, step, last, divergence, wrong, goal, onSeek, error }: { event: TraceEvent; step: number; last: boolean; divergence: Divergence | null | undefined; wrong: { position: number; value: Value; goal: Value }[]; goal: GoalState | null; onSeek?: (step: number) => void; error?: RunError | null }) {
  const go = (target: number | null | undefined, label: ReactNode) => target !== null && target !== undefined && onSeek ? <button onClick={() => onSeek(target)}>{label}</button> : null;
  const cycle = divergence?.cycle;
  let alert: ReactNode = null, tone = 'warn';
  if (event.type === 'ERROR' && cycle) {
    tone = 'bad';
    alert = <><Repeat2 size={16}/><div><strong>Infinite loop, proven</strong><p>The while loop on line {cycle.line} reached exactly the same state twice. Nothing changed between those iterations, so it would never finish.</p><span className="alert-actions">{go(cycle.first, `Step ${(cycle.first ?? 0) + 1}`)}{go(cycle.repeat, `Step ${(cycle.repeat ?? 0) + 1} · same state`)}</span></div></>;
  } else if (cycle && (step === cycle.first || step === cycle.repeat)) {
    alert = <><Repeat2 size={16}/><div><strong>{step === cycle.repeat ? `Same state as step ${(cycle.first ?? 0) + 1}` : `This state comes back at step ${(cycle.repeat ?? 0) + 1}`}</strong><p>Compare the variables: every value is identical, so the loop is going in circles.</p></div></>;
  } else if (event.type === 'ERROR') {
    // What stopped the program, in the learner's own names (errors.py), with Python's message kept small beneath.
    tone = 'bad';
    alert = <><TriangleAlert size={16}/>{error ? <ErrorBody told={explanationOf(error)} error={error}/> : <div><strong>The program stopped</strong><p>{event.detail}</p></div>}</>;
  } else if (wrong.length) {
    tone = 'bad';
    alert = <><CircleAlert size={16}/><div><strong>This write stays wrong to the end</strong><p>{wrong.map(w => `Position ${w.position} gets ${py(w.value)}${w.goal !== null ? ` — the goal has ${py(w.goal)} there` : ' — the goal does not include it'}.`).join(' ')} It is never changed afterwards. The cause may be earlier.</p></div></>;
  } else if (divergence && !divergence.cycle && (divergence.step === step || (divergence.step === null && last))) {
    tone = divergence.kind === 'Nothing returned yet' ? 'warn' : 'bad';
    // A program stopped after its record filled up has no stopping step: its error still shows on the last one.
    alert = divergence.kind === 'Execution stopped' && error ? <><TriangleAlert size={16}/><ErrorBody told={explanationOf(error)} error={error}/></>
      : <><CircleAlert size={16}/><div><strong>{divergence.title ?? divergence.kind}</strong><p>{divergence.message}</p></div></>;
  } else if (goal?.returned && goal.matches && step === goal.returnStep) {  // The program's own return: a design problem's last operation.
    tone = 'good';
    alert = <><BookOpenCheck size={16}/><div><strong>On target for this input</strong><p>Your result matches the goal. Run all tests to check other inputs.</p></div></>;
  }
  return alert ? <div className={`stage-alert alert-${tone}`} key={`${step}-${tone}`} role={tone === 'bad' ? 'alert' : 'status'}>{alert}</div> : null;
}

function Narration({ event, step, total, focus, bits, changes }: { event: TraceEvent; step: number; total: number; focus: Focus; bits?: TraceEvent; changes: string[] }) {
  const category = categoryOf(event.type);
  const Icon = icons[category];
  return <div className={`narration cat-${category}`} key={event.id}>
    <div className="narration-top"><span><Icon size={14}/> {verbs[category]}</span><code>line {event.line} · step {step + 1}/{total}</code></div>
    {bits ? <><h3>{event.type === 'BIT_OP' ? event.detail : event.explanation?.what ?? event.detail}</h3><BitStrip event={bits}/></>
      : focus.compare
      ? <div className="compare-visual"><code>{py(focus.compare.left)}</code><span>{focus.compare.expression.replace(/^.*?\s(==|!=|<=|>=|<|>|not in|in|is not|is)\s.*$/, '$1')}</span><code>{py(focus.compare.right)}</code><b className={focus.compare.result ? 'is-true' : 'is-false'}>{focus.compare.result ? 'True' : 'False'}</b><small>{focus.compare.expression}</small></div>
      : <h3>{event.explanation?.what ?? event.detail}</h3>}
    {/* What this step changed, in the program's own names: the step's evidence in one line. */}
    {changes.length > 0 && <div className="narration-changes" aria-label="What changed">{changes.slice(0, 5).map((c, i) => <code key={i} style={{ '--i': i } as CSSProperties}>{c}</code>)}{changes.length > 5 && <span>+{changes.length - 5} more</span>}</div>}
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

function ExecutionRibbon({ events, divergence, step, onSeek, code }: { events: TraceEvent[]; divergence: Divergence | null | undefined; step: number; onSeek?: (step: number) => void; code: string }) {
  const model = useMemo(() => ribbon({ events, divergence: divergence ?? null }), [events, divergence]);
  const chapters = useMemo(() => phases(events, code), [events, code]);
  const total = Math.max(1, events.length);
  const now = chapters ? chapters.findIndex(c => step >= c.start && step <= c.end) : -1;
  return <div className="ribbon" aria-label="Execution overview">
    {/* The run in chapters: passes of the outer loop, or the calls the top-level call makes. */}
    {chapters && now >= 0 && <div className="phases">
      <div className="phase-now"><b key={now}>{chapters[now].label}</b><span>{chapters[now].kind === 'pass' ? `pass ${chapters.slice(0, now + 1).filter(c => c.kind === 'pass').length} of ${chapters.filter(c => c.kind === 'pass').length}` : `part ${now + 1} of ${chapters.length}`}</span></div>
      <div className="phase-track">{chapters.map((c, i) => <button key={c.start} className={`phase phase-${c.kind} ${i < now ? 'is-done' : i === now ? 'is-now' : ''}`} style={{ flexGrow: c.end - c.start + 1 }}
        title={`${c.label} · steps ${c.start + 1}–${c.end + 1}`} aria-label={`${c.label}, steps ${c.start + 1} to ${c.end + 1}`} onClick={() => onSeek?.(c.start)}>
        {i === now && <i style={{ '--p': (step - c.start + 1) / (c.end - c.start + 1) } as CSSProperties}/>}
      </button>)}</div>
    </div>}
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
