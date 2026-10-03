import { ArrowRight, FileSpreadsheet, FlaskConical } from 'lucide-react';
import { inTopic, topicNamed } from '../topics';
import type { Problem, Sheet, Stage } from '../types';

/** A topic in the library, beyond its built-in labs: the labs the learner built for it from their own sheets,
 * and their sheets' problems on it, opened filtered to the topic. */
export default function SheetTopic({ topic, search, sheets, labs, progress, onPractice, onSheet }: {
  topic: string; search: string; sheets: Sheet[]; labs: Problem[]; progress: Record<string, Stage>;
  onPractice: (id: string, sheetId: string) => void; onSheet: (sheetId: string) => void;
}) {
  const t = topicNamed(topic);
  if (!t) return null;
  const query = search.toLowerCase();
  const own = labs.filter(l => inTopic(t.name, l.category ?? '', l.title) && `${l.title} ${l.category ?? ''}`.toLowerCase().includes(query));
  const bySheet = sheets.map(sheet => ({ sheet, rows: sheet.rows.filter(r => inTopic(t.name, r.topic, r.title)) }))
    .filter(x => x.rows.length).sort((a, b) => b.rows.length - a.rows.length);
  return <>
    {own.length > 0 && <h3 className="library-group">Your labs from your sheets</h3>}
    {own.map(l => <button key={l.id} onClick={() => onPractice(l.id, l.sheetId!)}>
      <span className="library-number"><FlaskConical size={14}/></span>
      <div><strong>{l.title}</strong><span>{l.sheetName} · {progress[l.id] || 'Ready to explore'}</span></div>
      <span className="difficulty own">Your lab</span><ArrowRight size={16}/></button>)}
    {bySheet.length > 0 && <div className="topic-sheets">
      <p>More {t.name.toLowerCase()} practice is in your sheets: build a lab from any of their problems, and your code is drawn as <b>{t.drawn}</b>.</p>
      <div className="topic-sheets-links">{bySheet.slice(0, 3).map(({ sheet, rows }) => {
        const ready = rows.filter(r => r.lab ?? r.match).length;
        return <button key={sheet.id} className="outline-button" onClick={() => onSheet(sheet.id)}><FileSpreadsheet size={15}/>
          <span><strong>{sheet.name}</strong><small>{rows.length} {t.short} problem{rows.length === 1 ? '' : 's'} · {ready ? `${ready} ready to practice` : 'build a lab from any of them'}</small></span><ArrowRight size={15}/></button>;
      })}</div>
    </div>}
  </>;
}
