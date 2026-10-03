import { ArrowRight, ArrowUpRight, BadgeCheck, Camera, Code2, Compass, FileSpreadsheet, Link2, MessageCircle, MoveHorizontal, Sparkles, Target, TextCursorInput, TriangleAlert } from 'lucide-react';
import type { Problem } from '../types';

// Each mode and feature names what the laboratory actually does today.
const modes = [
  { name: 'Understand', tone: 'silver', line: 'Decode the problem before choosing anything.', points: ['Input, goal and output made explicit', 'Two examples: predict, then reveal', 'Constraints that must stay true'], art: <UnderstandArt/> },
  { name: 'Discover', tone: 'violet', line: 'Reason your way to an approach.', points: ['Brute force → bottleneck → insight', 'Name what must become fast', 'Commit before the technique is shown'], art: <DiscoverArt/> },
  { name: 'Code & visualize', tone: 'orange', line: 'Write Python. Watch it actually run.', points: ['Your code animated as you type', 'A goal for your input: ✓ or ✗', 'Trace any failing test, step by step'], art: <CodeArt/> },
  { name: 'Reflect & transfer', tone: 'graphite', line: 'Make the idea yours.', points: ['Explain why your solution works', 'Adapt to a changed requirement', 'Carry it to an unseen problem'], art: <TransferArt/> },
];
const features = [
  { icon: MoveHorizontal, tone: 'violet', title: 'Your code, animated', text: 'Pointers glide and swaps arc; linked lists re-link, trees and tries grow, graphs light up as BFS spreads, DP tables fill, stacks, queues and heaps move, and recursion unfolds as a call tree. Every frame is a recorded step of the program you wrote.' },
  { icon: Target, tone: 'green', title: 'A goal for every input', text: 'The correct answer for your current input sits beside your result, so you know the moment you return whether you are on target.' },
  { icon: TriangleAlert, tone: 'coral', title: 'Wrong turns, proven', text: 'Out-of-range reads become ghost cells, a loop that repeats its exact state is proven infinite, and wrong values are marked where they were written.' },
  { icon: TextCursorInput, tone: 'orange', title: 'It follows your cursor', text: 'The line you are typing is summarised as you write: what it did on each pass, or that it never ran for this input.' },
  { icon: BadgeCheck, tone: 'silver', title: 'Evidence, not badges', text: 'Committing to an approach, adapting to a changed requirement and transferring are recorded only when your own work shows them.' },
  { icon: MessageCircle, tone: 'blue', title: 'A guide that reads your trace', text: 'Ask in your own words. It quotes the values your program actually produced, and asks a question before it gives an answer.' },
];

