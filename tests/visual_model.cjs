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
