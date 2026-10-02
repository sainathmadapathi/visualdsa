import { useState } from 'react';
import { ArrowLeft, ArrowRight, BookOpen, Check, ChevronRight, CircleHelp, Eye, FlaskConical, Lightbulb, Pencil, RotateCcw, Shuffle } from 'lucide-react';
import { activeProblem, notesKey, readNotes, useLab } from '../store';
import { constraintsFor, contrastingExamples, techniques } from '../learningContent';
import type { ApproachFeedback, Tab, Value, Verdict } from '../types';
import { display, inputView } from './Visualizer';
import { InputStage } from './VisualStage';
import DiscoveryExperiment from './DiscoveryExperiment';

type Notes = { discoveryAnswer?: string; discoveryStep?: string; discoveryAnswers?: Record<number, string>; assumptions?: string; decision?: string; counterexample?: string; prediction?: string; plan?: string; technique?: string; rationale?: string; reasoning?: string; mistake?: string; time?: string; space?: string; adaptation?: string; recall?: Record<number, string>; transferFrom?: string; transferFromId?: string; transferPlan?: string; operation?: string; cluesRevealed?: number[]; approachFeedback?: ApproachFeedback; modifyReasoning?: string };
type TextField = { [K in keyof Notes]-?: Notes[K] extends string | undefined ? K : never }[keyof Notes];
const verdictLabels: Record<Verdict, string> = { match: 'Your hypothesis holds.', alternative: 'A valid alternative, with a tradeoff.', partial: 'Part of the approach.', 'starting-point': 'A correct starting point.', different: 'A different approach than this problem rewards.' };

