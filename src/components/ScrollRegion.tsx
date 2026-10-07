import { useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties, ReactNode, RefObject } from 'react';

/** A view that can scroll, reachable by keyboard: while its content overflows it is a named, focusable region
 * (arrow keys then scroll it); when everything fits it adds no tab stop. `ref` lets a view scroll it itself. */
export default function ScrollRegion({ className, label, style, children, ref: outer }: { className: string; label: string; style?: CSSProperties; children: ReactNode; ref?: RefObject<HTMLDivElement | null> }) {
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
  return <div ref={node => { ref.current = node; if (outer) outer.current = node; }} className={`${className} scroll-region`} style={style} {...(scrolls ? { tabIndex: 0, role: 'region', 'aria-label': label } : {})}>{children}</div>;
}
