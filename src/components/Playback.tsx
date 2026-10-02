import { useEffect, useState } from 'react';
import { Check, ChevronDown, ChevronLeft, ChevronRight, CircleAlert, List, LoaderCircle, Pause, Play, RotateCcw, ScanSearch, SkipBack } from 'lucide-react';
import { useLab } from '../store';
import { display, eventLabel } from './Visualizer';

export default function Playback() {
  const { run, step, playing, speed, tour, play, seek, reset, source, args, busy, traceInput, problem } = useLab();
  const [timeline, setTimeline] = useState(false);
  const failing = !!run && !run.preview && run.tests.some(t => !t.passed);
  const [tests, setTests] = useState(failing);
  // A failing check is the start of debugging: keep its evidence in view.
  useEffect(() => { if (failing) setTests(true); }, [run, failing]);
  useEffect(() => {
    if (!playing || !run?.events.length) return;
    const timer = window.setInterval(() => {
      const state = useLab.getState();
      if (state.step >= (state.run?.events.length || 0) - 1) { if (!(state.tour && state.nextCase())) useLab.setState({ playing: false }); }
      else useLab.setState({ step: state.step + 1 });
    }, tour ? Math.max(200, speed / 2) : speed);  // A tour of every case moves at double speed.
    return () => window.clearInterval(timer);
  }, [playing, speed, run, tour]);
  const hasEvents = !!run?.events.length;
  const allPassed = !!run?.passed && !!run?.tests.every(t => t.passed);
  const divergence = run?.divergence;
  const origin = divergence?.origin;
  const shownArgs = run?.input ?? args;
  const tracing = (testArgs: unknown) => JSON.stringify(testArgs) === JSON.stringify(shownArgs);
  return <>
    {run?.truncated && <div className="stale-warning">Showing the first {run.events.length} events. Execution continued to the reported result; use a smaller input to trace every step.</div>}
    <div className="playback">
      <div className="playback-buttons"><button className="icon-button" title="Go to first step" aria-label="Go to first step" disabled={!hasEvents} onClick={reset}><SkipBack size={17}/></button><button className="icon-button" title="Previous step" aria-label="Previous step" disabled={!hasEvents || step === 0} onClick={() => seek(step - 1)}><ChevronLeft size={19}/></button><button className="play-button" title={playing ? 'Pause' : 'Play trace'} aria-label={playing ? 'Pause trace' : 'Play trace'} disabled={!hasEvents} onClick={play}>{playing ? <Pause size={16}/> : <Play size={16}/>}</button><button className="icon-button" title="Next step" aria-label="Next step" disabled={!hasEvents || step === (run?.events.length || 0) - 1} onClick={() => seek(step + 1)}><ChevronRight size={19}/></button><button className="icon-button" title="Replay from start" aria-label="Replay from start" disabled={!hasEvents} onClick={() => useLab.setState({ step: 0, playing: true })}><RotateCcw size={15}/></button></div>
      <div className="timeline-range"><input type="range" aria-label="Execution step" min="0" max={Math.max(0, (run?.events.length || 1) - 1)} value={step} disabled={!hasEvents} onChange={e => seek(Number(e.target.value))}/><span>{hasEvents ? `${step + 1} / ${run!.events.length}` : 'No steps yet'}</span></div>
      <select className="speed-select" aria-label="Playback speed" value={speed} onChange={e => useLab.setState({ speed: Number(e.target.value) })}><option value="1800">0.5×</option><option value="900">1×</option><option value="450">2×</option><option value="200">4×</option></select>
      <button className={`timeline-button ${timeline ? 'active' : ''}`} aria-label="Timeline" aria-expanded={timeline} onClick={() => setTimeline(!timeline)}><List size={15}/><span>Timeline</span><ChevronDown size={12}/></button>
    </div>
    {timeline && <div className="timeline-list">{hasEvents ? run!.events.map((e, i) => <button key={e.id} className={i === step ? 'selected' : ''} onClick={() => seek(i)}><span className="timeline-number">{i + 1}</span><code>L{e.line}</code><span>{eventLabel(e.type)}</span><code>{e.source}</code></button>) : <p>Run your code to record an execution timeline.</p>}</div>}
    {run?.preview && <div className="preview-result"><span className="live-indicator"/> Live preview &middot; current input <span>Returned <code>{display(run.result)}</code></span><span>Run all tests to check your solution.</span></div>}
    {run && !run.preview && <div className="results-section"><div className="result-line"><span className={`result-badge ${allPassed ? 'passed' : 'failed'}`}>{allPassed ? <Check size={15}/> : <CircleAlert size={15}/>} {allPassed ? source === 'mine' ? 'Your test cases passed' : 'Reference test cases passed' : run.error ? 'Execution stopped' : 'An opportunity to debug'}</span><span className="result-value">Traced <code>{problem?.params.map((name, i) => `${name}=${display(shownArgs[i])}`).join(', ')}</code> · returned <code>{display(run.result)}</code></span><button className="text-button" onClick={() => setTests(!tests)}>{run.tests.filter(t => t.passed).length}/{run.tests.length} tests<ChevronDown size={13}/></button></div>
      {divergence && <div className="divergence"><div><strong>{divergence.kind}</strong><span>{divergence.message}</span></div><div className="divergence-actions">{divergence.step !== null && <button className="text-button" disabled={!hasEvents} onClick={() => seek(divergence.step!)}>Inspect step {divergence.step + 1}<ChevronRight size={13}/></button>}{origin && (origin.unchanged ? <button className="text-button" onClick={() => seek(origin.step)}><code>{origin.name}</code> never changed<ChevronRight size={13}/></button> : <button className="text-button" onClick={() => seek(origin.step)}>Where <code>{origin.name}</code> last changed · step {origin.step + 1}<ChevronRight size={13}/></button>)}</div></div>}
      {tests && <div className="test-list">{run.tests.map(t => <div key={t.name} className={t.passed ? '' : 'test-failing'}><span className={t.passed ? 'test-pass' : 'test-fail'}>{t.passed ? <Check size={14}/> : <CircleAlert size={14}/>}</span><strong>{t.name}</strong><code>{t.args.map(display).join(' · ')}</code><span>Expected <code>{display(t.expected)}</code> · got <code>{t.error ? t.error.message : display(t.actual)}</code></span>{!t.passed && source === 'mine' && (tracing(t.args) ? <span className="trace-current">Traced above</span> : <button className="trace-input-button" disabled={busy} onClick={() => void traceInput(t.args)}>{busy ? <LoaderCircle className="spin" size={13}/> : <ScanSearch size={13}/>}Trace this input</button>)}</div>)}</div>}
      {run.stdout && <details className="console-output"><summary>Console output</summary><pre>{run.stdout}</pre></details>}
    </div>}
  </>;
}
