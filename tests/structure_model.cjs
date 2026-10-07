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

test('a grid is an island map only when its values prove it and it is an input; anything else is a table', () => {
  const roles = (rows, first, input = true) => { const role = model.islandMap(rows, first, input); return role && rows.map(r => r.map(role)); };
  assert.equal(roles([[1, 2], [3, 0]]), null);
  same(roles([['1', '0'], ['0', '1']]), [['land', 'water'], ['water', 'land']]);
  same(roles([['#', '.']]), [['land', 'water']]);
  // A character map stays a map when the code marks a cell; the mark is its own role.
  same(roles([['X', '0'], ['0', '1']], [['1', '0'], ['0', '1']]), [['mark', 'water'], ['water', 'land']]);
  // 0/1 integers are a map only while they are the only values.
  same(roles([[1, 0], [0, 1]]), [['land', 'water'], ['water', 'land']]);
  assert.equal(roles([[2, 0], [0, 1]], [[1, 0], [0, 1]]), null);
  assert.equal(roles([[1, 1], [1, 1]]), null, 'one value is not a land/water map');
  assert.equal(roles([[true, false]]), null);
  // A table the code builds is never a map, whatever its values and whatever it is called.
  assert.equal(roles([[1, 0], [0, 1]], undefined, false), null);
});

test('grid cells are marked by what holds them: exact in-bounds (r, c) pairs, named by their structure', () => {
  const marks = values => [...model.gridMarks([{ id: 'q', type: 'array', kind: 'queue', values }], 'grid', [2, 3]).queued];
  same(marks([[0, 0, 1]]), [], '(r, c, dist) or (dist, r, c) is ambiguous');
  same(marks([[0, 1], [1, 2], [2, 0], [-1, 0], [0.5, 1]]), ['0,1', '1,2']);
  // A set marks cells only when it is a set of this grid's cells; a same-shaped grid only when it holds booleans.
  const held = model.gridMarks([{ id: 'path', type: 'hashset', values: [[1, 1], [0, 2]] }, { id: 'flags', type: 'matrix', rows: [[true, false, false], [false, false, true]], shape: [2, 3] }, { id: 'dp', type: 'matrix', rows: [[1, 0, 0], [0, 0, 1]], shape: [2, 3] }], 'grid', [2, 3]);
  same([[...held.visited].sort(), held.names.visited], [['0,0', '0,2', '1,1', '1,2'], ['path', 'flags']]);
  same([...model.gridMarks([{ id: 'other', type: 'hashset', values: [[1, 1], [9, 9]] }], 'grid', [2, 3]).visited], [], 'not a set of this grid\'s cells');
});

