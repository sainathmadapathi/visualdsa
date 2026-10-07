"""What stopped a learner's program is explained in their own names and values, from facts the runner recorded."""
import os
import tempfile
import unittest
from unittest.mock import patch

# Importing app initializes its database: isolate it before the import, never touch learning.sqlite3.
os.environ['DSA_DATABASE'] = os.path.join(tempfile.mkdtemp(), 'import.sqlite3')  # Never the real database.
import app  # noqa: E402
import errors  # noqa: E402


def stopped(code, args):
    """The explanation for code that fails on these inputs, as the API gives it."""
    run = app.run_cases(code, [args])[0]
    return errors.explain(run['error'], run['error'].get('failure'), code, ['nums'], 'solve')


class ExplainedFromWhatFailed(unittest.TestCase):
    def test_a_none_pointer_names_the_variable_that_is_none(self):
        told = stopped('def solve(nums):\n    curr = None\n    return curr.next\n', [[1]])
        self.assertEqual((told['title'], told['line']), ('`curr` is None', 3))
        self.assertIn('`curr.next`', told['detail'])
        # Setting a field on None names the chain that is None, not Python's NoneType.
        told = stopped('class N:\n    def __init__(self):\n        self.next = None\n\ndef solve(nums):\n    curr = N()\n    curr.next.next = 5\n    return 1\n', [[1]])
        self.assertEqual(told['title'], '`curr.next` is None')
        self.assertNotIn('NoneType', told['detail'] + told['title'])

    def test_positions_and_keys_say_what_was_asked_and_what_exists(self):
        told = stopped('def solve(nums):\n    i = 0\n    while True:\n        x = nums[i]\n        i += 1\n', [[1, 2, 3]])
        self.assertEqual(told['title'], 'nums[i] is outside the list')
        self.assertIn('i = 3, but nums has 3 items: positions 0 to 2', told['detail'])
        self.assertEqual(stopped('def solve(nums):\n    best = []\n    return best[0]\n', [[1]])['title'], 'best is empty')
        self.assertIn('3 characters', stopped('def solve(nums):\n    return nums[10]\n', ['abc'])['detail'])
        self.assertEqual(stopped('def solve(nums):\n    counts = {}\n    for x in nums:\n        counts[x] = counts[x] + 1\n    return counts\n', [[1, 2]])['title'], 'Key 1 is not in counts')
        self.assertEqual(stopped("def solve(nums):\n    return nums['a']\n", [[1]])['title'], 'Positions in nums are whole numbers')

    def test_operations_name_the_operand_at_fault(self):
        told = stopped('def solve(nums):\n    total = sum(nums)\n    count = 0\n    return total / count\n', [[1, 2]])
        self.assertEqual(told['detail'], '`total / count` divides by `count`, which is 0 here.')
        told = stopped('def helper(x):\n    x + 1\n\ndef solve(nums):\n    total = helper(1)\n    return total + 1\n', [[1]])
        self.assertEqual(told['title'], '`total` is None')
        self.assertIn('Did a function return nothing?', told['hint'])
        self.assertEqual(stopped('def solve(nums):\n    best = None\n    for x in nums:\n        if x > best:\n            best = x\n    return best\n', [[1]])['title'], '`best` is None in a comparison')
        self.assertEqual(stopped('def solve(nums):\n    seen = None\n    return 3 in seen\n', [[1]])['title'], '`seen` is None')

    def test_emptied_collections_and_missing_items(self):
        self.assertEqual(stopped('def solve(nums):\n    stack = []\n    return stack.pop()\n', [[1]])['title'], '`stack` is empty')
        self.assertEqual(stopped('from collections import deque\ndef solve(nums):\n    queue = deque()\n    return queue.popleft()\n', [[1]])['title'], '`queue` is empty')
        self.assertEqual(stopped('import heapq\ndef solve(nums):\n    heap = []\n    return heapq.heappop(heap)\n', [[1]])['title'], '`heap` is empty')
        self.assertEqual(stopped('from heapq import heappop\ndef solve(nums):\n    heap = []\n    return heappop(heap)\n', [[1]])['title'], '`heap` is empty')
        self.assertEqual(stopped('def solve(nums):\n    return nums.index(9)\n', [[1, 2]])['title'], '9 is not in `nums`')

    def test_names_scope_recursion_and_limits(self):
        self.assertEqual(stopped('def solve(nums):\n    total = 0\n    return totl\n', [[1]])['hint'], 'Did you mean `total`?')
        self.assertEqual(stopped('def solve(nums):\n    if nums[0] > 5:\n        best = 1\n    return best\n', [[1]])['title'], "`best` is read before it's set")
        self.assertEqual(stopped('def solve(nums):\n    return solve(nums) + 1\n', [[1]])['title'], 'The calls went too deep')
        told = stopped('def solve(nums):\n    total = 0\n    i = 0\n    while i < 10 ** 6:\n        total += i\n        i += 1\n    return total\n', [[1]])
        self.assertEqual((told['title'], told['line']), ('The program ran too many steps', 6), 'a stopped loop still says where it was')
        self.assertEqual(stopped('def solve(nums):\n    i = 0\n    while i < 3:\n        total = i\n    return 1\n', [[1]])['title'], 'Infinite loop, proven')
        told = stopped('def solve(nums, target, extra):\n    return 1\n', [[1]])
        self.assertEqual(told['title'], "solve's parameters don't match this problem")
        self.assertIn('solve(nums)', told['detail'])

    def test_python_jargon_and_runner_internals_never_reach_the_learner(self):
        programs = ['def solve(nums):\n    curr = None\n    return curr.next\n', 'def solve(nums):\n    return nums.encode()\n', 'def solve(nums):\n    total = None\n    return total + 1\n']
        for code in programs:
            told = stopped(code, ['abc'])
            for word in ('NoneType', '<student>', 'tracer', 'worker'):
                self.assertNotIn(word, told['title'] + told['detail'] + told['hint'])


