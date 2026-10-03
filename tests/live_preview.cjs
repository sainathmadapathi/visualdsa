// Exercise the real store with controlled request timing, without touching learner data.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function harness() {
  const pending = [];
  const storage = new Map();
  const exports = {};
  const js = ts.transpileModule(fs.readFileSync('src/store.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  vm.runInNewContext(js, {
    exports, structuredClone,
    localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) },
    require: name => name === 'zustand' ? require('zustand') : name === './firebase' ? { auth: null, syncLearning: async () => {} } : name === './motion' ? { initialMotion: () => 'full', applyMotion: () => {} } : { api: (path, body) => new Promise((resolve, reject) => pending.push({ path, body, resolve, reject })) },
  });
  const store = exports.useLab;
  store.setState({ tab: 'code', problem: { id: 'two-sum' }, code: 'def solve(nums, target):\n    return [0, 1]', args: [[2, 7], 9] });
  return { store, pending };
}
const result = () => ({ preview: true, events: [{ id: 0 }], error: null, tests: [], result: [0, 1], attemptId: '', passed: false });

test('live preview keeps editing enabled and never records progress', async () => {
  const { store, pending } = harness();
  const work = store.getState().preview();
  assert.equal(store.getState().busy, false);
  assert.equal(store.getState().previewBusy, true);
  assert.equal(pending[0].path, '/preview');
  pending[0].resolve(result()); await work;
  assert.equal(store.getState().run.preview, true);
  assert.equal(store.getState().playing, false);  // Live traces stay anchored to the code; explicit runs play.
  assert.equal(pending.length, 1);
});
test('a trace that arrives while typing continues is kept, labelled with the code it ran', async () => {
  const { store, pending } = harness();
  const original = store.getState().code;
  const work = store.getState().preview();
  store.getState().setCode(original + '    # still typing');
  pending[0].resolve(result()); await work;
  assert.equal(store.getState().run.preview, true);
  assert.equal(store.getState().runCode, original);  // The version that actually ran...
  assert.notEqual(store.getState().runCode, store.getState().code);  // ...so the interface knows it is behind.
  assert.equal(store.getState().previewBusy, false);
});
test('input changes and disabling live invalidate pending previews', async () => {
  for (const change of [s => s.setArgs([[3, 3], 6]), s => s.toggleLive()]) {
    const { store, pending } = harness();
    const work = store.getState().preview(); change(store.getState());
    pending[0].resolve(result()); await work;
    assert.equal(store.getState().run, null);
  }
});
test('only one preview is issued at a time; incomplete code is quiet feedback', async () => {
  const { store, pending } = harness();
  const work = store.getState().preview();
  await store.getState().preview();
  assert.equal(pending.length, 1);
  pending[0].reject(new Error('Incomplete function')); await work;
  assert.equal(store.getState().error, '');
  assert.match(store.getState().previewMessage, /Waiting for runnable code/);
});
test('a late preview cannot replace an explicit full test run', async () => {
  const { store, pending } = harness();
  const preview = store.getState().preview();
  const full = store.getState().execute();
  pending[1].resolve({ ...result(), preview: false, attemptId: 'verified' }); await full;
  pending[0].resolve(result()); await preview;
  assert.equal(store.getState().run.attemptId, 'verified');
});

test('only the code stage can start a live preview', async () => {
  const { store, pending } = harness();
  for (const tab of ['understand', 'discover', 'reflect']) {
    store.getState().setTab(tab);
    await store.getState().preview();
  }
  assert.equal(pending.length, 0);
});

test('leaving code invalidates pending preview even after returning immediately', async () => {
  const { store, pending } = harness();
  const original = store.getState().code;
  const work = store.getState().preview();
  store.getState().setTab('reflect');
  store.getState().setTab('code');
  pending[0].resolve(result()); await work;
  assert.equal(store.getState().run, null);
  assert.equal(store.getState().code, original);
  assert.equal(store.getState().playing, false);
});

test('stage navigation keeps completed evidence and pauses playback', () => {
  const { store } = harness();
  const run = result();
  store.setState({ run, runCode: store.getState().code, step: 1, playing: true });
  for (const tab of ['reflect', 'understand', 'discover', 'code']) store.getState().setTab(tab);
  assert.equal(store.getState().run, run);
  assert.equal(store.getState().step, 1);
  assert.equal(store.getState().playing, false);
});

