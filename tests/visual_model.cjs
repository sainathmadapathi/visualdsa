// The visual model decides every animation. It must only describe what the recorded trace shows.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const loaded = {};
const js = ts.transpileModule(fs.readFileSync(path.join(__dirname, '..', 'src', 'visualModel.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
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