class RefusedCodeIsExplained(unittest.TestCase):
    def refusal(self, code):
        try:
            app.validate_source(code)
        except (ValueError, SyntaxError) as exc:
            return errors.refused(exc)
        self.fail('the code was accepted')

    def test_syntax_errors_say_what_is_missing_where(self):
        self.assertEqual(self.refusal('def solve(n)\n    return n\n'), {'title': 'A colon is missing', 'detail': 'Line 1 starts a block (if, for, while, def, class or else) but does not end with a colon.', 'hint': 'What should come right after the condition or header on line 1?', 'line': 1})
        self.assertEqual(self.refusal('def solve(n):\n    x = (1, 2\n    return n\n')['title'], 'A bracket is never closed')
        self.assertEqual(self.refusal('def solve(n):\nreturn n\n')['title'], 'A block has no body')
        self.assertEqual(self.refusal("def solve(n):\n    s = 'abc\n    return n\n")['title'], 'A string is not closed')

    def test_unsupported_code_has_its_line_and_a_way_forward(self):
        told = self.refusal('def solve(n):\n    return lenn(n)\n')
        self.assertEqual((told['title'], told['hint'], told['line']), ('`lenn` isn\'t defined', 'Did you mean `len`?', 2))
        self.assertEqual(self.refusal('import os\ndef solve(n):\n    return n\n')['line'], 1)
        told = self.refusal('def solve(n):\n    return n\nprint(solve(3))\n')
        self.assertEqual((told['title'], told['line']), ('Code outside a function', 3))
        self.assertEqual(self.refusal('def helper(n):\n    return n\n')['title'], 'No solve function')
        # The first refusal is the first in the code, whatever the syntax tree's order.
        self.assertEqual(self.refusal('def solve(n):\n    if n:\n        return lenn(n)\n    return typo(n)\nimport os\n')['line'], 3)


