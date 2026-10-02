import { activeProblem, notesKey, readNotes, useLab } from './store';

// Send references to evidence, never client-provided trace state.
export function guideContext() {
  const state = useLab.getState();
  let notes: Record<string, string> = {};
  try {
    // Notes belong to the original problem, including the learner's account of a changed requirement.
    const saved = readNotes(notesKey(state.problem?.id || ''));
    const fields = ['plan', 'technique', 'rationale', 'reasoning', 'mistake', 'time', 'space', 'adaptation', 'discoveryAnswer', 'discoveryStep', 'operation', 'modifyReasoning'];
    notes = Object.fromEntries(fields.filter(k => typeof saved[k] === 'string').map(k => [k, (saved[k] as string).slice(0, 900)]));
    if (saved.discoveryAnswers && typeof saved.discoveryAnswers === 'object') notes.discoveryAnswer = Object.entries(saved.discoveryAnswers).filter(([, v]) => typeof v === 'string').map(([step, value]) => `Step ${Number(step) + 1}: ${value}`).join(' | ').slice(0, 1200);
  } catch { /* Notes are optional; traces are always resolved by the server. */ }
  return { problemId: activeProblem(state)?.id, stage: state.tab, code: state.code, args: state.run?.input ?? state.args,
    attemptId: state.run?.attemptId || '', traceId: state.run?.traceId || '', step: state.step, notes };
}
