import { useEffect, useMemo, useRef, useState } from 'react';
import type { ClipboardEvent, DragEvent } from 'react';
import { ArrowRight, ArrowUpRight, Camera, Check, CircleAlert, ClipboardPaste, FileSpreadsheet, FlaskConical, Link2, LoaderCircle, Pencil, Plus, Search, Trash2, Upload, Wand2, X } from 'lucide-react';
import { api } from '../api';
import { findProblem, useLab } from '../store';
import type { FetchedProblem, Problem, Sheet, SheetDraft, SheetRow, SourceExample, Stage } from '../types';
import { inTopic } from '../topics';
import Modal from './Modal';
import { host, mainLink, otherLinks, readable } from '../sheetLinks';

type Source = SheetDraft['source'];
type Payload = { sheets: Sheet[]; labs: Problem[] };
type CaseText = { name: string; args: string[]; expected: string; explanation?: string };
const solvedStages: Stage[] = ['Reproduced', 'Explained', 'Modified', 'Independent', 'Transferred'];
const sources: { key: Source; label: string; icon: typeof Upload; hint: string }[] = [
  { key: 'file', label: 'Upload a file', icon: Upload, hint: 'CSV · Excel · TXT · Markdown · JSON' },
  { key: 'link', label: 'Paste a link', icon: Link2, hint: 'Google Sheets · CSV · a web page' },
  { key: 'image', label: 'Photo or screenshot', icon: Camera, hint: 'Read on your device' },
  { key: 'paste', label: 'Paste the list', icon: ClipboardPaste, hint: 'Rows copied from a sheet' },
];
/** What a parameter is: judges write linked lists and trees as lists; the program receives nodes. */
const kindOptions: [string, string][] = [['', 'A value'], ['linkedlist', 'Linked list'], ['dll', 'Doubly linked list'], ['tree', 'Binary tree'], ['linkedlists', 'List of linked lists'], ['cycle', 'Cycle position (pos)']];
const edgeIdeas = ['Empty input', 'One element', 'Duplicates', 'Negatives and zero', 'Already sorted', 'No valid answer'];
/** The lab a row opens: the learner's own lab first, then a built-in match. */
const rowLab = (row: SheetRow) => row.lab ?? row.match;
const show = (value: unknown) => JSON.stringify(value);
function RowLinks({ row }: { row: SheetRow }) {
  const main = mainLink(row);
  return <>{main && <a href={main} target="_blank" rel="noreferrer noopener" title={main}>{host(main)}<ArrowUpRight size={11}/></a>}
    {otherLinks(row).map(link => <a key={link} className="also-link" href={link} target="_blank" rel="noreferrer noopener" title={`Also attached: ${link}`}>also {host(link)}<ArrowUpRight size={10}/></a>)}</>;
}

