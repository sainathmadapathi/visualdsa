import { useEffect, useRef, useState } from 'react';
import type { CSSProperties, PointerEvent } from 'react';
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUpRight } from 'lucide-react';
import { TOPICS } from '../topics';

const DARK = '#161618', CREAM = '#f6e6d2', LILAC = '#e7d6ff', INK = '#242027', ASH = '#dad4ca', VIOLET = '#b895f2', EMBER = '#f07b35';
const mono = { fontFamily: 'monospace' } as const;

function AlgorithmArt({ kind }: { kind: string }) {
  return <svg className={`algorithm-art art-${kind}`} viewBox="0 0 240 260" aria-hidden="true">
    {kind === 'array' && <g transform="translate(119 125) rotate(-30) skewX(20)">{[4, 3, 2, 1, 0].map(n => <g key={n} className="art-slab" style={{ '--layer': n } as CSSProperties} transform={`translate(${-78 + n * 4} ${-68 + n * 28})`}><path d="M0 0h132v18H0z" fill="#181818"/><path d="M132 0l16 -12v18l-16 12" fill="#45413c"/><path d="M0 0l16 -12h132l-16 12z" fill="#eee7dd"/><text x="15" y="13" fill="#f08a42" fontSize="12" fontFamily="monospace">0{n}</text></g>)}</g>}
    {kind === 'map' && <><g className="art-network" stroke="#e5d6ff" strokeWidth="1.3" fill="none"><path d="M52 67L172 55 190 163 78 192 52 67 190 163M78 192 172 55M52 67 115 127 190 163M115 127 78 192"/>{[[52,67],[172,55],[190,163],[78,192],[115,127]].map(([x,y],i)=><g key={i}><circle cx={x} cy={y} r={i===4?26:15} fill="#242027"/><circle cx={x} cy={y} r="4" fill="#e7d6ff"/></g>)}</g><text x="120" y="241" textAnchor="middle" fill="#24182e" fontSize="13" fontFamily="monospace">key → possibility</text></>}
    {kind === 'pointer' && <><g className="art-pointer-a"><path d="M29 62h79v46H69v45H29z" fill="#161618"/><path d="M108 62l33 23 -33 23z" fill="#161618"/></g><g className="art-pointer-b"><path d="M211 190h-79v-46h39V99h40z" fill="#f07b35"/><path d="M132 190l-33 -23 33 -23z" fill="#f07b35"/></g><circle cx="121" cy="124" r="54" fill="none" stroke="#393738" strokeDasharray="2 5"/><text x="120" y="244" textAnchor="middle" fill="#373235" fontSize="13" fontFamily="monospace">left → ← right</text></>}
    {kind === 'window' && <><g transform="translate(22 45)">{[0,1,2,3,4,5,6].map(n=><rect key={n} x={n*29} y={35+(n%3)*15} width="20" height={105-(n%3)*15} rx="2" fill={n>1&&n<5?'#f6e6d2':'#713a22'}/>)}<rect className="art-window-frame" x="49" y="17" width="92" height="150" rx="7" fill="none" stroke="#161518" strokeWidth="6"/></g><text x="120" y="239" textAnchor="middle" fill="#392217" fontSize="13" fontFamily="monospace">one move. new insight.</text></>}
    {kind === 'search' && <><g transform="translate(25 38)">{[0,1,2,3,4,5,6,7,8,9,10,11].map(n=><path key={n} d={`M${n*7} ${n*14}h${190-n*14}`} stroke={n>6?'#b895f2':'#dad4ca'} strokeWidth="7"/>)}</g><circle className="art-search-dot" cx="126" cy="192" r="9" fill="#f28845"/><text x="120" y="241" textAnchor="middle" fill="#c6bfce" fontSize="13" fontFamily="monospace">½ the space. every step.</text></>}

    {kind === 'string' && <>{/* A palindrome: each character paired with its mirror, read by a moving caret. */}
      {'racecar'.split('').map((c, i) => <g key={i}><text x={33 + i * 29} y="84" textAnchor="middle" fill="#3d2a52" fontSize="10" {...mono}>{i}</text><rect x={20 + i * 29} y="94" width="26" height="36" rx="4" fill={INK}/><text x={33 + i * 29} y="118" textAnchor="middle" fill={LILAC} fontSize="16" {...mono}>{c}</text></g>)}
      <g fill="none" stroke={INK} strokeWidth="1.6">{[0, 1, 2].map(i => <path key={i} d={`M${33 + i * 29} 136Q120 ${136 + (6 - 2 * i) * 14} ${33 + (6 - i) * 29} 136`}/>)}</g>
      <rect className="art-caret" x="17" y="90" width="32" height="44" rx="6" fill="none" stroke="#f7efff" strokeWidth="2.5"/>
      <text x="120" y="241" textAnchor="middle" fill="#24182e" fontSize="13" {...mono}>char by char.</text></>}

    {kind === 'list' && <>{/* Three nodes, each value beside its next pointer; a curr badge walks the chain. */}
      {[[20, 62, 3], [86, 108, 7], [152, 154, 9]].map(([x, y, v], i) => <g key={i}><rect x={x} y={y} width="40" height="32" rx="3" fill={DARK}/><text x={x + 20} y={y + 21} textAnchor="middle" fill="#e2dcd3" fontSize="14" {...mono}>{v}</text><rect x={x + 40} y={y} width="18" height="32" rx="3" fill={EMBER}/><circle cx={x + 49} cy={y + 16} r="3" fill={DARK}/></g>)}
      <g fill="none" stroke={DARK} strokeWidth="2.4" strokeLinejoin="round"><path className="art-flow" d="M69 78V124H80"/><path className="art-flow" d="M135 124V170H146"/><path d="M201 170V196"/></g>
      <g fill={DARK}><path d="M86 124l-8 -5v10z"/><path d="M152 170l-8 -5v10z"/></g>
      <text x="201" y="212" textAnchor="middle" fill="#373235" fontSize="11" {...mono}>None</text>
      <g className="art-curr"><rect x="16" y="30" width="48" height="20" rx="10" fill={EMBER}/><text x="40" y="44" textAnchor="middle" fill={DARK} fontSize="11" {...mono}>curr</text><path d="M40 50v8" stroke={DARK} strokeWidth="2"/></g>
      <text x="120" y="244" textAnchor="middle" fill="#373235" fontSize="13" {...mono}>follow next.</text></>}

    {kind === 'stack' && <>{/* An open container; the top plate lifts out and drops back: push and pop. */}
      <path d="M56 74V204H184V74" fill="none" stroke="#161518" strokeWidth="6" strokeLinejoin="round"/>
      {[[176, '#713a22', CREAM, 1], [150, CREAM, '#3b2416', 5], [124, '#181818', CREAM, 8]].map(([y, fill, ink, v]) => <g key={v as number}><rect x="68" y={y as number} width="104" height="22" rx="3" fill={fill as string}/><text x="120" y={(y as number) + 15} textAnchor="middle" fill={ink as string} fontSize="12" {...mono}>{v}</text></g>)}
      <g className="art-plate"><rect x="68" y="98" width="104" height="22" rx="3" fill={CREAM} stroke="#161518" strokeWidth="2"/><text x="120" y="113" textAnchor="middle" fill="#3b2416" fontSize="12" {...mono}>push 4</text></g>
      <text x="198" y="113" fill="#392217" fontSize="11" {...mono}>top</text><path d="M195 109h-14" stroke="#392217" strokeWidth="1.5"/>
      <text x="120" y="241" textAnchor="middle" fill="#392217" fontSize="13" {...mono}>last in. first out.</text></>}

    {kind === 'queue' && <>{/* A conveyor: values enter at the back and leave from the front. */}
      <defs><clipPath id="art-queue-clip"><rect x="30" y="96" width="180" height="48"/></clipPath></defs>
      <g clipPath="url(#art-queue-clip)"><g className="art-conveyor">{[0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map(n => <rect key={n} x={34 + n * 36} y="106" width="28" height="28" rx="4" fill={n % 3 === 1 ? VIOLET : ASH}/>)}</g></g>
      <path d="M26 94H214M26 146H214" stroke={ASH} strokeWidth="3"/>
      <g fill="#c6bfce" fontSize="11" {...mono}><text x="30" y="170">front</text><text x="210" y="170" textAnchor="end">back</text></g>
      <path d="M150 74H90m0 0l8 -5m-8 5l8 5" fill="none" stroke="#f28845" strokeWidth="2"/>
      <text x="120" y="241" textAnchor="middle" fill="#c6bfce" fontSize="13" {...mono}>first in. first out.</text></>}

    {kind === 'heap' && <>{/* A min-heap as a tree and as the array that stores it. */}
      <g stroke="#e5d6ff" strokeWidth="1.3"><path d="M120 58L78 104M120 58L162 104M78 104L56 150M78 104L100 150M162 104L140 150M162 104L184 150"/></g>
      {[[120, 58, 18, 1], [78, 104, 15, 3], [162, 104, 15, 2], [56, 150, 12, 7], [100, 150, 12, 4], [140, 150, 12, 5], [184, 150, 12, 9]].map(([x, y, r, v], i) => <g key={i} className={i === 0 ? 'art-heap-root' : undefined} style={{ transformOrigin: `${x}px ${y}px` }}><circle cx={x} cy={y} r={r} fill={i === 0 ? '#f7efff' : INK}/><text x={x} y={y + 4} textAnchor="middle" fill={i === 0 ? INK : LILAC} fontSize={i === 0 ? 13 : 11} {...mono}>{v}</text></g>)}
      {[1, 3, 2, 7, 4, 5, 9].map((v, i) => <g key={i}><rect x={34 + i * 25} y="190" width="22" height="20" rx="3" fill={i === 0 ? '#f7efff' : INK}/><text x={45 + i * 25} y="204" textAnchor="middle" fill={i === 0 ? INK : LILAC} fontSize="10" {...mono}>{v}</text></g>)}
      <text x="120" y="241" textAnchor="middle" fill="#24182e" fontSize="13" {...mono}>smallest on top.</text></>}

    {kind === 'recursion' && <>{/* Calls nested inside calls, down to the base case. */}
      {[[28, 56, 184, 160, 'solve(4)'], [50, 78, 140, 116, 'solve(3)'], [72, 100, 96, 72, 'solve(2)']].map(([x, y, w, h, label], i) => <g key={i} className="art-frame" style={{ '--layer': i, transformOrigin: '120px 136px' } as CSSProperties}><rect x={x as number} y={y as number} width={w as number} height={h as number} rx="8" fill="none" stroke={DARK} strokeWidth="2.4"/><text x={(x as number) + 8} y={(y as number) + 15} fill={DARK} fontSize="10.5" {...mono}>{label}</text></g>)}
      <rect x="94" y="124" width="52" height="36" rx="6" fill={EMBER}/><text x="120" y="146" textAnchor="middle" fill={DARK} fontSize="12" {...mono}>base</text>
      <path className="art-flow" d="M146 142C184 142 200 118 200 74" fill="none" stroke={EMBER} strokeWidth="2.4"/><path d="M200 66l-5 9h10z" fill={EMBER}/>
      <text x="120" y="244" textAnchor="middle" fill="#373235" fontSize="13" {...mono}>call. return.</text></>}

    {kind === 'tree' && <>{/* A binary tree; a ring walks from the root down to a leaf. */}
      <g stroke="#181818" strokeWidth="3"><path d="M120 62L74 114M120 62L166 114M74 114L50 166M74 114L98 166M166 114L190 166"/></g>
      {[[120, 62, 18, '#181818'], [74, 114, 15, CREAM], [166, 114, 15, '#181818'], [50, 166, 12, CREAM], [98, 166, 12, '#713a22'], [190, 166, 12, CREAM]].map(([x, y, r, fill], i) => <circle key={i} cx={x as number} cy={y as number} r={r as number} fill={fill as string} stroke="#181818" strokeWidth="2"/>)}
      <circle className="art-walk" cx="120" cy="62" r="24" fill="none" stroke={CREAM} strokeWidth="3" strokeDasharray="4 4"/>
      <text x="120" y="241" textAnchor="middle" fill="#392217" fontSize="13" {...mono}>root → leaves.</text></>}

    {kind === 'trie' && <>{/* cat, car and dog share their beginnings; the path for "cat" is lit. */}
      <g stroke={ASH} strokeWidth="1.6" fill="none"><path d="M120 48L80 96M120 48L160 96M80 96V144M80 144L50 192M80 144L110 192M160 96V144M160 144V192"/></g>
      <path className="art-flow art-path" d="M120 48L80 96V144L50 192" fill="none" stroke="#f28845" strokeWidth="3"/>
      <circle cx="120" cy="48" r="7" fill={ASH}/>
      {[[80, 96, 'c'], [80, 144, 'a'], [50, 192, 't', 1], [110, 192, 'r', 1], [160, 96, 'd'], [160, 144, 'o'], [160, 192, 'g', 1]].map(([x, y, c, end]) => <g key={`${x}${y}`}><circle cx={x as number} cy={y as number} r="13" fill={end ? VIOLET : '#2b2830'} stroke={ASH} strokeWidth="1.5"/><text x={x as number} y={(y as number) + 5} textAnchor="middle" fill={end ? '#151417' : '#e0d9e8'} fontSize="13" {...mono}>{c}</text></g>)}
      <text x="120" y="241" textAnchor="middle" fill="#c6bfce" fontSize="13" {...mono}>prefix by prefix.</text></>}

    {kind === 'graph' && <>{/* Breadth-first search: a wave leaves the start, visiting the nearest ring first. */}
      <circle className="art-ripple" cx="120" cy="124" r="58" fill="none" stroke="#f7efff" strokeWidth="2" strokeDasharray="3 5"/>
      <g stroke="#e5d6ff" strokeWidth="1.3"><path d="M120 66L200 82M120 66L40 82M170 153L196 190M70 153L44 190M200 82L196 190M40 82L44 190"/></g>
      <g stroke={INK} strokeWidth="2.4"><path d="M120 124L120 66M120 124L170 153M120 124L70 153"/></g>
      {[[200, 82], [196, 190], [44, 190], [40, 82]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r="10" fill={INK}/>)}
      {[[120, 66], [170, 153], [70, 153]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r="11" fill="#f7efff" stroke={INK} strokeWidth="2"/>)}
      <circle cx="120" cy="124" r="15" fill={INK}/><circle cx="120" cy="124" r="5" fill={LILAC}/>
      <text x="120" y="241" textAnchor="middle" fill="#24182e" fontSize="13" {...mono}>visit. queue. repeat.</text></>}

    {kind === 'grid' && <>{/* A grid of land and water; one island floods cell by cell. */}
      <g fill="#373235" fontSize="10" {...mono}>{[0, 1, 2, 3, 4].map(n => <g key={n}><text x={56 + n * 32} y="44" textAnchor="middle">{n}</text><text x="30" y={70 + n * 32} textAnchor="middle">{n}</text></g>)}</g>
      {[0, 1, 2, 3, 4].flatMap(r => [0, 1, 2, 3, 4].map(c => {
        const land = ['11000', '11001', '00011', '01000', '01100'][r][c] === '1';
        const flood = [[0, 0], [0, 1], [1, 0], [1, 1]].findIndex(([a, b]) => a === r && b === c);
        return <rect key={`${r}${c}`} className={flood >= 0 ? 'art-flood' : undefined} style={flood >= 0 ? { '--layer': flood } as CSSProperties : undefined} x={42 + c * 32} y={52 + r * 32} width="28" height="28" rx="3" fill={flood >= 0 ? EMBER : land ? DARK : 'none'} stroke={land ? 'none' : '#8f8b85'} strokeWidth="1.4"/>;
      }))}
      <text x="120" y="244" textAnchor="middle" fill="#373235" fontSize="13" {...mono}>row by column.</text></>}

    {kind === 'dp' && <>{/* Unique paths: each cell is the sum of the cell above and the cell to its left. */}
      {[0, 1, 2, 3].flatMap(r => [0, 1, 2, 3, 4].map(c => {
        const value = [[1, 1, 1, 1, 1], [1, 2, 3, 4, 5], [1, 3, 6, 10, 15], [1, 4, 10, 20, 35]][r][c];
        const current = r === 3 && c === 3, known = r < 3 || c < 3;
        return <g key={`${r}${c}`}><rect x={37 + c * 34} y={52 + r * 34} width="30" height="30" rx="3" fill={current ? '#181818' : known ? CREAM : 'none'} stroke={known || current ? 'none' : '#713a22'} strokeWidth="1.4" className={current ? 'art-cell' : undefined}/>{(known || current) && <text x={52 + c * 34} y={72 + r * 34} textAnchor="middle" fill={current ? CREAM : '#3b2416'} fontSize="11" {...mono}>{value}</text>}</g>;
      }))}
      <g stroke="#181818" strokeWidth="2" fill="none"><path className="art-flow" d="M139 172H143"/><path className="art-flow" d="M156 154V158"/></g>
      <g fill="#181818"><path d="M147 172l-6 -4v8z"/><path d="M156 162l-4 -6h8z"/></g>
      <text x="120" y="211" textAnchor="middle" fill="#392217" fontSize="11" {...mono}>10 + 10 = 20</text>
      <text x="120" y="241" textAnchor="middle" fill="#392217" fontSize="13" {...mono}>solve once. reuse.</text></>}

    {kind === 'bits' && <>{/* 13 shifted left by one is 26: every bit moves one place. */}
      {[[0, 0, 0, 0, 1, 1, 0, 1], [0, 0, 0, 1, 1, 0, 1, 0]].map((row, r) => <g key={r}>
        <text x="16" y={r ? 176 : 92} fill="#c6bfce" fontSize="11" {...mono}>{r ? '26' : '13'}</text>
        {row.map((b, i) => <g key={i} className={r && b ? 'art-bit' : undefined} style={{ '--layer': i } as CSSProperties}><rect x={42 + i * 23} y={r ? 154 : 70} width="20" height="32" rx="3" fill={b ? VIOLET : 'none'} stroke={b ? 'none' : ASH} strokeWidth="1.4"/><text x={52 + i * 23} y={r ? 175 : 91} textAnchor="middle" fill={b ? '#151417' : ASH} fontSize="13" {...mono}>{b}</text></g>)}</g>)}
      <g fill="#8f849b" fontSize="9" {...mono}>{[7, 6, 5, 4, 3, 2, 1, 0].map((k, i) => <text key={k} x={52 + i * 23} y="62" textAnchor="middle">{k}</text>)}</g>
      <g stroke="#f28845" strokeWidth="1.6" fill="none">{[4, 5, 7].map(i => <path key={i} d={`M${52 + i * 23} 106L${52 + (i - 1) * 23} 150`}/>)}</g>
      <text x="16" y="134" fill="#f28845" fontSize="11" {...mono}>{'<<1'}</text>
      <text x="120" y="241" textAnchor="middle" fill="#c6bfce" fontSize="13" {...mono}>1 {'<<'} k.</text></>}
  </svg>;
}

const loop = ['Understand', 'Discover', 'Commit', 'Code', 'See your execution', 'Debug', 'Adapt', 'Transfer'];
const N = TOPICS.length;
const VISIBLE = 2;  // Cards on each side of the front one.

/** The homepage hero: every topic the laboratory draws, in motion. Choosing a topic opens its practice. */
export default function KineticHero({ onTopic, onEnter, onExplain }: { onTopic: (topic: string) => void; onEnter: () => void; onExplain: () => void }) {
  const [active, setActive] = useState(2);
  const [focused, setFocused] = useState(false);
  const [visible, setVisible] = useState(true);
  const root = useRef<HTMLElement>(null);
  const strip = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: .15 });
    if (root.current) observer.observe(root.current);
    return () => { observer.disconnect(); };
  }, []);
  useEffect(() => {
    // Keep focused links in place for keyboard navigation; their 3D motion continues. Every change, chosen or
    // automatic, gives the front card its full time before the next one comes forward.
    if (focused || !visible) return;
    const timer = window.setTimeout(() => setActive(n => (n + 1) % N), 3600);
    return () => window.clearTimeout(timer);
  }, [focused, visible, active]);
  useEffect(() => {
    // The topic strip follows the front card without scrolling the page.
    const list = strip.current, chip = list?.children[active] as HTMLElement | undefined;
    if (list && chip) list.scrollTo({ left: chip.offsetLeft - (list.clientWidth - chip.offsetWidth) / 2, behavior: 'smooth' });
  }, [active]);
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
  const topic = TOPICS[active];
  return <section className="kinetic-hero home-hero" data-motion={visible ? 'playing' : 'offscreen'} ref={root} aria-labelledby="home-title" onPointerMove={move} onPointerLeave={e => { e.currentTarget.style.setProperty('--pan', '0px'); e.currentTarget.style.setProperty('--pitch', '0deg'); e.currentTarget.style.setProperty('--yaw', '0deg'); }} onFocusCapture={() => setFocused(true)} onBlurCapture={e => { if (!e.currentTarget.contains(e.relatedTarget)) setFocused(false); }}>
    <div className="kinetic-meta"><span><span className="live-indicator"/> THE VISUAL DSA LABORATORY</span><span>THINK IT. SEE IT. UNDERSTAND IT.</span></div>
    <div className="hero-head">
      <div><span className="kinetic-overline">DON’T JUST SEE THE SOLUTION.</span><h1 id="home-title">Algorithms.<br/><span>In full motion.</span></h1></div>
      <div className="hero-pitch"><p>See how a solution is <b>discovered</b>. Watch what <b>your own code</b> actually does, step by step. Then solve the next problem yourself.</p>
        <div className="hero-actions"><button className="enter-lab" onClick={onEnter}>Enter the laboratory <ArrowRight size={18}/></button><button className="text-button hero-secondary" onClick={onExplain}>How it works<ArrowDown size={14}/></button></div></div>
    </div>
    <div className="kinetic-gallery" aria-label="Explore data structure topics">
      <div className="gallery-orbit" aria-hidden="true"/>
      {TOPICS.map((subject, i) => {
        // Position relative to the front card, the shorter way round; cards beyond the visible five wait just off-stage.
        const rel = ((i - active) % N + N) % N, raw = rel > N / 2 ? rel - N : rel;
        const offset = Math.max(-VISIBLE - 1, Math.min(VISIBLE + 1, raw)), hidden = Math.abs(raw) > VISIBLE;
        return <button key={subject.name} className={`poster poster-${subject.color} ${i === active ? 'poster-active' : ''}`} data-hidden={hidden || undefined} tabIndex={hidden ? -1 : undefined} aria-hidden={hidden || undefined}
          style={{ '--offset': offset, '--distance': Math.abs(offset), '--card-index': i, zIndex: 5 - Math.abs(offset) } as CSSProperties} onClick={() => onTopic(subject.name)} aria-label={`Explore ${subject.name}`}>
          <span className="poster-top">{String(i + 1).padStart(2, '0')} / EXPLORE<ArrowUpRight size={17}/></span><AlgorithmArt kind={subject.kind}/><span className="poster-title">{subject.name}</span><span className="poster-bottom">A new way to see it <ArrowUpRight size={14}/></span></button>;
      })}
    </div>
    <div className="kinetic-caption"><span key={active} className="caption-copy"><b>{String(active+1).padStart(2,'0')}</b> {topic.line}</span><span className="caption-hint">{N} topics · choose one to practice</span><div className="gallery-controls"><button aria-label="Previous topic card" onClick={() => setActive(n => (n + N - 1) % N)}><ArrowLeft size={18}/></button><button aria-label="Next topic card" onClick={() => setActive(n => (n + 1) % N)}><ArrowRight size={18}/></button></div></div>
    <div className="topic-strip" ref={strip} aria-label="All topics">{TOPICS.map((t, i) => <button key={t.name} className={`topic-chip chip-${t.color}`} aria-pressed={i === active} onClick={() => setActive(i)}>{t.name}</button>)}</div>
    <div className="kinetic-ticker" aria-hidden="true"><div>{[0, 1].map(n => <span key={n}>{loop.map(step => <span key={step}>{step.toUpperCase()} <i>↗</i> </span>)}</span>)}</div></div>
  </section>;
}
