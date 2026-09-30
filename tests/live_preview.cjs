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
    require: name => name === 'zustand' ? require('zustand') : name === './firebase' ? { auth: null, syncLearning: async () => {} } : { api: (path, body) => new Promise((resolve, reject) => pending.push({ path, body, resolve, reject })) },
  });
  const store = exports.useLab;
  store.setState({ problem: { id: 'two-sum' }, code: 'def solve(nums, target):\n    return [0, 1]', args: [[2, 7], 9] });
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
  assert.equal(store.getState().playing, true);
  assert.equal(pending.length, 1);
});
test('typing again invalidates an in-flight result, including A → B → A edits', async () => {
  const { store, pending } = harness();
  const original = store.getState().code;
  const work = store.getState().preview();
  store.getState().setCode('def solve(');
  store.getState().setCode(original);
  pending[0].resolve(result()); await work;
  assert.equal(store.getState().run, null);
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
