import copy
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Importing app initializes its database: isolate it before the import, never touch learning.sqlite3.
os.environ.setdefault('DSA_DATABASE', os.path.join(tempfile.mkdtemp(), 'import.sqlite3'))
import app  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class LearningLoopTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        db = patch.object(app, 'DB', os.path.join(self.directory.name, 'loop.sqlite3'))
        db.start()
        self.addCleanup(db.stop)
        env = patch.dict(os.environ, {'LLM_API_KEY': '', 'APP_ENV': 'development', 'FIREBASE_PROJECT_ID': ''})
        env.start()
        self.addCleanup(env.stop)
        app.initialize()
        self.client = app.app.test_client()

    def post(self, path, status=200, **body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, status, response.get_json())
        return response.get_json()

    def commit(self, problem_id, technique, operation, status=200, **extra):
        return self.post('/api/approach', status, problemId=problem_id, technique=technique, operation=operation, **extra)

    def solve(self, problem_id, code=None):
        p = app.problem_by_id(problem_id)
        return self.post('/api/execute', problemId=problem_id, code=code or p['solution'], args=p['example']['args'])

    # ---------------------------------------------------------------- Discover
    def test_library_hides_the_approach_and_private_modification_parts(self):
        rows = self.client.get('/api/problems').get_json()
        self.assertEqual(len(rows), 24)
        payload = json.dumps(rows)
        for p in app.PROBLEMS:
            self.assertNotIn(p['approach']['operation'], payload)
            self.assertNotIn(json.dumps(p['modification']['solution'])[1:-1], payload)
            self.assertNotIn(p['modification']['insight'], payload)
        self.assertNotIn('approach', rows[0])
        self.assertEqual(set(rows[0]['modification']), {'id', 'title', 'statement', 'returns', 'question', 'example', 'hints'})

    def test_commitment_reveals_and_explains_the_reasoning_gap(self):
        plan = 'For each x compute target - x and look it up in a dict of value -> index; check before storing x.'
        match = self.commit('two-sum', 'Hash map / set', plan)
        self.assertEqual(match['verdict'], 'match')
        self.assertEqual(len(match['resolved']), 3, match)
        self.assertEqual(match['intended']['technique'], 'Hash map / set')
        self.assertTrue(match['first'])
        self.assertFalse(match['guided'])
        partial = self.commit('two-sum', 'Hash map / set', 'remember the numbers I have already seen')
        self.assertIn('Should the current value be stored before or after', ' '.join(partial['unresolved']))
        self.assertFalse(partial['first'])
        self.assertEqual(partial['firstCommitment']['operation'], plan)  # The first hypothesis is the evidence.
        different = self.commit('palindrome', 'Hash map / set', 'count characters and compare the counts')
        self.assertEqual(different['verdict'], 'different')
        self.assertIn('relies on remembering earlier information', different['gap'])
        self.assertIn('Two pointers', different['gap'])
        self.assertEqual(self.commit('longest-unique', 'Hash map / set', 'remember where each character was last seen')['verdict'], 'partial')
        brute = self.commit('max-window-sum', 'Direct iteration / brute force', 'sum every group of k values')
        self.assertEqual(brute['verdict'], 'starting-point')
        self.assertIn('Neighboring groups share', brute['gap'])

    def test_commitment_requires_a_hypothesis_and_records_guidance_honestly(self):
        self.commit('two-sum', 'Hash map / set', 'too short', status=400)
        self.commit('two-sum', 'Magic', 'look up partners quickly', status=400)
        guided = self.commit('palindrome', 'Two pointers', 'compare characters from both ends', topicKnown=True, cluesRevealed=1)
        self.assertTrue(guided['guided'])
        self.assertEqual(len(guided['reasons']), 2)
        self.post('/api/hint', problemId='binary-search', level=1)
        self.assertIn('you used hints or the guide on this problem', self.commit('binary-search', 'Binary search', 'compare with the middle and discard half')['reasons'])

    def test_guide_withholds_the_topic_until_commitment(self):
        with app.app.test_request_context():
            before = app.tutor_context('local-learner', app.problem_by_id('palindrome'), {'stage': 'discover'})
        self.assertNotIn('category', before['metadata'])
        self.assertIsNone(before['approach'])
        self.commit('palindrome', 'Two pointers', 'compare characters from both ends moving inward')
        with app.app.test_request_context():
            after = app.tutor_context('local-learner', app.problem_by_id('palindrome'), {'stage': 'discover'})
        self.assertEqual(after['metadata']['category'], 'Two pointers')
        reply = self.post('/api/chat', message='What next?', context={'problemId': 'palindrome', 'stage': 'discover'})
        self.assertIn('You committed to Two pointers', reply['text'])

    # --------------------------------------------------------------- Debugging
    def test_traced_failing_input_points_to_the_observable_return_and_its_origin(self):
        code = 'def solve(nums, k):\n    best = 0\n    for i in range(len(nums) - k + 1):\n        total = sum(nums[i:i + k])\n        if total > best:\n            best = total\n    return best'
        case = next(t for t in app.problem_by_id('max-window-sum')['tests'] if t['name'] == 'Negative values')
        run = self.post('/api/execute', problemId='max-window-sum', code=code, args=case['args'])
        self.assertFalse(run['passed'])
        divergence = run['divergence']
        self.assertEqual(divergence['kind'], 'Observed result mismatch')
        returned = run['events'][divergence['step']]
        self.assertEqual(returned['type'], 'RETURN')
        self.assertIn('does not establish the first incorrect intermediate step', divergence['message'])
        self.assertEqual(divergence['origin']['name'], 'best')
        self.assertTrue(divergence['origin']['unchanged'] is False)
        self.assertEqual(run['events'][divergence['origin']['step']]['line'], 2)  # best = 0 was never improved.
        reply = self.post('/api/chat', message='What is wrong with my code?', context={'problemId': 'max-window-sum', 'attemptId': run['attemptId'], 'code': code, 'args': case['args']})
        self.assertIn('`best` last changed at step', reply['text'])

    def test_divergence_reports_contract_types_and_untouched_inputs(self):
        run = self.post('/api/execute', problemId='move-zeroes', code='def solve(nums):\n    return nums', args=[[0, 1]], test=False)
        self.assertTrue(run['divergence']['origin']['unchanged'])
        run = self.post('/api/execute', problemId='average-window', code='def solve(nums, k):\n    return 9', args=[[1, 9], 1], test=False)
        self.assertEqual(run['divergence']['kind'], 'Output contract mismatch')
        self.assertIn('Returned 9, an integer; the contract asks for a float', run['divergence']['message'])
        run = self.post('/api/execute', problemId='two-sum', code='def solve(nums, target):\n    return nums[99]', test=False)
        self.assertEqual(run['divergence']['kind'], 'First recorded runtime failure')
        self.assertIsNone(self.post('/api/execute', problemId='two-sum', code=app.problem_by_id('two-sum')['solution'], test=False)['divergence'])

    # ------------------------------------------------------------ Modification
    def test_modification_requires_adapted_code_and_records_evidence(self):
        p = app.problem_by_id('two-sum')
        variant = app.problem_by_id('two-sum-modified')
        self.assertEqual(variant['parent'], 'two-sum')
        original = self.post('/api/execute', problemId=variant['id'], code=p['solution'], args=variant['example']['args'])
        self.assertFalse(original['passed'])  # The original approach does not satisfy the new contract.
        self.assertTrue(all(t['name'] for t in original['tests']))
        self.post('/api/progress', 400, problemId='two-sum', stage='Modified', attemptId=original['attemptId'], evidence='Counts instead of positions now.')
        solved_original = self.solve('two-sum')
        self.post('/api/progress', 400, problemId='two-sum', stage='Modified', attemptId=solved_original['attemptId'], evidence='Counts instead of positions now.')
        adapted = self.post('/api/execute', problemId=variant['id'], code=variant['solution'], args=variant['example']['args'])
        self.assertTrue(adapted['passed'])
        self.post('/api/progress', 400, problemId='two-sum', stage='Modified', attemptId=adapted['attemptId'], evidence='short')
        self.post('/api/progress', 400, problemId=variant['id'], stage='Modified', attemptId=adapted['attemptId'], evidence='Counts instead of positions now.')
        self.post('/api/progress', problemId='two-sum', stage='Independent', attemptId=solved_original['attemptId'])
        saved = self.post('/api/progress', problemId='two-sum', stage='Modified', attemptId=adapted['attemptId'], evidence='Store counts per value instead of one index.')
        self.assertEqual(saved['stage'], 'Independent')  # The ladder never regresses...
        self.assertIn('frequency', saved['insight'])
        evidence = self.client.get('/api/progress').get_json()['evidence']
        self.assertEqual([e['kind'] for e in evidence], ['modified'])  # ...but the adaptation is still recorded.

    def test_revealed_modification_reference_is_not_adaptation(self):
        variant = app.problem_by_id('palindrome-modified')
        self.client.get('/api/problems/palindrome-modified/solution')
        run = self.post('/api/execute', problemId=variant['id'], code=variant['solution'], args=variant['example']['args'])
        self.post('/api/progress', 400, problemId='palindrome', stage='Modified', attemptId=run['attemptId'], evidence='Two branches after a mismatch.')

    def test_modification_keeps_input_rules_and_guide_context(self):
        with self.assertRaises(ValueError):
            app.valid_args(app.problem_by_id('binary-search-modified'), [[3, 1], 1])
        hint = self.post('/api/hint', problemId='two-sum-modified', level=1)
        self.assertIn('Is it enough to count', hint['text'])
        reply = self.post('/api/chat', message='Help', context={'problemId': 'two-sum-modified', 'stage': 'code'})
        self.assertIn('The changed requirement', reply['text'])
        self.assertIn('Which part of your solution still holds', reply['text'])
        with app.connect() as db:
            self.assertGreaterEqual(app.support_row(db, 'local-learner', 'two-sum-modified')['hint_level'], 1)  # Help on the change is recorded on the change.

    # ---------------------------------------------------------------- Transfer
    def test_transfer_requires_prior_solution_and_unaided_matching_commitment(self):
        source, target = app.problem_by_id('palindrome'), app.problem_by_id('reverse-string')
        self.assertEqual(source['transfer'], target['id'])
        self.solve(source['id'])
        self.commit(target['id'], 'Two pointers', 'swap the mirrored characters from both ends inward', transferFrom=source['id'])
        solved = self.solve(target['id'])
        saved = self.post('/api/progress', problemId=target['id'], stage='Independent', attemptId=solved['attemptId'])
        self.assertEqual(saved['transferred'], [source['id']])
        progress = self.client.get('/api/progress').get_json()
        self.assertEqual(next(r['stage'] for r in progress['progress'] if r['problem_id'] == source['id']), 'Transferred')
        record = next(e for e in progress['evidence'] if e['kind'] == 'transferred')
        self.assertTrue(record['detail']['prompted'])
        self.post('/api/progress', 400, problemId=source['id'], stage='Transferred', attemptId=solved['attemptId'])

    def test_transfer_is_not_manufactured(self):
        # Committed before solving the source problem.
        self.commit('first-occurrence', 'Binary search', 'find a match then keep searching left')
        self.solve('binary-search')
        run = self.solve('first-occurrence')
        self.assertEqual(self.post('/api/progress', problemId='first-occurrence', stage='Reproduced', attemptId=run['attemptId'])['transferred'], [])
        # Guided recognition, and a wrong first hypothesis, are not transfer.
        self.solve('max-window-sum')
        self.commit('average-window', 'Sliding window', 'add the entering value and remove the leaving one', topicKnown=True)
        run = self.solve('average-window')
        self.assertEqual(self.post('/api/progress', problemId='average-window', stage='Independent', attemptId=run['attemptId'])['transferred'], [])
        self.solve('valid-anagram')
        self.commit('first-unique', 'Two pointers', 'compare characters from both ends of the string')
        self.commit('first-unique', 'Hash map / set', 'count every character then scan again in order')
        run = self.solve('first-unique')
        self.assertEqual(self.post('/api/progress', problemId='first-unique', stage='Independent', attemptId=run['attemptId'])['transferred'], [])

    def test_lower_stage_keeps_higher_stage_evidence(self):
        reflection = 'The dictionary holds every earlier value, so the partner is found once.'
        self.post('/api/progress', problemId='two-sum', stage='Explained', evidence=reflection)
        self.post('/api/progress', problemId='two-sum', stage='Understood')
        row = next(r for r in self.client.get('/api/progress').get_json()['progress'] if r['problem_id'] == 'two-sum')
        self.assertEqual(json.loads(row['evidence']), reflection)


