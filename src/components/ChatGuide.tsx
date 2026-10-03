import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, BookOpen, LoaderCircle, MessageCircle, Send, Sparkles, X } from 'lucide-react';
import { api } from '../api';
import { guideContext } from '../guideContext';
import { useLab } from '../store';
import type { Tab } from '../types';

type Source = { id: string; title: string; text: string; problemId: string | null; tab: Tab };
type Reply = { text: string; provider: string; status: string; sources: Source[]; assistedProblemIds: string[]; hintLevel?: number; sections?: { label: string; text: string }[]; focus?: { problem?: string; stage?: string; step?: number | null; stale?: boolean; preview?: boolean } };
type Message = { role: 'user' | 'assistant'; content: string; reply?: Reply; problemId?: string };
export default function ChatGuide({ open, onOpen, onClose, practice, onPractice, onLibrary, onJourney }: { open: boolean; onOpen: () => void; onClose: () => void; practice: boolean; onPractice: (id: string, tab?: Tab) => void; onLibrary: () => void; onJourney: () => void }) {
  const lab = useLab();
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [share, setShare] = useState(true);
  const [ai, setAi] = useState<boolean | null>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const launcher = useRef<HTMLButtonElement>(null);
  const sending = useRef(false);
  useEffect(() => { if (open) { useLab.setState({ playing: false }); field.current?.focus(); void api<{ ai: boolean }>('/health').then(r => setAi(r.ai)).catch(() => setAi(null)); } }, [open]);
  useEffect(() => { if (open) end.current?.scrollIntoView({ block: 'nearest' }); }, [messages, busy, open]);
  const close = () => { onClose(); launcher.current?.focus(); };
  const send = async (question = draft) => {
    if (!question.trim() || sending.current) return;
    sending.current = true; setBusy(true); setError(''); setDraft('');
    const scope = practice && share ? lab.problem?.id : undefined;
    const history = messages.filter(m => m.problemId === scope).slice(-8).map(({ role, content }) => ({ role, content: content.slice(0, 1500) }));
    const message = question.trim();
    setMessages(rows => [...rows, { role: 'user', content: message, problemId: scope }]);
    const state = useLab.getState();
    try {
      const reply = await api<Reply>('/chat', { message, history, ...(practice && share && state.problem ? { context: guideContext() } : {}) });
      setMessages(rows => [...rows, { role: 'assistant', content: reply.text, reply, problemId: scope }]);
      const current = useLab.getState();
      const support = { ...current.support };
      for (const id of reply.assistedProblemIds) support[id] = { hint_level: Math.max(1, reply.focus?.problem === state.problem?.title && id === state.problem?.id ? reply.hintLevel || 0 : 0, support[id]?.hint_level || 0), revealed: support[id]?.revealed || 0 };
      useLab.setState({ support, ...(current.problem && reply.assistedProblemIds.includes(current.problem.id) ? { hints: support[current.problem.id]?.hint_level || current.hints } : {}) });
      if (reply.assistedProblemIds.length) void useLab.getState().reloadProblems();  // Guidance counts as hints asked for.
    } catch (e) { setError(e instanceof Error ? e.message : 'The guide could not respond.'); setDraft(message); }
    finally { sending.current = false; setBusy(false); }
  };
  const stageNames = { understand: 'Understand', discover: 'Discover', code: 'Code & Visualize', reflect: 'Reflect & Transfer' };
  const suggestions = { understand: ['What should the output represent?', 'What do the constraints tell us?'], discover: ['Help me find the bottleneck', 'Give me the next hint'], code: ['Explain this execution step', 'What is wrong with my code?'], reflect: ['Why does my approach work?', 'How can I transfer this reasoning?'] };
  const openSource = (source: Source) => {
    onClose();
    if (source.problemId) onPractice(source.problemId, source.tab);
    else if (source.id === 'help:progress') onJourney();
    else if (lab.problem) onPractice(lab.problem.id, source.tab);
    else onLibrary();
  };
  return <>
    <button ref={launcher} className="guide-launcher" onClick={open ? close : onOpen} aria-expanded={open} aria-controls="studio-guide"><MessageCircle size={20}/><span>Ask the guide</span></button>
    {open && <section id="studio-guide" className="guide-panel" role="region" aria-label="Studio guide chat" onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); close(); } }}>
      <header className="guide-header"><div className="guide-avatar"><Sparkles size={20}/></div><div><h2>Studio guide</h2><p>{ai === true ? 'AI + your learning context' : ai === false ? 'Grounded tutor · no AI model configured' : 'Your learning companion'}</p></div><button className="icon-button" onClick={close} aria-label="Close studio guide"><X size={19}/></button></header>
      {practice && share && <div className="tutor-context-bar"><strong>{lab.problem?.title} · {stageNames[lab.tab]}</strong><span>{lab.run?.events[lab.step] ? `${lab.run.preview ? 'Live preview' : 'Recorded run'} · step ${lab.step + 1} · line ${lab.run.events[lab.step].line}${lab.runCode !== lab.code ? ' · earlier draft' : ''}` : 'No execution evidence yet'}</span><small>{lab.hints ? `Guidance level ${lab.hints} · ${lab.progress[lab.problem?.id || ''] || 'Seen'}` : 'Start with your own reasoning'}</small></div>}
      <div className="guide-messages" role="log" aria-label="Conversation" aria-live="polite" aria-relevant="additions">
        {!messages.length && <div className="guide-welcome"><span className="kinetic-overline">LET’S CONNECT THE DOTS</span><h3>What’s on your mind?</h3><p>Tell me what you expected, what you observed, or which decision you’re unsure about. We’ll work through the next thought together.</p><div className="guide-suggestions">{(practice ? suggestions[lab.tab] : ['I’m new to DSA. Where do I start?', 'When should I use a sliding window?', 'How does live visualization work?']).map(q => <button key={q} disabled={busy} onClick={() => void send(q)}>{q}<ArrowUpRight size={14}/></button>)}</div></div>}
        {messages.map((m, i) => <article key={i} className={`guide-message guide-${m.role}`}><span className="guide-speaker">{m.role === 'user' ? 'YOU' : m.reply?.provider || 'STUDIO GUIDE'}</span>{m.reply?.focus?.problem && <small className="tutor-message-context">{m.reply.focus.problem} · {m.reply.focus.stage}{m.reply.focus.step != null ? ` · step ${m.reply.focus.step + 1}` : ''}{m.reply.focus.stale ? ' · earlier code/input' : ''}</small>}{m.reply?.sections?.length ? m.reply.sections.map((section, index) => <div className="tutor-section" key={index}><strong>{section.label}</strong><p>{section.text}</p></div>) : <p>{m.content}</p>}{m.reply && <><small className="guide-status">{m.reply.status}</small>{m.reply.sources.length > 0 && <details className="guide-sources"><summary><BookOpen size={13}/> Retrieved lessons · {m.reply.sources.length}</summary>{m.reply.sources.map(s => <div key={s.id}><strong>{s.title}</strong>{s.text && <p>{s.text}</p>}<button onClick={() => openSource(s)}>Open lesson <ArrowUpRight size={13}/></button></div>)}</details>}{m.reply.sources[0] && <button className="guide-next" onClick={() => openSource(m.reply!.sources[0])}>Explore {m.reply.sources[0].title.split(' · ')[0]}<ArrowUpRight size={14}/></button>}</>}</article>)}
        {busy && <div className="guide-thinking" role="status"><LoaderCircle size={15} className="spin"/> Reading your context…</div>}
        <div ref={end}/>
      </div>
      <form className="guide-compose" onSubmit={e => { e.preventDefault(); void send(); }}>
        {practice && <label className="guide-context"><input type="checkbox" checked={share} onChange={e => setShare(e.target.checked)}/> Include {lab.problem?.title || 'practice'} stage, notes, draft, input & recorded step</label>}
        {error && <p className="guide-error" role="alert">{error} Your message is ready to retry.</p>}
        <div className="guide-input"><textarea ref={field} aria-label="Message the studio guide" placeholder="Ask a question in your own words…" maxLength={2000} rows={2} value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); } }}/><button aria-label="Send message" type="submit" disabled={busy || !draft.trim()}><Send size={18}/></button></div>
        <div className="guide-footnote"><span>Grounded in platform lessons. Guidance counts as assistance.</span><button type="button" disabled={busy || !messages.length} onClick={() => { setMessages([]); setError(''); }}>New chat</button></div>
      </form>
    </section>}
  </>;
}