export default function Landing({ onPractice, onLibrary, onGuide, onSheets, problem, count, error, onRetry }: { onPractice: () => void; onLibrary: () => void; onGuide: () => void; onSheets: () => void; problem: Problem | null; count: number; error: string; onRetry: () => void }) {
  return <div className="landing-content">
    <section className="home-intro" id="how-it-works" aria-labelledby="intro-title">
      <div><span className="kinetic-overline">WHAT IS VISUAL DSA</span><h2 id="intro-title">A laboratory for how you <span>think through</span> a problem.</h2>
        <p>Most platforms show you an answer. Visual DSA runs <b>your own Python</b>, records every step it really takes, and teaches the reasoning that leads to a solution — so the next unfamiliar problem is yours to solve.</p>
        <ol className="home-path" aria-label="How a problem becomes understanding">{['Problem', 'Reasoning', 'Your code', 'Actual execution', 'Understanding'].map((label, i) => <li key={label}>{i > 0 && <ArrowRight size={12} aria-hidden="true"/>}<span>{label}</span></li>)}</ol></div>
      <div className="home-contrast"><div><span>THE USUAL WAY</span><p>Read a solution. Nod along. Meet the next problem with nothing to carry.</p></div><div><span>THE LABORATORY</span><p>Reason to an approach, commit to it, run your own code, inspect what it really did — then take the idea somewhere new.</p></div></div>
    </section>

    <section className="home-section" aria-labelledby="modes-title">
      <div className="home-head"><div><span className="kinetic-overline">FOUR MODES · ONE JOURNEY</span><h2 id="modes-title">Every problem moves through <span>four modes.</span></h2></div><p>Move at your own pace. Each mode builds evidence for the next, from making sense of the question to carrying the idea into a new one.</p></div>
      <div className="mode-grid">{modes.map((mode, i) => <article key={mode.name} className={`mode-card mode-${mode.tone}`}>
        <span className="mode-top">0{i + 1} / MODE</span>
        <div className="mode-art" aria-hidden="true">{mode.art}</div>
        <h3>{mode.name}</h3><p className="mode-line">{mode.line}</p>
        <ul>{mode.points.map(point => <li key={point}>{point}</li>)}</ul>
      </article>)}</div>
    </section>

    <section className="home-section" aria-labelledby="features-title">
      <div className="home-head"><div><span className="kinetic-overline">INSIDE THE LAB</span><h2 id="features-title">What you will see — <span>and why you can trust it.</span></h2></div><p>Everything in the laboratory comes from your own recorded run. When something is wrong, it shows only what the run proves.</p></div>
      <div className="feature-grid">{features.map(({ icon: Icon, tone, title, text }) => <article key={title} className={`feature feature-${tone}`}><span className="feature-icon"><Icon size={19}/></span><h3>{title}</h3><p>{text}</p></article>)}</div>
    </section>

    <section className="home-section own-sheet" aria-labelledby="sheet-title">
      <div className="own-sheet-copy"><span className="kinetic-overline">YOUR OWN SHEET</span><h2 id="sheet-title">Practice the sheet <span>you already follow.</span></h2>
        <p>Import the list you are working through. Problems the laboratory knows open straight into their lab; for the rest, paste the problem’s examples and they become a lab of your own — traced live, case by case, with every wrong turn shown.</p>
        <button className="primary-button" onClick={onSheets}>Import your sheet<ArrowRight size={15}/></button></div>
      <div className="own-sheet-sources">{[{ icon: FileSpreadsheet, title: 'A file', text: 'Excel, CSV, a text or Markdown list' }, { icon: Link2, title: 'A link', text: 'A shared Google Sheet or a page of problem links' }, { icon: Camera, title: 'A photo', text: 'A screenshot or picture, read on your device' }].map(({ icon: Icon, title, text }, i) => <button key={title} onClick={onSheets} style={{ ['--i' as string]: i }}><span><Icon size={20}/></span><strong>{title}</strong><small>{text}</small><ArrowUpRight size={15}/></button>)}</div>
    </section>

    <section className="landing-paths home-section" aria-labelledby="paths-title">
      <div className="home-head"><div><span className="kinetic-overline">ENTER THE LAB</span><h2 id="paths-title">Find your <span>way in.</span></h2></div><p>Start a problem cold, follow a pattern, or think out loud with the guide.</p></div>
      <div className="entry-grid">
        <button className="entry-card entry-practice" onClick={onPractice}><span className="entry-top"><Code2/><span>01 / MAKE IT REAL</span><ArrowUpRight/></span><div className="entry-art" aria-hidden="true"><span>[</span><i>2</i><i>7</i><i>11</i><span>]</span></div><h3>Enter the laboratory</h3><p>Write Python. Watch your own code unfold, one step at a time.</p><span className="entry-link">{problem ? `Continue with ${problem.title}` : 'Start practicing'} <ArrowRight size={17}/></span></button>
        <button className="entry-card entry-library" onClick={onLibrary}><span className="entry-top"><Compass/><span>02 / FIND A PROBLEM</span><ArrowUpRight/></span><div className="entry-art orbit-art" aria-hidden="true"><i/><i/><i/><i/></div><h3>Explore the problems</h3><p>{count || '24'} focused experiments, listed without their techniques so that you can discover them.</p><span className="entry-link">Find your next challenge <ArrowRight size={17}/></span></button>
        <button className="entry-card entry-guide" onClick={onGuide}><span className="entry-top"><Sparkles/><span>03 / GET UNSTUCK</span><ArrowUpRight/></span><div className="entry-art guide-art" aria-hidden="true"><span>what if</span><span>↗</span></div><h3>A guide by your side</h3><p>Ask in your own words. It reads your actual trace, and asks before it tells.</p><span className="entry-link">Talk to the studio guide <ArrowRight size={17}/></span></button>
      </div>
      {error && <div className="landing-error" role="alert">The problem library could not load. <button onClick={onRetry}>Try again</button></div>}
    </section>
  </div>;
}

