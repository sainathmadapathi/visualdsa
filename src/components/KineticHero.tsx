import { useEffect, useRef, useState } from 'react';
import type { CSSProperties, PointerEvent } from 'react';
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUpRight } from 'lucide-react';

const subjects = [
  { name: 'Arrays', line: 'Every position tells a story.', color: 'orange', kind: 'array' },
  { name: 'Hash maps', line: 'Find the connection. Skip the search.', color: 'violet', kind: 'map' },
  { name: 'Two pointers', line: 'Two perspectives. One discovery.', color: 'silver', kind: 'pointer' },
  { name: 'Sliding window', line: 'Move the frame. See the pattern.', color: 'orange', kind: 'window' },
  { name: 'Binary search', line: 'Less to search. More to understand.', color: 'graphite', kind: 'search' },
];

function AlgorithmArt({ kind }: { kind: string }) {
  return <svg className={`algorithm-art art-${kind}`} viewBox="0 0 240 260" aria-hidden="true">
    {kind === 'array' && <g transform="translate(119 125) rotate(-30) skewX(20)">{[4, 3, 2, 1, 0].map(n => <g key={n} className="art-slab" style={{ '--layer': n } as CSSProperties} transform={`translate(${-78 + n * 4} ${-68 + n * 28})`}><path d="M0 0h132v18H0z" fill="#181818"/><path d="M132 0l16 -12v18l-16 12" fill="#45413c"/><path d="M0 0l16 -12h132l-16 12z" fill="#eee7dd"/><text x="15" y="13" fill="#f08a42" fontSize="12" fontFamily="monospace">0{n}</text></g>)}</g>}
    {kind === 'map' && <><g className="art-network" stroke="#e5d6ff" strokeWidth="1.3" fill="none"><path d="M52 67L172 55 190 163 78 192 52 67 190 163M78 192 172 55M52 67 115 127 190 163M115 127 78 192"/>{[[52,67],[172,55],[190,163],[78,192],[115,127]].map(([x,y],i)=><g key={i}><circle cx={x} cy={y} r={i===4?26:15} fill="#242027"/><circle cx={x} cy={y} r="4" fill="#e7d6ff"/></g>)}</g><text x="120" y="241" textAnchor="middle" fill="#24182e" fontSize="13" fontFamily="monospace">key → possibility</text></>}
    {kind === 'pointer' && <><g className="art-pointer-a"><path d="M29 62h79v46H69v45H29z" fill="#161618"/><path d="M108 62l33 23 -33 23z" fill="#161618"/></g><g className="art-pointer-b"><path d="M211 190h-79v-46h39V99h40z" fill="#f07b35"/><path d="M132 190l-33 -23 33 -23z" fill="#f07b35"/></g><circle cx="121" cy="124" r="54" fill="none" stroke="#393738" strokeDasharray="2 5"/><text x="120" y="244" textAnchor="middle" fill="#373235" fontSize="13" fontFamily="monospace">left → ← right</text></>}
    {kind === 'window' && <><g transform="translate(22 45)">{[0,1,2,3,4,5,6].map(n=><rect key={n} x={n*29} y={35+(n%3)*15} width="20" height={105-(n%3)*15} rx="2" fill={n>1&&n<5?'#f6e6d2':'#713a22'}/>)}<rect className="art-window-frame" x="49" y="17" width="92" height="150" rx="7" fill="none" stroke="#161518" strokeWidth="6"/></g><text x="120" y="239" textAnchor="middle" fill="#392217" fontSize="13" fontFamily="monospace">one move. new insight.</text></>}
    {kind === 'search' && <><g transform="translate(25 38)">{[0,1,2,3,4,5,6,7,8,9,10,11].map(n=><path key={n} d={`M${n*7} ${n*14}h${190-n*14}`} stroke={n>6?'#b895f2':'#dad4ca'} strokeWidth="7"/>)}</g><circle className="art-search-dot" cx="126" cy="192" r="9" fill="#f28845"/><text x="120" y="241" textAnchor="middle" fill="#c6bfce" fontSize="13" fontFamily="monospace">½ the space. every step.</text></>}
  </svg>;
}

