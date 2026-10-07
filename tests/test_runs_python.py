"""The runner gives the answer Python gives: the same program, run for real, is the reference for every case here."""
import copy
import os
import tempfile
import unittest

# Importing app initializes its database: isolate it before the import, never touch learning.sqlite3.
os.environ['DSA_DATABASE'] = os.path.join(tempfile.mkdtemp(), 'import.sqlite3')  # Never the real database.
import app  # noqa: E402

PROGRAMS = {
    # x op= v evaluates x's parts once, and works in place.
    'a subscript target is evaluated once': ("def solve(nums):\n    c = [0, 0, 0, 0, 0]\n    q = [1, 2, 3]\n    c[q.pop()] += 1\n    return [c, q]\n", [[1]]),
    'list += extends the same list': ("def solve(nums):\n    b = nums\n    b += [9]\n    return nums\n", [[1, 2]]),
    'set |= updates the same set': ("def solve(nums):\n    s = set()\n    t = s\n    t |= {1}\n    return sorted(s)\n", [[1]]),
    'list += takes any iterable': ("def solve(nums):\n    out = []\n    out += (1, 2)\n    return out\n", [[1]]),
    'a field op= v': ("class C:\n    def __init__(self):\n        self.n = 1\n\ndef solve(nums):\n    c = C()\n    c.n += 5\n    return c.n\n", [[1]]),
    'a slice op= v': ("def solve(nums):\n    nums[0:1] += [7]\n    return nums\n", [[1, 2]]),
    # Loops that progress through a global are not infinite.
    'a while loop driven by a global': ("count = 0\n\ndef bump():\n    global count\n    count += 1\n\ndef solve(n):\n    while count < n:\n        bump()\n    return count\n", [3]),
    'defaultdict and Counter answer missing keys': ("from collections import defaultdict, Counter\ndef solve(nums):\n    d = defaultdict(int)\n    for x in nums:\n        d[x] += 1\n    return [d[5], Counter(nums)[7]]\n", [[1, 1]]),
    '*args and **kwargs': ("def f(*args, **kw):\n    return len(args) + len(kw)\n\ndef solve(nums):\n    return f(1, 2) + f(3, k=4)\n", [[1]]),
    # Errors handled by the program itself.
    'try / except': ("def solve(nums):\n    try:\n        return nums[10]\n    except IndexError:\n        return -1\n", [[1]]),
    'try / finally': ("def solve(nums):\n    out = []\n    try:\n        out.append(1)\n    finally:\n        out.append(2)\n    return out\n", [[1]]),
    'raise and catch': ("def check(x):\n    if x < 0:\n        raise ValueError('negative')\n    return x\n\ndef solve(nums):\n    try:\n        return check(-1)\n    except ValueError as e:\n        return str(e)\n", [[1]]),
    # Classes as Python writes them.
    'staticmethod and classmethod': ("class Util:\n    base = 10\n    @staticmethod\n    def double(x):\n        return x * 2\n    @classmethod\n    def plus(cls, x):\n        return cls.base + x\n\ndef solve(nums):\n    return Util.double(4) + Util.plus(1)\n", [[1]]),
    'property': ("class Box:\n    def __init__(self):\n        self.v = 3\n    @property\n    def twice(self):\n        return self.v * 2\n\ndef solve(nums):\n    return Box().twice\n", [[1]]),
    'special methods': ("class P:\n    def __init__(self, x):\n        self.x = x\n    def __add__(self, o):\n        return P(self.x + o.x)\n    def __iter__(self):\n        return iter([self.x])\n    def __contains__(self, v):\n        return v == self.x\n\ndef solve(nums):\n    p = P(1) + P(2)\n    return [list(p), 3 in p]\n", [[1]]),
    'super().__init__': ("class A:\n    def __init__(self, x):\n        self.x = x\n\nclass B(A):\n    def __init__(self, x):\n        super().__init__(x)\n        self.y = 2\n\ndef solve(nums):\n    b = B(5)\n    return b.x + b.y\n", [[1]]),
    'annotation-only fields': ("class Pair:\n    a: int\n    b: int\n\ndef solve(nums):\n    p = Pair()\n    p.a = 1\n    return p.a\n", [[1]]),
    # Functions as values.
    'calls through a dict, a variable or a parameter': ("def apply(fn, x):\n    return fn(x)\n\ndef solve(nums):\n    ops = {'+': lambda a, b: a + b}\n    f = max\n    return ops['+'](2, 3) + f(nums) + apply(len, nums)\n", [[1, 9]]),
    'type, hasattr, callable, getattr with a default': ("def solve(nums):\n    return [type(nums) == list, hasattr(nums, 'append'), callable(len), getattr(nums, 'missing', 7)]\n", [[1]]),
    'match with a dotted pattern': ("class Color:\n    RED = 1\n\ndef solve(nums):\n    match nums[0]:\n        case Color.RED:\n            return 'red'\n        case _:\n            return 'other'\n", [[1]]),
    # Competitive-programming scaffolding around solve.
    'setrecursionlimit, tuple constants and a __main__ block': ("import sys\nsys.setrecursionlimit(10000)\nLIMIT, STEP = 10, 2\n\ndef solve(nums):\n    return LIMIT + STEP\n\nif __name__ == '__main__':\n    print(solve([1]))\n", [[1]]),
}


