import { useEffect, useState } from 'react';
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUpRight, Bookmark, BookOpen, Braces, Check, ChevronDown, ChevronRight, CircleAlert, Code2, Compass, FlaskConical, FolderOpen, GitBranch, GraduationCap, HelpCircle, Lightbulb, LoaderCircle, Menu, Play, Plus, Search, Settings2, Sparkles, Terminal, X } from 'lucide-react';
import { onAuthStateChanged } from 'firebase/auth';
import { api } from './api';
import { auth, cloudLearning, logOut, signIn } from './firebase';
import { draftKey, useLab } from './store';
import type { Tab, Value } from './types';
import CodeEditor from './components/CodeEditor';
import Visualizer, { display } from './components/Visualizer';
import LearningPanel from './components/LearningPanel';
import Playback from './components/Playback';
import Modal from './components/Modal';
import KineticHero from './components/KineticHero';
import LivePreview from './components/LivePreview';

const tabs: { key: Tab; label: string; icon: typeof BookOpen }[] = [
  { key: 'understand', label: 'Understand', icon: BookOpen }, { key: 'discover', label: 'Discover', icon: Compass },
  { key: 'code', label: 'Code & visualize', icon: Code2 }, { key: 'reflect', label: 'Reflect & transfer', icon: GitBranch },
];
type Dialog = 'library' | 'bookmarks' | 'progress' | 'input' | 'explore' | 'help' | 'break' | 'complexity' | 'account' | null;

function Logo() { return <div className="brand-mark" aria-hidden="true"><svg viewBox="0 0 32 32"><rect x="3" y="3" width="11" height="11" rx="3" fill="currentColor"/><rect x="18" y="3" width="11" height="11" rx="3" fill="currentColor" opacity=".4"/><rect x="3" y="18" width="11" height="11" rx="3" fill="currentColor" opacity=".4"/><rect x="18" y="18" width="11" height="11" rx="3" fill="currentColor"/><path d="M9 14v4m5-9h4m-4 15h4m6-10v4" stroke="currentColor"/></svg></div>; }

