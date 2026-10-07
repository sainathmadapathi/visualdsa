import copy
import json
import os
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

test_directory = tempfile.TemporaryDirectory()
os.environ['DSA_DATABASE'] = os.path.join(test_directory.name, 'test.sqlite3')
import app


class TraceTests(unittest.TestCase):
    def test_live_preview_is_ephemeral_and_never_mastery_evidence(self):
        client = app.app.test_client()
        with app.connect() as db:
            before = db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]
        response = client.post('/api/preview', json={'problemId': 'two-sum', 'code': 'def solve(nums, target):\n    return [0, 1]', 'args': [[2, 7], 9]})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['preview'])
        self.assertEqual(data['result'], [0, 1])
        self.assertTrue(data['events'])
        self.assertIn('explanation', data['events'][0])
        self.assertEqual(data['tests'], [])
        self.assertEqual(data['attemptId'], '')
        self.assertFalse(data['passed'])
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], before)

    def test_live_preview_preserves_validation_and_runtime_limits(self):
        client = app.app.test_client()
        for code in ['def solve(', 'import os\ndef solve(nums, target):\n    return []']:
            response = client.post('/api/preview', json={'problemId': 'two-sum', 'code': code})
            self.assertEqual(response.status_code, 400)
        response = client.post('/api/preview', json={'problemId': 'two-sum', 'code': 'def solve(nums, target):\n    while True:\n        pass'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['error']['type'], 'ExecutionLimit')

    def test_every_authored_solution_and_brute_force(self):
        for p in app.PROBLEMS:
            # Linked lists and trees reach the code as nodes; a design problem builds its class.
            shape = {'kinds': [p.get('kinds', {}).get(name) for name in p['params']], 'entry': p.get('entry', 'solve')}
            for case in p['tests']:
                with self.subTest(problem=p['id'], case=case['name'], check='input rules'):
                    app.valid_args(p, case['args'])
                for mode in ('solution', 'brute'):
                    with self.subTest(problem=p['id'], case=case['name'], mode=mode):
                        trace = app.execute_worker({'code': p[mode], 'args': copy.deepcopy(case['args']), **shape})
                        self.assertIsNone(trace['error'])
                        self.assertTrue(app.correct(p, trace['result'], case['args'], case['expected']), trace['result'])

    def test_actual_map_and_comparison_events(self):
        p = app.problem_by_id('two-sum')
        trace = app.execute_worker({'code': p['solution'], 'args': copy.deepcopy(p['example']['args'])})
        lookup = [e for e in trace['events'] if e['type'] == 'HASHMAP_LOOKUP']
        self.assertFalse(lookup[0]['meta']['found'])
        self.assertTrue(lookup[1]['meta']['found'])
        insert = next(e for e in trace['events'] if e['type'] == 'HASHMAP_INSERT')
        self.assertEqual(next(s for s in insert['state']['structures'] if s['id'] == 'seen')['entries'], [{'key': 2, 'value': 0}])
        self.assertEqual(next(s for s in lookup[0]['state']['structures'] if s['id'] == 'seen')['entries'], [])

    def test_wrong_code_is_not_replaced(self):
        code = 'def solve(nums, target):\n    seen = {}\n    for i, x in enumerate(nums):\n        seen[x] = i\n        if target - x in seen:\n            return [seen[target - x], i]\n    return []'
        trace = app.execute_worker({'code': code, 'args': [[3, 3], 6]})
        self.assertEqual(trace['result'], [0, 0])
        self.assertFalse(app.correct(app.problem_by_id('two-sum'), trace['result'], [[3, 3], 6], [0, 1]))

    def test_runtime_error_preserves_prior_events(self):
        trace = app.execute_worker({'code': 'def solve(nums):\n    i = len(nums)\n    return nums[i]', 'args': [[1, 2]]})
        self.assertEqual(trace['error']['type'], 'IndexError')
        self.assertEqual(trace['error']['line'], 3)
        self.assertTrue(any(e['type'] == 'POINTER_MOVE' for e in trace['events']))

    def test_semantics_and_single_evaluation(self):
        code = 'def solve(nums):\n    a = [1, 2]\n    if a.pop() > 1:\n        return a\n    return []'
        trace = app.execute_worker({'code': code, 'args': [[]]})
        self.assertEqual(trace['result'], [1])
        self.assertEqual(len([e for e in trace['events'] if e['type'] == 'STACK_POP']), 1)

    def test_no_aliasing_and_swaps(self):
        trace = app.execute_worker({'code': 'def solve(nums):\n    nums[0], nums[1] = nums[1], nums[0]\n    return nums', 'args': [[2, 7]]})
        self.assertEqual(trace['result'], [7, 2])
        first = trace['events'][0]['state']['structures'][0]['values']
        self.assertEqual(first, [2, 7])

    def test_tuple_assignments_are_labeled_by_their_targets(self):
        trace = app.execute_worker({'code': app.problem_by_id('reverse-string')['solution'], 'args': ['ab']})
        swap = next(e for e in trace['events'] if e['meta'].get('targets'))
        self.assertEqual(swap['type'], 'ARRAY_WRITE')
        self.assertEqual(swap['detail'], 'chars[left], chars[right] updated.')
        self.assertEqual(swap['meta']['targets'], ['chars[left]', 'chars[right]'])
        self.assertEqual(next(s for s in swap['state']['structures'] if s['id'] == 'chars')['values'], ['b', 'a'])
        self.assertIn('entire right side first', app.explanation(swap)['why'])
        code = 'def solve(nums):\n    seen = {}\n    left, right = 0, len(nums) - 1\n    a, b = 0, 1\n    i, nums[0] = 1, 5\n    seen[1], seen[2] = 2, 1\n    total = nums[left] + nums[right]\n    return nums'
        events = {e['detail']: e for e in app.execute_worker({'code': code, 'args': [[2, 7]]})['events']}
        # A pointer move is an assignment to names the code uses as positions (nums[left]), whatever they are called.
        self.assertEqual(events['left, right updated.']['type'], 'POINTER_MOVE')
        self.assertEqual(events['a, b updated.']['type'], 'STATE_CHANGE')
        self.assertEqual(events['i, nums[0] updated.']['type'], 'ARRAY_WRITE')
        self.assertEqual(events['seen[1], seen[2] updated.']['type'], 'HASHMAP_INSERT')
        self.assertEqual(events['total updated.']['type'], 'STATE_CHANGE')
        self.assertEqual(events['total updated.']['meta'], {})

    def test_loop_and_allocation_limits(self):
        for code in ['def solve(nums):\n    while True:\n        pass', 'def solve(nums):\n    return [1] * 100000000', 'def solve(nums):\n    x = [1]\n    x *= 100000000\n    return x']:
            trace = app.execute_worker({'code': code, 'args': [[]]})
            self.assertEqual(trace['error']['type'], 'ExecutionLimit')

    def test_budget_covers_generators_lambdas_top_level_and_builtin_loops(self):
        # Each ran untraced until the OS killed the worker ("Execution worker stopped"); the budget must stop them.
        runaway = {
            'generator expression': 'def solve(nums):\n    return sum(1 for i in range(10000) for j in range(10000))',
            'lambda': 'def solve(nums):\n    f = lambda n: sum(1 for i in range(10000) for j in range(n))\n    return f(10000)',
            'top-level value': 'x = sum(1 for i in range(10000) for j in range(10000))\ndef solve(nums):\n    return x',
            'iter(callable, sentinel)': 'def solve(nums):\n    return sum(iter(int, 1))',
            'itertools.count': 'import itertools\ndef solve(nums):\n    return max(itertools.count())',
            'itertools.permutations': 'import itertools\ndef solve(nums):\n    return max(itertools.permutations(range(12)))',
            'Counter.elements': 'from collections import Counter\ndef solve(nums):\n    c = Counter()\n    c[1] = 1000000000\n    return sum(c.elements())',
            'sum of lists': 'def solve(nums):\n    return len(sum([[1]] * 10000 + [[2] * 10000], []))',
            'math.comb': 'import math\ndef solve(nums):\n    return math.comb(4000000, 2000000) % 7',
            'math.factorial': 'import math\ndef solve(nums):\n    return math.factorial(2000000) % 7',
            'pow': 'def solve(nums):\n    return pow(3 ** 1000, 4000) % 7',
        }
        for name, code in runaway.items():
            with self.subTest(name):
                trace = app.execute_worker({'code': code, 'args': [[]], 'budget': 1})
                self.assertEqual(trace['error']['type'], 'ExecutionLimit', trace['error'])
                self.assertLess(trace['durationMs'], 1500)
        started = time.monotonic()
        runs = app.run_cases(runaway['generator expression'], [[[1]], [[2]]])
        self.assertLess(time.monotonic() - started, 4)  # Stopped by the budget, not by the OS limit.
        self.assertEqual([run['error']['type'] for run in runs], ['ExecutionLimit', 'ExecutionLimit'])
        # Ordinary uses are unchanged.
        for code, expected in [('def solve(nums):\n    return sum(x for x in nums if x > 0)', 4), ('import itertools\ndef solve(nums):\n    return len(list(itertools.permutations(nums)))', 6),
                               ('import math\ndef solve(nums):\n    return math.comb(10, 3) + math.factorial(5)', 240), ('def solve(nums):\n    return sorted(nums, key=lambda x: -x)', [3, 1, -2]),
                               ('def solve(nums):\n    return sum([[x] for x in nums], [])', [1, -2, 3]), ('def solve(nums):\n    it = iter(nums)\n    return next(it)', 1)]:
            with self.subTest(code):
                trace = app.execute_worker({'code': code, 'args': [[1, -2, 3]]})
                self.assertIsNone(trace['error'])
                self.assertEqual(trace['result'], expected)

    def test_a_stopped_worker_keeps_finished_cases_and_reports_the_limit(self):
        ready, finished = json.dumps({'ready': True}), json.dumps(app.execute_worker({'code': 'def solve(nums):\n    return nums', 'args': [[1]]}))
        crashed = subprocess.CompletedProcess([], 1, stdout=f'{ready}\n{finished}\n{{"events": [', stderr='')
        with patch('app.subprocess.run', return_value=crashed):
            runs = app.run_cases('def solve(nums):\n    return nums', [[[1]], [[2]], [[3]]])
        self.assertEqual(runs[0]['result'], [1])
        self.assertEqual(runs[1]['error']['type'], 'ExecutionLimit')
        self.assertEqual(runs[2]['error']['type'], 'NotRun')
        with patch('app.subprocess.run', side_effect=subprocess.TimeoutExpired([], 9, output=f'{ready}\n'.encode())):
            runs = app.run_cases('def solve(nums):\n    return nums', [[[1]]])
        self.assertEqual(runs[0]['error']['type'], 'ExecutionLimit')
        with patch('app.subprocess.run', return_value=subprocess.CompletedProcess([], 1, stdout='', stderr='boom')), self.assertRaises(ValueError):
            app.run_cases('def solve(nums):\n    return nums', [[[1]]])  # The worker never started: a configuration problem, not a limit.

    def test_deeply_nested_input_is_a_clear_json_error(self):
        client = app.app.test_client()
        response = client.post('/api/execute', data='[' * 15000 + ']' * 15000, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['ok'], False)
        self.assertIn('nested too deeply', response.get_json()['error'])

    def test_unsafe_code_is_rejected(self):
        for code in ['import os\ndef solve(nums):\n    return []', 'def solve(nums):\n    return nums.__class__', 'def solve(nums):\n    return open("file")', 'def solve(nums):\n    return eval("1")']:
            with self.assertRaises(ValueError):
                app.validate_source(code)

    def test_subprocess_execution(self):
        trace = app.run_isolated('def solve(nums):\n    return sum(nums)', [[1, 2, 3]])
        self.assertEqual(trace['result'], 6)
        self.assertIsNone(trace['error'])

    def test_api_wrong_and_correct_and_persistence(self):
        client = app.app.test_client()
        p = app.problem_by_id('two-sum')
        response = client.post('/api/execute', json={'problemId': p['id'], 'code': p['solution'], 'args': [[2, 7, 11, 15], 9]})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['passed'])
        self.assertTrue(all(t['passed'] for t in data['tests']))
        feedback = client.post('/api/explain', json={'attemptId': data['attemptId'], 'step': 1}).get_json()
        self.assertEqual(feedback['provider'], 'Trace guide')
        wrong = client.post('/api/execute', json={'problemId': p['id'], 'code': 'def solve(nums, target):\n    return [0, 0]', 'args': [[3, 3], 6]}).get_json()
        self.assertFalse(wrong['passed'])
        self.assertIsNotNone(wrong['divergence'])
        self.assertEqual(wrong['result'], [0, 0])

    def test_assistance_history_and_progress_do_not_regress(self):
        client = app.app.test_client()
        p = app.problem_by_id('two-sum')
        run = client.post('/api/execute', json={'problemId': p['id'], 'code': p['solution'], 'args': p['example']['args']}).get_json()
        hint = client.post('/api/hint', json={'problemId': p['id'], 'level': 7, 'attemptId': run['attemptId']}).get_json()
        self.assertEqual(hint['level'], 1)  # A first click cannot skip to implementation.
        saved = client.post('/api/progress', json={'problemId': p['id'], 'stage': 'Independent', 'attemptId': run['attemptId']}).get_json()
        self.assertEqual(saved['stage'], 'Reproduced')
        saved = client.post('/api/progress', json={'problemId': p['id'], 'stage': 'Understood'}).get_json()
        self.assertEqual(saved['stage'], 'Reproduced')

    def test_public_execution_requires_container(self):
        old = os.environ.get('APP_ENV')
        os.environ['APP_ENV'] = 'production'
        try:
            with self.assertRaises(ValueError):
                app.run_isolated('def solve(nums):\n    return nums', [[]])
        finally:
            if old is None:
                os.environ.pop('APP_ENV', None)
            else:
                os.environ['APP_ENV'] = old

    def test_input_contract_and_invalid_result_are_safe(self):
        p = app.problem_by_id('max-window-sum')
        with self.assertRaises(ValueError):
            app.valid_args(p, [[1, 2], 0])
        self.assertFalse(app.correct(app.problem_by_id('unique-values'), [[1]], [[1]], [1]))
        self.assertTrue(app.correct(app.problem_by_id('binary-search'), 0, [[2, 2, 2], 2], 1))
        with self.assertRaises(ValueError):
            app.valid_args(app.problem_by_id('merge-sorted'), [[1, 2], [3, 1]])

    def test_trace_cap_does_not_change_result(self):
        trace = app.execute_worker({'code': 'def solve(nums):\n    total = 0\n    for i in range(800):\n        total += i\n    return total', 'args': [[]]})
        self.assertTrue(trace['truncated'])
        self.assertEqual(trace['result'], sum(range(800)))
        self.assertIsNone(trace['error'])
        self.assertEqual(len(trace['events']), app.MAX_EVENTS)

    def test_result_is_not_truncated_like_a_snapshot(self):
        trace = app.execute_worker({'code': 'def solve(nums):\n    return list(range(400))', 'args': [[]]})
        self.assertEqual(trace['result'], list(range(400)))

    def test_recursion_and_short_circuit(self):
        code = 'def solve(nums):\n    return factorial(len(nums))\ndef factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)'
        trace = app.execute_worker({'code': code, 'args': [[1, 2, 3, 4]]})
        self.assertEqual(trace['result'], 24)
        self.assertGreater(max(len(e['state']['callstack']) for e in trace['events']), 3)
        trace = app.execute_worker({'code': 'def solve(nums):\n    if len(nums) == 0 or nums[0] > 2:\n        return True\n    return False', 'args': [[]]})
        self.assertEqual(trace['result'], True)
        self.assertFalse(any(e['type'] == 'ARRAY_ACCESS' for e in trace['events']))


if __name__ == '__main__':
    unittest.main()
