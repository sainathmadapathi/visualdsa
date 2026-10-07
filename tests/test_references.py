import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch

# Importing app initializes its database: isolate it before the import, never touch learning.sqlite3.
os.environ['DSA_DATABASE'] = os.path.join(tempfile.mkdtemp(), 'import.sqlite3')  # Never the real database.
import app  # noqa: E402
import references  # noqa: E402

# The problems as their takeuforward pages give them: each page's examples, exactly as read into a learner's lab.
SUDOKU_1 = [list('53..7....'), list('6..195...'), list('.98....6.'), list('8...6...3'), list('4..8.3..1'), list('7...2...6'), list('.6....28.'), list('...419..5'), list('....8..79')]
SUDOKU_2 = [list('......7..'), list('7.5...9..'), list('...975431'), list('9...41..7'), list('.5.8.764.'), list('.7..2....'), list('.4.....69'), list('16.43....'), list('....623.4')]
SOLVED_2 = [list('419386752'), list('735214986'), list('826975431'), list('983641527'), list('251897643'), list('674523198'), list('347158269'), list('162439875'), list('598762314')]
PAGES = {
    'sudoku': dict(title='Sudoku Solver', params=['board'], source='https://takeuforward.org/practice/dsa/sudoko-solver',
                   cases=[{'name': 'Example 1', 'args': [SUDOKU_1], 'expected': references.SOLVED}, {'name': 'Example 2', 'args': [SUDOKU_2], 'expected': SOLVED_2}]),
    'prime': dict(title='Check if a Number is Prime or Not', params=['num'], source='https://takeuforward.org/practice/dsa/check-if-a-number-is-prime-or-not',
                  cases=[{'name': 'Example 1', 'args': [5], 'expected': True}, {'name': 'Example 2', 'args': [15], 'expected': False}]),
    'depth': dict(title='Maximum Depth in BT', params=['root'], kinds={'root': 'tree'}, source='https://takeuforward.org/practice/dsa/maximum-depth-in-bt',
                  cases=[{'name': 'Example 1', 'args': [[1, 2, 3, None, None, None, 6]], 'expected': 3}, {'name': 'Example 2', 'args': [[3, 9, 20, None, None, 15, 7]], 'expected': 3}]),
    'merge': dict(title='Merge Sorting', params=['nums'], source='https://takeuforward.org/practice/dsa/merge-sorting',
                  cases=[{'name': 'Example 1', 'args': [[7, 4, 1, 5, 3]], 'expected': [1, 3, 4, 5, 7]}, {'name': 'Example 2', 'args': [[5, 4, 4, 1, 1]], 'expected': [1, 1, 4, 4, 5]}]),
    'insertion': dict(title='Insertion Sorting', params=['nums'], source='https://takeuforward.org/practice/dsa/insertion-sorting',
                      cases=[{'name': 'Example 1', 'args': [[7, 4, 1, 5, 3]], 'expected': [1, 3, 4, 5, 7]}, {'name': 'Example 2', 'args': [[5, 4, 4, 1, 1]], 'expected': [1, 1, 4, 4, 5]}]),
}
LEARNER_SUDOKU = """def solve(board):
    def ok(r, c, d):
        for i in range(9):
            if board[r][i] == d or board[i][c] == d:
                return False
        for i in range(r // 3 * 3, r // 3 * 3 + 3):
            for j in range(c // 3 * 3, c // 3 * 3 + 3):
                if board[i][j] == d:
                    return False
        return True
    def go():
        for r in range(9):
            for c in range(9):
                if board[r][c] == '.':
                    for d in '123456789':
                        if ok(r, c, d):
                            board[r][c] = d
                            if go():
                                return True
                            board[r][c] = '.'
                    return False
        return True
    go()
"""


