// The visual model decides every animation. It must only describe what the recorded trace shows.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const loaded = {};
const js = ts.transpileModule(fs.readFileSync(path.join(__dirname, '..', 'src', 'visualModel.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;  // Like the app's build: real iterators.
vm.runInNewContext(js, { exports: loaded, JSON });
const model = loaded;
const same = (actual, expected) => assert.equal(JSON.stringify(actual), JSON.stringify(expected));

const array = (id, values, extra = {}) => ({ id, type: 'array', values, length: values.length, highlights: [], pointers: {}, ...extra });
const event = (id, type, line, structures, variables = [], meta = {}, detail = '') => ({ id, type, line, source: '', detail, meta, state: { structures, variables, callstack: ['solve'] }, explanation: { what: detail, why: '' } });

test('a two-element exchange is a swap; other writes are writes with their old values', () => {
  const before = event(0, 'LOOP_START', 4, [array('chars', ['h', 'e', 'y'])]);
  const swap = event(1, 'ARRAY_WRITE', 5, [array('chars', ['y', 'e', 'h'])], [], { targets: ['chars[left]', 'chars[right]'] });
  same(model.stepChange(before, swap).swapped, { chars: [0, 2] });
  const write = event(2, 'ARRAY_WRITE', 6, [array('chars', ['y', 'z', 'h'])]);
  const change = model.stepChange(swap, write);
  same(change.swapped, {});
  same(change.written, { chars: [1] });
  same(change.old, { chars: { 1: 'e' } });
});

test('changes across different frames are never animated as edits', () => {
  const caller = event(0, 'STATE_CHANGE', 2, [array('nums', [1, 2])]);
  const callee = { ...event(1, 'RECURSION_CALL', 5, [array('nums', [9, 9])]), state: { structures: [array('nums', [9, 9])], variables: [], callstack: ['solve', 'helper'] } };
  same(model.stepChange(caller, callee).written, {});
});

test('pointers attach to the sequences the code actually indexes', () => {
  const events = [
    event(0, 'RECURSION_CALL', 1, [array('text', ['a', 'b'], { pointers: { left: 0 } }), array('chars', ['a', 'b'], { pointers: { left: 0 } })]),
    event(1, 'ARRAY_ACCESS', 5, [array('text', ['a', 'b']), array('chars', ['a', 'b'])], [{ id: 'right', value: 1 }, { id: 'left', value: 0 }], { structure: 'chars', key: 1, index: 'right' }),
    event(2, 'ARRAY_ACCESS', 5, [array('text', ['a', 'b']), array('chars', ['a', 'b'])], [], { structure: 'chars', key: 0, index: 'left' }),
    event(3, 'ARRAY_ACCESS', 6, [array('chars', ['a', 'b'])], [{ id: 'best_start', value: 1 }], { structure: 'chars', key: 1, index: 'best_start' }),
  ];
  same(model.pointerNames(events), { chars: ['left', 'right', 'best_start'] });  // `left` sits on top; `text` is never indexed.
  const pointers = model.pointersAt(event(4, 'STATE_CHANGE', 7, [], [{ id: 'left', value: 2 }, { id: 'right', value: -1 }]), array('chars', ['a', 'b']), ['left', 'right']);
  same(pointers, [{ name: 'left', index: 2, outside: 'after' }, { name: 'right', index: -1, outside: 'before' }]);
});

test('a comparison highlights only the reads that fed it on the same line', () => {
  const s = [array('nums', [3, 8, 5])];
  const events = [
    event(0, 'ARRAY_ACCESS', 4, s, [], { structure: 'nums', key: 0, index: 'i' }),
    event(1, 'ARRAY_ACCESS', 5, s, [], { structure: 'nums', key: 1, index: 'j' }),
    event(2, 'ARRAY_ACCESS', 5, s, [], { structure: 'nums', key: -1 }),
    event(3, 'COMPARE', 5, s, [], { expression: 'nums[j] < nums[-1]', left: 8, right: 5, result: false }),
  ];
  const focus = model.focusAt(events, 3);
  same(focus.compared, { nums: [2, 1] });
  same(focus.compare, { expression: 'nums[j] < nums[-1]', left: 8, right: 5, result: false });
  same(model.focusAt([event(0, 'HASHMAP_LOOKUP', 4, [], [], { expression: 'need in seen', left: 7, result: false, found: false })], 0).lookup, { structure: 'seen', key: 7, found: false });
});

test('the line lens reports what a line did, and never-run lines honestly', () => {
  const run = {
    lines: { 3: 3, 4: 2 },
    events: [
      event(0, 'LOOP_START', 3, [], [{ id: 'i', value: 0 }, { id: 'x', value: 2 }], {}, 'i, x updated.'),
      event(1, 'STATE_CHANGE', 4, [], [{ id: 'need', value: 7 }], {}, 'need updated.'),
      event(2, 'LOOP_START', 3, [], [{ id: 'i', value: 1 }, { id: 'x', value: 7 }], {}, 'i, x updated.'),
      event(3, 'STATE_CHANGE', 4, [], [{ id: 'need', value: 2 }], {}, 'need updated.'),
    ],
  };
  const code = 'def solve(nums, target):\n    seen = {}\n    for i, x in enumerate(nums):\n        need = target - x\n    return []';
  const need = model.lineLens(run, code, 4);
  same([need.ran, need.samples.map(s => s.label)], [2, ['need = 7', 'need = 2']]);
  same(model.lineLens(run, code, 3).iterations, 2);
  same(model.lineLens(run, code, 5).note, 'This line never ran for this input.');
  same(model.lineLens(run, code, 1).note, 'Function header.');
});

test('the ribbon marks only steps the evidence names, and the goal waits for the return', () => {
  const events = [event(0, 'RECURSION_CALL', 1, []), event(1, 'ARRAY_WRITE', 4, []), event(2, 'RETURN', 6, [], [], { value: [4] })];
  const divergence = { kind: 'Observed result mismatch', message: '', step: 2, elements: { name: 'result', wrong: [{ position: 0, value: 4, goal: 3, step: 1, line: 4, unchanged: false }], missing: 0, ordered: true } };
  same(model.ribbon({ events, divergence }).markers.map(m => [m.step, m.kind]), [[1, 'wrong'], [2, 'divergence']]);
  same(model.ribbon({ events, divergence }).ticks, ['call', 'write', 'return']);
  const run = { events, goal: { expected: [3], matches: false }, preview: true, expected: null, passed: false, result: [4], error: null };
  same([model.goalAt(run, 1).returned, model.goalAt(run, 2).returned], [false, true]);
  same(model.wrongAt(divergence, 1).map(w => w.position), [0]);
});

// squares: res is built, then the return line at step 4; the returned list differs from the goal.
const returning = (source, preview = true) => {
  const res = values => array('res', values);
  const events = [
    event(0, 'RECURSION_CALL', 1, [res([])]),
    event(1, 'ARRAY_WRITE', 3, [res([9])]),
    event(2, 'ARRAY_WRITE', 3, [res([9, 4])]),
    event(3, 'ARRAY_ACCESS', 4, [res([9, 4])], [{ id: 'i', value: 1 }], { structure: 'res', key: 1, index: 'i' }),
    { ...event(4, 'RETURN', 5, [res([9, 4])], [], { value: [9, 4] }), source },
    event(5, 'RECURSION_RETURN', 5, [res([9, 4])]),
  ];
  return { events, goal: { expected: [4, 9], matches: false }, preview, expected: null, passed: false, result: [9, 4], error: null };
};

test('a live preview claims a result only from the step the program returned, like an explicit run', () => {
  for (const preview of [true, false]) {
    const run = returning('return res', preview);
    same(run.events.map((_, i) => model.goalAt(run, i).returned), [false, false, false, false, true, true]);
    // Before the return no lane carries goal marks, so its pointers stay visible.
    same([1, 3].map(step => model.goalRowFor(model.goalAt(run, step), 'res', 'res')), [null, null]);
    same([4, 5].map(step => model.goalRowFor(model.goalAt(run, step), 'res', 'res')), [[4, 9], [4, 9]]);
    same(model.goalAt(run, 2).expected, [4, 9]);  // The goal itself is shown throughout.
  }
});

test('only a bare `return name` puts the goal under that lane', () => {
  const lane = source => model.returnedLane(returning(source).events);
  same(['return res', 'return res  # done', 'return res[::-1]', 'return sorted(res)', 'return res + [1]', 'return'].map(lane), ['res', 'res', null, null, null, null]);
  const goal = model.goalAt(returning('return res[::-1]'), 4);
  same(model.goalRowFor(goal, 'res', model.returnedLane(returning('return res[::-1]').events)), null);
  same(model.goalRowFor({ ...goal, matches: true }, 'res', 'res'), null);  // A matching result needs no goal row.
});

test('a design problem returns only after its last operation', () => {
  // RecentCounter: __init__, then ping(1) and ping(100); every operation returns at the top level.
  const op = (id, type, fn, meta = {}, source = '') => ({ ...event(id, type, 5, [array('self.q', [])], [], meta), source, state: { structures: [array('self.q', [])], variables: [], callstack: [`RecentCounter.${fn}`] } });
  const events = [
    op(0, 'RECURSION_CALL', '__init__'), op(1, 'RECURSION_RETURN', '__init__'),
    op(2, 'RECURSION_CALL', 'ping'), op(3, 'RETURN', 'ping', { value: 1 }, 'return len(self.q)'), op(4, 'RECURSION_RETURN', 'ping'),
    op(5, 'RECURSION_CALL', 'ping'), op(6, 'QUEUE_PUSH', 'ping'), op(7, 'RETURN', 'ping', { value: 2 }, 'return len(self.q)'), op(8, 'RECURSION_RETURN', 'ping'),
  ];
  same(model.isDesignTrace(events), true);
  same(model.isDesignTrace(returning('return res').events), false);
  same(model.programReturn(events), 7);
  const run = { events, goal: { expected: [null, 1, 2], matches: true }, preview: false, expected: [null, 1, 2], passed: true, result: [null, 1, 2], error: null };
  same(events.map((_, i) => model.goalAt(run, i).returned), [false, false, false, false, false, false, false, true, true]);
  same(model.goalAt(run, 3).returnStep, 7);  // "On target" belongs to step 7, not the first ping's return.
  same(model.returnedLane(events), null);  // The answers list is no variable's lane.
  // An operation without an explicit return returns at its frame's exit.
  same(model.programReturn(events.filter(e => e.id !== 7).map((e, i) => ({ ...e, id: i }))), 7);
  // Stopped or cut short, the program never returned.
  const stopped = [...events.slice(0, 7), { ...op(7, 'ERROR', 'ping'), meta: {} }];
  same(stopped.map((_, i) => model.goalAt({ ...run, events: stopped, error: { type: 'KeyError', message: '', line: 5 } }, i).returned).includes(true), false);
  same(events.map((_, i) => model.goalAt({ ...run, truncated: true }, i).returned).indexOf(true), events.length - 1);
});

test('grid pointers are only the names the code used to index that grid', () => {
  const grid = { id: 'grid', type: 'matrix', rows: [[1, 0], [0, 1]], shape: [2, 2], hot: [] };
  const vars = [{ id: 'r', value: 1 }, { id: 'c', value: 0 }, { id: 'x', value: 1 }, { id: 'i', value: 0 }, { id: 'j', value: 1 }];
  const events = [
    event(0, 'ARRAY_ACCESS', 3, [grid], vars, { structure: 'grid', key: 1, index: 'r' }),
    event(1, 'ARRAY_ACCESS', 3, [grid], vars, { structure: 'grid[r]', key: 0, index: 'c' }),
    event(2, 'ARRAY_ACCESS', 4, [grid], vars, { structure: 'grid', key: 0, index: 'r - 1' }),
    event(3, 'ARRAY_WRITE', 5, [grid], vars, {}, 'grid[i][j] updated.'),
    event(4, 'STATE_CHANGE', 6, [grid], vars, {}, 'x updated.'),
  ];
  same(model.gridPointerNames(events), { grid: { rows: ['r', 'i'], cols: ['c', 'j'] } });
  same(model.gridPointerNames([event(0, 'STATE_CHANGE', 1, [grid], vars)]), {});  // x, i, r by name alone are nothing.
});

test('values read like Python', () => {
  same([model.py(null), model.py(true), model.py('a'), model.py([1, 'b']), model.py({ k: false })], ['None', 'True', "'a'", "[1, 'b']", "{'k': False}"]);
});

test('every edge case comes with a question worth asking', () => {
  same(model.casePrompt('Empty').startsWith('Nothing to process'), true);
  same(model.casePrompt('No pair').includes('No valid answer'), true);
  same(model.casePrompt('Repeated values').includes('Repeated values'), true);
  same(model.casePrompt('Negative values').includes('Negatives and zero'), true);
  same(model.casePrompt('Case matters').includes('Exact characters'), true);
  same(model.casePrompt('Something new').startsWith('Predict'), true);
});

// Meaning added to each step: all of it read from the recorded trace and the learner's own code.
const at = (id, type, line, structures, variables, extra = {}) => ({ ...event(id, type, line, structures, variables, extra.meta || {}, extra.detail || ''), source: extra.source || '', state: { structures, variables, callstack: extra.callstack || ['solve'] } });

test("what a step changed, in the program's own names, within one frame only", () => {
  const v = (id, value) => ({ id, value });
  const a = at(0, 'LOOP_START', 3, [array('nums', [3, 1])], [v('i', 0), v('best', 3)]);
  const b = at(1, 'ARRAY_WRITE', 4, [array('nums', [3, 7])], [v('i', 1), v('best', 3), v('seen', true)]);
  same(model.changeLabels(a, b), ['nums[1] = 7', 'i: 0 → 1', 'seen = True']);
  same(model.changeLabels(a, { ...b, state: { ...b.state, callstack: ['solve', 'go'] } }), []);
  const list = (links, refs) => ({ id: '@nodes', type: 'nodes', nodes: [{ id: 1, label: 4, cls: 'ListNode', links: { next: links[0] }, kids: [], attrs: {} }, { id: 2, label: 3, cls: 'ListNode', links: { next: links[1] }, kids: [], attrs: {} }], refs });
  const before = at(0, 'STATE_CHANGE', 5, [list([null, null], { curr: 1, prev: 2 })], []);
  const relinked = at(1, 'LINK_WRITE', 6, [list([2, null], { curr: 1, prev: 2 })], [], { source: 'curr.next = prev' });
  same(model.changeLabels(before, relinked), ['4.next → 3']);
  same(model.changeLabels(relinked, at(2, 'STATE_CHANGE', 7, [list([2, null], { curr: null, prev: 1 })], [])), ['curr → None', 'prev → node 4']);
  same(model.lineLens({ events: [before, relinked], lines: { 6: 1 } }, 'x\nx\nx\nx\nx\ncurr.next = prev', 6).samples.map(s => s.label), ['4.next → 3']);
});

test('work so far counts recorded events of each kind, out of the whole run', () => {
  const events = [at(0, 'ARRAY_ACCESS', 2, [], []), at(1, 'COMPARE', 2, [], []), at(2, 'ARRAY_ACCESS', 2, [], []), at(3, 'RETURN', 3, [], [])];
  same(model.workDone(events, 1), [{ label: 'reads', done: 1, total: 2 }, { label: 'comparisons', done: 1, total: 1 }]);
  // The program's own call is not work; a node built inside a call is not a call of the algorithm.
  const calls = [at(0, 'RECURSION_CALL', 1, [], [], { meta: { call: { id: 1, fn: 'solve', args: {}, depth: 1 } } }), at(1, 'RECURSION_CALL', 1, [], [], { meta: { call: { id: 2, fn: 'ListNode.__init__', args: {}, depth: 2 } } })];
  same(model.workDone(calls, 1), []);
});

test('read counts are per position, within one call, and only while the list keeps its length', () => {
  const read = (id, i, values = [5, 6, 7]) => at(id, 'ARRAY_ACCESS', 3, [array('nums', values)], [], { meta: { structure: 'nums', key: i, index: 'i' } });
  const events = [read(0, 0), read(1, 1), read(2, 0), read(3, -1)];
  same(model.readCounts(events, 3, 'nums', [1, 1, 1, 1]), { 0: 2, 1: 1, 2: 1 });
  same(model.readCounts(events, 1, 'nums', [1, 1, 1, 1]), { 0: 1, 1: 1 });
  same(model.readCounts(events, 3, 'nums', [1, 1, 2, 2]), null);  // Another call's list of the same name.
  same(model.readCounts([read(0, 0), read(1, 0, [5, 6, 7, 8])], 1, 'nums', [1, 1]), null);  // The list grew.
});

test('a variable role comes from the code and the trace, never from its name', () => {
  const code = 'def solve(nums):\n    count = 0\n    total = 0\n    best = 0\n    for i in range(len(nums)):\n        count += 1\n        total += nums[i]\n        best = max(best, total)\n        seen = 1\n    return best';
  const events = [at(0, 'LOOP_START', 5, [array('nums', [1])], [{ id: 'i', value: 0 }, { id: 'count', value: 0 }, { id: 'total', value: 0 }, { id: 'best', value: 0 }, { id: 'seen', value: 1 }], { detail: 'i updated.' })];
  same(model.variableRoles(events, code, { nums: ['i'] }), { i: 'loop index into nums', count: 'counter · += 1', total: 'running total · +=', best: 'kept with max()' });
  same(model.variableRoles(events, code, {}).i, 'loop variable');
  same(model.variableRoles(events, code.replace(/\n/g, '\r\n'), {}).count, 'counter · += 1');  // Windows line endings.
});

test('a value trail is the values held before, within the running call only', () => {
  const v = (value) => [{ id: 'x', value }];
  const events = [at(0, 'STATE_CHANGE', 1, [], v(0)), at(1, 'STATE_CHANGE', 1, [], v(1)), at(2, 'STATE_CHANGE', 1, [], v(9)), at(3, 'STATE_CHANGE', 1, [], v(1)), at(4, 'STATE_CHANGE', 1, [], v(2))];
  same(model.valueTrail(events, [1, 1, 2, 1, 1], 4, 'x'), [0, 1]);  // 9 belonged to another call.
  same(model.valueTrail(events, [1, 1, 1, 1, 1], 4, 'x', 2), [9, 1]);
});

test('the run in chapters: passes of the outer loop, or the calls the top-level call makes', () => {
  const code = 'def solve(nums):\n    total = 0\n    for i in range(2):\n        for j in range(2):\n            total += 1\n    return total';
  const loop = (id, line, i, detail) => at(id, 'LOOP_START', line, [], [{ id: 'i', value: i }], { detail });
  const events = [at(0, 'STATE_CHANGE', 2, [], []), loop(1, 3, 0, 'i updated.'), loop(2, 4, 0, 'j updated.'), loop(3, 4, 0, 'j updated.'), loop(4, 3, 1, 'i updated.'), loop(5, 4, 1, 'j updated.'), at(6, 'LOOP_END', 3, [], []), at(7, 'RETURN', 6, [], [])];
  same(model.phases(events, code).map(p => [p.start, p.end, p.label]), [[0, 0, 'before the loop'], [1, 3, 'pass 1 · i = 0'], [4, 6, 'pass 2 · i = 1'], [7, 7, 'after the loop']]);
  // solve calling itself: its own calls are the chapters (a design problem's top-level operations are, instead).
  const c = (id, n, depth) => at(id, 'RECURSION_CALL', 1, [], [], { meta: { call: { id, fn: 'solve', args: { n }, depth } }, callstack: Array(depth).fill('solve') });
  const r = (id, depth) => at(id, 'RECURSION_RETURN', 1, [], [], { meta: { ret: { id, value: 1 } }, callstack: Array(depth).fill('solve') });
  const recursion = [c(0, 3, 1), c(1, 2, 2), r(2, 2), at(3, 'STATE_CHANGE', 1, [], [], { callstack: ['solve'] }), c(4, 1, 2), r(5, 2), at(6, 'RETURN', 1, [], [], { callstack: ['solve'] })];
  same(model.phases(recursion, 'def solve(n):\n    return 1').map(p => [p.start, p.label]), [[0, 'solve begins'], [1, 'solve(2)'], [3, 'back in solve'], [4, 'solve(1)'], [6, 'back in solve']]);
  // solve hands the work to one helper: the helper's own calls are the chapters.
  const h = (id, fn, n, depth) => at(id, 'RECURSION_CALL', 1, [], [], { meta: { call: { id, fn, args: { n }, depth } }, callstack: ['solve', ...Array(depth - 1).fill('go')] });
  const hr = (id, depth) => at(id, 'RECURSION_RETURN', 1, [], [], { meta: { ret: { id, value: null } }, callstack: ['solve', ...Array(depth - 1).fill('go')] });
  const helper = [h(0, 'solve', 0, 1), h(1, 'go', 0, 2), h(2, 'go', 1, 3), hr(3, 3), at(4, 'STATE_CHANGE', 1, [], [], { callstack: ['solve', 'go'] }), h(5, 'go', 2, 3), hr(6, 3), hr(7, 2), at(8, 'RETURN', 1, [], [])];
  same(model.phases(helper, 'x').map(p => [p.start, p.label]), [[0, 'solve begins'], [2, 'go(1)'], [4, 'back in go'], [5, 'go(2)'], [7, 'back in go']]);
  same(model.phases([at(0, 'RETURN', 1, [], [])], 'x'), null);
});

test('a reorder or a length change moves values; a same-length write moves nothing', () => {
  // A sort: every value goes where it now is, from the position that held it.
  same(model.valueMoves([3, 1, 2], [1, 2, 3]), { moves: [[0, 1], [1, 2], [2, 0]], gone: [], added: [] });
  // A reverse keeps the middle value in place.
  same(model.valueMoves(['a', 'b', 'c'], ['c', 'b', 'a']).moves, [[0, 2], [2, 0]]);
  // insert(0, 9): the rest slide right, the 9 is new.
  same(model.valueMoves([1, 2], [9, 1, 2]), { moves: [[1, 0], [2, 1]], gone: [], added: [0] });
  // pop(0): the rest slide left, the front value leaves.
  same(model.valueMoves([5, 6, 7], [6, 7]), { moves: [[0, 1], [1, 2]], gone: [0], added: [] });
  // An append moves nothing and adds the new position.
  same(model.valueMoves([1, 2], [1, 2, 3]), { moves: [], gone: [], added: [2] });
  // Duplicates keep their own place when they can.
  same(model.valueMoves([1, 2, 1], [1, 1, 2]).moves, [[1, 2], [2, 1]]);
  // A write of a new value is not a move, and neither is an unchanged lane.
  same(model.valueMoves([1, 2, 3], [1, 7, 3]), { moves: [], gone: [], added: [] });
  same(model.valueMoves([1, 2], [1, 2]), { moves: [], gone: [], added: [] });
});

test('a copy flies only from a position the same line read, with the value written', () => {
  const read = (id, key, value, values) => event(id, 'ARRAY_ACCESS', 7, [array('nums', values)], [], { structure: 'nums', key, value });
  // nums[j + 1] = nums[j] in insertion sort: the 5 read at 1 lands at 2.
  const events = [event(0, 'LOOP_START', 6, [array('nums', [2, 5, 3])]), read(1, 1, 5, [2, 5, 3]), event(2, 'ARRAY_WRITE', 7, [array('nums', [2, 5, 5])])];
  same(model.copySources(events, 2, 'nums', [2]), [[2, 1]]);
  same(model.laneMotion(events, 2, 'nums'), { moves: [], copies: [[2, 1]], gone: [], added: [], vacated: [] });
  // A value computed from the read (nums[j] + 1) is a write, not a copy.
  const computed = [events[0], events[1], event(2, 'ARRAY_WRITE', 7, [array('nums', [2, 5, 6])])];
  same(model.copySources(computed, 2, 'nums', [2]), []);
  // A read on another line (key = nums[i] … nums[j + 1] = key) proves nothing.
  const elsewhere = [events[0], { ...events[1], line: 4 }, events[2]];
  same(model.copySources(elsewhere, 2, 'nums', [2]), []);
});

test('lane motion covers a removal, never crosses frames, and moves only cells on view', () => {
  const lane = (id, values, callstack = ['solve']) => ({ ...event(id, 'STATE_CHANGE', 3, [array('q', values)]), state: { structures: [array('q', values)], variables: [], callstack } });
  same(model.laneMotion([lane(0, [4, 5, 6]), lane(1, [5, 6])], 1, 'q'), { moves: [[0, 1], [1, 2]], copies: [], gone: [{ from: 0, value: 4 }], added: [], vacated: [2] });
  same(model.laneMotion([lane(0, [4, 5, 6]), lane(1, [5, 6], ['solve', 'helper'])], 1, 'q'), { moves: [], copies: [], gone: [], added: [], vacated: [] });
  // A value entering from past the cells on view shifts what is on view; nothing moves to or from an unseen cell.
  same(model.laneMotion([lane(0, [1, 2, 3, 4]), lane(1, [0, 1, 2, 3, 4])], 1, 'q', 3), { moves: [[1, 0], [2, 1]], copies: [], gone: [], added: [0], vacated: [] });
});

test('two pointers bound a range only when each moves one way, whatever they are called', () => {
  const at = (id, vars, callstack = ['solve']) => ({ ...event(id, 'STATE_CHANGE', 2, [array('nums', [1, 2, 3, 4])], Object.entries(vars).map(([k, v]) => ({ id: k, value: v }))), state: { structures: [array('nums', [1, 2, 3, 4])], variables: Object.entries(vars).map(([k, v]) => ({ id: k, value: v })), callstack } });
  // a and b close in: a window. i and j as nested loops: j jumps back each pass, so nothing is bounded.
  const closing = [at(0, { a: 0, b: 3 }), at(1, { a: 1, b: 3 }), at(2, { a: 1, b: 2 })];
  same(model.rangePairs(closing, { nums: ['a', 'b'] }), { nums: ['a', 'b'] });
  const nested = [at(0, { i: 0, j: 1 }), at(1, { i: 0, j: 2 }), at(2, { i: 1, j: 2 }), at(3, { i: 1, j: 3 }), at(4, { i: 2, j: 3 })].map((e, k) => k === 2 ? { ...e, state: { ...e.state, variables: [{ id: 'i', value: 1 }, { id: 'j', value: 2 }] } } : e);
  const reset = [...nested.slice(0, 2), at(2, { i: 1, j: 1 }), at(3, { i: 1, j: 2 })];
  same(model.rangePairs(reset, { nums: ['i', 'j'] }), {});
  // Values restored on returning to a caller are a different call's, not a move back.
  const calls = [at(0, { lo: 0, hi: 3 }), at(1, { lo: 1, hi: 3 }), at(2, { lo: 3, hi: 3 }, ['solve', 'solve']), at(3, { lo: 1, hi: 3 }), at(4, { lo: 1, hi: 2 })];
  same(model.rangePairs(calls, { nums: ['lo', 'hi'] }), { nums: ['lo', 'hi'] });
  assert.equal(model.pointerRange([{ name: 'a', index: 1, outside: null }, { name: 'b', index: 3, outside: null }], ['a', 'b']).join(), '1,3');
  assert.equal(model.pointerRange([{ name: 'left', index: 1, outside: null }, { name: 'right', index: 3, outside: null }]), null, 'no pair from names alone');
});