class CurriculumTests(unittest.TestCase):
    def test_every_modification_requires_adaptation(self):
        for p in app.PROBLEMS:
            m = p['modification']
            failures = 0
            for case in m['tests']:
                with self.subTest(problem=p['id'], case=case['name']):
                    trace = app.execute_worker({'code': m['solution'], 'args': copy.deepcopy(case['args'])})
                    self.assertIsNone(trace['error'])
                    self.assertTrue(app.correct(app.VARIANTS[m['id']], trace['result'], case['args'], case['expected']), trace['result'])
                original = app.execute_worker({'code': p['solution'], 'args': copy.deepcopy(case['args'])})
                failures += bool(original['error']) or not app.correct(app.VARIANTS[m['id']], original['result'], case['args'], case['expected'])
            self.assertGreater(failures, 0, f"{p['id']}: the original solution already satisfies the changed requirement")

    def test_approach_vocabulary_matches_the_learner_interface(self):
        interface = (ROOT / 'src' / 'learningContent.ts').read_text(encoding='utf-8')
        for technique in app.TECHNIQUES:
            self.assertIn(f"'{technique}'", interface)
        for p in app.PROBLEMS:
            self.assertIn(p['approach']['technique'], app.TECHNIQUES)
            self.assertTrue(set(p['approach']['alternatives']) <= set(app.TECHNIQUES) - {p['approach']['technique']})
            for checkpoint in p['approach']['checkpoints']:
                re.compile(checkpoint['pattern'])