class SameAnswerAsPython(unittest.TestCase):
    def test_every_program_answers_as_python_does(self):
        for name, (code, args) in PROGRAMS.items():
            with self.subTest(name):
                app.validate_source(code)
                env = {'__name__': 'real'}
                exec(compile(code, '<real>', 'exec'), env)
                expected = app.result_value(env['solve'](*copy.deepcopy(args)))
                run = app.run_cases(code, [args])[0]
                self.assertIsNone(run['error'], run['error'])
                self.assertEqual(run['result'], expected)

    def test_print_writes_what_python_writes(self):
        run = app.run_cases("def solve(nums):\n    print(1, 2, sep='-', end='!')\n    print((1, 2), {3}, {'a': 1})\n    return 0\n", [[[1]]])[0]
        self.assertEqual(run['stdout'], "1-2!(1, 2) {3} {'a': 1}\n")

    def test_a_missing_key_read_says_the_key_was_not_there(self):
        run = app.run_cases("from collections import defaultdict\ndef solve(nums):\n    d = defaultdict(int)\n    return d[5]\n", [[[1]]])[0]
        read = next(e for e in run['events'] if e['type'] == 'HASHMAP_LOOKUP')
        self.assertFalse(read['meta']['found'])

    def test_calls_record_their_star_arguments(self):
        run = app.run_cases("def f(*args, **kw):\n    return 1\n\ndef solve(nums):\n    return f(1, 2, k=3)\n", [[[1]]])[0]
        call = next(e for e in run['events'] if e['type'] == 'RECURSION_CALL' and e['meta']['call']['fn'] == 'f')
        self.assertEqual(call['meta']['call']['order'], ['args', 'kw'])
        self.assertEqual(call['meta']['call']['args'], {'args': [1, 2], 'kw': {'k': 3}})


class LimitsStayLimits(unittest.TestCase):
    def test_no_except_block_can_swallow_a_runner_limit(self):
        for handler in ('except BaseException:', 'except:', 'except Exception:'):
            with self.subTest(handler):
                code = f"def solve(nums):\n    try:\n        while True:\n            nums.append(1)\n            nums.pop()\n    {handler}\n        return 'caught'\n"
                run = app.run_cases(code, [[[1]]])[0]
                self.assertEqual(run['error']['type'], 'ExecutionLimit')

    def test_a_handled_failure_does_not_explain_a_later_one(self):
        code = "def solve(nums):\n    try:\n        nums[10]\n    except IndexError:\n        pass\n    return 1 / 0\n"
        run = app.run_cases(code, [[[1]]])[0]
        self.assertEqual(run['error']['failure'], {'op': {'op': '/', 'text': '1 / 0', 'ltext': '1', 'rtext': '0', 'ltype': 'int', 'rtype': 'int'}})


if __name__ == '__main__':
    unittest.main()