class ApiCarriesExplanations(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        db = patch.object(app, 'DB', os.path.join(self.directory.name, 'errors.sqlite3'))
        db.start()
        self.addCleanup(db.stop)
        env = patch.dict(os.environ, {'LLM_API_KEY': '', 'APP_ENV': 'development', 'FIREBASE_PROJECT_ID': ''})
        env.start()
        self.addCleanup(env.stop)
        app.initialize()
        self.client = app.app.test_client()

    def test_a_refused_program_answers_with_its_line_and_explanation(self):
        response = self.client.post('/api/preview', json={'problemId': 'two-sum', 'code': 'def solve(nums, target)\n    return []\n'})
        body = response.get_json()
        self.assertEqual(response.status_code, 400)
        self.assertEqual((body['line'], body['code'], body['explanation']['title']), (1, True, 'A colon is missing'))
        self.assertNotIn('<student>', body['error'])
        # A request problem (not the code) gets no code explanation.
        body = self.client.post('/api/preview', json={'problemId': 'nope', 'code': 'def solve():\n    return 1'}).get_json()
        self.assertNotIn('explanation', body)

    def test_a_failing_trace_explains_its_error_event_and_divergence(self):
        code = 'def solve(nums, target):\n    i = 0\n    while True:\n        if nums[i] == target:\n            return [i]\n        i += 1\n'
        run = self.client.post('/api/preview', json={'problemId': 'two-sum', 'code': code, 'args': [[1, 2], 9]}).get_json()
        self.assertEqual(run['error']['explanation']['title'], 'nums[i] is outside the list')
        event = run['events'][-1]
        self.assertEqual((event['type'], event['explanation']['what']), ('ERROR', 'nums[i] is outside the list'))
        self.assertEqual(run['divergence']['title'], 'nums[i] is outside the list')
        self.assertIn('i = 2, but nums has 2 items', run['divergence']['message'])

    def test_returning_nothing_never_tells_the_answer(self):
        run = self.client.post('/api/preview', json={'problemId': 'two-sum', 'code': 'def solve(nums, target):\n    return None\n', 'args': [[2, 7, 11, 15], 9]}).get_json()
        self.assertEqual(run['divergence']['kind'], 'Nothing returned yet')
        self.assertNotIn('[0, 1]', run['divergence']['message'])


if __name__ == '__main__':
    unittest.main()


class FactsTravelWithTheException(unittest.TestCase):
    def test_an_object_of_the_learners_own_is_explained_where_it_failed(self):
        code = "class Box:\n    def __init__(self):\n        self.data = [1, 2]\n    def __getitem__(self, i):\n        return self.data[i]\n\ndef solve(nums):\n    b = Box()\n    return b[5]\n"
        told = stopped(code, [[1]])
        self.assertEqual((told['title'], told['line']), ('self.data[i] is outside the list', 5))
        # An object of the learner's own that raises IndexError itself has no size to state, and is still explained.
        own = "class Empty:\n    def __getitem__(self, i):\n        return [][i]\n\ndef solve(nums):\n    return Empty()[3]\n"
        self.assertTrue(stopped(own, [[1]])['title'])
        self.assertIn('has nothing there', errors.access_failure({}, {'structure': 'b', 'key': 5, 'index': '5', 'size': None, 'kind': 'sequence', 'of': 'Box'}, 9)['title'])

    def test_an_error_python_handled_never_explains_a_later_one(self):
        code = "class Seq:\n    def __init__(self):\n        self.data = [1, 2]\n    def __getitem__(self, i):\n        return self.data[i]\n\ndef solve(nums):\n    total = 0\n    for x in Seq():\n        total += x\n    return None + total\n"
        self.assertEqual(stopped(code, [[1]])['title'], "None can't be used with +")
        caught = "def solve(nums):\n    try:\n        nums[10]\n    except IndexError:\n        pass\n    return 1 / 0\n"
        self.assertEqual(stopped(caught, [[1]])['title'], 'Division by zero')

    def test_a_full_run_that_fails_further_keeps_the_trace_and_says_what_came_after(self):
        code = "def solve(nums):\n    total = 0\n    for i in range(9000):\n        total += i\n    return nums[5]\n"
        p = {'params': ['nums'], 'kinds': {}, 'entry': 'solve', 'answer': None}
        run = app.with_full_runs(p, code, [{'args': [[1]]}], app.run_cases(code, [[[1]]]))[0]
        self.assertEqual(run['error']['type'], 'ExecutionLimit')
        self.assertIn('went further and then stopped at line 5: nums[5] is outside the list', errors.explain(run['error'], run['error']['failure'], code, ['nums'])['detail'])
