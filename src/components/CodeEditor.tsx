import { useEffect, useRef } from 'react';
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api';
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';
import 'monaco-editor/esm/vs/basic-languages/python/python.contribution';
import { useLab } from '../store';

self.MonacoEnvironment = { getWorker: () => new EditorWorker() };
monaco.editor.defineTheme('dsa-studio', {
  base: 'vs-dark', inherit: true,
  rules: [{ token: 'comment', foreground: '8E9DA4', fontStyle: 'italic' }, { token: 'keyword', foreground: 'ACBDD9' }, { token: 'string', foreground: '9AC9B3' }, { token: 'number', foreground: 'DABD94' }, { token: 'identifier', foreground: 'D8DFE2' }],
  colors: { 'editor.background': '#101518', 'editor.foreground': '#D8DFE2', 'editorLineNumber.foreground': '#809098', 'editorLineNumber.activeForeground': '#BED6D3', 'editor.lineHighlightBackground': '#182126', 'editor.selectionBackground': '#334B50', 'editorCursor.foreground': '#ACBDD9', 'editorGutter.background': '#101518', 'editorWidget.background': '#1B252A', 'editorWidget.border': '#3B4D52' },
});

export default function CodeEditor() {
  const host = useRef<HTMLDivElement>(null);
  const editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const decorations = useRef<monaco.editor.IEditorDecorationsCollection | null>(null);
  const { code, source, run, step, runCode, busy } = useLab();
  useEffect(() => {
    if (!host.current) return;
    editor.current = monaco.editor.create(host.current, {
      value: useLab.getState().code, language: 'python', theme: 'dsa-studio', automaticLayout: true,
      fontFamily: '"Cascadia Code", "Consolas", monospace', fontSize: 15, lineHeight: 27,
      minimap: { enabled: false }, scrollBeyondLastLine: false, padding: { top: 23, bottom: 22 },
      lineNumbersMinChars: 3, folding: false, glyphMargin: true, renderLineHighlight: 'line',
      wordWrap: 'on', tabSize: 4, overviewRulerLanes: 0, hideCursorInOverviewRuler: true,
      scrollbar: { verticalScrollbarSize: 5, horizontalScrollbarSize: 5 },
    });
    decorations.current = editor.current.createDecorationsCollection();
    const subscription = editor.current.onDidChangeModelContent(() => {
      const next = editor.current?.getValue() || '';
      if (next !== useLab.getState().code) useLab.getState().setCode(next);
    });
    editor.current.addAction({ id: 'run-trace', label: 'Run and visualize', keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter], run: () => useLab.getState().execute() });
    return () => { subscription.dispose(); editor.current?.getModel()?.dispose(); editor.current?.dispose(); };
  }, []);
  useEffect(() => { if (editor.current && editor.current.getValue() !== code) editor.current.setValue(code); }, [code]);
  useEffect(() => { editor.current?.updateOptions({ readOnly: source !== 'mine' || busy }); }, [source, busy]);
  useEffect(() => {
    const event = run?.events[step];
    if (!event || runCode !== code) { decorations.current?.clear(); return; }
    decorations.current?.set([{ range: new monaco.Range(event.line, 1, event.line, 1), options: { isWholeLine: true, className: event.type === 'ERROR' ? 'trace-line-error' : 'trace-line', glyphMarginClassName: 'trace-glyph' } }]);
    // Keep live feedback from moving the viewport away from the typing cursor.
    if (!run?.preview) editor.current?.revealLineInCenterIfOutsideViewport(event.line);
  }, [run, step, code, runCode]);
  return <div className="monaco-host" ref={host} aria-label="Python code editor" />;
}
