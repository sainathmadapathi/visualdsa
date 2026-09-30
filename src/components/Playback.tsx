import { useEffect, useState } from 'react';
import { Check, ChevronDown, ChevronLeft, ChevronRight, CircleAlert, List, Pause, Play, RotateCcw, SkipBack } from 'lucide-react';
import { useLab } from '../store';
import { display, eventLabel } from './Visualizer';

export default function Playback() {
  const { run, step, playing, speed, play, seek, reset, source } = useLab();
  const [timeline, setTimeline] = useState(false);
  const [tests, setTests] = useState(false);
  useEffect(() => {
    if (!playing || !run?.events.length) return;
    const timer = window.setInterval(() => {
      const state = useLab.getState();
      if (state.step >= (state.run?.events.length || 0) - 1) useLab.setState({ playing: false });
      else useLab.setState({ step: state.step + 1 });
    }, speed);
    return () => window.clearInterval(timer);
  }, [playing, speed, run]);
  const hasEvents = !!run?.events.length;
  const allPassed = !!run?.passed && !!run?.tests.every(t => t.passed);
  return <>
    {run?.truncated && <div className="stale-warning">Showing the first {run.events.length} events. Execution continued to the reported result; use a smaller input to trace every step.</div>}
    <div className="playback">
      <div className="playback-buttons"><button className="icon-button" title="Go to first step" aria-label="Go to first step" disabled={!hasEvents} onClick={reset}><SkipBack size={17}/></button><button className="icon-button" title="Previous step" aria-label="Previous step" disabled={!hasEvents || step === 0} onClick={() => seek(step - 1)}><ChevronLeft size={19}/></button><button className="play-button" title={playing ? 'Pause' : 'Play trace'} aria-label={playing ? 'Pause trace' : 'Play trace'} disabled={!hasEvents} onClick={play}>{playing ? <Pause size={16}/> : <Play size={16}/>}</button><button className="icon-button" title="Next step" aria-label="Next step" disabled={!hasEvents || step === (run?.events.length || 0) - 1} onClick={() => seek(step + 1)}><ChevronRight size={19}/></button><button className="icon-button" title="Replay from start" aria-label="Replay from start" disabled={!hasEvents} onClick={() => useLab.setState({ step: 0, playing: true })}><RotateCcw size={15}/></button></div>
      <div className="timeline-range"><input type="range" aria-label="Execution step" min="0" max={Math.max(0, (run?.events.length || 1) - 1)} value={step} disabled={!hasEvents} onChange={e => seek(Number(e.target.value))}/><span>{hasEvents ? `${step + 1} / ${run!.events.length}` : 'No steps yet'}</span></div>
      <select className="speed-select" aria-label="Playback speed" value={speed} onChange={e => useLab.setState({ speed: Number(e.target.value) })}><option value="1800">0.5×</option><option value="900">1×</option><option value="450">2×</option><option value="200">4×</option></select>
      <button className={`timeline-button ${timeline ? 'active' : ''}`} onClick={() => setTimeline(!timeline)}><List size={15}/><span>Timeline</span><ChevronDown size={12}/></button>
    </div>
    {timeline && <div className="timeline-list">{hasEvents ? run!.events.map((e, i) => <button key={e.id} className={i === step ? 'selected' : ''} onClick={() => seek(i)}><span className="timeline-number">{i + 1}</span><code>L{e.line}</code><span>{eventLabel(e.type)}</span><code>{e.source}</code></button>) : <p>Run your code to record an execution timeline.</p>}</div>}
    {run?.preview && <div className="preview-result"><span className="live-indicator"/> Live preview &middot; current input <span>Returned <code>{display(run.result)}</code></span><span>Run all tests to check your solution.</span></div>}
    {run && !run.preview && <div className="results-section"><div className="result-line"><span className={`result-badge ${allPassed ? 'passed' : 'failed'}`}>{allPassed ? <Check size={15}/> : <CircleAlert size={15}/>} {allPassed ? source === 'mine' ? 'Your test cases passed' : 'Reference test cases passed' : run.error ? 'Execution stopped' : 'An opportunity to debug'}</span><span className="result-value">Returned <code>{display(run.result)}</code></span><button className="text-button" onClick={() => setTests(!tests)}>{run.tests.filter(t => t.passed).length}/{run.tests.length} tests<ChevronDown size={13}/></button></div>
      {run.divergence && <div className="divergence"><span>{run.divergence.message}</span><button className="text-button" disabled={!hasEvents} onClick={() => seek(run.divergence!.step)}>Inspect this state<ChevronRight size={13}/></button></div>}
      {tests && <div className="test-list">{run.tests.map(t => <div key={t.name}><span className={t.passed ? 'test-pass' : 'test-fail'}>{t.passed ? <Check size={14}/> : <CircleAlert size={14}/>}</span><strong>{t.name}</strong><code>{t.args.map(display).join(' · ')}</code><span>Expected <code>{display(t.expected)}</code> · got <code>{display(t.actual)}</code></span></div>)}</div>}
      {run.stdout && <details className="console-output"><summary>Console output</summary><pre>{run.stdout}</pre></details>}
    </div>}
  </>;
}
