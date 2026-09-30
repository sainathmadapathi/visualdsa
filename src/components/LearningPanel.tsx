import { useState } from 'react';
import { ArrowRight, Box, Check, ChevronRight, CircleHelp, Flag, Lightbulb, Pencil, RotateCcw, Search, Target, Workflow } from 'lucide-react';
import { useLab } from '../store';
import { display } from './Visualizer';

export default function LearningPanel({ onExplore }: { onExplore: () => void }) {
  const { problem: p, tab, setTab, hints, hint, hintContext, stage, run, problems, select } = useLab();
  const [discovery, setDiscovery] = useState(0);
  const [answer, setAnswer] = useState('');
  const [feedback, setFeedback] = useState('');
  const [choice, setChoice] = useState('');
  if (!p) return null;
  const related = problems.find(q => q.id === p.transfer);
  const partner = p.id === 'two-sum' || p.id === 'two-sum-sorted';
  const exampleNums = p.example.args[0] as number[];
  const examplePair = p.example.expected as number[];
  return <div className="learning-panel">
    {tab === 'understand' && <>
      <div className="decoder-cards">
        <div className="decoder-card"><div className="decoder-icon"><Box size={17}/></div><div><span className="tiny-label">WHAT YOU HAVE</span><p>{p.decoder.given}</p><code>{p.example.args.map(display).join(' · ')}</code></div></div>
        <div className="decoder-card"><div className="decoder-icon amber"><Search size={17}/></div><div><span className="tiny-label">WHAT YOU NEED</span><p>{p.decoder.find}</p><span className="decoder-detail">{partner ? 'Different positions. Values can repeat.' : 'Try the smallest valid input first.'}</span></div></div>
        <div className="decoder-card"><div className="decoder-icon blue"><Flag size={17}/></div><div><span className="tiny-label">WHAT YOU RETURN</span><p>{p.decoder.returns}</p><code>Example → {display(p.example.expected)}</code></div></div>
      </div>
      <div className="understand-foot"><span><CircleHelp size={14}/>{partner ? `For the example: ${exampleNums[examplePair[0]]} + ${exampleNums[examplePair[1]]} = ${p.example.args[1]}, so return ${display(examplePair)}. Those are the positions.` : 'The example output shows what a valid answer looks like, without choosing an algorithm.'}</span><button className="text-button" onClick={() => { void stage('Understood'); setTab('discover'); }}>I understand the problem <ArrowRight size={14}/></button></div>
    </>}
    {tab === 'discover' && <div className="discovery-layout">
      <div className="discovery-main"><span className="tiny-label"><Workflow size={13}/> HOW AN APPROACH IS DISCOVERED</span><h3>{['Start simple.', 'Notice the repeated work.', 'Find the missing information.', 'Build a better approach.'][discovery]}</h3><p>{p.discovery[discovery]}</p><div className="discovery-steps">{p.discovery.map((_, i) => <button key={i} aria-label={`Discovery step ${i + 1}`} className={i <= discovery ? 'complete' : ''} onClick={() => setDiscovery(i)}>{i + 1}</button>)}</div><div className="discovery-actions"><button className="outline-button" onClick={onExplore}><Workflow size={14}/> Explore both approaches</button><button className="text-button" onClick={() => setDiscovery(Math.min(3, discovery + 1))}>{discovery === 3 ? 'Reread the reasoning' : 'Next observation'}<ArrowRight size={14}/></button></div></div>
      <div className="detective"><span className="tiny-label"><Target size={13}/> PATTERN DETECTIVE</span><h4>What information would remove repeated work?</h4><div className="detective-choices">{['Previously seen values', 'Useful input order', 'A shared continuous range', 'A running best value'].map(c => <button key={c} className={choice === c ? 'chosen' : ''} onClick={() => setChoice(c)}>{c}{choice === c && <Check size={13}/>}</button>)}</div>{choice && <p className="small">Explain why “{choice.toLowerCase()}” helps this particular problem. Compare that claim with the discovery steps.</p>}</div>
    </div>}
    {tab === 'code' && <div className="code-guidance"><div className="guide-icon"><Pencil size={19}/></div><div><span className="tiny-label">YOUR APPROACH, YOUR EXPERIMENT</span><h3>Start with the simplest idea that could work.</h3><p>Write <code>solve({p.params.join(', ')})</code>, pause to see the live trace, and follow the state. Try changing the input or a single line.</p></div><button className="outline-button" onClick={onExplore}>Explore an approach<ArrowRight size={14}/></button></div>}
    {tab === 'reflect' && <div className="reflect-layout"><div><span className="tiny-label">EXPLAIN IT IN YOUR OWN WORDS</span><h3>Could you teach your approach to someone?</h3><p className="small">{p.recall.join(' ')}</p><textarea value={answer} onChange={e => { setAnswer(e.target.value); setFeedback(''); }} placeholder="I noticed… My simplest idea was… I improved it by…" aria-label="Explain your approach"/><button className="outline-button" disabled={answer.trim().length < 40} onClick={async () => { await stage('Explained', answer); setFeedback('Reasoning saved. Check that your explanation covers the observation, repeated work, chosen operation, and why it is correct. This is a self-review, not an automated mastery assessment.'); }}><Check size={14}/> Save my reasoning</button>{feedback && <p className="small reflection-feedback">{feedback}</p>}</div><div className="transfer-card"><RotateCcw size={22}/><h3>Change one assumption.</h3><p>Try <strong>{related?.title}</strong>. What changed? What part of your reasoning still works?</p><button className="text-button" onClick={() => related && select(related.id)}>Try the variation<ArrowRight size={14}/></button><span className="small">{run?.passed ? 'A passing solution is a starting point for transfer.' : 'Run your approach, then reflect on the result.'}</span></div></div>}
    {hints > 0 && <div className="hint-history">{hintContext && <div className="hint-item"><Lightbulb size={15}/><div><span className="tiny-label">ABOUT YOUR ACTUAL ATTEMPT</span><p>{hintContext}</p></div></div>}{p.hints.slice(0, hints).map((text, i) => <div className="hint-item" key={i}><Lightbulb size={15}/><div><span className="tiny-label">HINT {i + 1} / {p.hints.length}</span><p>{text}</p></div></div>)}{hints < p.hints.length && <button className="text-button" onClick={() => void hint()}>A little more guidance<ChevronRight size={14}/></button>}</div>}
  </div>;
}