if __name__ == '__main__':
    unittest.main()


class VisualEvidenceTests(unittest.TestCase):
    """Evidence that powers the visual stage: every claim must be provable from the recorded run."""
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        db = patch.object(app, 'DB', os.path.join(self.directory.name, 'visual.sqlite3'))
        db.start()
        self.addCleanup(db.stop)
        app.initialize()
        self.client = app.app.test_client()

    def preview(self, problem_id, code, args=None):
        body = {'problemId': problem_id, 'code': code, **({'args': args} if args is not None else {})}
        response = self.client.post('/api/preview', json=body)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_a_repeated_while_state_proves_an_infinite_loop(self):
        code = 'def solve(nums, target):\n    left = 0\n    right = len(nums) - 1\n    while left < right:\n        total = nums[left] + nums[right]\n        if total < target:\n            left = left\n        else:\n            right -= 1\n    return []'
        run = self.preview('two-sum-sorted', code, [[1, 2, 3], 9])
        self.assertEqual(run['divergence']['kind'], 'Proven infinite loop')
        cycle = run['divergence']['cycle']
        first, repeat = run['events'][cycle['first']], run['events'][cycle['repeat']]
        self.assertEqual((first['type'], repeat['type'], first['line'], repeat['line']), ('LOOP_START', 'LOOP_START', 4, 4))
        self.assertEqual(first['state'], repeat['state'])  # The claim is visible in the recorded snapshots.
        self.assertLess(len(run['events']), 60)  # Found at the repeat, long before the execution budget.

    def test_hidden_iterator_state_is_never_called_a_cycle(self):
        code = 'def solve(nums):\n    z = zip(nums)\n    done = False\n    x = 0\n    while not done:\n        done = True\n        for t in z:\n            x = t[0]\n            done = False\n            break\n    return x'
        trace = app.execute_worker({'code': code, 'args': [[5, 5]]})
        self.assertIsNone(trace['error'])
        self.assertEqual(trace['result'], 5)
        for code in ['def solve(nums):\n    k = 0\n    while k < 3:\n        k += 1\n    return k', 'def solve(nums):\n    total = 0\n    for x in nums:\n        total += 0\n    return total']:
            self.assertIsNone(app.execute_worker({'code': code, 'args': [[3, 3, 3]]})['error'])

    def test_failed_reads_and_line_counts_are_recorded(self):
        run = self.preview('two-sum', 'def solve(nums, target):\n    i = len(nums)\n    return [nums[i], 0]', [[4, 5], 9])
        self.assertEqual(run['divergence']['access'], {'structure': 'nums', 'key': 2, 'index': 'i', 'size': 2, 'kind': 'sequence'})
        run = self.preview('two-sum', app.problem_by_id('two-sum')['solution'], [[2, 7, 11], 9])
        self.assertEqual(run['lines'], {'2': 1, '3': 2, '4': 2, '5': 2, '6': 1, '7': 1})  # `return []` never ran.
        self.assertIn('need', [e['meta'].get('index') for e in run['events']])

    def test_preview_goal_and_honest_in_progress_states(self):
        correct = self.preview('two-sum', app.problem_by_id('two-sum')['solution'])
        self.assertEqual(correct['goal'], {'expected': [0, 1], 'matches': True})
        self.assertIsNone(correct['divergence'])
        self.assertFalse(correct['passed'])  # A preview is never a test pass.
        unfinished = self.preview('two-sum', 'def solve(nums, target):\n    seen = {}\n    for i, x in enumerate(nums):\n        seen[x] = i')
        self.assertEqual(unfinished['divergence']['kind'], 'Nothing returned yet')
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 0)

    def test_wrong_elements_name_the_write_that_kept_them(self):
        code = 'def solve(nums, other):\n    result = []\n    i = 0\n    while i < len(nums):\n        result.append(nums[i])\n        result.append(other[i])\n        i += 1\n    return result'
        run = self.preview('merge-sorted', code, [[1, 4], [2, 3]])
        elements = run['divergence']['elements']
        self.assertEqual([(w['position'], w['value'], w['goal']) for w in elements['wrong']], [(2, 4, 3), (3, 3, 4)])
        for wrong in elements['wrong']:
            after = next(s for s in run['events'][wrong['step']]['state']['structures'] if s['id'] == 'result')['values']
            before = next((s for s in run['events'][wrong['step'] - 1]['state']['structures'] if s['id'] == 'result'), {'values': []})['values']
            self.assertEqual(after[wrong['position']], wrong['value'])  # This step wrote the value...
            self.assertLessEqual(len(before), wrong['position'])  # ...which was not there before it.
        surplus = self.preview('unique-values', 'def solve(nums):\n    result = []\n    for x in nums:\n        result.append(x)\n    return result', [[2, 2, 7]])
        self.assertEqual([w['position'] for w in surplus['divergence']['elements']['wrong']], [1])  # The second 2 is the surplus.
        reply = self.client.post('/api/chat', json={'message': 'What is wrong with my code?', 'context': {'problemId': 'merge-sorted', 'traceId': run['traceId'], 'code': code, 'args': [[1, 4], [2, 3]]}}).get_json()
        self.assertIn('Position 2 of `result` received 4', reply['text'])