export default function LearningPanel({ onExplore, onChoose, onEditLab }: { onExplore: () => void; onChoose: (id: string, tab?: Tab) => void; onEditLab: () => void }) {
  const lab = useLab();
  const { problem: p, tab, setTab, hints, hint, hintContext, stage, run, runCode, code, source, problems, mode, evidence } = lab;
  const noteKey = notesKey(p?.id || '');
  const [notes, setNotes] = useState<Notes>(() => readNotes(noteKey) as Notes);
  const [saved, setSaved] = useState('Notes stay on this device.');
  const [exampleIndex, setExampleIndex] = useState(0);
  const [showOutput, setShowOutput] = useState(false);
  const [selected, setSelected] = useState<{ param: number; index: number } | null>(null);
  const [discovery, setDiscovery] = useState(Number(notes.discoveryStep) || 0);
  const [clues, setClues] = useState<number[]>(notes.cluesRevealed || []);
  const [feedback, setFeedback] = useState('');
  const [committing, setCommitting] = useState(false);
  const [revealComplexity, setRevealComplexity] = useState(false);
  const update = (patch: Partial<Notes>) => {
    const next = { ...notes, ...patch }; setNotes(next);
    try { localStorage.setItem(noteKey, JSON.stringify(next)); setSaved('Notes saved on this device.'); } catch { setSaved('Device storage is unavailable. Keep this page open to retain your notes.'); }
  };
  if (!p) return null;
  const target = activeProblem(lab)!;
  const related = problems.find(q => q.id === p.transfer);
  // A learner's own lab is illustrated with their own cases; built-in labs with an authored contrast.
  const examples = p.custom && p.cases?.length ? p.cases.slice(0, 3).map(c => ({ label: c.name, args: c.args, expected: c.expected, why: c.explanation ? `From the problem’s page: ${c.explanation}` : `Your case “${c.name}”. The expected output is the one you wrote.` }))
    : [{ label: 'Example 1', ...p.example }, { label: 'Example 2', ...(contrastingExamples[p.id] || p.example) }];
  const example = examples[Math.min(exampleIndex, examples.length - 1)];
  const explanation = 'why' in example ? String(example.why) : p.id === 'two-sum' ? '2 + 7 = 9. The answer [0,1] contains their positions, not their values.' : p.decoder.find + ' ' + p.decoder.returns;
  const selectedValue = selected ? (example.args[selected.param] as Value[] | string)?.[selected.index] : undefined;
  // Nodes, trees, grids, graphs and design calls are shown as the program receives them, not as cells.
  const design = !!p.entry && p.entry !== 'solve';
  const kinds = Object.values(p.kinds || {});
  const structured = design || kinds.length > 0 || example.args.some(v => Array.isArray(v) && v.some(x => Array.isArray(x)));
  const receives = design ? 'Each line is one call, in order: the first builds the class, and each later line calls one of its methods.'
    : kinds.includes('linkedlist') ? 'Your code receives the head node: each node has val and next, and the last next is None.'
    : kinds.includes('tree') ? 'Your code receives the root node: each node has val, left and right, and a missing child is None.'
    : kinds.includes('graph') ? 'graph[i] lists the neighbours of node i; the drawing shows each edge once.'
    : `${p.params.find((_, i) => Array.isArray(example.args[i]) && (example.args[i] as Value[]).some(Array.isArray)) || 'grid'}[r][c] is the value in row r, column c.`;
  const flatInput = !structured && (typeof p.example.args[0] === 'string' || (Array.isArray(p.example.args[0]) && p.example.args[0].every(x => x === null || typeof x !== 'object')));
  const stale = !!run && runCode !== code;
  const tested = !!run && !run.preview && source === 'mine' && !stale;
  const next = (target: Tab) => setTab(target);
  const committed = evidence[p.id]?.approach?.detail;
  const review = notes.approachFeedback;
  const modified = evidence[p.id]?.modified?.detail;
  const transferred = evidence[p.id]?.transferred?.detail;
  const moveDiscovery = (index: number) => { setDiscovery(index); update({ discoveryStep: String(index), discoveryAnswer: notes.discoveryAnswers?.[index] || '' }); };
  // Prompts from the key observation onward point at the approach; before commitment they count as guidance.
  const revealClue = () => { const rows = [...clues, discovery]; setClues(rows); if (!committed && discovery >= 2) update({ cluesRevealed: [...new Set([...(notes.cluesRevealed || []), discovery])] }); };
  const noteField = (label: string, field: TextField, placeholder: string, rows = 3) => <label className="journey-field"><span>{label}</span><textarea value={notes[field] || ''} onChange={e => update({ [field]: e.target.value })} placeholder={placeholder} rows={rows} maxLength={6000}/></label>;
  const commit = async () => {
    setCommitting(true);
    const result = await lab.commitApproach({ technique: notes.technique || '', operation: notes.operation || '', rationale: notes.rationale || '', plan: notes.plan || '', cluesRevealed: (notes.cluesRevealed || []).length, ...(notes.transferFromId ? { transferFrom: notes.transferFromId } : {}) });
    setCommitting(false);
    if (result) update({ approachFeedback: result });
  };
  const canCommit = !!notes.technique && (notes.operation || '').trim().length >= 12;

  return <div className={`learning-panel lesson-stage-${tab}`}>
    {tab === 'understand' && <>
      <div className="stage-intro"><span className="stage-badge"><BookOpen size={18}/> 01 / MAKE SENSE OF IT</span><h2>Understand the question.</h2><p>Explore what goes in, what comes out, and the rules connecting them.</p></div>
      <div className="understand-contract">{[['Input', p.decoder.given], ['Goal', p.decoder.find], ['Output', p.decoder.returns]].map(([title, text], i) => <div key={title}><span>0{i + 1} / {title}</span><p>{text}</p></div>)}</div>
      <div className="understand-grid"><section className="lesson-card example-lab" aria-label="Visual example explorer"><div className="lesson-card-heading"><h3>Make the example tangible.</h3><div className="example-switch">{examples.map(({ label }, i) => <button key={label + i} aria-pressed={exampleIndex === i} onClick={() => { setExampleIndex(i); setSelected(null); setShowOutput(false); }}>{label}</button>)}</div></div>
        {design ? <ol className="design-calls">{(example.args[0] as string[]).map((op, i) => <li key={i}><code>{i === 0 ? op : `.${op}`}({((example.args[1] as Value[][])[i] || []).map(display).join(', ')})</code></li>)}</ol>
          : structured ? <InputStage {...inputView(p, example.args)}/>
          : p.params.map((name, param) => <div className="example-parameter" key={name}><span className="tiny-label">{name}</span>{Array.isArray(example.args[param]) || typeof example.args[param] === 'string' ? <div className="intuition-cells">{Array.from(example.args[param] as Value[]).map((value, index) => <button key={index} className={selected?.param === param && selected.index === index ? 'selected' : ''} aria-label={`${name} index ${index}: ${display(value)}`} onClick={() => setSelected({ param, index })}><small>{index}</small><strong>{value === ' ' ? '␣' : display(value)}</strong></button>)}{!(example.args[param] as Value[] | string).length && <span className="small">Empty sequence · no positions</span>}</div> : <code className="example-scalar">{display(example.args[param])}</code>}</div>)}
        <p className="intuition-note" role="status">{structured ? <>{receives} This is an input illustration, not a code execution.</> : selected ? <>{p.params[selected.param]} at position <b>{selected.index}</b> holds <b>{display(selectedValue ?? null)}</b>. A position and its value are different things.</> : example.args.some(v => Array.isArray(v) || typeof v === 'string') ? 'Select an element to explore its position and value. This is an input illustration, not a code execution.' : `${p.params.join(' and ')} ${p.params.length > 1 ? 'are single values' : 'is a single value'}: there are no positions to explore. What does the answer depend on?`}</p>
        {noteField('Predict the output', 'prediction', 'Before revealing the result, what should this example return?', 2)}
        <button className="outline-button" onClick={() => setShowOutput(!showOutput)}><Eye size={15}/>{showOutput ? 'Hide expected output' : 'Reveal expected output'}</button>
        {showOutput && <div className="example-answer"><span className="tiny-label">EXPECTED OUTPUT</span><code>{display(example.expected)}</code><p>{explanation}</p></div>}
      </section><aside className="lesson-card constraint-card"><span className="tiny-label">{p.custom ? 'YOUR LAB’S CONTRACT' : 'THE CONTRACT'}</span><h3>What must stay true?</h3><ul>{constraintsFor(p).map(rule => <li key={rule}>{rule}</li>)}</ul>{p.custom && <button className="outline-button" onClick={onEditLab}><Pencil size={14}/>Edit your cases ({p.cases?.length ?? 0})</button>}<div className="think-prompt"><Lightbulb size={18}/><p>What would the smallest valid input look like? What changes when values repeat?</p></div></aside></div>
      <div className="stage-next"><span>Can you describe the goal without choosing an algorithm?</span><button className="primary-button" onClick={() => { void stage('Understood'); next('discover'); }}>Continue to Discover<ArrowRight size={16}/></button></div>
    </>}

    {tab === 'discover' && <>
      <div className="stage-intro"><span className="stage-badge"><Lightbulb size={18}/> 02 / FIND THE APPROACH</span><h2>Reason before you write.</h2><p>Start with an obvious idea. Find the repeated work. Name the operation that must become fast, then commit to a technique.</p></div>
      <div className="reasoning-workspace"><section className="reasoning-path" aria-label="Approach discovery"><div className="reasoning-rail">{['Brute force', 'Bottleneck', 'Key observation', 'Optimization'].map((label, i) => <button key={label} aria-pressed={discovery === i} className={discovery === i ? 'selected' : ''} onClick={() => moveDiscovery(i)}><span>0{i + 1}</span>{label}<ChevronRight size={14}/></button>)}</div><article className="reasoning-observation"><span className="tiny-label">OBSERVATION {discovery + 1} / 4</span><h3>{['What is the simplest correct idea?', 'Where are you repeating work?', 'What information is missing?', 'How can you reuse what you know?'][discovery]}</h3><label className="journey-field"><span>Your reasoning at this step</span><textarea rows={3} maxLength={2000} placeholder={['What would you try first on the example?', 'Which operation happens again and again?', 'What could you remember from earlier work?', 'What must remain true as your approach advances?'][discovery]} value={notes.discoveryAnswers?.[discovery] || ''} onChange={e => update({ discoveryAnswer: e.target.value, discoveryAnswers: { ...notes.discoveryAnswers, [discovery]: e.target.value } })}/></label>{p.custom ? <p className="small own-lab-note">You brought this problem, so there are no authored prompts to compare with. Write your reasoning; your cases will test it.</p> : clues.includes(discovery) ? <div className="discovery-clue"><span className="tiny-label">COMPARE YOUR OBSERVATION</span><p>{p.discovery[discovery]}</p></div> : <><button className="outline-button" onClick={revealClue}>Reveal a reasoning prompt</button>{discovery >= 2 && !committed && <p className="small clue-cost">This prompt points toward the approach. Revealing it before you commit records your commitment as guided.</p>}</>}<button className="text-button" onClick={() => moveDiscovery((discovery + 1) % 4)}>{discovery === 3 ? 'Revisit the simple idea' : 'Next observation'}<ArrowRight size={15}/></button></article></section>
      <section className="lesson-card approach-notebook commit-card" aria-label={p.custom ? 'Plan your approach' : 'Commit to an approach'}><div className="lesson-card-heading"><h3>{p.custom ? 'Plan your approach' : 'Commit to an approach'}</h3><span className="tiny-label">{p.custom ? 'YOUR OWN LAB · NOTHING HIDDEN, NOTHING TO COMPARE' : committed ? `COMMITTED · ${committed.technique}` : 'THE TECHNIQUE STAYS HIDDEN UNTIL YOU COMMIT'}</span></div>
        {notes.transferPlan && notes.transferFrom && <div className="carried-plan"><span className="tiny-label">YOUR PLAN FROM {notes.transferFrom.toUpperCase()}</span><p>{notes.transferPlan}</p></div>}
        {noteField('Which operation must become fast?', 'operation', 'e.g. “For each value, find whether … appeared earlier.” Name the repeated work your approach removes.', 2)}
        <label className="journey-field"><span>Your technique hypothesis</span><select value={notes.technique || ''} onChange={e => update({ technique: e.target.value })}><option value="">Choose a hypothesis…</option>{techniques.map(t => <option key={t}>{t}</option>)}</select></label>
        {noteField('Why does it fit that operation?', 'rationale', 'Which repeated work does it remove? What does it assume about the input?', 2)}
        {noteField('Your approach, step by step', 'plan', '1. Keep track of…\n2. For each…\n3. If…\n4. Return…', 6)}
        {p.custom ? <p className="notebook-status own-lab-note"><FlaskConical size={13}/> No authored approach exists for a problem you brought, so this plan isn’t graded. It travels with you to Code, where your cases test it. {saved}</p> : <>
        <button className="primary-button commit-button" disabled={!canCommit || committing} onClick={() => void commit()}><Check size={15}/>{committed ? 'Compare my revised approach' : 'Commit to this approach'}</button>
        <p className="notebook-status">{canCommit ? committed ? 'Your first commitment stays on record. Revisions get fresh feedback.' : 'Commit before the comparison appears. Your first hypothesis is kept as evidence.' : 'Name the operation and choose a technique to commit.'} {saved}</p></>}</section></div>
      {review ? <ApproachReview review={review}/> : committed && <section className="approach-review lesson-card"><span className="tiny-label">YOUR COMMITMENT · {committed.technique}</span><h3>You committed to an approach earlier.</h3><p>Commit again to see the comparison with your current notes. Your first commitment remains the record.</p></section>}
      {!p.custom && flatInput && <DiscoveryExperiment problem={p} phase={discovery}/>}
      <div className="stage-next"><button className="text-button" onClick={() => next('understand')}><ArrowLeft size={15}/> Revisit the problem</button><button className="primary-button" onClick={() => next('code')}>{p.custom ? 'Take my plan to code' : committed ? 'Take my approach to code' : 'Code without committing'}<ArrowRight size={16}/></button></div>
    </>}

    {tab === 'code' && <><div className="stage-intro code-stage-intro"><span className="stage-badge"><Pencil size={18}/> 03 / TEST YOUR THINKING</span><h2>{mode === 'modify' ? 'Adapt your solution to the new contract.' : 'Make your idea executable.'}</h2><p>Your program determines every state and step below—even when its behavior is incorrect.</p>{mode === 'solve' && !p.custom && <button className="text-button" onClick={onExplore}>Study a reference approach<ArrowRight size={14}/></button>}</div>
      {mode === 'modify' && notes.modifyReasoning ? <details className="approach-carry" open><summary>What you said changes</summary><pre>{notes.modifyReasoning}</pre><button className="text-button" onClick={() => next('reflect')}>Revise the reasoning<ArrowLeft size={13}/></button></details>
        : mode === 'solve' && (notes.plan || notes.transferPlan || notes.operation) && <details className="approach-carry" open><summary>{notes.transferFrom && !notes.plan ? `Adaptation from ${notes.transferFrom}` : 'Your approach from Discover'}</summary>{notes.technique && <span>{notes.technique}</span>}{notes.operation && <p className="carry-operation">Make fast: {notes.operation}</p>}<pre>{notes.plan || notes.transferPlan}</pre><button className="text-button" onClick={() => next('discover')}>Revise the reasoning<ArrowLeft size={13}/></button></details>}</>}

    {tab === 'reflect' && <>
      <div className="stage-intro"><span className="stage-badge"><RotateCcw size={18}/> 04 / MAKE IT YOURS</span><h2>Explain it. Change it. Transfer it.</h2><p>Turn the result of an experiment into reasoning you can use again.</p></div>
      <section className="reflection-evidence lesson-card"><span className="tiny-label">YOUR EXPERIMENT</span><h3>{tested ? run!.error ? 'Execution stopped. What assumption broke?' : run!.passed && run!.tests.every(t => t.passed) ? 'Your tests passed. Why does it work?' : 'A mismatch is a clue.' : stale ? 'Your code changed after this trace.' : 'Build evidence for your reasoning.'}</h3>{run ? <><p>{run.preview ? 'Current-input preview' : source !== 'mine' ? 'Reference execution' : mode === 'modify' ? 'Latest adaptation run' : 'Latest learner execution'} · returned <code>{display(run.result)}</code>{!run.preview && <> · {run.tests.filter(t => t.passed).length}/{run.tests.length} checks passed</>}</p>{run.error && <p className="evidence-error">{run.error.type}: {run.error.message}</p>}{run.divergence && <p>{run.divergence.message}</p>}{stale && <p>This trace describes earlier code. Run your current draft before using it as evidence.</p>}</> : <p>No execution yet. You can draft your explanation now, then return to Code & Visualize to test it.</p>}<button className="text-button" onClick={() => next('code')}>Revisit Code & Visualize<ArrowRight size={15}/></button></section>
      <div className="reflection-grid"><section className="lesson-card"><h3>Why does your solution work?</h3>{noteField('Your invariant or correctness argument', 'reasoning', 'What stays true after each step? Why does that guarantee the required result?', 4)}{noteField('Which assumption does your approach rely on?', 'assumptions', 'Sorted input? Distinct positions? Contiguous ranges? Why is this needed?', 2)}{noteField('Defend one important decision', 'decision', 'Why this data structure or boundary update instead of another?', 2)}{noteField('Mistake → lesson', 'mistake', 'What did you expect? What actually happened? Which assumption did you change?', 3)}<div className="complexity-estimates">{noteField('Time growth', 'time', 'e.g. O(n), because…', 2)}{noteField('Extra space', 'space', 'What grows with the input?', 2)}</div>{p.complexity && <button className="text-button" onClick={() => setRevealComplexity(!revealComplexity)}>{revealComplexity ? 'Hide reference complexity' : 'Compare with reference complexity'}<Eye size={14}/></button>}{revealComplexity && p.complexity && <p className="complexity-reference">Authored optimized approach: <b>{p.complexity.time}</b> time, <b>{p.complexity.space}</b> space. This is not a measurement of your draft. Explain any difference.</p>}<button className="outline-button save-reflection" disabled={(notes.reasoning || '').trim().length < 40} onClick={async () => { useLab.getState().clearError(); await stage('Explained', JSON.stringify({ reasoning: notes.reasoning, mistake: notes.mistake, time: notes.time, space: notes.space, recall: notes.recall })); setFeedback(useLab.getState().error ? 'Could not save progress. Local notes are retained; try again.' : 'Reflection saved. This records your explanation, not an automated judgment of mastery.'); }}><Check size={15}/> Save reflection</button>{feedback && <p className="small" role="status">{feedback}</p>}</section>
      <section className="lesson-card recall-card"><span className="tiny-label">ACTIVE RECALL</span><h3>Close the code. Retrieve the idea.</h3>{p.recall.map((question, i) => <label className="journey-field" key={question}><span><b>0{i + 1}</b> {question}</span><textarea rows={3} maxLength={2000} placeholder="Explain from memory…" value={notes.recall?.[i] || ''} onChange={e => update({ recall: { ...notes.recall, [i]: e.target.value } })}/></label>)}{noteField('Try to break your own reasoning', 'counterexample', 'If input size grows 10× or an assumption changes, give an input that challenges your approach. What would you test?', 3)}<p className="notebook-status">{saved}</p></section></div>
      {p.modification && <section className="modify-workshop lesson-card" aria-label="Changed requirement">
        <div><span className="tiny-label"><Shuffle size={12}/> MODIFY · THE REQUIREMENT CHANGES</span><h3>{p.modification.title}</h3><p>The input stays the same. The contract does not. Decide what changes in your reasoning before you touch the code.</p>
          <div className="transfer-contracts"><div><span>THE ORIGINAL CONTRACT</span><p>{p.statement}</p></div><div><span>THE CHANGED CONTRACT</span><p>{p.modification.statement}</p><code>Example: {p.modification.example.args.map(display).join(' · ')} → {display(p.modification.example.expected)}</code></div></div></div>
        <div>{noteField('What changes in your reasoning?', 'modifyReasoning', p.modification.question, 4)}
          {modified ? <div className="evidence-recorded"><Check size={15}/><div><strong>Adaptation recorded</strong><p>{modified.insight}</p></div></div> : null}
          <button className="primary-button" disabled={(notes.modifyReasoning || '').trim().length < 20 || lab.busy} onClick={() => lab.startModify()}>{mode === 'modify' ? 'Continue adapting my code' : modified ? 'Revisit my adaptation' : 'Adapt my code to this requirement'}<ArrowRight size={15}/></button>
          <p className="small">Your adaptation starts from your own solution and runs against the changed contract's tests. No reference is offered: adapting is the exercise.</p></div>
      </section>}
      {related && <section className="transfer-workshop lesson-card" aria-label="Transfer challenge"><div><span className="tiny-label">TRANSFER · A PROBLEM YOU HAVEN'T SOLVED</span><h3>Does your reasoning travel?</h3><p>Read the contract first. Decide what carries over before you see its technique.</p><div className="transfer-contracts"><div><span>A NEW PROBLEM</span><p>{related.statement}</p><code>Example: {related.example.args.map(display).join(' · ')} → {display(related.example.expected)}</code></div></div></div>
        <div>{noteField(`What, if anything, carries over from ${p.title}? What must change?`, 'adaptation', 'Name the idea you would reuse and the assumption that differs — or explain why nothing carries over.', 4)}
          {transferred ? <div className="evidence-recorded"><Check size={15}/><div><strong>Transfer recorded</strong><p>You committed to the right approach for {transferred.toTitle} before any hint, then solved it.</p></div></div>
            : <p className="small transfer-rule"><CircleHelp size={13}/> Transfer is recorded when you have solved {p.title}, then commit to the new problem's approach in Discover before any hint or reference, and pass its tests.</p>}
          <button className="primary-button" disabled={(notes.adaptation || '').trim().length < 20} onClick={() => { const key = notesKey(related.id); try { localStorage.setItem(key, JSON.stringify({ ...readNotes(key), transferFrom: p.title, transferFromId: p.id, transferPlan: notes.adaptation })); } catch { setFeedback('Could not carry the plan to the new problem. Copy your notes before continuing.'); return; } onChoose(related.id, 'understand'); }}>Open the new problem<ArrowRight size={15}/></button><p className="small">Your plan travels with you. The new problem starts at Understand with its own draft.</p></div></section>}
    </>}
    {(tab === 'discover' || tab === 'code') && hints > 0 && <details className="journey-hints"><summary><Lightbulb size={15}/> Your guidance · {hints} hint{hints === 1 ? '' : 's'}</summary>{hintContext && <p>{hintContext}</p>}{target.hints.slice(0, hints).map((text, i) => <p key={i}><b>{i + 1}.</b> {text}</p>)}{hints < target.hints.length && <button className="text-button" onClick={() => void hint()}>A little more guidance<ChevronRight size={14}/></button>}</details>}
  </div>;
}

function ApproachReview({ review }: { review: ApproachFeedback }) {
  const first = review.firstCommitment;
  return <section className={`approach-review lesson-card verdict-${review.verdict}`} aria-live="polite" aria-label="Approach comparison">
    <div className="review-head"><span className="tiny-label">YOUR COMMITMENT · {review.chosen}</span><h3>{verdictLabels[review.verdict]}</h3><p>{review.summary}</p></div>
    <div className="review-grid">
      <div className="review-intended"><span className="tiny-label">THE APPROACH THIS LAB IS BUILT AROUND</span><strong>{review.intended.technique}</strong><p><b>Make fast:</b> {review.intended.operation}</p><p className="small">{review.intended.why}</p></div>
      <div className="review-notes"><span className="tiny-label">VISIBLE IN YOUR NOTES</span>{review.resolved.length ? <ul className="resolved-list">{review.resolved.map(item => <li key={item}><Check size={13}/>{item}</li>)}</ul> : <p className="small">None of the key decisions appear in your notes yet.</p>}
        {review.unresolved.length > 0 && <><span className="tiny-label">STILL OPEN</span><ul className="open-list">{review.unresolved.map(item => <li key={item}><CircleHelp size={13}/>{item}</li>)}</ul></>}</div>
    </div>
    {review.verdict !== 'match' || review.unresolved.length ? <div className="reasoning-gap"><span className="tiny-label">THE REASONING GAP</span><p>{review.gap}</p></div> : <div className="reasoning-gap"><span className="tiny-label">NEXT</span><p>{review.gap}</p></div>}
    <p className="small review-footnote">{!review.first && first.technique !== review.chosen ? `Your first commitment (${first.technique}) stays as the record of your independent hypothesis. ` : ''}{first.guided ? `Recorded as guided practice: ${first.reasons.join('; ')}. ` : 'Recorded as an unaided commitment. '}“Visible in your notes” means the idea appears in what you wrote — it is not a judgment of your understanding.</p>
  </section>;
}
