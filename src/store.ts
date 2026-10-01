import { create } from 'zustand';
import { api } from './api';
import { auth, syncLearning } from './firebase';
import type { Problem, Run, Stage, Tab, Value } from './types';

interface Store {
  problems: Problem[]; problem: Problem | null; code: string; args: Value[]; tab: Tab;
  run: Run | null; runCode: string; step: number; playing: boolean; speed: number; busy: boolean;
  error: string; notice: string; hints: number; revealed: boolean; source: 'mine' | 'reference' | 'brute';
  hintContext: string;
  live: boolean; previewBusy: boolean; previewMessage: string; revision: number;
  preview: () => Promise<void>; toggleLive: () => void;
  support: Record<string, { hint_level: number; revealed: number }>;
  bookmarks: string[]; progress: Record<string, Stage>; saved: Record<string, string>;
  load: () => Promise<void>; select: (id: string) => void; setCode: (code: string) => void;
  setTab: (tab: Tab) => void; setArgs: (args: Value[]) => void; execute: () => Promise<void>;
  seek: (step: number) => void; play: () => void; reset: () => void;
  save: () => Promise<void>; bookmark: () => Promise<void>; hint: () => Promise<void>;
  reveal: (mode: 'reference' | 'brute') => Promise<void>; stage: (stage: Stage, evidence?: string) => Promise<void>;
  clearError: () => void;
}

