import contextlib
import json
import os
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

# Importing app initializes its database: isolate it before the import, never touch learning.sqlite3.
os.environ['DSA_DATABASE'] = os.path.join(tempfile.mkdtemp(), 'import.sqlite3')  # Never the real database.
import app  # noqa: E402

PILOTS = ('two-sum', 'max-window-sum', 'valid-parentheses', 'climb-ways')
REASONING = {
    'observe': 'Each answer is a pair of positions whose values add up to the target.',
    'brute': 'Try every pair i < j and return the first pair whose sum is the target.',
    'bottleneck': 'For each value the inner loop scans all the other values again, so it is quadratic.',
    'information': 'At each value I only need to know whether its partner appeared earlier, and where.',
}


class DiscoveryEvidenceTests(unittest.TestCase):
    """Discover's reasoning layers as server-side evidence: what the learner reasoned, in what order, and what
    assistance the server had already given when they did."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        db = patch.object(app, 'DB', os.path.join(self.directory.name, 'discovery.sqlite3'))
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

    def record(self, problem_id, layer, text=None, status=200, **extra):
        return self.post('/api/discovery', status, problemId=problem_id, layer=layer, text=text or REASONING[layer], **extra)

    def reason(self, problem_id, through='information'):
        for layer in app.DISCOVERY_LAYERS[:app.DISCOVERY_LAYERS.index(through) + 1]:
            self.record(problem_id, layer)

    def commit(self, problem_id, status=200, **extra):
        p = app.problem_by_id(problem_id)
        return self.post('/api/approach', status, problemId=problem_id, technique=p['approach']['technique'], operation='find the partner of each value without scanning again', **extra)

    def evidence(self, problem_id, kind='discovery'):
        return next((e['detail'] for e in self.client.get('/api/progress').get_json()['evidence'] if e['problem_id'] == problem_id and e['kind'] == kind), None)

    # 1
    def test_observe_is_recorded_with_its_assistance_snapshot(self):
        reply = self.record('two-sum', 'observe')
        self.assertEqual((reply['layer'], reply['first']['text'], reply['first']['assisted'], reply['independent'], reply['next']), ('observe', REASONING['observe'], [], True, 'brute'))
        self.assertTrue(reply['first']['at'].endswith('+00:00'))
        stored = self.evidence('two-sum')['layers']['observe']
        self.assertEqual((stored['first']['text'], stored['first']['committed']), (REASONING['observe'], False))
        # Whitespace-only or too-short reasoning is not an entry; neither is a non-string.
        for text in ('   ', 'too short', 7, None, 'x' * 2001):
            with self.subTest(text=text):
                self.post('/api/discovery', 400, problemId='climb-ways', layer='observe', text=text)

    # 2
    def test_layers_are_recorded_in_order(self):
        self.assertIn('Record your observation first', self.record('two-sum', 'brute', status=400)['error'])
        self.record('two-sum', 'observe')
        self.assertIn('Record your brute force first', self.record('two-sum', 'bottleneck', status=400)['error'])
        self.assertEqual(self.record('two-sum', 'brute')['next'], 'bottleneck')
        self.assertIn('Record your bottleneck first', self.record('two-sum', 'information', status=400)['error'])
        self.assertEqual(self.record('two-sum', 'bottleneck')['next'], 'information')
        self.assertEqual(self.record('two-sum', 'information')['next'], 'commit')
        # Technique and approach belong to the commitment, not to a reasoning layer.
        for layer in ('technique', 'approach', 'Observe', None, ['observe']):
            with self.subTest(layer=layer):
                self.post('/api/discovery', 400, problemId='two-sum', layer=layer, text=REASONING['observe'])
        layers = self.evidence('two-sum')['layers']
        self.assertEqual(set(layers), set(app.DISCOVERY_LAYERS))
        times = [layers[layer]['first']['at'] for layer in app.DISCOVERY_LAYERS]
        self.assertEqual(times, sorted(times))  # The order is in the evidence itself.

    # 3
    def test_reasoning_persists_on_the_server(self):
        self.reason('climb-ways', 'brute')
        app.initialize()  # A restart keeps it.
        fresh = app.app.test_client()
        stored = next(e['detail'] for e in fresh.get('/api/progress').get_json()['evidence'] if e['kind'] == 'discovery')
        self.assertEqual({k: v['first']['text'] for k, v in stored['layers'].items()}, {'observe': REASONING['observe'], 'brute': REASONING['brute']})
        with app.connect() as db:
            self.assertEqual(list(app.discovery_record(db, 'local-learner', 'climb-ways')['layers']), ['observe', 'brute'])

    # 4
    def test_the_first_entry_is_immutable_evidence(self):
        first = self.record('two-sum', 'observe')['first']
        self.post('/api/hint', problemId='two-sum', level=1)  # Assistance after the entry does not rewrite it.
        revised = self.record('two-sum', 'observe', text='Revised: the target fixes the partner of every value.')
        self.assertEqual(revised['first'], first)
        self.assertEqual(revised['latest']['text'], 'Revised: the target fixes the partner of every value.')
        self.assertTrue(revised['independent'])
        stored = self.evidence('two-sum')['layers']['observe']
        self.assertEqual((stored['first'], stored['latest']['text']), (first, 'Revised: the target fixes the partner of every value.'))

    # 5
    def test_browser_claims_are_ignored(self):
        claims = dict(independent=True, guided=False, revealed=False, solved=False, previewSolved=False, assisted=[], committed=False, first={'text': 'forged', 'assisted': []})
        self.post('/api/hint', problemId='two-sum', level=1)
        reply = self.record('two-sum', 'observe', **claims)
        self.assertEqual((reply['first']['text'], reply['first']['assisted'], reply['independent']), (REASONING['observe'], ['hints'], False))
        # ...in either direction.
        unaided = self.record('climb-ways', 'observe', independent=False, guided=True, revealed=True, solved=True, previewSolved=True)
        self.assertEqual((unaided['first']['assisted'], unaided['independent']), ([], True))
        self.reason('valid-parentheses')
        committed = self.commit('valid-parentheses', basis='reasoned', discovery={'recorded': [], 'direct': True}, guided=False, complexityCheck={'status': 'matched'})
        stored = self.evidence('valid-parentheses', 'approach')
        self.assertEqual((committed['basis'], stored['basis'], stored['discovery']['recorded']), ('reasoned', 'reasoned', list(app.DISCOVERY_LAYERS)))
        self.assertNotIn('complexityCheck', stored)

    # 6
    def test_a_comparison_is_never_returned_before_the_learners_own_entry(self):
        p = app.problem_by_id('two-sum')
        for layer in ('observe', 'brute', 'bottleneck', 'information', 'approach'):
            with self.subTest(layer=layer):
                self.assertIn('first', self.post('/api/discovery', 400, problemId='two-sum', layer=layer, reveal=True)['error'])
                self.post('/api/discovery', 400, problemId='two-sum', layer=layer, check=True)
        self.record('two-sum', 'observe')
        self.post('/api/discovery', 400, problemId='two-sum', layer='brute', reveal=True)  # Its own layer's entry, not an earlier one.
        self.assertEqual(self.post('/api/discovery', problemId='two-sum', layer='observe', reveal=True)['text'], p['discover']['observe'])
        self.record('two-sum', 'brute')
        self.assertEqual(self.post('/api/discovery', problemId='two-sum', layer='brute', reveal=True)['text'], p['discovery'][0])
        # One operation per request, and reveal/check must be exactly true.
        for body in ({'reveal': 'yes'}, {'check': 1}, {'reveal': True, 'check': True}, {'text': REASONING['brute'], 'reveal': True}, {}):
            with self.subTest(body=body):
                self.post('/api/discovery', 400, problemId='two-sum', layer='brute', **body)
        with app.connect() as db:
            self.assertIsNone(app.support_row(db, 'local-learner', 'two-sum'))

    # 7
    def test_a_required_information_check_counts_as_guidance(self):
        self.reason('two-sum')
        check = self.post('/api/discovery', problemId='two-sum', layer='information', check=True)
        self.assertTrue(check['guidance'])
        self.assertIsInstance(check['visible'], list)
        feedback = self.commit('two-sum')
        self.assertTrue(feedback['guided'])
        self.assertIn('you asked for a check of your required-information reasoning', feedback['reasons'])
        self.assertEqual(feedback['basis'], 'guided')
        # Revealing the information comparison is guidance too (the prompt that points toward the approach).
        self.reason('climb-ways')
        reveal = self.post('/api/discovery', problemId='climb-ways', layer='information', reveal=True)
        self.assertEqual((reveal['text'], reveal['guidance']), (app.problem_by_id('climb-ways')['discovery'][2], True))
        self.assertIn('you revealed reasoning prompts that point toward the approach', self.commit('climb-ways')['reasons'])

    # 8
    def test_earlier_checks_and_comparisons_do_not_count(self):
        for layer in ('observe', 'brute', 'bottleneck'):
            self.record('max-window-sum', layer)
            check = self.post('/api/discovery', problemId='max-window-sum', layer=layer, check=True)
            reveal = self.post('/api/discovery', problemId='max-window-sum', layer=layer, reveal=True)
            self.assertEqual((check['guidance'], reveal['guidance']), (False, False))
            self.assertTrue(check['question'] is None or check['question'].endswith('?'))
        self.assertTrue(self.record('max-window-sum', 'information')['independent'])
        feedback = self.commit('max-window-sum')
        self.assertEqual((feedback['guided'], feedback['reasons'], feedback['basis']), (False, [], 'reasoned'))
        self.assertEqual(feedback['discovery']['independent'], list(app.DISCOVERY_LAYERS))
        # After the commitment, checking the information layer is no longer guidance on it.
        self.assertFalse(self.post('/api/discovery', problemId='max-window-sum', layer='information', check=True)['guidance'])
        self.assertEqual(self.evidence('max-window-sum', 'approach')['reasons'], [])

    # 9
    def test_the_guide_in_discover_remains_guidance(self):
        self.record('valid-parentheses', 'observe')
        self.post('/api/chat', message='How do I start?', context={'problemId': 'valid-parentheses', 'stage': 'discover'})
        brute = self.record('valid-parentheses', 'brute')
        self.assertEqual((brute['first']['assisted'], brute['independent']), (['hints'], False))
        with app.connect() as db:
            first = app.discovery_record(db, 'local-learner', 'valid-parentheses')['layers']['observe']['first']
        self.assertEqual(first['assisted'], [])  # The observation before the Guide stays unaided.
        feedback = self.commit('valid-parentheses')
        self.assertIn('you used hints or the guide on this problem', feedback['reasons'])
        self.assertEqual((feedback['basis'], feedback['discovery']['assisted']), ('guided', ['brute']))

    # 10
    def test_the_technique_stays_hidden_at_the_boundary(self):
        for pid in PILOTS:
            with self.subTest(pid):
                p = app.problem_by_id(pid)
                words = {w for w in re.findall(r'[a-z]+', f"{p['approach']['technique']} {p['category']}".lower()) if len(w) > 3}
                replies = []
                for layer in ('observe', 'brute', 'bottleneck'):
                    replies.append(self.record(pid, layer))
                    replies.append(self.post('/api/discovery', problemId=pid, layer=layer, reveal=True))
                    replies.append(self.post('/api/discovery', problemId=pid, layer=layer, check=True))
                replies.append(self.record(pid, 'information'))
                text = json.dumps(replies).lower()
                self.assertFalse([w for w in words if re.search(r'\b' + w, text)], text)
                # The information check is a question, not the answer.
                self.assertNotIn(p['approach']['technique'].lower(), json.dumps(self.post('/api/discovery', problemId=pid, layer='information', check=True)).lower())

    # 11
    def test_a_direct_commitment_stays_possible(self):
        feedback = self.commit('two-sum')
        self.assertEqual((feedback['verdict'], feedback['first'], feedback['guided']), ('match', True, False))
        # On a lab without authored discover data, too.
        self.assertEqual(self.post('/api/approach', problemId='palindrome', technique='Two pointers', operation='compare characters from both ends moving inward')['first'], True)

    # 12
    def test_a_direct_commitment_is_not_independent_discovery(self):
        feedback = self.commit('two-sum')
        self.assertEqual((feedback['basis'], feedback['discovery']), ('known', {'recorded': [], 'independent': [], 'assisted': [], 'direct': True}))
        # Reasoning written after the commitment is kept, but never as discovery before it.
        late = self.record('two-sum', 'observe')
        self.assertEqual((late['first']['committed'], late['independent']), (True, False))
        stored = self.evidence('two-sum', 'approach')
        self.assertEqual((stored['basis'], stored['discovery']['direct']), ('known', True))
        self.assertEqual(self.commit('two-sum')['firstCommitment']['basis'], 'known')  # The first commitment is the evidence.

    # 13
    def test_no_cross_problem_or_cross_endpoint_leakage(self):
        self.reason('two-sum')
        # Another problem starts from its own first layer.
        self.record('climb-ways', 'brute', status=400)
        self.post('/api/discovery', 400, problemId='climb-ways', layer='bottleneck', reveal=True)
        self.assertIsNone(self.evidence('climb-ways'))
        # Changed requirements, unknown and own labs have no reasoning layers.
        self.commit('two-sum')
        for pid in ('two-sum-modified', 'nope', None, 'custom-123'):
            with self.subTest(pid=pid):
                self.post('/api/discovery', 400, problemId=pid, layer='observe', text=REASONING['observe'])
        self.assertNotIn('discover', app.problem_by_id('two-sum-modified'))
        # Another learner sees none of it, and starts at Observe.
        with patch.object(app, 'identity', return_value='someone-else'):
            self.assertIsNone(self.evidence('two-sum'))
            self.record('two-sum', 'brute', status=400)
            self.assertEqual(self.record('two-sum', 'observe')['first']['assisted'], [])
        # Authored discover data reaches no other payload: the library, progress or the Guide's context.
        authored = [text for pid in PILOTS for text in [app.problem_by_id(pid)['discover']['observe']] + [c[k] for cs in app.problem_by_id(pid)['discover']['checks'].values() for c in cs for k in ('label', 'question')]]
        library = self.client.get('/api/problems').get_json()
        self.assertFalse([row['id'] for row in library if 'discover' in row])
        with app.app.test_request_context():
            contexts = [app.tutor_context('local-learner', app.problem_by_id(pid), {'stage': 'discover'}) for pid in PILOTS]
        payload = json.dumps([library, self.client.get('/api/progress').get_json(), contexts])
        self.assertFalse([text for text in authored if text in payload])

    # 14
    def test_independent_modified_and_transfer_evidence_still_hold(self):
        # Transfer, with reasoning recorded before an unaided commitment (palindrome → reverse-string).
        self.post('/api/execute', problemId='palindrome', code=app.problem_by_id('palindrome')['solution'], args=app.problem_by_id('palindrome')['example']['args'])
        self.reason('reverse-string', 'bottleneck')
        q = app.problem_by_id('reverse-string')
        self.assertEqual(self.post('/api/approach', problemId=q['id'], technique=q['approach']['technique'], operation='swap the mirrored characters from both ends inward', transferFrom='palindrome')['basis'], 'reasoned')
        run = self.post('/api/execute', problemId=q['id'], code=q['solution'], args=q['example']['args'])
        self.assertEqual(self.post('/api/progress', problemId=q['id'], stage='Independent', attemptId=run['attemptId'])['transferred'], ['palindrome'])
        # Modified, after a commitment.
        self.commit('two-sum')
        variant = app.problem_by_id('two-sum-modified')
        adapted = self.post('/api/execute', problemId=variant['id'], code=variant['solution'], args=variant['example']['args'])
        self.assertTrue(self.post('/api/progress', problemId='two-sum', stage='Modified', attemptId=adapted['attemptId'], evidence='Counting needs every earlier partner, not one index.')['insight'])
        # The step form the current Discover screen uses keeps its rules: free prompts, then guidance from prompt 3.
        self.assertEqual(self.post('/api/discovery', problemId='kth-largest', step=1)['text'], app.problem_by_id('kth-largest')['discovery'][1])
        self.post('/api/discovery', problemId='kth-largest', step=2)
        self.assertIn('you revealed reasoning prompts that point toward the approach', self.post('/api/approach', problemId='kth-largest', technique='Heap / priority queue', operation='keep only the k largest values seen so far')['reasons'])
        # ...and a prompt revealed that way is assistance on a layer recorded after it.
        self.post('/api/discovery', problemId='climb-ways', step=3)
        self.assertEqual(self.record('climb-ways', 'observe')['first']['assisted'], ['prompts'])

    # 15
    def test_an_existing_database_opens_and_its_commitments_still_read(self):
        path = os.path.join(self.directory.name, 'old.sqlite3')
        old = {'technique': 'Hash map / set', 'verdict': 'match', 'operation': 'look up each partner value', 'guided': False, 'reasons': [], 'transferFrom': None, 'solvedBefore': []}
        with contextlib.closing(sqlite3.connect(path)) as db:
            db.executescript("""CREATE TABLE learning_support(user_id TEXT, problem_id TEXT, hint_level INTEGER DEFAULT 0, revealed INTEGER DEFAULT 0, PRIMARY KEY(user_id,problem_id));
                CREATE TABLE learning_evidence(user_id TEXT, problem_id TEXT, kind TEXT, detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id,problem_id,kind));
                INSERT INTO learning_support VALUES('local-learner','climb-ways',1,0);""")
            db.execute("INSERT INTO learning_evidence(user_id,problem_id,kind,detail) VALUES('local-learner','two-sum','approach',?)", (json.dumps(old),))
            db.commit()
        with patch.object(app, 'DB', path):
            app.initialize()
            self.assertEqual(self.commit('two-sum')['firstCommitment'], old)  # A commitment from before discovery evidence is kept as it was.
            self.assertEqual(self.record('climb-ways', 'observe')['first']['assisted'], ['hints'])  # Old support still counts.
            self.reason('two-sum')
            with app.connect() as db:
                self.assertEqual(sorted(r[0] for r in db.execute("SELECT kind FROM learning_evidence WHERE problem_id='two-sum'")), ['approach', 'discovery'])

    def test_complexity_is_captured_in_natural_words_and_never_gates(self):
        self.reason('two-sum')
        feedback = self.commit('two-sum', complexity='linear time, one pass', information=REASONING['information'])
        self.assertEqual((feedback['verdict'], feedback['complexityCheck']['status']), ('match', 'matched'))
        stored = self.evidence('two-sum', 'approach')
        self.assertEqual((stored['complexity'], stored['information']), ('linear time, one pass', REASONING['information']))
        self.assertEqual(self.commit('climb-ways', complexity='exponential')['complexityCheck']['status'], 'not-matched')  # Advisory only.
        self.assertEqual(self.commit('max-window-sum', complexity='pretty fast')['complexityCheck']['status'], 'unrecognized')
        for complexity in ('', '   ', 7, 'x' * 301):
            with self.subTest(complexity=complexity):
                self.commit('valid-parentheses', 400, complexity=complexity)
        for answer, status in [('O(n)', 'matched'), ('O(N) time', 'matched'), ('n log n', 'not-matched'), ('O(n^2) brute, then O(n)', 'partial'), ('quadratic', 'not-matched')]:
            with self.subTest(answer=answer):
                self.assertEqual(app.complexity_check(answer, 'O(n)')['status'], status)


class DiscoverCurriculumTests(unittest.TestCase):
    def test_only_the_pilots_carry_authored_discover_data(self):
        self.assertEqual(sorted(p['id'] for p in app.PROBLEMS if 'discover' in p), sorted(PILOTS))
        for pid in PILOTS:
            with self.subTest(pid):
                p = app.problem_by_id(pid)
                spec = p['discover']
                self.assertEqual(set(spec), {'observe', 'checks', 'replay'})
                self.assertGreaterEqual(len(spec['observe']), 40)
                self.assertEqual(list(spec['checks']), list(app.DISCOVERY_LAYERS))
                for layer, checks in spec['checks'].items():
                    self.assertTrue(checks)
                    for check in checks:
                        re.compile(check['pattern'])
                        self.assertTrue(check['label'] and check['question'].endswith('?'))
                # Replay metadata only: an input the brute force accepts, never executed per request.
                self.assertEqual(len(spec['replay']['input']), len(p['example']['args']))
                self.assertIn(spec['replay']['of'], [*p['params'], 'solve'])
                self.assertTrue(p['brute'])
                self.assertEqual(len(p['discovery']), 4)  # The existing prompts are each layer's comparison: no duplicate.


if __name__ == '__main__':
    unittest.main()
