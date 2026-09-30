import copy
import os
import tempfile
import unittest

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
            for case in p['tests']:
                for mode in ('solution', 'brute'):
                    with self.subTest(problem=p['id'], case=case['name'], mode=mode):
                        trace = app.execute_worker({'code': p[mode], 'args': copy.deepcopy(case['args'])})
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

    def test_loop_and_allocation_limits(self):
        for code in ['def solve(nums):\n    while True:\n        pass', 'def solve(nums):\n    return [1] * 100000000', 'def solve(nums):\n    x = [1]\n    x *= 100000000\n    return x']:
            trace = app.execute_worker({'code': code, 'args': [[]]})
            self.assertEqual(trace['error']['type'], 'ExecutionLimit')

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