export default function SheetsPage({ route, onPractice }: { route: string; onPractice: (id: string, sheetId: string) => void }) {
  const { sheets, labs, problems, progress } = useLab();
  const query = new URLSearchParams(route.split('?')[1] || '');
  const [draft, setDraft] = useState<SheetDraft | null>(null);
  const [active, setActive] = useState<string | null>(query.get('sheet'));
  const [building, setBuilding] = useState<number | null>(query.get('edit') !== null ? Number(query.get('edit')) : null);
  const [topic, setTopic] = useState<string | null>(query.get('topic'));  // Arriving from a topic: only its problems.
  const [deleteError, setDeleteError] = useState('');  // Shown here, where the sheet was removed — never later in practice.
  const sheet = sheets.find(s => s.id === active) ?? sheets[0] ?? null;
  useEffect(() => { void useLab.getState().loadSheets(); }, []);
  useEffect(() => { const q = new URLSearchParams(route.split('?')[1] || ''); if (q.get('sheet')) setActive(q.get('sheet')); if (q.get('edit') !== null) setBuilding(Number(q.get('edit'))); setTopic(q.get('topic')); }, [route]);
  useEffect(() => { if (topic && sheet) document.getElementById('my-sheets')?.scrollIntoView({ block: 'start' }); }, [topic, !!sheet]);
  const saved = (payload: Payload & { id: string }) => { useLab.getState().applySheets(payload); setActive(payload.id); setDraft(null); };

  return <div className="sheets-page">
    <section className="sheets-hero" aria-labelledby="sheets-title">
      <div><span className="kinetic-overline">YOUR SHEET · YOUR LAB</span><h1 id="sheets-title">Practice the list <span>you chose.</span></h1>
        <p>Bring the sheet you already follow — a spreadsheet, a link, or a photo of it. Problems the laboratory knows open straight into their lab. For the rest, you build the lab from the problem’s own examples, and every tool here works on it: live tracing, the case deck, wrong turns shown in the visual pane.</p></div>
      <ol className="sheets-steps" aria-label="How a sheet becomes practice">{[['Import', 'File, link or photo'], ['Match', 'Built-in labs found for you'], ['Build', 'Your cases become the lab'], ['Practice', 'Trace every case, live']].map(([title, text], i) => <li key={title}><span>0{i + 1}</span><strong>{title}</strong><small>{text}</small></li>)}</ol>
    </section>

    {draft ? <Review draft={draft} problems={problems} onCancel={() => setDraft(null)} onSaved={saved}/> : <Importer onRead={setDraft}/>}

    {sheets.length > 0 && <section className="sheets-library" aria-labelledby="my-sheets">
      <div className="home-head"><div><span className="kinetic-overline">{sheets.length} SHEET{sheets.length === 1 ? '' : 'S'}</span><h2 id="my-sheets">Your <span>sheets.</span></h2></div></div>
      <div className="sheet-tabs" role="tablist" aria-label="Your sheets">{sheets.map(s => {
        const done = s.rows.filter(r => rowLab(r) && solvedStages.includes(progress[rowLab(r)!])).length;
        return <button key={s.id} role="tab" aria-selected={s.id === sheet?.id} className={s.id === sheet?.id ? 'selected' : ''} onClick={() => { setActive(s.id); setDeleteError(''); }}>
          <FileSpreadsheet size={16}/><span><strong>{s.name}</strong><small>{s.rows.length} problems · {done} solved</small></span><i style={{ ['--done' as string]: `${s.rows.length ? done / s.rows.length * 100 : 0}%` }}/></button>;
      })}</div>
      {deleteError && <p className="field-error" role="alert">Could not remove the sheet: {deleteError}</p>}
      {sheet && <SheetView key={sheet.id} sheet={sheet} labs={labs} problems={problems} progress={progress} onPractice={id => onPractice(id, sheet.id)} onBuild={setBuilding}
        topic={topic} onClearTopic={() => { setTopic(null); window.history.replaceState({}, '', `/sheets?sheet=${sheet.id}`); }}
        onEdit={() => { setDraft({ id: sheet.id, name: sheet.name, source: sheet.source, origin: sheet.origin, rows: sheet.rows }); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
        onDelete={async () => { if (!window.confirm(`Remove “${sheet.name}” and the labs you built for it? Your attempts and progress stay in your history.`)) return; setDeleteError(''); try { useLab.getState().applySheets(await api<Payload>(`/sheets/${sheet.id}`, undefined, 'DELETE')); setActive(null); } catch (e) { setDeleteError(e instanceof Error ? e.message : String(e)); } }}/>}
    </section>}

    {sheet && building !== null && sheet.rows[building] && <LabBuilder key={`${sheet.id}:${building}`} sheet={sheet} index={building} existing={labs.find(l => l.id === sheet.rows[building].lab) ?? null}
      onClose={() => setBuilding(null)} onSaved={id => { setBuilding(null); onPractice(id, sheet.id); }}/>}
  </div>;
}

/** Three ways in: a file, a link, or a picture of the sheet (read in the browser). */
function Importer({ onRead }: { onRead: (draft: SheetDraft) => void }) {
  const [source, setSource] = useState<Source>('file');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [url, setUrl] = useState('');
  const [text, setText] = useState('');
  const [image, setImage] = useState<{ file: File; preview: string } | null>(null);
  const [progress, setProgress] = useState(0);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);
  useEffect(() => () => { if (image) URL.revokeObjectURL(image.preview); }, [image]);
  const read = async (body: FormData | object, label: string) => {
    setBusy(label); setError('');
    try { onRead(await api<SheetDraft>('/sheets/read', body)); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(''); setProgress(0); }
  };
  const pickImage = (file: File) => { setSource('image'); setError(''); setImage({ file, preview: URL.createObjectURL(file) }); };
  const take = (file: File | undefined) => {
    if (!file) return;
    if (file.type.startsWith('image/')) { pickImage(file); return; }
    if (file.size > 3_000_000) { setError('That file is larger than 3 MB. Save just the problem list (CSV works well) and try again.'); return; }
    const form = new FormData(); form.append('file', file);
    void read(form, `Reading ${file.name}…`);
  };
  const drop = (event: DragEvent) => { event.preventDefault(); setDragging(false); take(event.dataTransfer.files[0]); };
  const paste = (event: ClipboardEvent) => { const file = [...event.clipboardData.files].find(f => f.type.startsWith('image/')); if (file) { event.preventDefault(); pickImage(file); } };
  const recognise = async () => {
    if (!image) return;
    setBusy('Starting text recognition…'); setError('');
    try {
      // Recognition runs in this browser: the image is never uploaded, only the text it contains.
      const { createWorker, PSM } = await import('tesseract.js');
      const worker = await createWorker('eng', 1, { logger: (m: { status: string; progress: number }) => { setProgress(m.progress); setBusy(m.status === 'recognizing text' ? 'Reading the text in your image…' : 'Preparing text recognition (first time only)…'); } });
      // Automatic layout analysis: the default single-block mode garbles bordered tables.
      await worker.setParameters({ tessedit_pageseg_mode: PSM.AUTO });
      const { data } = await worker.recognize(image.file);
      await worker.terminate();
      if (!data.text.trim()) throw new Error('No text was found in this image. Try a sharper, closer screenshot.');
      await read({ text: data.text, source: 'image', name: image.file.name.replace(/\.[^.]+$/, '') }, 'Finding problems in the text…');
    } catch (e) { setBusy(''); setProgress(0); setError(e instanceof Error ? e.message : 'Text recognition could not start. Check your connection the first time you use it.'); }
  };

  return <section className="sheet-importer" aria-label="Import a sheet" onPaste={paste}>
    <div className="importer-sources" role="tablist" aria-label="Where your sheet comes from">{sources.map(s => <button key={s.key} role="tab" aria-selected={source === s.key} className={source === s.key ? 'selected' : ''} onClick={() => { setSource(s.key); setError(''); }}><s.icon size={18}/><span><strong>{s.label}</strong><small>{s.hint}</small></span></button>)}</div>
    <div className="importer-body">
      {source === 'file' && <div className={`drop-zone ${dragging ? 'dragging' : ''}`} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={drop}>
        <FileSpreadsheet size={30}/><h2>Drop your sheet here</h2><p>A spreadsheet (.xlsx, .csv), a list (.txt, .md) or .json — one problem per row. Titles and links are enough; every tab of a workbook is read.</p>
        <button className="primary-button" disabled={!!busy} onClick={() => fileInput.current?.click()}><Upload size={15}/>Choose a file</button>
        <input ref={fileInput} type="file" hidden accept=".csv,.tsv,.xlsx,.xlsm,.txt,.md,.markdown,.json,.html,.htm,image/*" onChange={e => { take(e.target.files?.[0]); e.target.value = ''; }}/></div>}
      {source === 'link' && <form className="link-form" onSubmit={e => { e.preventDefault(); if (url.trim()) void read({ url: url.trim() }, 'Opening the link…'); }}>
        <label className="field-label" htmlFor="sheet-link">Link to your sheet</label>
        <div className="link-row"><Link2 size={17}/><input id="sheet-link" type="url" inputMode="url" placeholder="https://docs.google.com/spreadsheets/d/…" value={url} onChange={e => setUrl(e.target.value)}/><button className="primary-button" disabled={!url.trim() || !!busy}>Read the link<ArrowRight size={15}/></button></div>
        <ul className="importer-notes"><li><b>Google Sheets:</b> set Share → General access to “Anyone with the link”. The tab you link is read.</li><li><b>Sheet sites and web pages:</b> pages like Striver’s A2Z sheet on takeuforward.org, and tables or lists of problem links (LeetCode, GeeksforGeeks, Codeforces and more), are read with their sections as topics. A few sites only load their list after you open them — use a screenshot for those.</li><li>Your local laboratory server fetches the link once; nothing else is sent anywhere.</li></ul>
      </form>}
      {source === 'image' && (image ? <div className="image-read">
        <img src={image.preview} alt="Your sheet, to be read"/>
        <div><h2>Read this picture of your sheet</h2><p>Text recognition runs in your browser: the image never leaves this device. The first time, the recognition engine (a few MB) is downloaded.</p>
          <p className="small">Recognised text can contain mistakes. You will check every row before anything is saved.</p>
          <div className="image-actions"><button className="primary-button" disabled={!!busy} onClick={() => void recognise()}><Wand2 size={15}/>Read the problems</button><button className="outline-button" disabled={!!busy} onClick={() => setImage(null)}>Choose another</button></div></div>
      </div> : <div className={`drop-zone ${dragging ? 'dragging' : ''}`} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={drop} tabIndex={0}>
        <Camera size={30}/><h2>Add a photo or screenshot</h2><p>Drop an image, choose one, or press <kbd>Ctrl V</kbd> to paste a screenshot. Straight, well-lit pictures of the problem names read best.</p>
        <button className="primary-button" onClick={() => imageInput.current?.click()}><Camera size={15}/>Choose an image</button>
        <input ref={imageInput} type="file" hidden accept="image/*" onChange={e => { const f = e.target.files?.[0]; if (f) pickImage(f); e.target.value = ''; }}/></div>)}
      {source === 'paste' && <div className="paste-form">
        <label className="field-label" htmlFor="sheet-text">Your list</label>
        <textarea id="sheet-text" rows={8} placeholder={'Copy rows straight from Excel or Google Sheets, or write one problem per line:\n\nTwo Sum - Easy\nhttps://leetcode.com/problems/3sum/\n## Sliding window\n- Longest Substring Without Repeating Characters'} value={text} onChange={e => setText(e.target.value)}/>
        <button className="primary-button" disabled={!text.trim() || !!busy} onClick={() => void read({ text, source: 'paste' }, 'Finding problems…')}>Find the problems<ArrowRight size={15}/></button></div>}
      {busy && <div className="importer-status" role="status"><LoaderCircle className="spin" size={16}/><span>{busy}</span>{progress > 0 && progress < 1 && <i style={{ ['--progress' as string]: `${Math.round(progress * 100)}%` }}/>}</div>}
      {error && <p className="field-error" role="alert">{error}</p>}
    </div>
  </section>;
}

/** Every row is checked before saving: titles, matches and which rows to keep. */
function Review({ draft, problems, onCancel, onSaved }: { draft: SheetDraft; problems: Problem[]; onCancel: () => void; onSaved: (payload: Payload & { id: string }) => void }) {
  const [name, setName] = useState(draft.name);
  const [rows, setRows] = useState(draft.rows.map(row => ({ ...row, keep: true })));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const kept = rows.filter(r => r.keep);
  const counts = { same: kept.filter(r => r.match && r.fit !== 'close').length, close: kept.filter(r => r.fit === 'close').length, build: kept.filter(r => !r.match && !r.lab).length };
  const edit = (i: number, patch: Partial<SheetRow & { keep: boolean }>) => setRows(rows.map((r, j) => j === i ? { ...r, ...patch } : r));
  const save = async () => {
    setBusy(true); setError('');
    try { onSaved(await api<Payload & { id: string }>('/sheets', { ...draft, name, rows: kept.map(({ keep: _keep, ...row }) => row) })); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); setBusy(false); }
  };
  return <section className="sheet-review lesson-card" aria-label="Check your sheet">
    <div className="review-top">
      <div><span className="tiny-label">{draft.id ? 'EDIT YOUR SHEET' : `FOUND ${draft.rows.length} PROBLEM${draft.rows.length === 1 ? '' : 'S'}${draft.source === 'image' ? ' IN YOUR PICTURE' : draft.origin ? ` IN ${draft.source === 'link' ? host(draft.origin).toUpperCase() : draft.origin.toUpperCase()}` : ''}`}</span>
        <label className="sheet-name"><span className="sr-only">Sheet name</span><input value={name} maxLength={80} onChange={e => setName(e.target.value)} aria-label="Sheet name"/><Pencil size={15}/></label></div>
      <div className="review-counts"><span className="count-same"><b>{counts.same}</b> built-in lab{counts.same === 1 ? '' : 's'}</span>{counts.close > 0 && <span className="count-close"><b>{counts.close}</b> close match{counts.close === 1 ? '' : 'es'}</span>}<span className="count-build"><b>{counts.build}</b> to build</span></div>
    </div>
    {rows.length > 3 && <div className="review-bulk" role="group" aria-label="Choose rows to keep"><span className="small">Keep</span><button onClick={() => setRows(rows.map(r => ({ ...r, keep: true })))}>all</button><button onClick={() => setRows(rows.map(r => ({ ...r, keep: false })))}>none</button>{rows.some(r => r.url) && <button onClick={() => setRows(rows.map(r => ({ ...r, keep: !!r.url })))}>rows with links</button>}{rows.some(r => r.match) && <button onClick={() => setRows(rows.map(r => ({ ...r, keep: !!r.match })))}>built-in labs only</button>}</div>}
    <p className="small review-help">{draft.source === 'image' ? 'Read from your picture — fix any misread titles. ' : ''}Untick rows that aren’t problems. A <b>close match</b> opens a built-in lab whose contract differs slightly from the original (for example, it returns a list instead of editing in place) — read its statement, or choose to build your own.</p>
    <div className="review-table" role="table" aria-label="Problems in your sheet">
      <div className="review-row review-head" role="row"><span role="columnheader">Keep</span><span role="columnheader">Problem</span><span role="columnheader">Level · topic</span><span role="columnheader">Practice in</span></div>
      {rows.map((row, i) => <div key={i} role="row" className={`review-row ${row.keep ? '' : 'dropped'}`}>
        <span role="cell"><input type="checkbox" checked={row.keep} aria-label={`Keep ${row.title}`} onChange={e => edit(i, { keep: e.target.checked })}/></span>
        <span role="cell" className="review-title"><input value={row.title} maxLength={160} aria-label={`Title of row ${i + 1}`} onChange={e => edit(i, { title: e.target.value })}/><RowLinks row={row}/></span>
        <span role="cell" className="review-meta">{row.difficulty && <em className={`level-${row.difficulty.toLowerCase()}`}>{row.difficulty}</em>}{row.topic && <small>{row.topic}</small>}</span>
        <span role="cell"><select value={row.match ?? ''} aria-label={`Lab for ${row.title}`} className={row.match ? row.fit === 'close' ? 'is-close' : 'is-matched' : ''} onChange={e => edit(i, { match: e.target.value || null, fit: e.target.value ? 'manual' : null })}>
          <option value="">{row.lab ? 'My own lab' : 'Build my own lab'}</option>
          {problems.map(p => <option key={p.id} value={p.id}>{row.match === p.id && row.fit === 'close' ? 'Close: ' : 'Built-in: '}{p.title}</option>)}</select></span>
      </div>)}
    </div>
    {error && <p className="field-error" role="alert">{error}</p>}
    <div className="modal-actions review-actions"><button className="outline-button" onClick={onCancel}><X size={14}/>Discard</button><button className="primary-button" disabled={!kept.length || !name.trim() || busy} onClick={() => void save()}>{busy ? <LoaderCircle className="spin" size={15}/> : <Check size={15}/>}{draft.id ? 'Save changes' : `Save ${kept.length} problem${kept.length === 1 ? '' : 's'}`}</button></div>
  </section>;
}