test('explicit tests can finish during reflection without starting hidden playback', async () => {
  const { store, pending } = harness();
  const work = store.getState().execute();
  store.getState().setTab('reflect');
  pending[0].resolve({ ...result(), preview: false, attemptId: 'reflection-evidence' }); await work;
  assert.equal(store.getState().run.attemptId, 'reflection-evidence');
  assert.equal(store.getState().playing, false);
});

// ------------------------------------------------------------------ Learning loop
const modified = { id: 'two-sum-modified', title: 'Count every pair', statement: 'Count pairs.', returns: 'Return an integer count.', question: 'Is one index enough?', hints: ['q', 'clue'], example: { args: [[3, 3, 3], 6], expected: 3 } };
const twoSum = { id: 'two-sum', title: 'Two Sum', params: ['nums', 'target'], hints: ['h1', 'h2'], starter: 'def solve(nums, target):\n    pass', example: { args: [[2, 7], 9], expected: [0, 1] }, modification: modified };
function loopHarness() {
  const h = harness();
  h.store.setState({ problems: [twoSum], problem: twoSum, mode: 'solve', entry: 'open' });
  return h;
}

test('trace this input runs the exact failing input through the normal execution path', async () => {
  const { store, pending } = loopHarness();
  const failing = [[3, 3], 6];
  const work = store.getState().traceInput(failing);
  assert.deepEqual(store.getState().args, failing);
  assert.equal(pending[0].path, '/execute');
  assert.equal(JSON.stringify(pending[0].body), JSON.stringify({ problemId: 'two-sum', code: store.getState().code, args: failing, test: true }));
  pending[0].resolve({ ...result(), preview: false, passed: false, attemptId: 'traced', tests: [{ name: 'Repeated values', passed: false }] }); await work;
  assert.equal(store.getState().run.attemptId, 'traced');
  assert.equal(pending.length, 1);  // A failing run records no progress.
});

test('adapting runs the changed requirement with its own draft and returns cleanly', async () => {
  const { store, pending } = loopHarness();
  const original = store.getState().code;
  store.getState().startModify();
  assert.equal(store.getState().mode, 'modify');
  assert.equal(store.getState().tab, 'code');
  assert.equal(store.getState().code, original);  // Adaptation starts from the learner's own solution.
  assert.deepEqual(store.getState().args, modified.example.args);
  store.getState().setCode('def solve(nums, target):\n    return 3');
  const work = store.getState().preview();
  assert.equal(pending[0].body.problemId, 'two-sum-modified');
  store.getState().endModify();
  pending[0].resolve(result()); await work;
  assert.equal(store.getState().run, null);  // A late adaptation trace never lands on the original.
  assert.equal(store.getState().code, original);
  assert.deepEqual(store.getState().args, twoSum.example.args);
  store.getState().startModify();
  assert.equal(store.getState().code, 'def solve(nums, target):\n    return 3');  // The adaptation draft is kept.
});

test('passing the changed requirement records Modified with the learner\'s own reasoning', async () => {
  const { store, pending } = loopHarness();
  store.getState().startModify();
  const work = store.getState().execute();
  assert.equal(pending[0].body.problemId, 'two-sum-modified');
  pending[0].resolve({ ...result(), preview: false, passed: true, attemptId: 'adapted', tests: [{ passed: true }] });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(pending[1].path, '/progress');
  assert.equal(pending[1].body.stage, 'Modified');
  assert.equal(pending[1].body.problemId, 'two-sum');
  assert.equal(pending[1].body.attemptId, 'adapted');
  pending[1].resolve({ stage: 'Modified', insight: 'Counts replace positions.', transferred: [] });
  await new Promise(resolve => setImmediate(resolve));
  pending[2]?.resolve({ saved: [], progress: [], bookmarks: [], support: [], evidence: [] });
  await work;
  assert.match(store.getState().notice, /Adaptation recorded/);
});

test('opening a problem from its topic is remembered as guided context', () => {
  const { store } = loopHarness();
  store.getState().select('two-sum', 'topic');
  assert.equal(store.getState().entry, 'topic');
  store.getState().select('two-sum', 'open');
  assert.equal(store.getState().entry, 'topic');  // Knowing the technique cannot be undone by reopening.
});