export default function App() {
  const lab = useLab();
  const [dialog, setDialog] = useState<Dialog>(null);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('All topics');
  const [input, setInput] = useState('');
  const [inputError, setInputError] = useState('');
  const [mobileNav, setMobileNav] = useState(false);
  const [userName, setUserName] = useState('');
  const [aiText, setAiText] = useState('');
  const [aiBusy, setAiBusy] = useState(false);
  const [breakLine, setBreakLine] = useState(1);
  const [sampleSize, setSampleSize] = useState(16);
  const [aiProvider, setAiProvider] = useState('');
  const p = lab.problem;
  useEffect(() => {
    if (!mobileNav) return;
    const trigger = document.activeElement as HTMLElement | null;
    document.querySelector<HTMLButtonElement>('.drawer-close')?.focus();
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setMobileNav(false); };
    window.addEventListener('keydown', escape);
    return () => { window.removeEventListener('keydown', escape); trigger?.focus(); };
  }, [mobileNav]);
  useEffect(() => { if (!lab.problems.length) void useLab.getState().load(); }, [lab.problems.length]);
  useEffect(() => {
    if (!auth) return;
    return onAuthStateChanged(auth, user => {
      setUserName(user?.displayName?.split(' ')[0] || '');
      void useLab.getState().load();
      if (user) void cloudLearning().then(rows => {
        // Firebase owns cross-device drafts/preferences, not execution evidence.
        const saved = { ...useLab.getState().saved };
        for (const row of rows as { problemId: string; code?: string }[]) if (row.code && !saved[row.problemId]) saved[row.problemId] = row.code;
        useLab.setState({ saved });
      }).catch(() => {});
    });
  }, []);
  useEffect(() => { setAiText(''); }, [p?.id, lab.run?.attemptId, lab.step]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setDialog('library'); } };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  const openLibrary = (type: 'library' | 'bookmarks' = 'library', topic = 'All topics') => { setSearch(''); setCategory(topic); setDialog(type); setMobileNav(false); };
  const choose = (id: string) => { lab.select(id); setDialog(null); setMobileNav(false); };
  const openInput = () => { setInput(JSON.stringify(lab.args)); setInputError(''); setDialog('input'); };
  const restore = () => { if (!p) return; const draft = localStorage.getItem(draftKey(p.id)) || p.starter; useLab.setState({ source: 'mine', code: draft, revision: lab.revision + 1, previewMessage: '', run: null, runCode: '', playing: false, step: 0 }); };
  const filtered = lab.problems.filter(q => (dialog !== 'bookmarks' || lab.bookmarks.includes(q.id)) && (category === 'All topics' || q.category === category) && `${q.title} ${q.category}`.toLowerCase().includes(search.toLowerCase()));
  const title = dialog === 'library' ? 'Find your next experiment' : dialog === 'bookmarks' ? 'Your bookmarked problems' : dialog === 'progress' ? 'Your learning journey' : dialog === 'input' ? 'Experiment with the input' : dialog === 'explore' ? 'Follow an approach' : dialog === 'break' ? 'Break it. Understand it. Repair it.' : dialog === 'complexity' ? 'Make complexity visible' : dialog === 'account' ? 'Your learning workspace' : 'A quick guide to your laboratory';

  return <div className="app-shell">
    <LivePreview/>
    {mobileNav && <div className="nav-scrim" onClick={() => setMobileNav(false)}/>}
    <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`} inert={!mobileNav}><button className="drawer-close icon-button" aria-label="Close navigation" onClick={() => setMobileNav(false)}><X size={20}/></button>
      <a className="brand" href="#" onClick={e => { e.preventDefault(); if (lab.problems[0]) choose(lab.problems[0].id); }}><Logo/><span>visual<span className="brand-dsa">dsa</span><span className="brand-dot">.</span></span></a>
      <div className="workspace-tag"><span className="live-indicator"/> YOUR LEARNING WORKSPACE</div>
      <nav className="primary-nav" aria-label="Main navigation">
        <button className="nav-item active" onClick={() => { setDialog(null); setMobileNav(false); }}><FlaskConical size={17}/><span>Learning laboratory</span><span className="nav-active-dot"/></button>
        <button className="nav-item" onClick={() => openLibrary()}><FolderOpen size={17}/><span>Problem library</span><span className="nav-count">{lab.problems.length || '—'}</span></button>
        <button className="nav-item" onClick={() => { setDialog('progress'); setMobileNav(false); }}><GraduationCap size={18}/><span>My learning journey</span></button>
        <button className="nav-item" onClick={() => openLibrary('bookmarks')}><Bookmark size={17}/><span>Bookmarks</span>{lab.bookmarks.length > 0 && <span className="nav-count">{lab.bookmarks.length}</span>}</button>
      </nav>
      <div className="sidebar-divider"/>
      <div className="sidebar-label">EXPLORE THE FOUNDATIONS</div>
      <div className="topic-nav">{['Arrays', 'Strings', 'Hash maps', 'Two pointers', 'Sliding window', 'Binary search'].map((topic, i) => <button key={topic} onClick={() => openLibrary('library', topic)}><span className="topic-icon">{['▤', 'Aa', '{}', '⇄', '▱', '⌕'][i]}</span><span>{topic}</span><ChevronRight size={12}/></button>)}</div>
      <div className="sidebar-divider"/>
      <div className="sidebar-label">A GOOD PLACE TO START <button aria-label="Browse all problems" onClick={() => openLibrary()}><Plus size={13}/></button></div>
      <div className="quick-problems">{lab.problems.slice(0, 4).map(q => <button key={q.id} className={p?.id === q.id ? 'selected' : ''} onClick={() => choose(q.id)}><span>{String(q.number).padStart(2, '0')}</span>{q.title}{lab.progress[q.id] && <Check size={12}/>}</button>)}</div>
      <div className="sidebar-bottom"><div className="sidebar-quote"><div className="quote-icon"><Lightbulb size={17}/></div><h4>Understand the why.</h4><p>A working answer is the beginning.<br/>Your reasoning is the real progress.</p></div><button className="nav-item" onClick={() => setDialog('help')}><HelpCircle size={17}/><span>A little help getting started</span><ArrowUpRight size={13}/></button><div className="sidebar-version">VISUAL DSA <span>v0.1 · Learning lab</span></div></div>
    </aside>

    <div className="main-shell" inert={mobileNav}>
      <header className="topbar"><div><button className="mobile-menu icon-button" aria-label="Open navigation" onClick={() => setMobileNav(true)}><Menu size={20}/></button><a className="header-brand" href="#" onClick={e => { e.preventDefault(); window.scrollTo({top:0,behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'}); }}><Logo/>visualdsa<span>.</span></a><span className="header-edition">THE LEARNING STUDIO</span></div><div className="topbar-right"><button className="search-trigger" onClick={() => openLibrary()}><Search size={15}/><span>Find a problem</span><kbd>Ctrl K</kbd></button><button className="header-journey" onClick={() => setDialog('progress')}>Your journey<ArrowUpRight size={14}/></button><span className="topbar-divider"/><button className="account-button" onClick={() => setDialog('account')}><span className="local-label">{userName || 'Local workspace'}</span><span className="avatar">{userName ? userName[0].toUpperCase() : 'L'}</span><ChevronDown size={12}/></button></div></header>
      <main>
        <KineticHero onTopic={topic => openLibrary('library', topic)}/>
        <div className="page-eyebrow" id="learning-lab"><span className="eyebrow-icon"><FlaskConical size={13}/></span> THE LEARNING LAB / {String(p?.number || 1).padStart(2, '0')} <span className="eyebrow-line"/></div>
        <div className="problem-heading"><div><div className="problem-title"><h1>{p?.title || 'Your thinking starts here.'}</h1>{p && <span className={`difficulty ${p.difficulty === 'Medium' ? 'medium' : ''}`}><span/>{p.difficulty}</span>}</div><p className="problem-statement">{p?.statement || 'Loading your learning laboratory…'}</p></div><div className="heading-actions"><button className={`icon-button bookmark-button ${p && lab.bookmarks.includes(p.id) ? 'bookmarked' : ''}`} aria-label="Bookmark this problem" onClick={() => void lab.bookmark()}><Bookmark size={18}/></button><button className="next-problem" onClick={() => { const next = lab.problems[((p?.number || 1)) % lab.problems.length]; if (next) choose(next.id); }}>Next problem<ArrowRight size={15}/></button></div></div>
        <div className="learning-tabs" role="tablist" aria-label="Learning stages">{tabs.map((t, i) => <button key={t.key} role="tab" aria-selected={lab.tab === t.key} className={lab.tab === t.key ? 'selected' : ''} onClick={() => lab.setTab(t.key)}><span className="tab-number">0{i + 1}</span><t.icon size={15}/><span>{t.label}</span></button>)}<div className="learning-stage"><span className="live-indicator"/>{p && lab.progress[p.id] || 'Start with curiosity'}</div></div>
        <LearningPanel key={p?.id} onExplore={() => setDialog('explore')}/>

        {lab.error && <div className="notification error-notice" role="alert"><CircleAlert size={17}/><span>{lab.error}</span><button className="icon-button" aria-label="Dismiss error" onClick={lab.clearError}><X size={15}/></button></div>}
        {lab.notice && <div className="notification" role="status"><Check size={16}/><span>{lab.notice}</span><button className="icon-button" aria-label="Dismiss notification" onClick={lab.clearError}><X size={15}/></button></div>}

        <section className="workbench" aria-label="Code and visualization workspace">
          <div className="workbench-bar"><div className="workbench-label"><Terminal size={16}/><strong>The experiment</strong><span className="vertical-rule"/><span>Code. Run. Observe.</span></div><div className="workbench-actions"><button className={`live-toggle ${lab.live ? 'is-live' : ''}`} role="switch" aria-checked={lab.live} aria-label="Live preview while typing" onClick={lab.toggleLive}><span className="live-indicator"/>Live {lab.live ? 'on' : 'off'}</button><button className="hint-button" disabled={!p || lab.hints >= p.hints.length} onClick={lab.hint}><Lightbulb size={15}/>{lab.hints ? `Next hint (${lab.hints}/${p?.hints.length})` : 'A gentle hint'}</button><button className="run-button" onClick={() => void lab.execute()} disabled={lab.busy || !p}>{lab.busy ? <LoaderCircle className="spin" size={15}/> : <Play size={14}/>}<span>{lab.busy ? 'Checking your code…' : 'Run all tests'}</span><kbd>Ctrl ↵</kbd></button></div></div>
          <div className="workbench-panes">
            <div className="editor-pane"><div className="pane-header"><div><Code2 size={15}/><span>{lab.source === 'mine' ? 'Your code' : lab.source === 'brute' ? 'Simple approach · reference' : 'Optimized approach · reference'}</span>{lab.source !== 'mine' && <button className="text-button" onClick={restore}><ArrowLeft size={12}/> My draft</button>}</div><span className="language-pill"><span className="python-dot"/>Python 3<ChevronDown size={11}/></span></div><CodeEditor/><div className="editor-status"><span><span className="live-indicator"/>{lab.source === 'mine' ? 'Draft stays on this device' : 'Reference · read only'}</span><button onClick={() => void lab.save()} disabled={!p || lab.source !== 'mine'}><Check size={12}/> Save code</button></div></div>
            <div className="visual-pane"><div className="pane-header"><div><EyeIcon/><span>{lab.source === 'mine' ? 'Your code, visualized' : 'Reference, visualized'}</span><span className="actual-tag">{lab.run?.preview ? 'LIVE TRACE' : lab.run ? 'ACTUAL TRACE' : 'INPUT PREVIEW'}</span></div><button className="text-button" onClick={openInput}><Settings2 size={13}/><span>Edit input</span></button></div><Visualizer/></div>
          </div>
          <Playback/>
        </section>

        <div className="below-lab"><div className="lab-takeaway"><div className="takeaway-icon"><Lightbulb size={19}/></div><div><span className="tiny-label">SMALL EXPERIMENTS. DEEPER UNDERSTANDING.</span><p>Change a value. Remove a line. Notice what happens.</p></div><button className="text-button" onClick={() => { setBreakLine(Math.min(2, lab.code.split('\n').length)); setDialog('break'); }}>Break & repair<ArrowUpRight size={14}/></button></div><button className="complexity-link" onClick={() => setDialog('complexity')}><span className="complexity-icon">n<span>²</span></span><span>Where does the work go?<small>Explore complexity</small></span><ArrowUpRight size={15}/></button></div>
        {lab.run?.attemptId && lab.run.events.length ? <div className="trace-teacher"><Sparkles size={16}/><div><strong>Understand this step</strong><p>{aiText || 'Get a teaching explanation grounded in the selected execution event.'}</p>{aiProvider && aiText && <span className="tiny-label">{aiProvider}</span>}</div><button className="outline-button" disabled={aiBusy} onClick={async () => { setAiBusy(true); lab.seek(lab.step); try { const data = await api<{ text: string; provider: string }>('/explain', { attemptId: lab.run!.attemptId, step: lab.step }); setAiText(data.text); setAiProvider(data.provider); } catch (e) { useLab.setState({ error: String(e) }); } finally { setAiBusy(false); } }}>{aiBusy ? <LoaderCircle className="spin" size={14}/> : <Sparkles size={14}/>} Explain this step</button></div> : null}
        <footer className="page-footer"><span><Braces size={13}/> Built for understanding, one step at a time.</span><button onClick={() => setDialog('help')}>How this laboratory works<ArrowUpRight size={12}/></button></footer>
        <div className="studio-wordmark" aria-hidden="true">think. build. <span>understand.</span></div>
      </main>
    </div>

    {dialog && <Modal title={title} onClose={() => setDialog(null)} wide={['library', 'bookmarks', 'progress', 'complexity'].includes(dialog)}>
      {(dialog === 'library' || dialog === 'bookmarks') && <><p className="modal-intro">24 focused laboratories. Each one connects understanding, reasoning, execution, and transfer.</p><div className="library-filters"><div><Search size={16}/><input placeholder="Search problems or topics…" aria-label="Search problems" value={search} onChange={e => setSearch(e.target.value)} autoFocus/></div><select value={category} onChange={e => setCategory(e.target.value)} aria-label="Filter by topic">{['All topics', 'Arrays', 'Strings', 'Hash maps', 'Two pointers', 'Sliding window', 'Binary search'].map(c => <option key={c}>{c}</option>)}</select></div><div className="library-list">{filtered.map(q => <button key={q.id} onClick={() => choose(q.id)}><span className="library-number">{String(q.number).padStart(2, '0')}</span><div><strong>{q.title}</strong><span>{q.category} · {lab.progress[q.id] || 'Ready to explore'}</span></div><span className={`difficulty ${q.difficulty === 'Medium' ? 'medium' : ''}`}>{q.difficulty}</span><ArrowRight size={16}/></button>)}{!filtered.length && <p className="empty-library">{dialog === 'bookmarks' ? 'Bookmark a problem from your laboratory to find it here.' : 'No matching problems. Try another search.'}</p>}</div></>}
      {dialog === 'progress' && <><p className="modal-intro">Progress is evidence of learning. Seeing a solution and solving independently are recorded differently.</p><div className="mastery-stages">{['Seen', 'Understood', 'Reproduced', 'Explained', 'Modified', 'Independent', 'Transferred'].map((s, i) => <div key={s}><span>{i + 1}</span><strong>{s}</strong></div>)}</div><p className="small">“Explained” records your written reflection; it is not an automated assessment. Independent execution is recorded only when no hints or reference have been used on this device.</p><div className="library-list">{lab.problems.map(q => <button key={q.id} onClick={() => choose(q.id)}><span className="library-number">{String(q.number).padStart(2, '0')}</span><div><strong>{q.title}</strong><span>{lab.progress[q.id] || 'Not started yet'}</span></div>{lab.progress[q.id] ? <Check size={17}/> : <ArrowRight size={16}/>}</button>)}</div></>}
      {dialog === 'input' && <><p className="modal-intro">Change the parameters and see what your code does. Keep the same types as the example.</p><div className="input-labels">{p?.params.map((name, i) => <div key={name}><code>{name}</code><span>{display(p.example.args[i])}</span></div>)}</div><label className="field-label" htmlFor="input-json">Parameters as a JSON array</label><textarea id="input-json" className="json-input" value={input} onChange={e => setInput(e.target.value)} autoFocus/><p className="small">Example: {JSON.stringify(p?.example.args)}. Arrays may contain up to 200 integers; strings up to 200 characters.</p>{inputError && <p className="field-error">{inputError}</p>}<div className="modal-actions"><button className="outline-button" onClick={() => setInput(JSON.stringify(p?.example.args))}>Reset example</button><button className="primary-button" onClick={() => { try { const args: Value[] = JSON.parse(input); if (!Array.isArray(args) || args.length !== p?.params.length) throw new Error(`Provide ${p?.params.length} parameters inside an array.`); lab.setArgs(args); setDialog(null); } catch (e) { setInputError(e instanceof Error ? e.message : 'Invalid JSON.'); } }}>Use this input<ArrowRight size={14}/></button></div></>}
      {dialog === 'explore' && <><p className="modal-intro">Try your own idea first. When you want to study an approach, choose one to trace. Your draft is kept separately.</p><button className="approach-choice" onClick={() => { void lab.reveal('brute'); setDialog(null); }}><div className="approach-icon"><WorkflowIcon/></div><div><strong>Start with the simple approach</strong><p>Make the straightforward idea visible. Notice where work repeats.</p></div><ArrowRight size={19}/></button><button className="approach-choice" onClick={() => { void lab.reveal('reference'); setDialog(null); }}><div className="approach-icon"><Compass size={22}/></div><div><strong>Explore an optimized approach</strong><p>Follow the improvement. Ask what information removes repeated work.</p></div><ArrowRight size={19}/></button><div className="gentle-note"><Lightbulb size={15}/> Revealing an approach records future passing attempts as reproduction, rather than independent discovery.</div></>}
      {dialog === 'break' && <><p className="modal-intro">Choose one line from your own draft to disable, then run again. Observe its purpose by seeing what changes. Use Undo in the editor to repair it.</p>{lab.source !== 'mine' ? <div className="gentle-note">Return to your own draft first to make a change.</div> : <><label className="field-label" htmlFor="break-line">Line to disable</label><select id="break-line" className="break-select" value={breakLine} onChange={e => setBreakLine(Number(e.target.value))}>{lab.code.split('\n').map((line, i) => <option value={i + 1} key={i}>{i + 1}: {line || '(empty)'}</option>)}</select><pre className="break-preview">{lab.code.split('\n').map((line, i) => `${i + 1}  ${i + 1 === breakLine ? '# DISABLE → ' : ''}${line}`).join('\n')}</pre><div className="gentle-note">Disabling a structural line can produce a syntax error. That is also part of the experiment.</div><button className="primary-button" onClick={() => { const lines = lab.code.split('\n'); const original = lines[breakLine - 1]; const indent = original.match(/^\s*/)?.[0] || ''; lines[breakLine - 1] = `${indent}pass # disabled: ${original.trim()}`; lab.setCode(lines.join('\n')); setDialog(null); }}>Disable line {breakLine}<ArrowRight size={14}/></button></> }</>}
      {dialog === 'complexity' && <><p className="modal-intro">Compare growth as input size changes. These are theoretical models; the actual trace count appears below.</p><label className="complexity-slider">Input size <strong>n = {sampleSize}</strong><input type="range" min="2" max="64" value={sampleSize} onChange={e => setSampleSize(Number(e.target.value))}/></label><div className="growth-chart">{[{ name: 'Try every distinct pair', count: sampleSize * (sampleSize - 1) / 2, className: 'quadratic', model: 'n(n − 1) / 2' }, { name: 'One full pass', count: sampleSize, className: 'linear', model: 'n' }, { name: 'Halve a search interval', count: Math.floor(Math.log2(sampleSize)) + 1, className: 'logarithmic', model: '⌊log₂ n⌋ + 1' }].map(g => <div key={g.name}><div><span>{g.name} <code>{g.model}</code></span><strong>{g.count} steps</strong></div><div className="growth-track"><span className={g.className} style={{ width: `${Math.max(3, g.count / (sampleSize * (sampleSize - 1) / 2) * 100)}%` }}/></div></div>)}</div><div className="halving-model">{Array.from({ length: Math.floor(Math.log2(sampleSize)) + 1 }, (_, i) => <span key={i}>{Math.max(1, Math.floor(sampleSize / 2 ** i))}{i < Math.floor(Math.log2(sampleSize)) && <ArrowRight size={13}/>}</span>)}</div>{p && <div className="gentle-note">Reference approach: {p.complexity.time} time · {p.complexity.space} space. Complexity is a model of growth, not a measurement from one example.</div>}{lab.run && <div className="trace-counts"><h4>Your actual recorded operations</h4>{Object.entries(lab.run.counts).map(([name, count]) => <span key={name}>{name.toLowerCase().replaceAll('_', ' ')} <strong>{count}</strong></span>)}</div>}</>}
      {dialog === 'account' && <><p className="modal-intro">Your code and learning evidence are saved in the local SQLite database. Sign in with Firebase to sync drafts and preferences across devices.</p><div className="account-status"><span className="avatar">{userName ? userName[0] : 'L'}</span><div><strong>{userName || 'Local learner'}</strong><p>{auth ? userName ? 'Firebase connected' : 'Firebase sign-in available' : 'Local mode · no account needed'}</p></div></div>{auth ? <button className="primary-button" onClick={async () => { try { if (userName) await logOut(); else await signIn(); setDialog(null); } catch (e) { useLab.setState({ error: String(e) }); setDialog(null); } }}>{userName ? 'Sign out' : 'Continue with Google'}<ArrowRight size={15}/></button> : <p className="gentle-note">To enable cloud sign-in, add your Firebase web configuration to .env and configure Firebase Admin on the backend. Local learning is ready now.</p>}</>}
      {dialog === 'help' && <><p className="modal-intro">You don’t need to know an algorithm before starting. Follow the four stages at your own pace.</p><div className="help-steps">{tabs.map((t, i) => <div key={t.key}><span>0{i + 1}</span><div><strong>{t.label}</strong><p>{['Decode the input, goal, and output. An index starts at zero.', 'Start with a simple idea. Look for repeated work and useful information.', 'Write Python in solve. Run, pause, move backward, and inspect every state.', 'Explain your reasoning. Change a line or try a related problem.'][i]}</p></div></div>)}</div><div className="gentle-note"><Terminal size={15}/> Ctrl + Enter runs code. Ctrl + K opens the library. Playback controls inspect a completed trace; they never rerun the code.</div><p className="small">The local runner supports plain Python functions, arrays, strings, dictionaries, sets, loops, and selected built-in methods. Imports, file/network access, classes, and indirect calls are excluded.</p></>}
    </Modal>}
  </div>;
}
function EyeIcon() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>; }
function WorkflowIcon() { return <div style={{ display: 'flex', alignItems: 'center' }}><BoxIcon/><ArrowDown size={13}/><BoxIcon/></div>; }
function BoxIcon() { return <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="2" width="12" height="12" rx="2"/></svg>; }