function SheetView({ sheet, labs, problems, progress, topic, onPractice, onBuild, onEdit, onDelete, onClearTopic }: { sheet: Sheet; labs: Problem[]; problems: Problem[]; progress: Record<string, Stage>; topic: string | null; onPractice: (id: string) => void; onBuild: (index: number) => void; onEdit: () => void; onDelete: () => void; onClearTopic: () => void }) {
  const [filter, setFilter] = useState<'all' | 'ready' | 'build' | 'solved'>('all');
  const [search, setSearch] = useState('');
  const rows = sheet.rows.map((row, index) => ({ row, index, id: rowLab(row), stage: rowLab(row) ? progress[rowLab(row)!] : undefined }));
  const words = search.toLowerCase().split(/\s+/).filter(Boolean);
  const inView = topic ? rows.filter(r => inTopic(topic, r.row.topic, r.row.title)) : rows;
  const visible = inView.filter(r => (filter === 'all' || (filter === 'ready' ? !!r.id : filter === 'build' ? !r.id : !!r.stage && solvedStages.includes(r.stage)))
    && words.every(w => `${r.row.title} ${r.row.topic} ${r.row.difficulty}`.toLowerCase().includes(w)));
  const groups = useMemo(() => visible.reduce<{ topic: string; items: typeof visible }[]>((list, item) => {
    const topic = item.row.topic || '';
    if (list.length && list[list.length - 1].topic === topic) list[list.length - 1].items.push(item); else list.push({ topic, items: [item] });
    return list;
  }, []), [visible]);
  const ready = rows.filter(r => r.id).length, solved = rows.filter(r => r.stage && solvedStages.includes(r.stage)).length;
  const next = rows.find(r => r.id && !(r.stage && solvedStages.includes(r.stage)));
  return <div className="sheet-view">
    <div className="sheet-summary">
      {sheet.source === 'link' && /^https?:/.test(sheet.origin) && <a className="sheet-origin" href={sheet.origin} target="_blank" rel="noreferrer noopener"><FileSpreadsheet size={13}/>Tracking the sheet from <b>{host(sheet.origin)}</b> · open the original<ArrowUpRight size={11}/></a>}
      <div className="sheet-meter" role="img" style={{ ['--ready' as string]: `${ready / rows.length * 100}%`, ['--solved' as string]: `${solved / rows.length * 100}%` }} aria-label={`${solved} solved, ${ready} ready of ${rows.length}`}><span/><span/></div>
      <dl><div><dt>Problems</dt><dd>{rows.length}</dd></div><div><dt>Ready to practice</dt><dd>{ready}</dd></div><div><dt>Need your lab</dt><dd>{rows.length - ready}</dd></div><div><dt>Solved</dt><dd>{solved}</dd></div></dl>
      <div className="sheet-actions">{next && <button className="primary-button" onClick={() => onPractice(next.id!)}>Continue · {next.row.title}<ArrowRight size={15}/></button>}<button className="outline-button" onClick={onEdit}><Pencil size={14}/>Edit rows</button><button className="icon-button" aria-label={`Remove ${sheet.name}`} title="Remove this sheet" onClick={onDelete}><Trash2 size={16}/></button></div>
    </div>
    <div className="sheet-filter-bar"><div className="sheet-filters" role="radiogroup" aria-label="Show problems">{([['all', 'All'], ['ready', 'Ready to practice'], ['build', 'Need your lab'], ['solved', 'Solved']] as const).map(([key, label]) => <button key={key} role="radio" aria-checked={filter === key} className={filter === key ? 'selected' : ''} onClick={() => setFilter(key)}>{label}</button>)}</div>
      {topic && <button className="topic-filter" onClick={onClearTopic} aria-label={`Showing ${topic} only. Show every problem`}>{topic} · {inView.length}<X size={12}/></button>}
      {rows.length > 20 && <label className="sheet-search"><Search size={14}/><input type="search" placeholder={`Find in ${rows.length} problems or topics…`} aria-label="Find a problem in this sheet" value={search} onChange={e => setSearch(e.target.value)}/>{search && <span>{visible.length}</span>}</label>}</div>
    <div className="sheet-rows">{groups.map((group, g) => <div key={g} className="sheet-group">
      {group.topic && <h3 className="sheet-topic">{group.topic}</h3>}
      {group.items.map(({ row, index, id, stage }) => {
        const builtIn = row.match && !row.lab ? problems.find(p => p.id === row.match) : undefined;
        const own = row.lab ? labs.find(l => l.id === row.lab) : undefined;
        return <div key={index} className={`sheet-row ${id ? 'has-lab' : 'needs-lab'} ${stage && solvedStages.includes(stage) ? 'is-solved' : ''}`}>
          <span className="sheet-index">{String(index + 1).padStart(2, '0')}</span>
          <div className="sheet-problem"><strong>{row.title}</strong><span>{row.difficulty && <em className={`level-${row.difficulty.toLowerCase()}`}>{row.difficulty}</em>}<RowLinks row={row}/></span></div>
          <div className="sheet-lab">{own ? <span className="lab-own"><FlaskConical size={13}/>Your lab · {own.cases?.length ?? 0} case{own.cases?.length === 1 ? '' : 's'}</span>
            : builtIn ? <span className={row.fit === 'close' ? 'lab-close' : 'lab-builtin'} title={row.fit === 'close' ? 'A close relative: the built-in contract differs slightly. Read its statement.' : undefined}><Check size={13}/>{row.fit === 'close' ? 'Close' : 'Built-in'} · {builtIn.title}</span>
            : <span className="lab-none">No lab yet</span>}</div>
          <span className="sheet-stage">{stage || (id ? 'Not started' : '—')}</span>
          <div className="sheet-go">{id ? <button className="text-button" onClick={() => onPractice(id)}>Practice<ArrowRight size={14}/></button> : <button className="build-button" onClick={() => onBuild(index)}><Plus size={14}/>Build the lab</button>}
            {own && <button className="icon-button" aria-label={`Edit the lab for ${row.title}`} title="Edit your lab" onClick={() => onBuild(index)}><Pencil size={14}/></button>}</div>
        </div>;
      })}
    </div>)}{!visible.length && <p className="empty-library">{search ? `No problem in this sheet matches “${search}”.` : topic ? `No ${topic.toLowerCase()} problems in this sheet.` : 'Nothing here yet.'}</p>}</div>
  </div>;
}

