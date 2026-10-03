import { create } from 'zustand';
import { api } from './api';
import { auth, syncLearning } from './firebase';
import { applyMotion, initialMotion, type Motion } from './motion';
import type { ApproachFeedback, Evidence, Problem, Run, Sheet, Stage, Tab, Value } from './types';

/** solve: the problem as stated. modify: its changed requirement, executed and graded on the server. */
type Mode = 'solve' | 'modify';
/** topic: opened from a technique topic, so the approach was known before Discover. */
type Entry = 'topic' | 'open';
type EvidenceMap = Record<string, Partial<Record<Evidence['kind'], Evidence>>>;
type ProgressPayload = { saved: { problem_id: string; code: string }[]; progress: { problem_id: string; stage: Stage }[]; bookmarks: string[]; support: { problem_id: string; hint_level: number; revealed: number }[]; evidence?: Evidence[] };

interface Store {
  problems: Problem[]; problem: Problem | null; code: string; args: Value[]; tab: Tab;
  run: Run | null; runCode: string; step: number; playing: boolean; speed: number; busy: boolean;
  error: string; notice: string; hints: number; revealed: boolean; source: 'mine' | 'reference' | 'brute';
  hintContext: string;
  live: boolean; previewBusy: boolean; previewMessage: string; revision: number;
  mode: Mode; entry: Entry; evidence: EvidenceMap;
  /** The latest run with every case traced; `run` is the case on stage. `caseId` null means the main input. */
  batch: Run | null; caseId: string | null; tour: boolean;
  selectCase: (id: string, play?: boolean) => void; playCases: () => void; nextCase: () => boolean;
  /** The editor line under the cursor: the visual stage summarises what that line did. */
  cursorLine: number | null;
  /** Why the latest edit could not be traced yet (syntax or validation), with its line. */
  previewError: { message: string; line: number | null } | null;
  motion: Motion; setMotion: (motion: Motion) => void;
  preview: () => Promise<void>; toggleLive: () => void;
  support: Record<string, { hint_level: number; revealed: number }>;
  bookmarks: string[]; progress: Record<string, Stage>; saved: Record<string, string>;
  load: () => Promise<void>; refresh: () => Promise<void>; select: (id: string, entry?: Entry) => void; setCode: (code: string) => void;
  setTab: (tab: Tab) => void; setArgs: (args: Value[]) => void; execute: () => Promise<void>; traceInput: (args: Value[]) => Promise<void>;
  seek: (step: number) => void; play: () => void; reset: () => void;
  save: () => Promise<void>; bookmark: () => Promise<void>; hint: () => Promise<void>;
  reveal: (mode: 'reference' | 'brute') => Promise<void>; stage: (stage: Stage, evidence?: string) => Promise<void>;
  commitApproach: (body: { technique: string; operation: string; rationale: string; plan: string; cluesRevealed: number; transferFrom?: string }) => Promise<ApproachFeedback | null>;
  startModify: () => void; endModify: () => void;
  clearError: () => void;
  /** The learner's own sheets, and the labs they built for rows without a built-in lab. */
  sheets: Sheet[]; labs: Problem[];
  /** The sheet the current problem was opened from, so practice can continue down that sheet. */
  fromSheet: string | null;
  loadSheets: () => Promise<void>; applySheets: (data: { sheets: Sheet[]; labs: Problem[] }) => void;
}

