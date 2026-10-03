import { useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';

/** A view that can scroll, reachable by keyboard: while its content overflows it is a named, focusable region
 * (arrow keys then scroll it); when everything fits it adds no tab stop. */
export default function ScrollRegion({ className, label, style, children }: { className: string; label: string; style?: CSSProperties; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [scrolls, setScrolls] = useState(false);
  // Content changes with every step of a trace, so overflow is measured after each render and on resize.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const check = () => {
      const style = getComputedStyle(el), can = (overflow: string) => /auto|scroll/.test(overflow);
      setScrolls((can(style.overflowX) && el.scrollWidth > el.clientWidth + 1) || (can(style.overflowY) && el.scrollHeight > el.clientHeight + 1));
    };
    check();
    const observer = new ResizeObserver(check);
    observer.observe(el);
    if (el.firstElementChild) observer.observe(el.firstElementChild);
    return () => observer.disconnect();
  });
  return <div ref={ref} className={`${className} scroll-region`} style={style} {...(scrolls ? { tabIndex: 0, role: 'region', 'aria-label': label } : {})}>{children}</div>;
}