export default function KineticHero({ onTopic, onEnter }: { onTopic: (topic: string) => void; onEnter: () => void }) {
  const [active, setActive] = useState(2);
  const [focused, setFocused] = useState(false);
  const [visible, setVisible] = useState(true);
  const root = useRef<HTMLElement>(null);
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: .15 });
    if (root.current) observer.observe(root.current);
    return () => { observer.disconnect(); };
  }, []);
  useEffect(() => {
    // Keep focused links in place for keyboard navigation; their 3D motion continues.
    if (focused || !visible) return;
    const timer = window.setInterval(() => setActive(n => (n + 1) % subjects.length), 3600);
    return () => window.clearInterval(timer);
  }, [focused, visible]);
  useEffect(() => {
    let frame = 0;
    const update = () => { frame = 0; if (root.current) root.current.style.setProperty('--travel', String(Math.min(1, Math.max(0, -root.current.getBoundingClientRect().top / 650)))); };
    const scroll = () => { if (!frame) frame = requestAnimationFrame(update); };
    window.addEventListener('scroll', scroll, { passive: true }); update();
    return () => { window.removeEventListener('scroll', scroll); cancelAnimationFrame(frame); root.current?.style.removeProperty('--travel'); };
  }, []);
  const move = (e: PointerEvent<HTMLElement>) => {
    if (e.pointerType !== 'mouse') return;
    const r = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty('--pan', `${((e.clientX-r.left)/r.width-.5)*32}px`);
    e.currentTarget.style.setProperty('--pitch', `${((e.clientY-r.top)/r.height-.5)*-14}deg`);
    e.currentTarget.style.setProperty('--yaw', `${((e.clientX-r.left)/r.width-.5)*16}deg`);
  };
  return <section className="kinetic-hero" data-motion={visible ? 'playing' : 'offscreen'} ref={root} aria-label="Explore the visual learning studio" onPointerMove={move} onPointerLeave={e => { e.currentTarget.style.setProperty('--pan', '0px'); e.currentTarget.style.setProperty('--pitch', '0deg'); e.currentTarget.style.setProperty('--yaw', '0deg'); }} onFocusCapture={() => setFocused(true)} onBlurCapture={e => { if (!e.currentTarget.contains(e.relatedTarget)) setFocused(false); }}>
    <div className="kinetic-meta"><span><span className="live-indicator"/> THE VISUAL ALGORITHM STUDIO</span><span>THINK IT. SEE IT. UNDERSTAND IT.</span></div>
    <div className="kinetic-gallery" aria-label="Explore data structure topics">
      <div className="gallery-orbit" aria-hidden="true"/>
      {subjects.map((subject, i) => {
        const offset = ((i - active + 7) % 5) - 2;
        return <button key={subject.name} className={`poster poster-${subject.color} ${i === active ? 'poster-active' : ''}`} style={{ '--offset': offset, '--distance': Math.abs(offset), '--card-index': i, zIndex: 5 - Math.abs(offset) } as CSSProperties} onClick={() => onTopic(subject.name)} aria-label={`Explore ${subject.name}`}><span className="poster-top">0{i+1} / EXPLORE<ArrowUpRight size={17}/></span><AlgorithmArt kind={subject.kind}/><span className="poster-title">{subject.name}</span><span className="poster-bottom">A new way to see it <ArrowUpRight size={14}/></span></button>;
      })}
    </div>
    <div className="kinetic-caption"><span key={active} className="caption-copy"><b>{String(active+1).padStart(2,'0')}</b> {subjects[active].line}</span><div className="gallery-controls"><button aria-label="Previous topic card" onClick={() => setActive(n => (n+4)%5)}><ArrowLeft size={18}/></button><button aria-label="Next topic card" onClick={() => setActive(n => (n+1)%5)}><ArrowRight size={18}/></button></div></div>
    <div className="kinetic-heading"><div><span className="kinetic-overline">LESS MEMORIZING. MORE DISCOVERING.</span><h2>Algorithms.<br/><span>In full motion.</span></h2></div><div className="kinetic-invitation"><p>Write an idea. Watch it unfold.<br/>Make the understanding yours.</p><button className="enter-lab" onClick={onEnter}>Enter the laboratory <ArrowDown size={18}/></button></div></div>
    <div className="kinetic-ticker" aria-hidden="true"><div>{[0,1].map(n=><span key={n}>IDEA <i>↗</i> EXPERIMENT <i>↗</i> OBSERVE <i>↗</i> UNDERSTAND <i>↗</i> </span>)}</div></div>
  </section>;
}
