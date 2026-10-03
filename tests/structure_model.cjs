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
const same = (actual, expected, message) => assert.equal(JSON.stringify(actual), JSON.stringify(expected), message);  // Values from the vm realm.
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

test('a cycle is still drawn, starting at its first recorded node', () => {
  const scene = model.sceneOf(nodes([node(2, 2, { next: 1 }), node(1, 1, { next: 2 })]));
  assert.equal(scene.nodes.length, 2);
  assert.equal(scene.ends.length, 0);
  assert.equal(scene.edges.length, 2);
  const at = Object.fromEntries(scene.nodes.map(n => [n.id, n]));
  assert.ok(at[2].x < at[1].x, 'recorded order, not the smallest id, starts a pure cycle');
});

test('children from two list attributes keep distinct edge keys', () => {
  const n = (id, kids = []) => ({ id, label: id, cls: 'Node', links: {}, kids, attrs: {} });
  const scene = model.sceneOf(nodes([n(1, [[0, 2], [0, 3]]), n(2), n(3)]));
  const keys = scene.edges.map(e => e.key);
  assert.equal(keys.length, 2);
  assert.equal(new Set(keys).size, 2);
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

test('the call tree shows at most its limit, and counts exactly what it hides', () => {
  let id = 0;
  const fib = n => ({ id: ++id, fn: 'fib', args: { n }, done: true, step: 0, children: n < 2 ? [] : [fib(n - 1), fib(n - 2)] });
  const tree = fib(10);  // 177 calls.
  const layout = model.layoutCalls([tree]);
  assert.equal(layout.placed.length, 90);
  assert.equal(layout.hidden, 177 - 90);
  assert.equal(new Set(layout.placed.map(p => p.node.id)).size, 90);
  assert.ok(layout.placed.every(p => !p.parent || layout.placed.includes(p.parent)), 'every shown call hangs from a shown parent');
  const wide = { id: 1, fn: 'root', args: {}, done: true, step: 0, children: Array.from({ length: 95 }, (_, i) => ({ id: i + 2, fn: 'kid', args: {}, done: true, step: 0, children: [] })) };
  same([model.layoutCalls([wide]).placed.length, model.layoutCalls([wide]).hidden], [90, 6]);
  same([model.layoutCalls([fib(3)]).placed.length, model.layoutCalls([fib(3)]).hidden], [5, 0]);
});

test('a grid is an island map only when its values prove it; anything else is a table', () => {
  const roles = (rows, first, name = 'grid') => { const role = model.islandMap(name, rows, first); return role && rows.map(r => r.map(role)); };
  assert.equal(roles([[1, 2], [3, 0]], undefined, 'matrix'), null);
  same(roles([['1', '0'], ['0', '1']]), [['land', 'water'], ['water', 'land']]);
  same(roles([['#', '.']]), [['land', 'water']]);
  // A character map stays a map when the code marks a cell; the mark is its own role.
  same(roles([['X', '0'], ['0', '1']], [['1', '0'], ['0', '1']]), [['mark', 'water'], ['water', 'land']]);
  // 0/1 integers are a map only while they are the only values.
  same(roles([[1, 0], [0, 1]]), [['land', 'water'], ['water', 'land']]);
  assert.equal(roles([[2, 0], [0, 1]], [[1, 0], [0, 1]]), null);
  assert.equal(roles([[1, 1], [1, 1]]), null, 'one value is not a land/water map');
  assert.equal(roles([[true, false]]), null);
  assert.equal(roles([[1, 0], [0, 1]], undefined, 'dp'), null);
});

test('a queue marks a grid cell only by an exact, in-bounds (r, c) pair', () => {
  const marks = values => [...model.gridMarks([{ id: 'q', type: 'array', kind: 'queue', values }], 'grid', [2, 3]).queued];
  same(marks([[0, 0, 1]]), [], '(r, c, dist) or (dist, r, c) is ambiguous');
  same(marks([[0, 1], [1, 2], [2, 0], [-1, 0], [0.5, 1]]), ['0,1', '1,2']);
  const seen = model.gridMarks([{ id: 'seen', type: 'hashset', values: [[1, 1], [9, 9]] }, { id: 'visited', type: 'matrix', rows: [[true, false, false], [false, false, true]], shape: [2, 3] }], 'grid', [2, 3]).visited;
  same([...seen].sort(), ['0,0', '1,1', '1,2']);
});

test('a graph marks nodes only with plain node ids, named by their own variables', () => {
  const labels = [0, 1, 2, 3];
  const tuples = model.graphMarks([{ id: 'q', type: 'array', kind: 'queue', values: [[3, 0]] }], labels);
  same([...tuples.frontier], [], 'a (node, dist) tuple is ambiguous');
  const plain = model.graphMarks([{ id: 'q', type: 'array', kind: 'queue', values: [3, 1] }, { id: 'seen', type: 'hashset', values: [0] }], labels);
  same([[...plain.frontier], [...plain.visited], plain.names], [[3, 1], [0], { visited: ['seen'], frontier: ['q'] }]);
  const parent = model.graphMarks([{ id: 'parent', type: 'array', values: [-1, 0, 1, 2] }], labels);
  assert.equal(parent.below.name, 'parent', 'a parent array is shown as parent, never as dist');
  const both = model.graphMarks([{ id: 'parent', type: 'array', values: [-1, 0, 1, 2] }, { id: 'dist', type: 'array', values: [0, 1, 2, 3] }], labels);
  same([both.below.name, both.below.values], ['dist', [0, 1, 2, 3]]);
  const lettered = model.graphMarks([{ id: 'dist', type: 'array', values: [0, 1] }], ['A', 'B']);
  assert.equal(lettered.below, null, 'position i of an array is node i only when nodes are numbered 0..n-1');
});

test('the current node and its neighbour are the names the trace proves walk the graph', () => {
  const at = (type, meta = {}, source = '') => ({ id: 0, type, line: 1, source, detail: '', meta, state: { structures: [], variables: [], callstack: ['solve'] } });
  const events = [
    at('STATE_CHANGE', {}, 'start = 0'),
    at('ARRAY_ACCESS', { structure: 'graph', key: 1, index: 'node' }, 'for nei in graph[node]:'),
    at('LOOP_START', {}, 'for nei in graph[node]:'),
    at('ARRAY_ACCESS', { structure: 'graph', key: 2, index: 'node' }, 'for nei in graph[node]:'),
  ];
  same(model.graphRoles(events, 0, 'graph'), { current: null, next: null }, 'start is never a role by its name');
  same(model.graphRoles(events, 1, 'graph'), { current: 'node', next: null });
  same(model.graphRoles(events, 2, 'graph'), { current: 'node', next: 'nei' });
  same(model.graphRoles(events, 3, 'graph'), { current: 'node', next: null }, 'a new node: the old neighbour is stale');
  const weighted = [at('ARRAY_ACCESS', { structure: 'adj', index: 'u' }), at('LOOP_START', {}, 'for (v, w) in adj[u]:')];
  same(model.graphRoles(weighted, 1, 'adj'), { current: 'u', next: 'v' });
  const matrix = [at('ARRAY_ACCESS', { structure: 'graph', index: 'u' }), at('ARRAY_ACCESS', { structure: 'graph[u]', index: 'v' })];
  same(model.graphRoles(matrix, 1, 'graph'), { current: 'u', next: 'v' });
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