export const draftKey = (id: string) => `visual-dsa:${auth?.currentUser ? auth.currentUser.uid + ':' : ''}draft:${id}`;
export const useLab = create<Store>((set, get) => ({
  problems: [], problem: null, code: '', args: [], tab: 'understand', run: null, runCode: '', step: 0,
  playing: false, speed: 900, busy: false, error: '', notice: '', hints: 0, revealed: false, source: 'mine',
  bookmarks: [], progress: {}, saved: {},
  hintContext: '', support: {},
  live: true, previewBusy: false, previewMessage: '', revision: 0,
  toggleLive() { set({ live: !get().live, playing: false, revision: get().revision + 1, previewMessage: '' }); },
  async preview() {
    const { problem, code, args, source, revision, live, busy, previewBusy } = get();
    if (!problem || !live || busy || previewBusy || source !== 'mine' || get().tab !== 'code') return;
    set({ previewBusy: true, previewMessage: 'Tracing your latest edit…' });
    try {
      const run = await api<Run>('/preview', { problemId: problem.id, code, args });
      if (get().tab !== 'code' || get().revision !== revision || get().code !== code || JSON.stringify(get().args) !== JSON.stringify(args) || !get().live || get().busy || get().source !== source || get().problem?.id !== problem.id) return;
      set({ run, runCode: code, step: 0, playing: run.events.length > 0, previewMessage: run.error ? `${run.error.type}: ${run.error.message}` : 'Live trace updated · current input only' });
    } catch (e) {
      if (get().tab === 'code' && get().revision === revision && get().live && !get().busy) set({ previewMessage: `Waiting for runnable code. ${e instanceof Error ? e.message : String(e)}` });
    } finally { set({ previewBusy: false }); }
  },
  async load() {
    try {
      const problems = await api<Problem[]>('/problems');
      set({ problems });
      const previous = localStorage.getItem('visual-dsa:problem');
      get().select(problems.some(p => p.id === previous) ? previous! : problems[0].id);
      try {
        const data = await api<{ saved: { problem_id: string; code: string }[]; progress: { problem_id: string; stage: Stage }[]; bookmarks: string[]; support: { problem_id: string; hint_level: number; revealed: number }[] }>('/progress');
        set({ saved: Object.fromEntries(data.saved.map(s => [s.problem_id, s.code])), progress: Object.fromEntries(data.progress.map(s => [s.problem_id, s.stage])), bookmarks: data.bookmarks, support: Object.fromEntries((data.support || []).map(s => [s.problem_id, s])) });
        const p = get().problem;
        if (p && get().support[p.id]) set({ hints: get().support[p.id].hint_level, revealed: !!get().support[p.id].revealed });
        if (p && !localStorage.getItem(draftKey(p.id)) && get().saved[p.id]) set({ code: get().saved[p.id] });
      } catch { /* Local drafts still work before sign-in. */ }
    } catch (e) { set({ error: `Cannot reach the learning API. Start python app.py. ${String(e)}` }); }
  },
  select(id) {
    if (get().busy) { set({ notice: 'Wait for the current execution to finish.' }); return; }
    const problem = get().problems.find(p => p.id === id);
    if (!problem) return;
    const old = get().problem;
    if (old && get().source === 'mine') localStorage.setItem(draftKey(old.id), get().code);
    localStorage.setItem('visual-dsa:problem', id);
    set({ problem, code: localStorage.getItem(draftKey(id)) || get().saved[id] || problem.starter, args: structuredClone(problem.example.args), run: null, runCode: '', step: 0, playing: false, tab: 'understand', hints: get().support[id]?.hint_level ?? Number(localStorage.getItem(`visual-dsa:hints:${id}`) || 0), revealed: !!get().support[id]?.revealed || localStorage.getItem(`visual-dsa:revealed:${id}`) === 'true', hintContext: '', source: 'mine', error: '', notice: '', previewMessage: '', revision: get().revision + 1 });
  },
  setCode(code) {
    set({ code, playing: false, notice: '', previewMessage: '', revision: get().revision + 1 });
    const p = get().problem;
    if (p && get().source === 'mine') localStorage.setItem(draftKey(p.id), code);
  },
  setTab(tab) { if (tab !== get().tab) set({ tab, playing: false, previewMessage: '', revision: get().revision + (get().busy ? 0 : 1) }); },
  setArgs(args) { set({ args, run: null, runCode: '', playing: false, step: 0, previewMessage: '', revision: get().revision + 1 }); },
  async execute() {
    if (get().busy || !get().problem) return;
    const { problem, code, args, source } = get();
    const revision = get().revision + 1;
    set({ busy: true, playing: false, error: '', notice: '', previewMessage: '', revision });
    try {
      const run = await api<Run>('/execute', { problemId: problem!.id, code, args, test: true });
      if (get().revision !== revision || get().source !== source || get().problem?.id !== problem!.id) { set({ busy: false }); return; }
      set({ run, runCode: code, step: 0, playing: get().tab === 'code' && run.events.length > 0, busy: false });
      if (run.passed && run.tests.every(t => t.passed) && get().source === 'mine') {
        await get().stage(get().revealed || get().hints ? 'Reproduced' : 'Independent');
      }
    } catch (e) { set({ busy: false, error: e instanceof Error ? e.message : String(e) }); }
  },
  seek(step) { set({ step: Math.max(0, Math.min(step, (get().run?.events.length || 1) - 1)), playing: false }); },
  play() {
    const { run, step, playing } = get();
    if (!run?.events.length) return;
    set({ playing: !playing, step: step === run.events.length - 1 && !playing ? 0 : step });
  },
  reset() { set({ step: 0, playing: false }); },
  async save() {
    const { problem, code } = get();
    if (!problem) return;
    try {
      await api('/progress', { problemId: problem.id, code });
      set({ saved: { ...get().saved, [problem.id]: code }, notice: 'Code saved to your learning workspace.' });
      try { await syncLearning(problem.id, { code }); } catch { set({ notice: 'Saved locally. Cloud synchronization is unavailable.' }); }
    } catch (e) { set({ error: String(e) }); }
  },
  async bookmark() {
    const { problem, bookmarks } = get();
    if (!problem) return;
    const bookmark = !bookmarks.includes(problem.id);
    try {
      await api('/progress', { problemId: problem.id, bookmark });
      set({ bookmarks: bookmark ? [...bookmarks, problem.id] : bookmarks.filter(b => b !== problem.id) });
      try { await syncLearning(problem.id, { bookmark }); } catch { /* SQLite is authoritative. */ }
    } catch (e) { set({ error: String(e) }); }
  },
  async hint() {
    const p = get().problem;
    if (!p) return;
    try {
      const data = await api<{ level: number; text: string; context: string }>('/hint', { problemId: p.id, level: Math.min(get().hints + 1, p.hints.length), attemptId: get().run?.attemptId });
      localStorage.setItem(`visual-dsa:hints:${p.id}`, String(data.level));
      set({ hints: data.level, hintContext: data.context, support: { ...get().support, [p.id]: { hint_level: data.level, revealed: Number(get().revealed) } } });
    } catch (e) { set({ error: String(e) }); }
  },
  async reveal(mode) {
    const p = get().problem;
    if (!p) return;
    try {
      if (get().source === 'mine') localStorage.setItem(draftKey(p.id), get().code);
      const data = await api<{ code: string }>(`/problems/${p.id}/solution?mode=${mode === 'brute' ? 'brute' : 'optimized'}`);
      localStorage.setItem(`visual-dsa:revealed:${p.id}`, 'true');
      set({ code: data.code, source: mode, revealed: true, run: null, runCode: '', playing: false, step: 0, tab: 'code', revision: get().revision + 1, previewMessage: '', notice: mode === 'brute' ? 'Exploring the simple approach. Your draft is saved.' : 'Exploring the reference approach. Your draft is saved.' });
    } catch (e) { set({ error: String(e) }); }
  },
  async stage(stage, evidence = '') {
    const p = get().problem;
    if (!p) return;
    try {
      const response = await api<{ stage: Stage }>('/progress', { problemId: p.id, stage, evidence, attemptId: get().run?.attemptId });
      const stages: Stage[] = ['Seen', 'Understood', 'Reproduced', 'Explained', 'Modified', 'Independent', 'Transferred'];
      const old = get().progress[p.id];
      const recorded = old && stages.indexOf(old) > stages.indexOf(response.stage) ? old : response.stage;
      set({ progress: { ...get().progress, [p.id]: recorded } });
      try { await syncLearning(p.id, { stage: recorded }); } catch { /* Optional cloud sync. */ }
    } catch (e) { set({ error: String(e) }); }
  },
  clearError() { set({ error: '', notice: '' }); },
}));
