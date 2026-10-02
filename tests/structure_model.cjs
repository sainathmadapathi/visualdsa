// Layouts of the learner's structures: pure functions of one recorded snapshot.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const model = {};
const js = ts.transpileModule(fs.readFileSync(path.join(__dirname, '..', 'src', 'structureModel.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;  // Like the app's build: real iterators.
vm.runInNewContext(js, { exports: model, JSON, Math });
const node = (id, label, links = {}, kids = []) => ({ id, label, cls: 'ListNode', links, kids, attrs: {} });
const nodes = (list, refs = {}) => ({ id: '@nodes', type: 'nodes', nodes: list, refs });

test('a half-reversed list is two chains: the reversed part and the rest, each in its own row', () => {
  // 2 → 1 → None and 3 → 4 → None, as after two steps of reversing 1 → 2 → 3 → 4.
  const scene = model.sceneOf(nodes([node(1, 1, { next: null }), node(2, 2, { next: 1 }), node(3, 3, { next: 4 }), node(4, 4, { next: null })]));
  const at = Object.fromEntries(scene.nodes.map(n => [n.id, n]));
  assert.equal(at[2].y, at[1].y);
  assert.ok(at[2].x < at[1].x, 'the head of a chain comes first');
  assert.equal(at[3].y, at[4].y);
  assert.ok(at[3].y > at[2].y, 'a second chain gets a second row');
  assert.equal(scene.ends.length, 2, 'each chain ends at None');
  assert.ok(scene.edges.every(e => e.kind === 'next'));
});

test('a cycle is still drawn, starting at its smallest node', () => {
  const scene = model.sceneOf(nodes([node(1, 1, { next: 2 }), node(2, 2, { next: 1 })]));
  assert.equal(scene.nodes.length, 2);
  assert.equal(scene.ends.length, 0);
  assert.equal(scene.edges.length, 2);
});

test('a binary tree is laid out in order: left subtree left of the root, right subtree right', () => {
  const tree = (id, label, left = null, right = null) => ({ id, label, cls: 'TreeNode', links: { left, right }, kids: [], attrs: {} });
  const scene = model.sceneOf(nodes([tree(1, 3, 2, 3), tree(2, 9), tree(3, 20, 4, 5), tree(4, 15), tree(5, 7)]));
  const at = Object.fromEntries(scene.nodes.map(n => [n.id, n]));
  assert.ok(at[2].x < at[1].x && at[1].x < at[3].x);
  assert.ok(at[4].x < at[3].x && at[3].x < at[5].x);
  assert.ok(at[4].y > at[3].y && at[3].y > at[1].y);
  assert.equal(scene.edges.filter(e => e.kind === 'child').length, 4);
});

test('a trie centres each node over its children and labels the edges with letters', () => {
  const trie = (id, kids) => ({ id, label: null, cls: 'TrieNode', links: {}, kids, attrs: {} });
  const scene = model.sceneOf(nodes([trie(1, [['a', 2], ['b', 3]]), trie(2, []), trie(3, [])]));
  const at = Object.fromEntries(scene.nodes.map(n => [n.id, n]));
  assert.equal(at[1].x, (at[2].x + at[3].x) / 2);
  assert.equal(JSON.stringify(scene.edges.map(e => e.label).sort()), JSON.stringify(['a', 'b']));
});

test('changes between snapshots: re-linked fields and new nodes', () => {
  const before = nodes([node(1, 1, { next: 2 }), node(2, 2, { next: null })]);
  const after = nodes([node(1, 1, { next: null }), node(2, 2, { next: 1 }), node(3, 9, { next: null })]);
  const change = model.nodeChanges(before, after);
  assert.deepEqual([...change.relinked], ['2-next-']);
  assert.deepEqual([...change.fresh], [3]);
});

const call = (id, fn, args, depth) => ({ id, type: 'RECURSION_CALL', line: 1, source: '', detail: '', meta: { call: { id, fn, args, depth } }, state: { structures: [], variables: [], callstack: [] } });
const ret = (id, value) => ({ id: 0, type: 'RECURSION_RETURN', line: 1, source: '', detail: '', meta: { ret: { id, value } }, state: { structures: [], variables: [], callstack: [] } });

test('the call tree so far: finished calls carry their value, the running path is open', () => {
  const events = [call(1, 'fib', { n: 2 }, 1), call(2, 'fib', { n: 1 }, 2), ret(2, 1), call(3, 'fib', { n: 0 }, 2)];
  const tree = model.callTree(events, 3);
  assert.equal(tree.count, 3);
  assert.equal(tree.roots[0].children[0].value, 1);
  assert.equal(tree.roots[0].children[0].done, true);
  assert.equal(tree.active, 3);
  assert.deepEqual([...tree.path], [1, 3]);
  assert.equal(model.callLabel(tree.roots[0]), 'fib(2)');
  assert.ok(model.showCalls(events));
});

test('building nodes inside a call is not a step of the algorithm', () => {
  const events = [call(1, 'Trie.insert', { word: 'ab' }, 1), call(2, 'TrieNode.__init__', {}, 2), ret(2, null), ret(1, null), call(3, 'Trie.search', { word: 'a' }, 1)];
  const tree = model.callTree(events, 4);
  assert.equal(tree.count, 2);
  assert.equal(tree.roots[0].children.length, 0);
  assert.ok(model.showCalls(events), 'two operations are worth a call log');
  assert.ok(!model.showCalls([call(1, 'solve', {}, 1), call(2, 'ListNode.__init__', {}, 2)]));
});

test('heap positions and bits', () => {
  assert.deepEqual([0, 1, 2, 3].map(i => model.heapPosition(i, 400).depth), [0, 1, 1, 2]);
  assert.equal(model.heapPosition(0, 400).x, 200);
  assert.equal(model.bitsOf(5, 8), '00000101');
  assert.equal(model.bitsOf(-1, 8), '11111111');
  assert.equal(model.bitWidth(5, 3), 8);
  assert.equal(model.bitWidth(-5, 3), 16);
});

test('inputs written as lists are drawn as what the program receives', () => {
  const [list] = model.inputStructures(['head', 'k'], [[1, 2, 3], 2], { head: 'linkedlist' });
  assert.equal(list.type, 'nodes');
  assert.equal(list.nodes.length, 3);
  assert.equal(list.refs.head, 1);
  assert.equal(list.nodes[2].links.next, null);
  const [tree] = model.inputStructures(['root'], [[3, 9, 20, null, null, 15, 7]], { root: 'tree' });
  assert.equal(tree.nodes.length, 5);
  const [grid] = model.inputStructures(['grid'], [[['1', '0'], ['0', '1']]], {});
  assert.equal(grid.type, 'matrix');
});
