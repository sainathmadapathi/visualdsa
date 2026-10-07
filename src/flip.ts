import { useLayoutEffect, useRef } from 'react';
import type { RefObject } from 'react';
import { reducedMotion } from './motion';

/**
 * Items that the layout moves glide instead of jumping. After each change of `stamp`, every child of the
 * container marked `data-flip` (its identity) that sat elsewhere before slides from there to its new place. A
 * position is the item's layout offset in its container (the container must be positioned), so neither a
 * scroll nor a motion in flight reads as a move. New and departing items are left to their own entrance and
 * exit. With `animate` off (a jump, not a step), positions are only recorded. The returned lookup gives where an
 * item stood before this step, so an item that just left can fade out in its own place.
 */
export function useFlip(container: RefObject<HTMLElement | null>, stamp: unknown, animate: boolean, duration = 420) {
  const last = useRef(new Map<string, [number, number]>());
  useLayoutEffect(() => {
    const box = container.current;
    if (!box) return;
    const items = [...box.querySelectorAll<HTMLElement>(':scope > [data-flip]')];
    const now = new Map(items.map(item => [item.dataset.flip!, [item.offsetLeft, item.offsetTop] as [number, number]]));
    const runs: Animation[] = [];
    if (animate && !reducedMotion()) for (const item of items) {
      const was = last.current.get(item.dataset.flip!), at = now.get(item.dataset.flip!)!;
      if (!was || !item.animate) continue;
      const dx = was[0] - at[0], dy = was[1] - at[1];
      if (Math.abs(dx) + Math.abs(dy) > 1) runs.push(item.animate([{ translate: `${dx}px ${dy}px` }, { translate: '0px 0px' }], { duration, easing: 'cubic-bezier(.22, .9, .24, 1)' }));
    }
    last.current = now;
    return () => runs.forEach(run => run.cancel());
  }, [stamp]);  // eslint-disable-line react-hooks/exhaustive-deps
  return (key: string): [number, number] | undefined => last.current.get(key);
}