/** What was read from the problem's page, as the page structures it: sections, constraints, and every example
 * word for word with whether it became a case. Nothing here is inferred. */
function SourceRead({ read }: { read: FetchedProblem }) {
  const marks: Record<SourceExample['status'], string> = { parsed: 'read as a case', partial: 'output needs you', unparsed: 'not read: enter by hand', duplicate: 'duplicate, skipped' };
  return <details className="source-read" open={read.examples.some(e => e.status !== 'parsed')}>
    <summary>From the page: {[read.description && 'statement', read.sections.length && `${read.sections.length} section${read.sections.length === 1 ? '' : 's'} (${read.sections.map(s => s.heading).join(', ')})`,
      read.constraints.length && `${read.constraints.length} constraint${read.constraints.length === 1 ? '' : 's'}`, `${read.examples.length} example${read.examples.length === 1 ? '' : 's'}`].filter(Boolean).join(' · ')}</summary>
    <div className="source-examples">{read.examples.map(e => <div key={e.name} className={`source-example is-${e.status}`}>
      <div><b>{e.name}</b><span>{marks[e.status]}</span></div>
      {e.input && <pre><b>Input:</b> {e.input}</pre>}{e.output && <pre><b>Output:</b> {e.output}</pre>}{e.explanation && <pre><b>Explanation:</b> {e.explanation}</pre>}
      {e.issue && <p>{e.issue}</p>}
    </div>)}</div>
  </details>;
}