test('a graph marks nodes by what holds them, named by their own variables', () => {
  const labels = [0, 1, 2, 3];
  const tuples = model.graphMarks([{ id: 'q', type: 'array', kind: 'queue', values: [[3, 0]] }], labels);
  same([...tuples.frontier], [], 'a (node, dist) tuple is ambiguous');
  const plain = model.graphMarks([{ id: 'q', type: 'array', kind: 'queue', values: [3, 1] }, { id: 'seen', type: 'hashset', values: [0] }], labels);
  same([[...plain.frontier], [...plain.visited], plain.names], [[3, 1], [0], { visited: ['seen'], frontier: ['q'] }]);
  // A list is waiting only when the code serves it as a queue, stack or heap, never by its name.
  same([...model.graphMarks([{ id: 'queue', type: 'array', values: [3, 1] }], labels).frontier], []);
  // Below the nodes: the per-node numbers the run changes, under their own name.
  const arrays = [{ id: 'parent', type: 'array', values: [-1, 0, 1, 2] }, { id: 'dist', type: 'array', values: [0, 1, 2, 3] }];
  assert.equal(model.graphMarks(arrays, labels).below, null, 'numbers that never change are not shown');
  assert.equal(model.graphMarks(arrays, labels, new Set(['dist'])).below.name, 'dist');
  assert.equal(model.graphMarks(arrays, labels, new Set(['parent', 'dist'])).below.name, 'parent', 'the first that changes, whatever it is called');
  same([...model.graphMarks([{ id: 'done', type: 'array', values: [true, false, true, false] }], labels).visited], [0, 2]);
  const lettered = model.graphMarks([{ id: 'dist', type: 'array', values: [0, 1] }], ['A', 'B'], new Set(['dist']));
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
  // node = queue.popleft() before graph[node] is read: the neighbour belongs to the node before.
  const held = (value, e) => ({ ...e, state: { ...e.state, variables: [{ id: 'node', value }] } });
  const popped = [held(1, events[1]), held(1, events[2]), held(2, at('QUEUE_POP', {}, 'node = queue.popleft()'))];
  same(model.graphRoles(popped, 1, 'graph'), { current: 'node', next: 'nei' });
  same(model.graphRoles(popped, 2, 'graph'), { current: 'node', next: null }, 'the old neighbour is stale as soon as node moves on');
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

// The whole run's call tree: each step only changes where calls stand, so the drawing never jumps.
const frame = (ev, callstack, structures = []) => ({ ...ev, state: { ...ev.state, callstack, structures } });
const fibRun = () => [
  frame(call(1, 'fib', { n: 3 }, 1), ['fib']), frame(call(2, 'fib', { n: 2 }, 2), ['fib', 'fib']), frame(call(3, 'fib', { n: 1 }, 3), ['fib', 'fib', 'fib']), frame(ret(3, 1), ['fib', 'fib', 'fib']),
  frame(call(4, 'fib', { n: 0 }, 3), ['fib', 'fib', 'fib']), frame(ret(4, 0), ['fib', 'fib', 'fib']), frame(ret(2, 1), ['fib', 'fib']),
  frame(call(5, 'fib', { n: 1 }, 2), ['fib', 'fib']), frame(ret(5, 1), ['fib', 'fib']), frame(ret(1, 2), ['fib']),
];

test('the whole call history: every call with when it started and returned, and the call running at each event', () => {
  const history = model.callHistory(fibRun());
  same(history.all.map(n => [n.id, n.step, n.end, n.value]), [[1, 0, 9, 2], [2, 1, 6, 1], [3, 2, 3, 1], [4, 4, 5, 0], [5, 7, 8, 1]]);
  same(history.frames, [1, 2, 3, 3, 4, 4, 2, 5, 5, 1]);
  same(model.layoutCalls(history.roots).placed.length, 5);
  const at = model.callStates(history, 4);
  same([...at.states.entries()], [[1, 'waiting'], [2, 'waiting'], [3, 'returned'], [4, 'running'], [5, 'ahead']]);
  same([at.active, at.made, at.open, at.total], [4, 4, 3, 5]);
  same([...model.callStates(history, 9).states.values()], ['returned', 'returned', 'returned', 'returned', 'returned']);
});

test('a repeated call is one the trace proves asked the same question, and it names the earlier answer', () => {
  const history = model.callHistory(fibRun());
  same(history.twins.get('fib({"n":1})').map(n => n.id), [3, 5]);
  const again = model.earlierTwins(history, 5, 7);
  same([again.twins.map(n => n.id), again.answered.id, again.answered.value], [[3], 3, 1]);
  same(model.earlierTwins(history, 3, 2).answered, null);
  // Abbreviated lists can't be told apart, and two nodes with equal labels are different nodes.
  const long = [frame(call(1, 'go', { a: [1, 2, 3, 4, 5, 6, '…'] }, 1), ['go']), frame(call(2, 'go', { a: [1, 2, 3, 4, 5, 6, '…'] }, 2), ['go', 'go'])];
  same(model.callHistory(long).twins.size, 0);
  const refs = (id) => [{ id: '@nodes', type: 'nodes', nodes: [], refs: { root: id } }];
  const trees = [frame(call(1, 'depth', { root: '3' }, 1), ['depth'], refs(7)), frame(call(2, 'depth', { root: '3' }, 2), ['depth', 'depth'], refs(8)), frame(call(3, 'depth', { root: '3' }, 2), ['depth', 'depth'], refs(8))];
  same(model.callHistory(trees).twins.get('depth({"root":{"node":8}})').map(n => n.id), [2, 3]);
  same(model.callHistory(trees).twins.get('depth({"root":{"node":7}})').length, 1);
});

test('walked nodes are every node some variable has pointed at so far', () => {
  const snap = (refs) => ({ id: 0, type: 'STATE_CHANGE', line: 1, source: '', detail: '', meta: {}, state: { structures: [{ id: '@nodes', type: 'nodes', nodes: [], refs }], variables: [], callstack: ['solve'] } });
  const events = [snap({ head: 1, curr: 1 }), snap({ head: 1, curr: 2 }), snap({ head: 1, curr: null }), snap({ head: 1, curr: 3 })];
  same([...model.walkedNodes(events, 2)].sort(), [1, 2]);
  same([...model.walkedNodes(events, 3)].sort(), [1, 2, 3]);
});

test('a call reads in the order its function declares its parameters, though its arguments arrive sorted', () => {
  same(model.callLabel({ fn: 'is_valid', args: { col: 2, num: '1', row: 0 }, order: ['row', 'col', 'num'] }), 'is_valid(0, 2, 1)');
  same(model.callLabel({ fn: 'f', args: { b: 1, a: 2 } }), 'f(1, 2)');  // An older trace without the order keeps its keys.
});

test('a grid write is fed by the cells the same line read just before it', () => {
  const grid = hot => ({ id: 'dp', type: 'matrix', rows: [[1, 1], [1, 0]], shape: [2, 2], hot });
  const at = (id, type, line, hot, callstack = ['solve']) => ({ id, type, line, source: '', detail: '', meta: {}, state: { structures: [grid(hot)], variables: [], callstack }, explanation: { what: '', why: '' } });
  // dp[1][1] = dp[0][1] + dp[1][0]: an earlier iteration's read (step 1) and the loop header stop the walk.
  const events = [at(0, 'LOOP_START', 4, []), at(1, 'ARRAY_ACCESS', 5, [[0, 0]]), at(2, 'LOOP_START', 4, []), at(3, 'ARRAY_ACCESS', 5, [[0, 1]]), at(4, 'ARRAY_ACCESS', 5, [[1, 0]]), at(5, 'ARRAY_WRITE', 5, [])];
  same(model.gridSources(events, 5, 'dp', new Set(['1,1'])), [[0, 1], [1, 0]]);
  // Nothing written, nothing fed; the written cell is never its own source; another call's reads never count.
  same(model.gridSources(events, 5, 'dp', new Set()), []);
  same(model.gridSources(events, 5, 'dp', new Set(['1,1', '0,1'])), [[1, 0]]);
  const called = [...events.slice(0, 4), at(4, 'ARRAY_ACCESS', 5, [[1, 0]], ['solve', 'go']), events[5]];
  same(model.gridSources(called, 5, 'dp', new Set(['1,1'])), []);
});

test('the grid cursor is the cell a step read or alone wrote, else the last such cell, dimmed', () => {
  const at = (id, rows, hot = []) => ({ id, type: 'STATE_CHANGE', line: 1, source: '', detail: '', meta: {}, state: { structures: [{ id: 'g', type: 'matrix', rows, shape: [2, 2], hot }], variables: [], callstack: ['solve'] }, explanation: { what: '', why: '' } });
  const events = [at(0, [[0, 0], [0, 0]]), at(1, [[0, 0], [0, 0]], [[1, 0]]), at(2, [[0, 0], [0, 0]]), at(3, [[0, 0], [0, 7]]), at(4, [[1, 1], [0, 7]]), at(5, [[1, 1], [0, 7]])];
  same(model.gridFocus(events, 1, 'g'), { cell: [1, 0], kind: 'read', now: true });
  same(model.gridFocus(events, 2, 'g'), { cell: [1, 0], kind: 'read', now: false });
  same(model.gridFocus(events, 3, 'g'), { cell: [1, 1], kind: 'write', now: true });
  // Two cells written at once mark neither: the cursor stays on the last single cell.
  same(model.gridFocus(events, 5, 'g'), { cell: [1, 1], kind: 'write', now: false });
  same(model.gridFocus(events, 0, 'g'), null);
});
