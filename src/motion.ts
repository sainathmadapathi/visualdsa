/**
 * Motion follows the system's reduced-motion preference by default. A learner can override
 * it in the app; the choice is stored on this device and applied as html[data-motion].
 */
export type Motion = 'full' | 'reduced';
const KEY = 'visual-dsa:motion';

export function initialMotion(): Motion {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'full' || saved === 'reduced') return saved;
  } catch { /* Storage may be unavailable; fall back to the system preference. */ }
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches ? 'reduced' : 'full';
}

export function applyMotion(motion: Motion, persist = false) {
  if (typeof document !== 'undefined') document.documentElement.dataset.motion = motion;
  if (persist) try { localStorage.setItem(KEY, motion); } catch { /* The setting still applies for this visit. */ }
}

export const reducedMotion = () => typeof document !== 'undefined' && document.documentElement.dataset.motion === 'reduced';