class ReferenceTests(unittest.TestCase):
    """A learner's own lab, read from a problem page, gets the reference this platform wrote for that page only
    when it reproduces the lab's own cases; what it computes is marked computed and the reference never leaves."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        db = patch.object(app, 'DB', os.path.join(self.directory.name, 'refs.sqlite3'))
        db.start()
        self.addCleanup(db.stop)
        env = patch.dict(os.environ, {'LLM_API_KEY': '', 'APP_ENV': 'development', 'FIREBASE_PROJECT_ID': ''})
        env.start()
        self.addCleanup(env.stop)
        app.initialize()
        self.client = app.app.test_client()
        app.REFERENCE_CHECKS.clear()

    def post(self, path, status=200, **body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, status, response.get_json())
        return response.get_json()

    def lab(self, page, **change):
        spec = {**copy.deepcopy(PAGES[page]), **change}
        sheet = self.post('/api/sheets', name=f'Sheet {page}', source='paste', origin='', rows=[{'title': spec['title'], 'url': '', 'difficulty': '', 'topic': '', 'match': None, 'fit': None, 'lab': None}])
        sheet_id = next(s['id'] for s in sheet['sheets'] if s['name'] == f'Sheet {page}')
        made = self.post('/api/labs', sheetId=sheet_id, row=0, title=spec['title'], statement=f"{spec['title']}: as stated on its page.", params=spec['params'],
                         cases=spec['cases'], kinds=spec.get('kinds', {}), source=spec['source'])
        return made['lab']['id']

    def problem(self, lab_id):
        return app.problem_by_id(lab_id, 'local-learner')

    def test_every_reference_reproduces_its_pages_examples_and_adds_checked_edge_cases(self):
        expected = {
            'prime': [False, True, False, False, True, False],                    # 1, 2, 4, 49, 9973, 10000
            'depth': [1, 4, 3, 3],
            'merge': [[42], [1, 2], [3, 3, 3], [-10, -10, -5, 0, 10], [1, 2, 3, 4, 5], [1, 3, 5, 7, 9], [-10000, 0, 10000]],
            'sudoku': [references.SOLVED] * 5,                                   # Each edge board has exactly one solution.
        }
        expected['insertion'] = expected['merge']
        for page, answers in expected.items():
            with self.subTest(page):
                p = self.problem(self.lab(page))
                self.assertIn('reference', p)
                computed = [case for case in p['tests'] if case.get('computed')]
                self.assertEqual([case['expected'] for case in computed], answers)
                self.assertEqual(len(p['tests']), 2 + len(answers))
                self.assertEqual(len(p['cases']), 2)  # The learner's own cases are unchanged.

    def test_a_lab_whose_cases_the_reference_does_not_reproduce_gets_nothing(self):
        cases = copy.deepcopy(PAGES['prime']['cases'])
        cases[1]['expected'] = True  # 15 is not prime: this lab's specification disagrees with the reference.
        p = self.problem(self.lab('prime', cases=cases))
        self.assertNotIn('reference', p)
        self.assertEqual(len(p['tests']), 2)
        run = self.post('/api/preview', problemId=p['id'], code='def solve(num):\n    return num > 1', args=[7])
        self.assertIsNone(run['goal'])  # No checked reference: an input outside the cases has no known answer.

    def test_your_own_input_gets_a_computed_goal_marked_as_computed(self):
        lab_id = self.lab('prime')
        run = self.post('/api/preview', problemId=lab_id, code='def solve(num):\n    return num > 1', args=[91])
        self.assertEqual(run['goal'], {'expected': False, 'matches': False, 'computed': True})  # 91 = 7 × 13.
        by_name = {case['name']: case for case in run['cases']}
        self.assertFalse(by_name['Example 1']['computed'])
        self.assertNotIn('computed', by_name['Example 1']['goal'])  # The page's own example.
        self.assertTrue(by_name['A large prime']['computed'] and by_name['A large prime']['goal']['computed'])
        self.assertTrue(by_name['Your input']['custom'] and by_name['Your input']['computed'])

    def test_an_in_place_sudoku_is_judged_by_the_board_it_leaves(self):
        lab_id = self.lab('sudoku')
        run = self.post('/api/execute', problemId=lab_id, code=LEARNER_SUDOKU, args=[SUDOKU_1])
        tests = {t['name']: t for t in run['tests']}
        for name in ('Already solved', 'One empty cell', 'Empty main diagonal', 'One empty row', 'One empty column'):
            with self.subTest(name):
                self.assertTrue(tests[name]['passed'], tests[name])
                self.assertTrue(tests[name]['computed'])
                self.assertEqual(tests[name]['actual'], references.SOLVED)
        # A whole puzzle is longer than a trace records: its first steps are traced, and a full run of the same code
        # judges the page's own examples on the boards it leaves.
        for name in ('Example 1', 'Example 2'):
            with self.subTest(name):
                self.assertTrue(tests[name]['passed'], tests[name])
                self.assertFalse(tests[name].get('computed'), 'the page gives these outputs')
        self.assertTrue(all(c['fullRun'] for c in run['cases'] if c['name'] in ('Example 1', 'Example 2')))
        self.assertTrue(run['passed'] and all(t['passed'] for t in run['tests']))
        # A contract that returns its answer is still judged by what it returns.
        prime = self.post('/api/execute', problemId=self.lab('prime'), code='def solve(num):\n    pass', args=[5])
        self.assertFalse(any(t['passed'] for t in prime['tests']))

    def test_the_reference_never_leaves_the_server(self):
        lab_id = self.lab('sudoku')
        bodies = [self.client.get('/api/sheets').get_data(as_text=True), self.client.get('/api/problems').get_data(as_text=True),
                  json.dumps(self.post('/api/preview', problemId=lab_id, code=LEARNER_SUDOKU, args=[references.emptied([(4, 4)])])),
                  json.dumps(self.post('/api/execute', problemId=lab_id, code=LEARNER_SUDOKU, args=[references.emptied([(0, 0)])]))]
        for body in bodies:
            self.assertNotIn('def fill():', body)
            self.assertNotIn('"reference"', body)
        self.assertEqual(self.client.get(f'/api/problems/{lab_id}/solution').status_code, 404)

    def test_page_keys_ignore_scheme_www_query_and_trailing_slash(self):
        self.assertEqual(references.key('https://www.TakeUForward.org/practice/dsa/sudoko-solver/?tab=1#x'), 'takeuforward.org/practice/dsa/sudoko-solver')
        self.assertIsNone(references.find('https://takeuforward.org/practice/dsa/unknown'))
        self.assertIsNone(references.find(''))


if __name__ == '__main__':
    unittest.main()


class FullRunVerdicts(unittest.TestCase):
    """A case whose trace stops at the trace's own limits is judged by a full run of the same code (no steps recorded)."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        db = patch.object(app, 'DB', os.path.join(self.directory.name, 'full.sqlite3'))
        db.start()
        self.addCleanup(db.stop)
        env = patch.dict(os.environ, {'LLM_API_KEY': '', 'APP_ENV': 'development', 'FIREBASE_PROJECT_ID': ''})
        env.start()
        self.addCleanup(env.stop)
        app.initialize()

    def test_a_long_search_is_judged_to_the_end_and_its_trace_is_its_first_steps(self):
        runs = app.run_cases(LEARNER_SUDOKU, [[SUDOKU_1], [SUDOKU_2]], None, 'solve', 'in-place')
        self.assertTrue(all(app.limited(run) for run in runs), 'the traces stop at their limits')
        p = {'params': ['board'], 'kinds': {}, 'entry': 'solve', 'answer': 'in-place'}
        cases = [{'args': [SUDOKU_1]}, {'args': [SUDOKU_2]}]
        judged = app.with_full_runs(p, LEARNER_SUDOKU, cases, runs)
        self.assertEqual([run['result'] for run in judged], [app.result_value(references.SOLVED), SOLVED_2])
        for run in judged:
            self.assertEqual((run['error'], run['truncated'], run['fullRun']), (None, True, True))
            self.assertFalse(any(e['type'] == 'ERROR' for e in run['events']), 'the trace stopped recording; the program did not fail')

    def test_a_program_that_never_finishes_says_so_even_unrecorded(self):
        code = 'def solve(board):\n    n = 0\n    while n >= 0:\n        n += 1\n    return board\n'
        p = {'params': ['board'], 'kinds': {}, 'entry': 'solve', 'answer': None}
        run = app.with_full_runs(p, code, [{'args': [[1]]}], app.run_cases(code, [[[1]]]))[0]
        self.assertEqual(run['error']['failure']['unfinished'], app.QUIET_SECONDS)
        import errors
        self.assertIn("still hadn't finished", errors.explain(run['error'], run['error']['failure'], code, ['board'])['detail'])
