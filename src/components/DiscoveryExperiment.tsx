import { useState } from 'react';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import type { Problem, Value } from '../types';
import { display } from './Visualizer';

// Authored reasoning illustration. Never used as an execution trace.
export default function DiscoveryExperiment({ problem: p, phase }: { problem: Problem; phase: number }) {
  const [cursor, setCursor] = useState(0);
  const [retained, setRetained] = useState<number[]>([]);
  const [checked, setChecked] = useState(false);
  const input = p.example.args[p.id === 'intersection' ? 1 : 0];
  const values: Value[] = typeof input === 'string' ? Array.from(input) : Array.isArray(input) ? input : [];
  const candidateValues = p.id === 'intersection' && Array.isArray(p.example.args[0]) ? p.example.args[0] : values;
  const n = values.length;
  const fixedWindow = ['max-window-sum', 'average-window'].includes(p.id);
  const ranges = ['max-subarray', 'longest-unique'].includes(p.id);
  const pairs = ['two-sum', 'two-sum-sorted', 'contains-duplicate', 'pair-count', 'best-profit'].includes(p.id);
  const countScan = ['frequency-map', 'first-unique', 'valid-anagram', 'intersection'].includes(p.id);
  const candidates: number[][] = fixedWindow
    ? Array.from({ length: Math.max(0, n - Number(p.example.args[1]) + 1) }, (_, start) => Array.from({ length: Number(p.example.args[1]) }, (_, i) => start + i))
    : ranges ? values.flatMap((_, start) => Array.from({ length: n - start }, (_, j) => Array.from({ length: j + 1 }, (_, i) => start + i)))
    : pairs ? values.flatMap((_, i) => values.flatMap((__, j) => j > i ? [[i, j]] : []))
    : countScan ? candidateValues.map(() => values.map((_, i) => i))
    : values.map((_, i) => [i]);
  const at = Math.min(cursor, Math.max(0, candidates.length - 1));
  const current = candidates[at] || [];
  const upcoming = candidates[at + 1] || [];
  const overlap = current.filter(i => upcoming.includes(i));
  const visits = values.map((_, i) => candidates.slice(0, at + 1).filter(c => c.includes(i)).length);
  const reads = candidates.slice(0, at + 1).reduce((sum, c) => sum + c.length, 0);
  const right = retained.length === overlap.length && retained.every(i => overlap.includes(i));
  return <section className="discovery-experiment" aria-label="Repeated work experiment">
    <div className="lesson-card-heading"><h4>{fixedWindow || pairs ? 'Try a candidate. Count the repeated reads.' : 'Follow the candidates. Notice what repeats.'}</h4><span className="tiny-label">REASONING MODEL · NOT YOUR CODE</span></div>
    <p>{fixedWindow ? `Each candidate contains ${p.example.args[1]} consecutive values.` : ranges ? 'Try contiguous ranges, starting with the shortest at each position.' : pairs ? 'Each candidate uses two different positions.' : countScan ? `Candidate ${at + 1}: inspect ${p.id === 'intersection' ? 'the second sequence' : 'the sequence'} for ${display(candidateValues[at])}. Could information from an earlier scan help?` : 'Start by inspecting each position in order. What does this preserve, and what information could let you skip work?'}</p>
    <div className="candidate-cells">{values.map((v, i) => <button key={i} className={`${current.includes(i) ? 'candidate-active' : ''} ${retained.includes(i) ? 'candidate-kept' : ''}`} aria-label={`Remember position ${i}, value ${display(v)}`} aria-pressed={retained.includes(i)} onClick={() => { setRetained(rows => rows.includes(i) ? rows.filter(x => x !== i) : [...rows, i]); setChecked(false); }}><small>{i}</small><b>{display(v)}</b><span>{visits[i]} read{visits[i] !== 1 ? 's' : ''}</span></button>)}</div>
    <div className="candidate-controls"><button className="icon-button" aria-label="Previous candidate" disabled={at === 0} onClick={() => { setCursor(at - 1); setChecked(false); setRetained([]); }}><ArrowLeft size={16}/></button><span>Candidate {candidates.length ? at + 1 : 0}/{candidates.length} · {reads} total reads</span><button className="icon-button" aria-label="Next candidate" disabled={at + 1 >= candidates.length} onClick={() => { setCursor(at + 1); setChecked(false); setRetained([]); }}><ArrowRight size={16}/></button></div>
    {phase > 0 && upcoming.length > 0 && <div className="reuse-challenge"><p>The next candidate reads positions <code>{upcoming.join(', ')}</code>. Select the positions shared by both candidates, then check your observation.</p><button className="outline-button" onClick={() => setChecked(true)}>Check overlap</button>{checked && <p role="status">{right ? `Exactly: ${overlap.length ? overlap.join(', ') : 'no positions'} overlap. What information could you retain instead of repeating the same reads?` : 'Compare the highlighted candidate with the next positions. Select only positions that occur in both; try again.'}</p>}</div>}
    <p className="small">Counts describe this illustration only. Your actual operations are measured in Code & Visualize.</p>
  </section>;
}