export const draftKey = (id: string) => `visual-dsa:${auth?.currentUser ? auth.currentUser.uid + ':' : ''}draft:${id}`;
export const notesKey = (id: string) => draftKey(id) + ':learning-notes';
export const topicKey = (id: string) => draftKey(id) + ':topic-known';
export function readNotes(key: string): Record<string, unknown> {
  try { const value = JSON.parse(localStorage.getItem(key) || '{}'); return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; } catch { return {}; }
}
/** A built-in lab or one of the learner's own labs. */
export const findProblem = (s: { problems: Problem[]; labs: Problem[] }, id: string | null | undefined) => id ? s.problems.find(p => p.id === id) ?? s.labs.find(p => p.id === id) : undefined;
/** The problem that executes: the changed requirement while adapting, otherwise the problem itself. */
export const activeProblem = (s: { problem: Problem | null; mode: Mode }) => s.mode === 'modify' && s.problem?.modification ? { ...s.problem, ...s.problem.modification } : s.problem;
const groupEvidence = (rows: Evidence[] = []) => rows.reduce<EvidenceMap>((map, row) => ({ ...map, [row.problem_id]: { ...map[row.problem_id], [row.kind]: row } }), {});
const stages: Stage[] = ['Seen', 'Understood', 'Reproduced', 'Explained', 'Modified', 'Independent', 'Transferred'];
/** The step a live trace opens on: what the line being typed did, or the nearest line above it that ran. */
export function focusStep(events: Run['events'], line: number | null): number {
  if (!line) return 0;
  const exact = events.findIndex(e => e.line === line);
  if (exact >= 0) return exact;
  const above = events.reduce<Run['events'][number] | undefined>((best, e) => e.line < line && e.line > (best?.line ?? 0) ? e : best, undefined);
  return above ? above.id : 0;
}

/** The run for one case of a batch. The main case is the batch itself (it may carry an attempt). */
export function caseRun(batch: Run, id: string | null): Run {
  const found = batch.cases?.find(c => c.id === id);
  if (!found || found.id === batch.caseId) return batch;
  return { ...batch, ...found, attemptId: '', passed: !!found.goal?.matches, expected: found.goal?.expected ?? null, caseId: found.id, cases: batch.cases };
}

