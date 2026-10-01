import { ArrowRight, ArrowUpRight, Code2, Compass, Sparkles } from 'lucide-react';
import type { Problem } from '../types';

export default function Landing({ onPractice, onLibrary, onGuide, problem, count, error, onRetry }: { onPractice: () => void; onLibrary: () => void; onGuide: () => void; problem: Problem | null; count: number; error: string; onRetry: () => void }) {
  return <div className="landing-content">
    <section className="landing-paths" aria-labelledby="paths-title">
      <div className="landing-section-title"><span className="kinetic-overline">A LITTLE CURIOSITY GOES A LONG WAY</span><h2 id="paths-title">Find your way in.</h2><p>One place to discover. A dedicated space to practice.</p></div>
      <div className="entry-grid">
        <button className="entry-card entry-practice" onClick={onPractice}><span className="entry-top"><Code2/><span>01 / MAKE IT REAL</span><ArrowUpRight/></span><div className="entry-art" aria-hidden="true"><span>[</span><i>2</i><i>7</i><i>11</i><span>]</span></div><h3>Enter the laboratory</h3><p>Write Python. Watch your own code unfold, one step at a time.</p><span className="entry-link">{problem ? `Continue with ${problem.title}` : 'Start practicing'} <ArrowRight size={17}/></span></button>
        <button className="entry-card entry-library" onClick={onLibrary}><span className="entry-top"><Compass/><span>02 / FOLLOW A PATTERN</span><ArrowUpRight/></span><div className="entry-art orbit-art" aria-hidden="true"><i/><i/><i/><i/></div><h3>Explore the problems</h3><p>{count || '24'} focused experiments. Arrays, hash maps, pointers, windows, and more.</p><span className="entry-link">Find your next challenge <ArrowRight size={17}/></span></button>
        <button className="entry-card entry-guide" onClick={onGuide}><span className="entry-top"><Sparkles/><span>03 / GET UNSTUCK</span><ArrowUpRight/></span><div className="entry-art guide-art" aria-hidden="true"><span>what if</span><span>↗</span></div><h3>A guide by your side</h3><p>Ask in your own words. Connect a question to a lesson, a problem, or your next step.</p><span className="entry-link">Talk to the studio guide <ArrowRight size={17}/></span></button>
      </div>
      {error && <div className="landing-error" role="alert">The problem library could not load. <button onClick={onRetry}>Try again</button></div>}
    </section>
    <section className="landing-method" aria-labelledby="method-title"><div><span className="kinetic-overline">THE IDEA IS TO UNDERSTAND</span><h2 id="method-title">A small experiment.<br/><span>A lasting understanding.</span></h2></div><ol>{[['Understand', 'Make sense of the input, the goal, and what you return.'], ['Discover', 'Find a pattern before reaching for a solution.'], ['Experiment', 'Write, change, and replay your actual execution.'], ['Make it yours', 'Explain the why. Carry it into a new problem.']].map(([title, copy], i) => <li key={title}><span>0{i + 1}</span><div><h3>{title}</h3><p>{copy}</p></div></li>)}</ol></section>
  </div>;
}
