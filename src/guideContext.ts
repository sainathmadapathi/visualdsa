import { draftKey, useLab } from './store';

// Send references to evidence, never client-provided trace state.
export function guideContext() {
  const state = useLab.getState();
  let notes: Record<string, string> = {};
  try {
    const saved = JSON.parse(localStorage.getItem(draftKey(state.problem?.id || '') + ':learning-notes') || '{}');
    const fields = ['plan', 'technique', 'rationale', 'reasoning', 'mistake', 'time', 'space', 'adaptation', 'discoveryAnswer', 'discoveryStep'];
    notes = Object.fromEntries(fields.filter(k => typeof saved[k] === 'string').map(k => [k, saved[k].slice(0, 900)]));
    if (saved.discoveryAnswers && typeof saved.discoveryAnswers === 'object') notes.discoveryAnswer = Object.entries(saved.discoveryAnswers).filter(([, v]) => typeof v === 'string').map(([step, value]) => `Step ${Number(step) + 1}: ${value}`).join(' | ').slice(0, 1200);
  } catch { /* Notes are optional; traces are always resolved by the server. */ }
  return { problemId: state.problem?.id, stage: state.tab, code: state.code, args: state.args,
    attemptId: state.run?.attemptId || '', traceId: state.run?.traceId || '', step: state.step, notes };
}
