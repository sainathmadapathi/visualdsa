import { CircleHelp } from 'lucide-react';
import type { Explanation, RunError } from '../types';

/** What stopped the program, the same way everywhere: a plain title, the detail in the learner's own names and values,
 * a question that points where to look (never the fix), and Python's own message in small type for reference. */
export function ErrorBody({ told, error, onLine }: { told: Explanation; error?: Pick<RunError, 'type' | 'message'> | null; onLine?: (line: number) => void }) {
  const raw = error ? `${error.type && error.type !== 'ValueError' ? `${error.type}: ` : ''}${error.message}` : '';
  return <div className="error-body">
    <strong>{told.title}{told.line !== null && told.line !== undefined && (onLine ? <button className="error-line" onClick={() => onLine(told.line!)}>line {told.line}</button> : <span className="error-line">line {told.line}</span>)}</strong>
    <p>{told.detail}</p>
    {told.hint && <p className="error-hint"><CircleHelp size={13} aria-hidden="true"/>{told.hint}</p>}
    {raw && raw.trim() !== told.detail.trim() && <small className="error-raw" title="Python's own message">Python: {raw}</small>}
  </div>;
}

/** The explanation a recorded error carries, or a plain fallback built from Python's message when it has none. */
export function explanationOf(error: RunError): Explanation {
  return error.explanation ?? { title: error.type === 'NotRun' ? 'Not run' : 'The program stopped', detail: error.message.replace(/\s*\(<student>, line \d+\)/, ''), hint: '', line: error.line };
}