/** The learner defines the lab: the statement, the parameters and cases with expected outputs.
 * Pasting the problem's own examples fills them in; nothing is invented. */
function LabBuilder({ sheet, index, existing, onClose, onSaved }: { sheet: Sheet; index: number; existing: Problem | null; onClose: () => void; onSaved: (id: string) => void }) {
  const row = sheet.rows[index];
  const [title, setTitle] = useState(existing?.title ?? row.title);
  const [statement, setStatement] = useState(existing?.statement ?? '');
  const [params, setParams] = useState(existing?.params.join(', ') ?? '');
  const [returns, setReturns] = useState(existing?.returnsNote ?? '');
  const [anyOrder, setAnyOrder] = useState(existing?.order === 'any');
  const [kinds, setKinds] = useState<Record<string, string>>(existing?.kinds ?? {});
  const [entry, setEntry] = useState(existing?.entry ?? 'solve');
  const [answer, setAnswer] = useState<string>(existing?.answer ?? '');
  const [methods, setMethods] = useState<Record<string, string[]>>(existing?.methods ?? {});
  const design = entry !== 'solve';
  const [cases, setCases] = useState<CaseText[]>(existing?.cases?.map(c => ({ name: c.name, args: c.args.map(show), expected: show(c.expected) })) ?? [{ name: 'Example 1', args: [], expected: '' }]);
  const [examples, setExamples] = useState('');
  const [readings, setReadings] = useState<string[]>([]);  // How pasted examples were read beyond their notation.
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [fetched, setFetched] = useState<{ status: 'idle' | 'loading' | 'done' | 'error'; message?: string; notes?: string[]; source?: string; read?: FetchedProblem }>({ status: 'idle' });
  const [otherLink, setOtherLink] = useState('');
  const [filledFrom, setFilledFrom] = useState(existing?.sourceUrl || '');  // The page the fields were last read from.
  const names = params.split(',').map(p => p.trim()).filter(Boolean);
  const pageLink = mainLink(row);
  // The problem's own page fills the lab in; the learner checks it before building. Nothing missing is invented.
  const fetchProblem = async (url?: string) => {
    setFetched({ status: 'loading', source: url }); setError('');
    try {
      const data = await api<FetchedProblem>('/labs/fetch', { sheetId: sheet.id, row: index, ...(url ? { url } : {}) });
      if (data.title) setTitle(data.title);
      if (data.statement) setStatement(data.statement);
      if (data.params.length) setParams(data.params.join(', '));
      setKinds(data.kinds || {}); setEntry(data.entry || 'solve'); setMethods(data.methods || {}); setAnswer(data.answer || '');
      if (data.cases.length) setCases(data.cases.slice(0, 8).map(c => ({ name: c.name, args: c.args.map(show), expected: c.missing ? '' : show(c.expected), explanation: c.explanation || '' })));
      setFetched({ status: 'done', notes: data.notes, source: data.source || url || pageLink, read: data });
      setFilledFrom(data.source || url || pageLink);
    } catch (e) { setFetched({ status: 'error', message: e instanceof Error ? e.message : String(e), source: url || pageLink }); }
  };
  useEffect(() => { if (!existing && readable(row)) void fetchProblem(); }, []);  // Once, when a new lab opens.
  const sized = (c: CaseText) => ({ ...c, args: names.map((_, i) => c.args[i] ?? '') });
  const setCase = (i: number, patch: Partial<CaseText>) => setCases(cases.map((c, j) => j === i ? { ...sized(c), ...patch } : c));
  const readExamples = async () => {
    setBusy('examples'); setError(''); setReadings([]);
    try {
      const data = await api<{ params: string[]; cases: { name: string; args: unknown[]; expected: unknown }[]; kinds: Record<string, string>; entry: string; notes?: string[] }>('/labs/examples', { text: examples });
      setReadings(data.notes || []);
      setParams(data.params.join(', '));
      setKinds({ ...kinds, ...data.kinds }); setEntry(data.entry || 'solve');
      const blank = cases.every(c => !c.expected.trim() && c.args.every(a => !a.trim()));
      setCases([...(blank ? [] : cases), ...data.cases.map(c => ({ name: c.name, args: c.args.map(show), expected: show(c.expected) }))].slice(0, 8));
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(''); }
  };
  const save = async () => {
    setBusy('save'); setError('');
    try {
      const data = await api<Payload & { lab: Problem }>('/labs', { sheetId: sheet.id, row: index, title, statement, params: names, returns, order: anyOrder ? 'any' : 'exact', difficulty: row.difficulty, topic: row.topic, cases: cases.map(sized),
        kinds: Object.fromEntries(Object.entries(kinds).filter(([name, kind]) => kind && names.includes(name))), entry, methods, source: filledFrom || undefined, answer: answer || undefined });
      useLab.getState().applySheets(data);
      onSaved(data.lab.id);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); setBusy(''); }
  };
  const builtIn = row.match ? findProblem(useLab.getState(), row.match) : undefined;
  return <Modal title={existing ? `Edit your lab · ${row.title}` : `Build the lab · ${row.title}`} onClose={onClose} wide className="builder-modal">
    <p className="modal-intro">Your cases are this lab’s answer key: it runs your code on each one and shows whether it reaches the output you expect. It can’t check that your expected outputs are right — take them from the problem’s own examples.</p>
    {fetched.status === 'loading' ? <div className="fetch-status is-loading" role="status"><LoaderCircle className="spin" size={16}/><p>Reading the problem from <b>{host(fetched.source || pageLink)}</b>…</p></div>
      : fetched.status === 'done' ? <div className="fetch-status is-done" role="status"><Check size={16}/><div><p>Filled in from <a href={fetched.source} target="_blank" rel="noreferrer noopener">{host(fetched.source || pageLink)}<ArrowUpRight size={11}/></a>. Check the statement and cases against the original before you build.</p>{!!fetched.notes?.length && <ul>{fetched.notes.map(note => <li key={note}>{note}</li>)}</ul>}</div></div>
      : fetched.status === 'error' ? <div className="fetch-status is-error" role="alert"><CircleAlert size={16}/><div><p>{fetched.message}</p>{(fetched.source || pageLink) && <a href={fetched.source || pageLink} target="_blank" rel="noreferrer noopener">Open the problem on {host(fetched.source || pageLink)}<ArrowUpRight size={11}/></a>}</div></div>
      : pageLink && <div className="fetch-status"><ArrowUpRight size={16}/><div><p>This problem lives on <a href={pageLink} target="_blank" rel="noreferrer noopener">{host(pageLink)}</a>.</p>{readable(row) && <button className="text-button" onClick={() => { if (!existing || window.confirm('Replace the statement and cases with the ones on the problem’s page?')) void fetchProblem(); }}><Wand2 size={13}/>Fill in from {host(pageLink)}</button>}</div></div>}
    {fetched.status === 'done' && fetched.read && <SourceRead read={fetched.read}/>}
    <form className="other-link" onSubmit={e => { e.preventDefault(); if (otherLink.trim() && (!existing || window.confirm('Replace the statement and cases with the ones on that page?'))) void fetchProblem(otherLink.trim()); }}>
      <Link2 size={14}/><input type="url" inputMode="url" placeholder="Read the problem from another link (https://…)" aria-label="Read the problem from a link" value={otherLink} onChange={e => setOtherLink(e.target.value)}/>
      <button className="text-button" disabled={!otherLink.trim() || fetched.status === 'loading'}>Read this link<ArrowRight size={13}/></button>
    </form>
    {builtIn && <p className="gentle-note">This row also opens the built-in lab <b>{builtIn.title}</b>. Building your own lab replaces it for this row.</p>}
    <div className="builder-grid">
      <section className="builder-examples"><span className="tiny-label">{readable(row) ? 'OR PASTE THE EXAMPLES' : 'FASTEST · PASTE THE EXAMPLES'}</span>
        <textarea rows={7} value={examples} onChange={e => setExamples(e.target.value)} placeholder={'Input: nums = [2,7,11,15], target = 9\nOutput: [0,1]\n\nInput: nums = [3,2,4], target = 6\nOutput: [1,2]'} aria-label="Paste the problem's examples"/>
        <button className="outline-button" disabled={!examples.trim() || !!busy} onClick={() => void readExamples()}>{busy === 'examples' ? <LoaderCircle className="spin" size={14}/> : <Wand2 size={14}/>}Read the examples</button>
        <p className="small">Fills in the parameters and one case per “Input: … Output: …” pair. Check them below.</p>{readings.length > 0 && <ul className="small reading-notes" aria-label="How the examples were read">{readings.map(note => <li key={note}>{note}</li>)}</ul>}</section>
      <section className="builder-fields">
        <label className="journey-field"><span>Title</span><input className="builder-input" value={title} maxLength={160} onChange={e => setTitle(e.target.value)}/></label>
        <label className="journey-field"><span>The problem, in full</span><textarea rows={7} maxLength={12000} value={statement} onChange={e => setStatement(e.target.value)} placeholder="Paste or write the problem statement, including its rules and constraints."/></label>
        {design && <div className="design-note"><b>Design problem · class <code>{entry}</code></b><span>Each case creates {entry}, then calls {[...new Set(cases.flatMap(c => { try { const ops = JSON.parse(sized(c).args[0] || '[]'); return Array.isArray(ops) ? ops.slice(1) : []; } catch { return []; } }))].slice(0, 8).map(op => `${op}(${(methods[op] || []).join(', ')})`).join(', ') || 'its methods'} in order and compares every answer.</span>
          <button className="text-button" onClick={() => setEntry('solve')}>Treat as a function instead</button></div>}
        <div className="builder-pair"><label className="journey-field"><span>{design ? 'Inputs' : <>Parameters of <code>solve</code></>}</span><input className="builder-input mono" value={params} onChange={e => setParams(e.target.value)} placeholder="nums, target"/></label>
          <label className="journey-field"><span>What it returns <small>(optional)</small></span><input className="builder-input" value={returns} maxLength={400} onChange={e => setReturns(e.target.value)} placeholder={entry !== 'solve' ? 'e.g. what each method returns' : Object.values(kinds).some(k => k === 'linkedlist' || k === 'dll') ? 'e.g. the head of the changed list' : Object.values(kinds).includes('tree') ? 'e.g. the root of the tree' : 'e.g. a number, a list, or True / False'}/></label></div>
        {!design && names.length > 0 && <div className="kind-row" aria-label="What each parameter is">{names.map(name => <label key={name}><code>{name}</code>
          <select value={kinds[name] || ''} onChange={e => setKinds({ ...kinds, [name]: e.target.value })}>{kindOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>)}
          <span className="small">Lists you mark as a linked list or a tree reach your code as nodes, and are drawn as nodes.</span></div>}
        <label className="builder-check"><input type="checkbox" checked={anyOrder} onChange={e => setAnyOrder(e.target.checked)}/>The order of returned items doesn’t matter (“return in any order”)</label>
        <label className="builder-compare">Compare with each expected output
          <select value={answer} onChange={e => setAnswer(e.target.value)}><option value="">what solve returns</option><option value="node-value">the value of the node solve returns</option><option value="lines">the printed lines (trailing spaces ignored)</option></select></label>
      </section>
    </div>
    <section className="builder-cases" aria-label="Your cases"><div className="builder-cases-head"><span className="tiny-label">YOUR CASES · {cases.length}/8</span><span className="small">Write values as Python or JSON: <code>[2, 7]</code> <code>"abc"</code> <code>9</code> <code>True</code></span></div>
      <div className="case-table">{cases.map((c, i) => <div key={i} className="case-line">
        <input className="case-name" value={c.name} maxLength={40} aria-label={`Name of case ${i + 1}`} onChange={e => setCase(i, { name: e.target.value })}/>
        <div className="case-inputs">{names.length ? names.map((name, j) => <label key={name + j}><code>{name}</code><input className="mono" value={sized(c).args[j]} onChange={e => { const args = sized(c).args; args[j] = e.target.value; setCase(i, { args }); }} placeholder="value"/></label>) : <span className="small">Name the parameters first.</span>}</div>
        <label className="case-expected"><code>→</code><input className={`mono ${fetched.status === 'done' && !c.expected.trim() ? 'needs-value' : ''}`} value={c.expected} onChange={e => setCase(i, { expected: e.target.value })} placeholder={fetched.status === 'done' && !c.expected.trim() ? 'needs a value' : 'expected output'} aria-label={`Expected output of case ${i + 1}`}/></label>
        <button className="icon-button" aria-label={`Remove case ${i + 1}`} disabled={cases.length === 1} onClick={() => setCases(cases.filter((_, j) => j !== i))}><X size={15}/></button>
        {c.explanation && <p className="case-explanation"><b>From the page:</b> {c.explanation}</p>}
      </div>)}</div>
      {cases.length < 8 && <div className="edge-ideas"><span className="small">Add an edge case you can think of:</span>{edgeIdeas.filter(idea => !cases.some(c => c.name === idea)).map(idea => <button key={idea} onClick={() => setCases([...cases, { name: idea, args: names.map(() => ''), expected: '' }])}><Plus size={12}/>{idea}</button>)}<button onClick={() => setCases([...cases, { name: `Case ${cases.length + 1}`, args: names.map(() => ''), expected: '' }])}><Plus size={12}/>Another case</button></div>}
    </section>
    {error && <p className="field-error" role="alert">{error}</p>}
    <div className="modal-actions"><button className="outline-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={!!busy || !title.trim() || !names.length} onClick={() => void save()}>{busy === 'save' ? <LoaderCircle className="spin" size={15}/> : <FlaskConical size={15}/>}{existing ? 'Save and practice' : 'Build and practice'}<ArrowRight size={14}/></button></div>
  </Modal>;
}
