import { Check, CircleHelp, Eye, Pause, Play, TriangleAlert, X } from 'lucide-react';
import { useLab } from '../store';
import type { Problem, Structure, Value } from '../types';
import { casePrompt, goalAt, py } from '../visualModel';
import { inputStructures } from '../structureModel';
import VisualStage, { InputStage } from './VisualStage';
import { ErrorBody, explanationOf } from './ErrorCard';
import { SourceTag } from './Sheets';

/** A value as Python writes it (None, True, [1, 2]), the way the stage shows it; a string as its text. */
export const display = (value: Value | undefined): string => value === undefined ? '—' : typeof value === 'string' ? value : py(value);
export const eventLabel = (event: string) => event.toLowerCase().replaceAll('_', ' ');

/** An input as the program receives it: linked lists, trees, grids and graphs as structures, other lists and
 * strings as lanes, and everything else as named values. */
export function inputView(problem: Problem, args: Value[]): { structures: Structure[]; variables: { id: string; value: Value }[] } {
  const shaped = inputStructures(problem.params, args, problem.kinds || {});
  const taken = new Set([...Object.keys(problem.kinds || {}), ...shaped.filter(s => s.type === 'matrix').map(s => s.id)]);
  const structures: Structure[] = [...shaped, ...problem.params.flatMap((name, i) => {
    const value = args[i];
    return !taken.has(name) && (Array.isArray(value) || typeof value === 'string') ? [{ id: name, type: typeof value === 'string' ? 'string' as const : 'array' as const, values: typeof value === 'string' ? value.split('') : value, length: value.length }] : [];
  })];
  const variables = problem.params.flatMap((name, i) => !Array.isArray(args[i]) && typeof args[i] !== 'string' ? [{ id: name, value: args[i] }] : []);
  return { structures, variables };
}

/** The visual pane: the learner's recorded run, animated, with live-coding state around it. */
export default function Visualizer() {
  const { run, step, problem, args, code, runCode, source, live, previewBusy, previewMessage, previewError, playing, cursorLine, seek } = useLab();
  const stale = !!run && runCode !== code;
  const { structures: inputs, variables: scalars } = problem ? inputView(problem, args) : { structures: [], variables: [] };
  // Why the current edit has no trace: the code needs a change (said in plain words, with its line), or the runner
  // couldn't take it right now. Only ever about the code as it is now.
  const blocked = previewError && !previewBusy && previewError.for === code ? previewError : null;
  const told = blocked?.explanation;
  const unrunnable = !!blocked && !!run && (blocked.code || !!told);
  const status = source !== 'mine' ? 'Reference mode · run to explore'
    : blocked ? `${told ? `${told.line ? `Line ${told.line}: ` : ''}${told.title}` : blocked.code ? blocked.message : `Can't trace right now: ${blocked.message}`}${unrunnable ? ' · showing your last runnable version' : ''}`
    : previewBusy ? 'Tracing your edit…'
    : stale ? (live ? 'Typing…' : 'Your code changed · run again to update')
    : previewMessage || (live ? 'Live · updates as you type' : 'Live paused · run when you are ready');

  return <div className={`visual-body stage-shell ${playing ? 'trace-playing' : ''} ${unrunnable ? 'is-unrunnable' : ''}`}>
    <div className={`live-preview-status ${previewBusy || (stale && live) ? 'is-tracing' : ''} ${blocked ? 'has-error' : run?.error && !stale ? 'has-stop' : ''}`} role="status" title={status}><span className="signal-bars" aria-hidden="true"><i/><i/><i/></span><span>{status}</span></div>
    <div className="canvas-topline"><span className="live-indicator"/><span>{run ? source === 'mine' ? run.preview ? 'YOUR CODE, LIVE' : 'YOUR ACTUAL EXECUTION' : 'REFERENCE EXECUTION' : 'YOUR INPUT, VISUALLY'}</span><span className="canvas-line">{run?.events[step] ? `LINE ${run.events[step].line}` : 'READY TO EXPLORE'}</span></div>
    <CaseDeck/>
    {run?.events.length
      // Live or explicit, the goal for this input is shown throughout, and the verdict only from the step the program returned.
      ? <VisualStage events={run.events} step={step} onSeek={seek} goal={goalAt(run, step)} divergence={run.divergence} focusLine={stale ? null : cursorLine} lines={run.lines} code={runCode} error={run.error}/>
      : run ? run.error ? <div className="stage-empty stage-stopped" role="alert"><ErrorBody told={explanationOf(run.error)} error={run.error}/></div>
        : <div className="stage-empty"><Eye size={20}/><p>Your code ran without recorded steps.</p><code>returned {py(run.result)}</code></div>
      : <>
        <InputStage structures={inputs} variables={scalars}/>
        <div className="pre-run-guide"><div className="guide-icon"><Eye size={22}/></div><h3>See your thinking in motion.</h3><p>{live ? `Start typing in ${problem?.entry && problem.entry !== 'solve' ? `your ${problem.entry} class` : 'solve'} and pause for a moment:` : 'Write your approach, then run your code:'}<br/>every read, write and comparison will appear here.</p><div className="guide-flow"><span>Code</span><span>→</span><span>State</span><span>→</span><span>Goal</span></div></div>
      </>}
  </div>;
}

/** Every case of the problem, traced on the same code: pick one to watch, or tour them all. */
function CaseDeck() {
  const { batch, run, problem, tour, selectCase, playCases } = useLab();
  if (!batch?.cases?.length || !run || !problem) return null;
  const cases = batch.cases;
  const selected = cases.find(c => c.id === (run.caseId ?? batch.caseId)) ?? cases[0];
  const status = (c: typeof selected) => c.error ? 'error' : !c.goal ? 'unknown' : c.goal.matches ? 'ok' : 'off';
  const icons = { ok: Check, off: X, error: TriangleAlert, unknown: CircleHelp };
  const onTarget = cases.filter(c => c.goal?.matches).length;
  return <section className="case-deck" aria-label="Edge cases">
    <div className="case-head">
      <span className="stage-label">{problem.custom ? 'YOUR CASES' : 'EDGE CASES'} · <b className={onTarget === cases.length ? 'all-ok' : ''}>{onTarget}/{cases.length}</b> ON TARGET</span>
      <button className="case-tour" onClick={() => tour ? useLab.setState({ tour: false, playing: false }) : playCases()}>{tour ? <><Pause size={12}/> Stop the tour</> : <><Play size={12}/> Play every case</>}</button>
    </div>
    <div className="case-chips" role="tablist" aria-label="Choose a case to watch">{cases.map(c => {
      const Icon = icons[status(c)];
      return <button key={c.id} role="tab" aria-selected={c.id === selected.id} className={`case-chip case-${status(c)}`} onClick={() => selectCase(c.id, true)}
        title={`${c.name}: ${problem.params.map((name, i) => `${name} = ${py(c.input[i])}`).join(', ')}${c.error ? ` · stopped: ${c.error.explanation?.title ?? c.error.message}` : ''}${c.fullRun ? ' · judged by a full run (the trace shows its first steps)' : ''}`}><span className="case-mark"><Icon size={11}/></span>{c.name}{c.computed && !c.custom && <em className="computed-tag" title="Computed by a reference solution checked against this problem's page examples: not given by the page.">computed</em>}{c.source === 'leetcode' && <SourceTag source="leetcode"/>}</button>;
    })}</div>
    <div className="case-detail"><code>{problem.params.map((name, i) => `${name} = ${py(selected.input[i])}`).join(' · ')}</code><p>{casePrompt(selected.name)}</p></div>
  </section>;
}
