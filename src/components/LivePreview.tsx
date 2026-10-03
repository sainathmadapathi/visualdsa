import { useEffect, useRef } from 'react';
import { useLab } from '../store';

const lineCount = (code: string) => code.split('\n').length;

/** Coalesce edits and serialize previews. Old responses never replace newer code. */
export default function LivePreview() {
  const { problem, code, args, source, live, busy, previewBusy, preview, revision, run, runCode } = useLab();
  const signature = JSON.stringify([problem?.id, source, code, args, revision]);
  // Returning from reflection should preserve an unchanged, checked execution.
  const last = useRef(run && runCode === code ? signature : '');
  const testing = useRef(false);
  const pendingSince = useRef<number | null>(null);
  const lines = useRef(lineCount(code));
  useEffect(() => {
    const finishedLine = lineCount(code) > lines.current;
    lines.current = lineCount(code);
    if (!live || source !== 'mine') { last.current = ''; pendingSince.current = null; return; }
    if (busy) { if (!testing.current) last.current = signature; testing.current = true; return; }
    testing.current = false;
    if (!problem || previewBusy || signature === last.current) return;
    // Trace after a short pause, at once when a line is finished, and at least every 600 ms
    // during a continuous burst of typing, so the visual keeps pace with the code.
    const now = performance.now();
    pendingSince.current ??= now;
    const delay = finishedLine ? 0 : Math.max(0, Math.min(180, pendingSince.current + 600 - now));
    const timer = window.setTimeout(() => { last.current = signature; pendingSince.current = null; void preview(); }, delay);
    return () => window.clearTimeout(timer);
  }, [signature, problem, source, live, busy, previewBusy, preview]);  // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}
