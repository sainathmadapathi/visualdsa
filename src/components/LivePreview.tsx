import { useEffect, useRef } from 'react';
import { useLab } from '../store';

/** Coalesce edits and serialize previews. Old responses never replace newer code. */
export default function LivePreview() {
  const { problem, code, args, source, live, busy, previewBusy, preview, revision } = useLab();
  const last = useRef('');
  const testing = useRef(false);
  const signature = JSON.stringify([problem?.id, source, code, args, revision]);
  useEffect(() => {
    if (!live || source !== 'mine') { last.current = ''; return; }
    if (busy) { if (!testing.current) last.current = signature; testing.current = true; return; }
    testing.current = false;
    if (!problem || previewBusy || signature === last.current) return;
    const timer = window.setTimeout(() => { last.current = signature; void preview(); }, 850);
    return () => window.clearTimeout(timer);
  }, [signature, problem, source, live, busy, previewBusy, preview]);
  return null;
}