class LeetCodesForm(unittest.TestCase):
    TWO_SUM = ("from typing import List\nclass Solution:\n    def twoSum(self, nums: List[int], target: int) -> List[int]:\n        seen = {}\n"
               "        for i, x in enumerate(nums):\n            if target - x in seen:\n                return [seen[target - x], i]\n            seen[x] = i\n        return []\n")

    def test_class_solution_runs_the_method_that_solves_the_problem(self):
        run = app.run_cases(self.TWO_SUM, [[[2, 7, 11, 15], 9]])[0]
        self.assertEqual((run['result'], run['error']), ([0, 1], None))
        self.assertEqual(run['events'][0]['state']['callstack'], ['Solution.twoSum'], 'the method keeps its own name')

    def test_helpers_called_through_self_are_not_the_entry(self):
        code = ("class Solution:\n    def count(self, nums):\n        return self.add(nums, 0)\n"
                "    def add(self, nums, i):\n        return 0 if i == len(nums) else 1 + self.add(nums, i + 1)\n")
        self.assertEqual(app.run_cases(code, [[[4, 5, 6]]])[0]['result'], 3)

    def test_an_ambiguous_class_is_asked_about_not_guessed(self):
        with self.assertRaisesRegex(ValueError, 'several methods'):
            app.validate_source('class Solution:\n    def a(self, x):\n        return x\n    def b(self, x):\n        return x\n', 'solve', 1)

    def test_the_api_judges_class_solution_like_solve(self):
        from unittest.mock import patch
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        with patch.object(app, 'DB', os.path.join(directory.name, 'lc.sqlite3')), patch.dict(os.environ, {'LLM_API_KEY': '', 'APP_ENV': 'development', 'FIREBASE_PROJECT_ID': ''}):
            app.initialize()
            run = app.app.test_client().post('/api/execute', json={'problemId': 'two-sum', 'code': self.TWO_SUM, 'args': [[2, 7, 11, 15], 9]}).get_json()
        self.assertTrue(run['passed'], run.get('error'))
        self.assertTrue(all(t['passed'] for t in run['tests']))


class ReviewRegressions(unittest.TestCase):
    """Cases a review of the branch found: each answers as Python does, or stops as the runner's limits say."""

    def run_one(self, code, args):
        return app.run_cases(code, [args])[0]

    def test_a_limit_stays_reached_whatever_finally_does(self):
        proven = "def solve(nums):\n    i = 0\n    try:\n        while i < 5:\n            nums.append(1)\n            nums.pop()\n    finally:\n        return 'finished'\n"
        self.assertEqual(self.run_one(proven, [[1]])['error']['type'], 'ExecutionLimit')
        steps = "def solve(nums):\n    total = 0\n    while True:\n        try:\n            for k in range(9000):\n                total += k\n        finally:\n            break\n    return total\n"
        self.assertEqual(self.run_one(steps, [[1]])['error']['type'], 'ExecutionLimit')

    def test_targets_are_assigned_left_to_right_before_a_field_is_set(self):
        code = "class N:\n    def __init__(self):\n        self.next = 1\n\ndef solve(nums):\n    prev = None\n    curr = N()\n    prev, prev.next = curr, None\n    return curr.next\n"
        run = self.run_one(code, [[1]])
        self.assertEqual((run['error'], run['result']), (None, None))

    def test_a_class_solution_entry_can_be_told_apart_by_its_inputs(self):
        code = "class Solution:\n    def twoSum(self, nums, target):\n        return [0, 1]\n    def describe(self):\n        return 'two sum'\n"
        self.assertEqual(self.run_one(code, [[2, 7], 9])['result'], [0, 1])

    def test_writes_through_any_target_are_link_writes_by_the_value_written(self):
        code = ("class N:\n    def __init__(self, v):\n        self.val = v\n        self.next = None\n\ndef solve(nums):\n    nodes = [N(1), N(2)]\n"
                "    nodes[0].next = nodes[1]\n    nodes[1].val = 7\n    nodes[0].next = None\n    return nodes[1].val\n")
        run = self.run_one(code, [[1]])
        self.assertEqual(run['result'], 7)
        self.assertEqual([(e['type'], e['detail']) for e in run['events'] if e['detail'].startswith('nodes[')],
                         [('LINK_WRITE', 'nodes[0].next updated.'), ('STATE_CHANGE', 'nodes[1].val updated.'), ('LINK_WRITE', 'nodes[0].next updated.')])
        self.assertNotIn('_dsa_', str(run['events']), "the runner's own names never show")

    def test_type_of_a_class_cannot_make_classes(self):
        run = self.run_one("def solve(nums):\n    T = type(int)\n    return [T is type, T('X', (), {})]\n", [[1]])
        self.assertIn('three arguments', run['error']['message'])