// Small diagrams of each mode, drawn in the same ink-on-poster style as the hero cards.
function UnderstandArt() {
  return <svg viewBox="0 0 240 110"><g fontFamily="monospace" fontSize="11" fontWeight="700">
    {[['INPUT', 8], ['GOAL', 88], ['OUTPUT', 168]].map(([label, x]) => <g key={label as string}><rect x={x as number} y="34" width="64" height="40" rx="8" fill="#1d1a18"/><text x={(x as number) + 32} y="58" textAnchor="middle" fill="#efe9df">{label}</text></g>)}
    <path d="M74 54h12M154 54h12" stroke="#1d1a18" strokeWidth="2.5"/><path d="M83 49l5 5-5 5M163 49l5 5-5 5" fill="none" stroke="#1d1a18" strokeWidth="2.5"/>
    <text x="120" y="98" textAnchor="middle" fill="#3b3631" fontWeight="400">what goes in · what comes out</text></g></svg>;
}
function DiscoverArt() {
  return <svg viewBox="0 0 240 110"><g fontFamily="monospace" fontSize="10">
    <path d="M28 52h184" stroke="#24182e" strokeWidth="2" strokeDasharray="4 5"/>
    {['brute', 'bottleneck', 'insight'].map((label, i) => <g key={label}><circle cx={28 + i * 61} cy="52" r="10" fill="#24182e"/><text x={28 + i * 61} y="82" textAnchor="middle" fill="#24182e">{label}</text></g>)}
    <g transform="translate(211 52)"><rect x="-14" y="-10" width="28" height="22" rx="5" fill="#24182e"/><path d="M-8 -10v-7a8 8 0 0 1 16 0v7" fill="none" stroke="#24182e" strokeWidth="3"/><circle cy="1" r="3" fill="#cdb3f7"/></g>
    <text x="211" y="82" textAnchor="middle" fill="#24182e">commit</text></g></svg>;
}
function CodeArt() {
  return <svg viewBox="0 0 240 110" className="art-code"><g fontFamily="Manrope, sans-serif" fontWeight="800" fontSize="18">
    {[2, 7, 11, 15].map((value, i) => <g key={i}><rect x={22 + i * 52} y="46" width="44" height="44" rx="9" fill="#24170f" stroke="#1c120d" strokeWidth="2"/><text x={44 + i * 52} y="74" textAnchor="middle" fill="#f6e3d2">{value}</text></g>)}
    <g className="art-pointer"><text x="96" y="20" textAnchor="middle" fontFamily="monospace" fontSize="12" fill="#1c120d">i</text><path d="M96 25v13" stroke="#1c120d" strokeWidth="2.5"/><path d="M91 35l5 6 5-6" fill="#1c120d"/></g></g></svg>;
}
function TransferArt() {
  return <svg viewBox="0 0 240 110"><g fontFamily="monospace" fontSize="10">
    <rect x="18" y="26" width="78" height="56" rx="8" fill="none" stroke="#e0d9e8" strokeWidth="2"/><path d="M30 42h54M30 54h40M30 66h48" stroke="#e0d9e8" strokeWidth="2" opacity=".6"/>
    <path d="M106 54h26" stroke="#ed8b4d" strokeWidth="2.5"/><path d="M127 48l7 6-7 6" fill="none" stroke="#ed8b4d" strokeWidth="2.5"/>
    <rect x="144" y="26" width="78" height="56" rx="8" fill="#ed8b4d1f" stroke="#ed8b4d" strokeWidth="2" strokeDasharray="5 4"/><text x="183" y="58" textAnchor="middle" fill="#f2b383">new?</text>
    <text x="120" y="102" textAnchor="middle" fill="#a99cb5">same idea, new contract</text></g></svg>;
}