test('a live trace opens on the line being typed, or the nearest line above that ran', async () => {
  const lines = [{ id: 0, line: 1 }, { id: 1, line: 2 }, { id: 2, line: 3 }, { id: 3, line: 2 }, { id: 4, line: 6 }];
  for (const [cursor, expected] of [[3, 2], [5, 2], [6, 4], [null, 0], [1, 0]]) {
    const { store, pending } = harness();
    store.setState({ cursorLine: cursor });
    const work = store.getState().preview();
    pending[0].resolve({ ...result(), events: lines }); await work;
    assert.equal(store.getState().step, expected, `cursor on line ${cursor}`);
  }
});

test('an explicit run still plays from the first step', async () => {
  const { store, pending } = harness();
  store.setState({ cursorLine: 2 });
  const work = store.getState().execute();
  pending[0].resolve({ ...result(), preview: false, events: [{ id: 0, line: 1 }, { id: 1, line: 2 }], tests: [{ passed: false }] }); await work;
  assert.equal(store.getState().step, 0);
  assert.equal(store.getState().playing, true);
});

// ------------------------------------------------------------------ Case deck
const deck = () => {
  const ev = (n, line) => Array.from({ length: n }, (_, i) => ({ id: i, line: line + i }));
  const cases = [
    { id: 'case-0', name: 'Example', input: [[2, 7], 9], events: ev(3, 1), goal: { expected: [0, 1], matches: true }, traceId: 't0' },
    { id: 'case-1', name: 'Repeated values', input: [[3, 3], 6], events: ev(2, 1), goal: { expected: [0, 1], matches: false }, traceId: 't1' },
    { id: 'case-2', name: 'Empty', input: [[], 1], events: ev(4, 1), goal: { expected: [], matches: true }, traceId: 't2' },
  ];
  return { ...result(), events: cases[0].events, cases, caseId: 'case-0', traceId: 't0', input: cases[0].input };
};

test('a live update keeps the case being watched', async () => {
  const { store, pending } = harness();
  let work = store.getState().preview();
  pending[0].resolve(deck()); await work;
  store.getState().selectCase('case-1');
  assert.equal(store.getState().run.traceId, 't1');
  store.getState().setCode(store.getState().code + ' ');
  work = store.getState().preview();
  pending[1].resolve(deck()); await work;
  assert.equal(store.getState().run.caseId, 'case-1');
  assert.equal(store.getState().run.attemptId, '');  // Only the main case can carry an attempt.
});

test('choosing a case plays it from the start; a tour walks every case', async () => {
  const { store, pending } = harness();
  const work = store.getState().preview();
  pending[0].resolve(deck()); await work;
  store.getState().selectCase('case-2', true);
  assert.equal(store.getState().step, 0);
  assert.equal(store.getState().playing, true);
  store.getState().playCases();
  assert.equal(store.getState().run.traceId, 't0');
  assert.equal(store.getState().tour, true);
  assert.equal(store.getState().nextCase(), true);
  assert.equal(store.getState().run.traceId, 't1');
  assert.equal(store.getState().nextCase(), true);
  assert.equal(store.getState().nextCase(), false);  // The last case ends the tour.
  assert.equal(store.getState().tour, false);
  assert.equal(store.getState().playing, false);
});

test('trace this input plays an already traced case without a new run', async () => {
  const { store, pending } = harness();
  const work = store.getState().preview();
  pending[0].resolve(deck()); await work;
  store.setState({ runCode: store.getState().code });
  await store.getState().traceInput([[3, 3], 6]);
  assert.equal(pending.length, 1);
  assert.equal(store.getState().run.traceId, 't1');
  assert.equal(store.getState().playing, true);
});

test('playback starts at the speed its 1x option names', () => {
  const { store } = harness();
  // The speed menu's options, read from the component itself.
  const options = [...fs.readFileSync('src/components/Playback.tsx', 'utf8').matchAll(/<option value="(\d+)">([^<]+)<\/option>/g)].map(m => [Number(m[1]), m[2]]);
  assert.deepEqual(options.find(([value]) => value === store.getState().speed)?.[1], '1×');
});