export const useLab = create<Store>((set, get) => ({
  problems: [], problem: null, code: '', args: [], tab: 'understand', run: null, runCode: '', step: 0,
  playing: false, speed: 900, busy: false, error: '', notice: '', hints: 0, revealed: false, source: 'mine',
  bookmarks: [], progress: {}, saved: {},
  hintContext: '', support: {},
  live: true, previewBusy: false, previewMessage: '', revision: 0,
  mode: 'solve', entry: 'open', evidence: {},
  batch: null, caseId: null, tour: false,
  cursorLine: null, previewError: null,
  motion: initialMotion(),
  sheets: [], labs: [], fromSheet: null,
  async loadSheets() {
    try { get().applySheets(await api<{ sheets: Sheet[]; labs: Problem[] }>('/sheets')); } catch { /* Sheets are optional; built-in labs still work. */ }
  },
  applySheets({ sheets, labs }) {
    set({ sheets, labs });
    const current = get().problem;
    if (!current?.custom) return;
    const updated = labs.find(l => l.id === current.id);
    if (!updated) { if (get().problems.length) get().select(get().problems[0].id); return; }
    // Changed cases change what every trace is judged against: start this lab's runs afresh.
    const changed = JSON.stringify(updated.cases) !== JSON.stringify(current.cases) || updated.params.join() !== current.params.join();
    set({ problem: updated, ...(changed ? { args: structuredClone(updated.example.args), batch: null, caseId: null, run: null, runCode: '', step: 0, playing: false, tour: false, revision: get().revision + 1 } : {}) });
  },
  setMotion(motion) { applyMotion(motion, true); set({ motion }); },
  toggleLive() { set({ live: !get().live, playing: false, revision: get().revision + 1, previewMessage: '' }); },
  async preview() {
    const { problem, code, args, source, revision, live, busy, previewBusy, mode } = get();
    if (!problem || !live || busy || previewBusy || source !== 'mine' || get().tab !== 'code') return;
    set({ previewBusy: true, previewMessage: 'Tracing your latest edit…' });
    try {
      const run = await api<Run>('/preview', { problemId: activeProblem(get())!.id, code, args });
      // Previews are serialized, so this is the newest trace. While typing continues it is still shown,
      // as the trace of the code it ran; any other change of context discards it.
      if (get().tab !== 'code' || get().revision !== revision || JSON.stringify(get().args) !== JSON.stringify(args) || !get().live || get().busy || get().source !== source || get().problem?.id !== problem.id || get().mode !== mode) return;
      // Live typing stays anchored to the line being written: the trace opens there, paused,
      // and morphs from the previous state. Explicit runs still play from the start.
      const shown = caseRun(run, get().caseId);
      set({ batch: run, run: shown, runCode: code, step: focusStep(shown.events, get().cursorLine), playing: false, tour: false, previewError: null, previewMessage: run.error ? `${run.error.type}: ${run.error.message}` : 'Live · in step with your code' });
    } catch (e) {
      if (get().tab === 'code' && get().revision === revision && get().live && !get().busy) set({ previewMessage: `Waiting for runnable code. ${e instanceof Error ? e.message : String(e)}`, previewError: { message: e instanceof Error ? e.message : String(e), line: (e as { line?: number | null }).line ?? null } });
    } finally { set({ previewBusy: false }); }
  },
  async load() {
    try {
      const problems = await api<Problem[]>('/problems');
      set({ problems });
      await get().loadSheets();
      const previous = localStorage.getItem('visual-dsa:problem');
      get().select(findProblem(get(), previous) ? previous! : problems[0].id);
      await get().refresh();
      const p = get().problem;
      if (p && get().support[p.id]) set({ hints: get().support[p.id].hint_level, revealed: !!get().support[p.id].revealed });
      if (p && !localStorage.getItem(draftKey(p.id)) && get().saved[p.id]) set({ code: get().saved[p.id] });
    } catch (e) { set({ error: `Cannot reach the learning API. Start python app.py. ${String(e)}` }); }
  },
  async refresh() {
    try {
      const data = await api<ProgressPayload>('/progress');
      set({ saved: Object.fromEntries(data.saved.map(s => [s.problem_id, s.code])), progress: Object.fromEntries(data.progress.map(s => [s.problem_id, s.stage])), bookmarks: data.bookmarks, support: Object.fromEntries((data.support || []).map(s => [s.problem_id, s])), evidence: groupEvidence(data.evidence) });
    } catch { /* Local drafts still work before sign-in. */ }
  },
  select(id, entry = 'open') {
    if (get().busy) { set({ notice: 'Wait for the current execution to finish.' }); return; }
    const problem = findProblem(get(), id);
    if (!problem) return;
    const old = activeProblem(get());
    if (old && get().source === 'mine') localStorage.setItem(draftKey(old.id), get().code);
    localStorage.setItem('visual-dsa:problem', id);
    // Once a problem was opened from its technique topic, that knowledge cannot be unlearned.
    if (entry === 'topic') localStorage.setItem(topicKey(id), 'true');
    set({ problem, fromSheet: problem.custom ? problem.sheetId ?? null : null, mode: 'solve', batch: null, caseId: null, tour: false, entry: localStorage.getItem(topicKey(id)) === 'true' ? 'topic' : 'open', code: localStorage.getItem(draftKey(id)) || get().saved[id] || problem.starter, args: structuredClone(problem.example.args), run: null, runCode: '', step: 0, playing: false, tab: 'understand', hints: get().support[id]?.hint_level ?? Number(localStorage.getItem(`visual-dsa:hints:${id}`) || 0), revealed: !!get().support[id]?.revealed || localStorage.getItem(`visual-dsa:revealed:${id}`) === 'true', hintContext: '', source: 'mine', error: '', notice: '', previewMessage: '', revision: get().revision + 1 });
  },
  setCode(code) {
    // Typing does not invalidate an in-flight trace: it arrives labelled with the code it ran (runCode).
    set({ code, playing: false, tour: false, notice: '', previewMessage: '' });
    const target = activeProblem(get());
    if (target && get().source === 'mine') localStorage.setItem(draftKey(target.id), code);
  },
  setTab(tab) { if (tab !== get().tab) set({ tab, playing: false, previewMessage: '', revision: get().revision + (get().busy ? 0 : 1) }); },
  setArgs(args) { set({ args, batch: null, caseId: null, tour: false, run: null, runCode: '', playing: false, step: 0, previewMessage: '', previewError: null, revision: get().revision + 1 }); },
  async execute() {
    if (get().busy || !get().problem) return;
    const { problem, code, args, source, mode } = get();
    const target = activeProblem(get())!;
    const revision = get().revision + 1;
    set({ busy: true, playing: false, error: '', notice: '', previewMessage: '', revision });
    try {
      const run = await api<Run>('/execute', { problemId: target.id, code, args, test: true });
      if (get().revision !== revision || get().source !== source || get().problem?.id !== problem!.id || get().mode !== mode) { set({ busy: false }); return; }
      set({ batch: run, run, caseId: null, tour: false, runCode: code, step: 0, playing: get().tab === 'code' && run.events.length > 0, busy: false });
      if (run.passed && run.tests.every(t => t.passed) && get().source === 'mine') {
        // A changed requirement records adaptation; the learner's own account of the change is the evidence text.
        if (mode === 'modify') await get().stage('Modified', String(readNotes(notesKey(problem!.id)).modifyReasoning || ''));
        else await get().stage(get().revealed || get().hints ? 'Reproduced' : 'Independent');
      }
    } catch (e) { set({ busy: false, error: e instanceof Error ? e.message : String(e) }); }
  },
  async traceInput(args) {
    // A case already traced for this code plays at once; otherwise run that exact input explicitly.
    if (get().busy) return;
    const found = get().batch?.cases?.find(c => JSON.stringify(c.input) === JSON.stringify(args));
    if (found && get().runCode === get().code) { get().selectCase(found.id, true); return; }
    get().setArgs(structuredClone(args));
    await get().execute();
  },
  selectCase(id, play = false) {
    const batch = get().batch;
    if (!batch?.cases?.some(c => c.id === id)) return;
    const run = caseRun(batch, id);
    // Choosing a case means watching it from the start; later typing re-anchors to the line.
    set({ caseId: id, run, step: play ? 0 : run.preview ? focusStep(run.events, get().cursorLine) : 0, playing: play && run.events.length > 0, tour: false });
  },
  playCases() {
    const cases = get().batch?.cases;
    if (!cases?.length) return;
    get().selectCase(cases[0].id, true);
    set({ tour: true });
  },
  nextCase() {
    // During a tour, move on when a case finishes; false when the tour is over.
    const { batch, run, tour } = get();
    const cases = batch?.cases || [];
    const index = cases.findIndex(c => c.id === (run?.caseId ?? batch?.caseId));
    if (!tour || index < 0 || index + 1 >= cases.length) { set({ tour: false, playing: false }); return false; }
    get().selectCase(cases[index + 1].id, true);
    set({ tour: true });
    return true;
  },
  seek(step) { set({ step: Math.max(0, Math.min(step, (get().run?.events.length || 1) - 1)), playing: false, tour: false }); },
  play() {
    const { run, step, playing } = get();
    if (!run?.events.length) return;
    set({ playing: !playing, step: step === run.events.length - 1 && !playing ? 0 : step });
  },
  reset() { set({ step: 0, playing: false }); },
  async save() {
    const { code } = get();
    const target = activeProblem(get());
    if (!target) return;
    try {
      await api('/progress', { problemId: target.id, code });
      set({ saved: { ...get().saved, [target.id]: code }, notice: 'Code saved to your learning workspace.' });
      try { if (get().mode === 'solve') await syncLearning(target.id, { code }); } catch { set({ notice: 'Saved locally. Cloud synchronization is unavailable.' }); }
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
    const target = activeProblem(get());
    if (!target) return;
    try {
      const data = await api<{ level: number; text: string; context: string }>('/hint', { problemId: target.id, level: Math.min(get().hints + 1, target.hints.length), attemptId: get().run?.attemptId });
      localStorage.setItem(`visual-dsa:hints:${target.id}`, String(data.level));
      set({ hints: data.level, hintContext: data.context, support: { ...get().support, [target.id]: { hint_level: data.level, revealed: Number(get().revealed) } } });
    } catch (e) { set({ error: String(e) }); }
  },
  async reveal(mode) {
    const p = get().problem;
    if (!p || get().mode === 'modify') return;  // Adapting means changing your own solution.
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
      const response = await api<{ stage: Stage; insight?: string | null; transferred?: string[] }>('/progress', { problemId: p.id, stage, evidence, attemptId: get().run?.attemptId });
      const old = get().progress[p.id];
      const recorded = old && stages.indexOf(old) > stages.indexOf(response.stage) ? old : response.stage;
      set({ progress: { ...get().progress, [p.id]: recorded } });
      if (response.insight) set({ notice: `Adaptation recorded. ${response.insight}` });
      if (response.transferred?.length) {
        const from = response.transferred.map(id => get().problems.find(q => q.id === id)?.title || id).join(', ');
        set({ notice: `Transfer recorded: you carried your reasoning from ${from} into ${p.title} without being told the approach.` });
      }
      if (response.insight || response.transferred?.length) await get().refresh();
      try { await syncLearning(p.id, { stage: recorded }); } catch { /* Optional cloud sync. */ }
    } catch (e) { set({ error: String(e) }); }
  },
  async commitApproach(body) {
    const p = get().problem;
    if (!p) return null;
    try {
      // A live preview that already met every authored case's goal means the code came before the hypothesis.
      const batch = get().batch, authored = batch?.preview && get().mode === 'solve' ? (batch.cases || []).filter(c => !c.custom) : [];
      const previewSolved = authored.length > 0 && authored.every(c => !c.error && c.goal?.matches);
      const feedback = await api<ApproachFeedback>('/approach', { problemId: p.id, topicKnown: get().entry === 'topic', previewSolved, ...body });
      const record: Evidence = { problem_id: p.id, kind: 'approach', created_at: '', detail: feedback.firstCommitment };
      set({ evidence: { ...get().evidence, [p.id]: { ...get().evidence[p.id], approach: record } } });
      return feedback;
    } catch (e) { set({ error: e instanceof Error ? e.message : String(e) }); return null; }
  },
  startModify() {
    const { problem, busy } = get();
    if (!problem?.modification || busy || get().mode === 'modify') return;
    const m = problem.modification;
    if (get().source === 'mine') localStorage.setItem(draftKey(problem.id), get().code);
    // Adaptation starts from the learner's own solution, never from a reference.
    set({ mode: 'modify', source: 'mine', batch: null, caseId: null, tour: false, code: localStorage.getItem(draftKey(m.id)) || get().saved[m.id] || localStorage.getItem(draftKey(problem.id)) || get().saved[problem.id] || problem.starter, args: structuredClone(m.example.args), run: null, runCode: '', step: 0, playing: false, tab: 'code', hints: get().support[m.id]?.hint_level ?? Number(localStorage.getItem(`visual-dsa:hints:${m.id}`) || 0), hintContext: '', error: '', notice: '', previewMessage: '', revision: get().revision + 1 });
  },
  endModify() {
    const { problem, busy } = get();
    if (!problem?.modification || busy || get().mode !== 'modify') return;
    localStorage.setItem(draftKey(problem.modification.id), get().code);
    set({ mode: 'solve', batch: null, caseId: null, tour: false, code: localStorage.getItem(draftKey(problem.id)) || get().saved[problem.id] || problem.starter, args: structuredClone(problem.example.args), run: null, runCode: '', step: 0, playing: false, hints: get().support[problem.id]?.hint_level ?? Number(localStorage.getItem(`visual-dsa:hints:${problem.id}`) || 0), hintContext: '', notice: '', previewMessage: '', revision: get().revision + 1 });
  },
  clearError() { set({ error: '', notice: '' }); },
}));