class CaseDeckTests(unittest.TestCase):
    """Every live update traces every case, each with its own evidence."""
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        db = patch.object(app, 'DB', os.path.join(self.directory.name, 'cases.sqlite3'))
        db.start()
        self.addCleanup(db.stop)
        app.initialize()
        self.client = app.app.test_client()

    def test_every_authored_case_and_your_input_are_traced(self):
        p = app.problem_by_id('two-sum')
        self.assertGreaterEqual(len(p['tests']), 6)
        code = 'def solve(nums, target):\n    seen = {}\n    for i, x in enumerate(nums):\n        seen[x] = i\n        if target - x in seen:\n            return [seen[target - x], i]\n    return []'
        run = self.client.post('/api/preview', json={'problemId': 'two-sum', 'code': code, 'args': [[1, 2], 3]}).get_json()
        self.assertEqual([c['name'] for c in run['cases']], [t['name'] for t in p['tests']] + ['Your input'])
        self.assertEqual(run['caseId'], 'custom')
        for case, test in zip(run['cases'], p['tests']):
            self.assertEqual(case['input'], test['args'])
            self.assertTrue(case['events'])
            self.assertEqual(case['goal']['matches'], app.correct(p, case['result'], test['args'], test['expected']))
        verdicts = {c['name']: c['goal']['matches'] for c in run['cases']}
        self.assertFalse(verdicts['Repeated values'])  # [3, 3] reuses one position with this bug...
        self.assertTrue(verdicts['Example'])  # ...while the example still passes.
        self.assertEqual(len({c['traceId'] for c in run['cases']}), len(run['cases']))
        repeated = next(c for c in run['cases'] if c['name'] == 'Repeated values')
        reply = self.client.post('/api/chat', json={'message': 'What is wrong with my code?', 'context': {'problemId': 'two-sum', 'traceId': repeated['traceId'], 'code': code, 'args': repeated['input']}}).get_json()
        self.assertIn('First observable contract violation', reply['text'])

    def test_one_runaway_case_does_not_stop_the_others(self):
        run = self.client.post('/api/preview', json={'problemId': 'max-window-sum', 'code': 'def solve(nums, k):\n    while k > len(nums) - 1:\n        pass\n    return sum(nums[:k])'}).get_json()
        by_name = {c['name']: c for c in run['cases']}
        self.assertEqual(by_name['Whole array']['divergence']['kind'], 'Proven infinite loop')  # k == len(nums) loops forever.
        self.assertIsNone(by_name['Example']['error'])
        self.assertTrue(by_name['Example']['events'])

    def test_explicit_runs_record_only_the_main_input(self):
        p = app.problem_by_id('palindrome')
        run = self.client.post('/api/execute', json={'problemId': 'palindrome', 'code': p['solution'], 'args': ['noon']}).get_json()
        self.assertEqual(run['caseId'], 'custom')
        self.assertEqual(len(run['tests']), len(p['tests']))
        self.assertTrue(all(t['passed'] for t in run['tests']))
        self.assertEqual(len(run['cases']), len(p['tests']) + 1)
        with app.connect() as db:
            rows = db.execute('SELECT input, passed FROM attempts').fetchall()
        self.assertEqual([(json.loads(r['input']), r['passed']) for r in rows], [(['noon'], 1)])
