"""Authoring source for the data-structure laboratories: two per structure, each with the same parts as the
first 24 (decoder, cases, a reference and a simple solution, discovery, hints, recall, an approach to commit
to and a changed requirement). Inputs that are linked lists or trees are written as judges write them and
reach the learner's code as real nodes (`kinds`); design problems build a class and call its methods
(`entry`). Every solution, simple solution and changed requirement is executed by the test suite."""
import itertools

# Techniques a learner can commit to, beyond the six of the first labs (app.TECHNIQUES lists them all).
HASH, POINTERS, WINDOW, SEARCH, RUNNING, BRUTE = 'Hash map / set', 'Two pointers', 'Sliding window', 'Binary search', 'Running best / running total', 'Direct iteration / brute force'
LIST, STACK, QUEUE, BFS, DFS = 'Linked-list pointer rewiring', 'Stack', 'Queue / deque', 'Breadth-first search', 'Depth-first search'
RECURSION, HEAP, TRIE, DP, BITS = 'Recursion / backtracking', 'Heap / priority queue', 'Trie (prefix tree)', 'Dynamic programming', 'Bit manipulation'
TECHNIQUES = [LIST, STACK, QUEUE, BFS, DFS, RECURSION, HEAP, TRIE, DP, BITS]

LINKED = "The head of a singly linked list, written as its values from head to tail: [1, 2, 3] is 1 → 2 → 3, and [] is an empty list."
TREE = "The root of a binary tree, written level by level from left to right with None for a missing child: [1, None, 2] is 1 with only a right child 2."
DESIGN = "A list of operations and, beside it, each operation's arguments. The first creates the class; each later one calls a method on it."
DESIGN_RETURNS = "The answer of every operation in order: None for the constructor and for methods that return nothing."
GRAPH = "graph[i] lists the neighbours of node i in an undirected graph; every edge appears in both nodes' lists."


def fn(params, body, prelude=''):
    """A solution body inside solve(params), with any imports or helper classes it needs above it."""
    source = 'def solve(' + params + '):\n' + '\n'.join('    ' + line if line.strip() else '' for line in body.strip('\n').splitlines()) + '\n'
    return prelude.strip() + '\n\n\n' + source if prelude else source


def lab(id_, title, category, params, statement, given, find, returns, example, cases, edges, solution, brute, discovery, hints, recall, transfer,
        complexity, approach, modification, level='Easy', kinds=None, entry='solve', order=None, starter=None):
    args, expected = example
    technique, operation, why, alternatives, checkpoints = approach
    m_title, m_statement, m_returns, question, clue, insight, m_solution, m_cases = modification
    p = {
        'id': id_, 'title': title, 'category': category, 'difficulty': level, 'params': params.split(', '), 'statement': statement,
        'decoder': {'given': given, 'find': find, 'returns': returns}, 'example': {'args': args, 'expected': expected},
        'tests': [{'name': 'Example', 'args': args, 'expected': expected}] + [{'name': n, 'args': a, 'expected': e} for n, a, e in cases + edges],
        'starter': starter or f'def solve({params}):\n    # {find}\n    # {returns}\n    # Start with your simplest idea.\n    \n    pass\n',
        'solution': solution, 'brute': brute, 'discovery': discovery, 'hints': hints, 'recall': recall, 'transfer': transfer,
        'complexity': {'time': complexity[0], 'space': complexity[1]},
        'approach': {'technique': technique, 'operation': operation, 'why': why,
                     'alternatives': {name: {'kind': kind, 'note': note} for name, (kind, note) in alternatives.items()},
                     'checkpoints': [{'pattern': pattern, 'label': label, 'question': q} for pattern, label, q in checkpoints]},
        'modification': {'id': id_ + '-modified', 'title': m_title, 'statement': m_statement, 'returns': m_returns, 'question': question, 'clue': clue, 'insight': insight,
                         'solution': m_solution, 'example': {'args': m_cases[0][1], 'expected': m_cases[0][2]},
                         'tests': [{'name': n, 'args': a, 'expected': e} for n, a, e in m_cases]},
    }
    if kinds:
        p['kinds'] = kinds
    if entry != 'solve':
        p['entry'] = entry
    if order:
        p['order'] = order
    return p


def subsets_of(values):
    return [list(c) for size in range(len(values) + 1) for c in itertools.combinations(values, size)]


def orderings(values):
    return [list(p) for p in itertools.permutations(values)]


LABS = []

# ----------------------------------------------------------------------------- Linked lists
LABS.append(lab(
    'reverse-list', 'Reverse a Linked List', 'Linked lists', 'head',
    'Reverse a singly linked list by turning every next pointer around, and return the new head. The list may be empty.',
    LINKED, 'Reverse the direction of every next pointer.', 'Return the new head (the old tail); it is shown as its values from head to tail.',
    ([[1, 2, 3, 4, 5]], [5, 4, 3, 2, 1]),
    [('Two nodes', [[1, 2]], [2, 1]), ('Empty list', [[]], []), ('One node', [[7]], [7])],
    [('Repeated values', [[2, 2, 3]], [3, 2, 2]), ('Negatives', [[-1, 0, 1]], [1, 0, -1])],
    fn('head', '''
prev = None
curr = head
while curr:
    nxt = curr.next
    curr.next = prev
    prev = curr
    curr = nxt
return prev'''),
    fn('head', '''
values = []
node = head
while node:
    values.append(node.val)
    node = node.next
dummy = ListNode(0)
tail = dummy
for v in reversed(values):
    tail.next = ListNode(v)
    tail = tail.next
return dummy.next'''),
    ['Copy the values out, then build a new list in reverse order.', 'Copying stores n values and creates n new nodes, although every node you need already exists.',
     'Each node only needs its next pointer turned around to point at the node before it.', 'Walk once with prev and curr; save curr.next before you overwrite it.'],
    ['A singly linked list only knows the way forward: node.next.', 'Reversing means every next pointer should point at the node before it instead.', 'When you change curr.next, what do you lose?',
     'Keep three names: prev, curr, and the saved next node.', 'Order matters: save next, point curr back at prev, then advance prev and curr.', 'When curr becomes None, prev is the new head.'],
    ['Why must curr.next be saved before it is changed?', 'Why is prev the answer when the loop ends?'], 'merge-two-lists', ('O(n)', 'O(1)'),
    (LIST, "Turn each node's next pointer back toward the node before it, without losing the rest of the list.",
     'Three references (prev, curr and the saved next) let one pass rewire every pointer in place, with O(1) extra memory instead of copying values.',
     {STACK: ('alternative', 'Pushing every node on a stack and popping them to relink also works, but it stores all n nodes; three pointers need O(1) memory.'),
      RECURSION: ('alternative', 'Reversing the rest recursively and then fixing one pointer works too, but it uses O(n) call-stack depth.')},
     [(r'prev|previous|before|behind|backward|point(s|ing)? back', 'pointing each node at the one before it', "Where should each node's next pointer point after reversing?"),
      (r'save|store|keep|remember|temp|nxt|next node|lose|lost', 'saving the next node before rewiring', 'What do you lose when you overwrite curr.next, and how do you keep it?'),
      (r'new head|return prev|old tail|last node|curr (is|becomes) none|end of the list', 'returning the old tail as the new head', 'When the walk ends, which node is the new head?')]),
    ('Swap each pair', 'Now swap every two adjacent nodes and return the new head: 1 → 2 → 3 → 4 becomes 2 → 1 → 4 → 3. A final unpaired node stays where it is.', 'Return the new head.',
     'Reversing turned every pointer around. Which pointers change when only neighbours trade places?',
     'Work two nodes at a time: the node before the pair must point at the second node, the second at the first, and the first at whatever followed the pair.',
     'Pair swapping is local rewiring: the same "save what you are about to overwrite" discipline, applied to two nodes at a time behind a dummy node.',
     fn('head', '''
dummy = ListNode(0)
dummy.next = head
prev = dummy
while prev.next and prev.next.next:
    first = prev.next
    second = first.next
    first.next = second.next
    second.next = first
    prev.next = second
    prev = first
return dummy.next'''),
     [('Example', [[1, 2, 3, 4]], [2, 1, 4, 3]), ('Odd length', [[1, 2, 3]], [2, 1, 3]), ('Empty list', [[]], []), ('One node', [[5]], [5]), ('Six nodes', [[1, 2, 3, 4, 5, 6]], [2, 1, 4, 3, 6, 5])]),
    kinds={'head': 'linkedlist'}))

LABS.append(lab(
    'merge-two-lists', 'Merge Two Sorted Lists', 'Linked lists', 'list1, list2',
    'Two linked lists are each sorted in nondecreasing order. Splice their nodes together into one sorted list and return its head.',
    'The heads of two sorted linked lists, each written as its values from head to tail.', 'Combine them into one sorted list, reusing their nodes.',
    'Return the head of the merged list.',
    ([[1, 2, 4], [1, 3, 4]], [1, 1, 2, 3, 4, 4]),
    [('One empty', [[], [0]], [0]), ('Both empty', [[], []], []), ('No overlap', [[1, 2], [5, 6]], [1, 2, 5, 6])],
    [('Negatives', [[-3, 0], [-2]], [-3, -2, 0]), ('One longer', [[2], [1, 3, 5, 7]], [1, 2, 3, 5, 7])],
    fn('list1, list2', '''
dummy = ListNode(0)
tail = dummy
while list1 and list2:
    if list1.val <= list2.val:
        tail.next = list1
        list1 = list1.next
    else:
        tail.next = list2
        list2 = list2.next
    tail = tail.next
tail.next = list1 if list1 else list2
return dummy.next'''),
    fn('list1, list2', '''
values = []
for node in (list1, list2):
    while node:
        values.append(node.val)
        node = node.next
values.sort()
dummy = ListNode(0)
tail = dummy
for v in values:
    tail.next = ListNode(v)
    tail = tail.next
return dummy.next'''),
    ['Collect every value from both lists, sort them, and build a new list.', 'Sorting ignores the order both lists already have: O((n + m) log(n + m)) and n + m new nodes.',
     'The smallest remaining value is always at the front of one of the two lists.', 'Keep a tail pointer behind a dummy node; attach the smaller front node and advance that list.'],
    ['Both lists are already sorted.', 'Which two nodes could hold the smallest value overall?', 'Compare the two front nodes and take the smaller one.',
     'A dummy node before the result avoids a special case for the first node.', 'Keep a tail pointer: attach the chosen node after it, then move tail forward.',
     'When one list runs out, attach the rest of the other list in one step.'],
    ['Why does a dummy node simplify the code?', 'Why can the leftover list be attached without a loop?'], 'reverse-list', ('O(n + m)', 'O(1)'),
    (LIST, 'Repeatedly attach the smaller of the two front nodes to the end of the result.',
     'Only the two front nodes compete, because both lists are sorted; a tail pointer splices each winner in O(1), reusing the existing nodes.',
     {POINTERS: ('partial', 'One pointer per list is the idea from merging arrays. With linked lists the other half is rewiring: a tail pointer splices nodes instead of copying values.'),
      HEAP: ('alternative', 'A heap of front nodes merges any number of lists in O(n log k); for two lists one comparison per step is enough.')},
     [(r'smaller|smallest|compare|front|<=|less', 'taking the smaller front node', 'Which node must come next in the merged list?'),
      (r'dummy|sentinel|tail|attach|splice|link|\.next\s*=', 'attaching nodes after a tail pointer', 'How do you add a node to the end of the result in O(1)?'),
      (r'leftover|remaining|\brest\b|runs? out|exhaust|empty|one (list )?(is )?(done|finished)', 'attaching whatever remains', 'What happens when one list runs out?')]),
    ('Drop the duplicates', 'Now the merged list must contain each value only once, still in sorted order.', 'Return the head of the merged list without repeated values.',
     'The merge kept every node. How can you tell that a value is already at the end of the result?',
     'The merged list is sorted, so a repeated value can only equal the value at the current tail.',
     'Sorted order makes duplicate detection local: compare with the tail before attaching, and skip the node instead of splicing it.',
     fn('list1, list2', '''
dummy = ListNode(0)
tail = dummy
while list1 or list2:
    if not list2 or (list1 and list1.val <= list2.val):
        node = list1
        list1 = list1.next
    else:
        node = list2
        list2 = list2.next
    if tail is dummy or tail.val != node.val:
        tail.next = node
        tail = node
tail.next = None
return dummy.next'''),
     [('Example', [[1, 2, 4], [1, 3, 4]], [1, 2, 3, 4]), ('All equal', [[2, 2], [2]], [2]), ('Both empty', [[], []], []), ('No overlap', [[1], [3]], [1, 3]),
      ('Repeats in one list', [[1, 1, 2], []], [1, 2])]),
    kinds={'list1': 'linkedlist', 'list2': 'linkedlist'}))

# ----------------------------------------------------------------------------- Stacks
LABS.append(lab(
    'valid-parentheses', 'Valid Parentheses', 'Stacks', 'text',
    'The string contains only the brackets ( ) [ ] { }. Return True if every opening bracket is closed by a bracket of the same type, in the correct order.',
    'A string of brackets.', 'Check that every bracket is closed by the same type, in the right order.', 'Return True or False.',
    (['([]{})'], True),
    [('Wrong order', ['([)]'], False), ('Empty string', [''], True), ('Unclosed', ['(('], False)],
    [('Closing first', [')('], False), ('Nested deeply', ['{[()()]}'], True)],
    fn('text', '''
pairs = {')': '(', ']': '[', '}': '{'}
stack = []
for ch in text:
    if ch in pairs:
        if not stack or stack.pop() != pairs[ch]:
            return False
    else:
        stack.append(ch)
return not stack'''),
    fn('text', '''
while '()' in text or '[]' in text or '{}' in text:
    text = text.replace('()', '').replace('[]', '').replace('{}', '')
return not text'''),
    ['Repeatedly delete adjacent matching pairs such as () until nothing changes.', 'Each deletion pass rescans the whole string, and deep nesting needs about n / 2 passes: O(n²).',
     'The bracket that must close next is always the most recent opening bracket that is still unclosed.', 'Push opening brackets; on a closing bracket, pop and check that it matches.'],
    ['Look at ([)]: every type has as many openings as closings, yet it is invalid. Counting is not enough.', 'When you meet a closing bracket, which opening bracket must it match?',
     'The most recently opened bracket must be closed first.', 'Last opened, first closed: that is a stack.', 'Push each opening bracket. On a closing bracket, pop and compare with its partner.',
     'At the end the stack must be empty: no bracket may be left open.'],
    ['Why is counting each bracket type not enough?', 'What does a non-empty stack at the end mean?'], 'daily-temperatures', ('O(n)', 'O(n)'),
    (STACK, 'For each closing bracket, find the most recent opening bracket that is still unclosed.',
     'A stack keeps the unclosed brackets in order, so the one that must close next is always on top: O(1) per character.',
     {HASH: ('partial', 'A map from each closing bracket to its opening partner checks the type, but it does not remember the order brackets were opened in; the stack does.')},
     [(r'most recent|last (open|unclosed)|latest|innermost|\btop\b', 'matching the most recent unclosed bracket', 'Which opening bracket must the next closing bracket match?'),
      (r'push|pop|stack|append', 'pushing opening brackets and popping on closing ones', 'What happens to an opening bracket, and what happens on a closing one?'),
      (r'empty|left over|leftover|remain|unclosed|at the end', 'checking that nothing is left open', 'What must be true when the whole string has been read?')]),
    ('Deepest nesting', 'Now return how deeply the brackets nest — the largest number of brackets open at once — or -1 if the string is invalid.', 'Return an integer depth, or -1.',
     'The stack already holds every bracket that is currently open. What does its size tell you?',
     'Track the largest stack size reached; keep the validity checks, and return -1 where you returned False.',
     'The same stack answers a richer question: its size at each moment is the current nesting depth.',
     fn('text', '''
pairs = {')': '(', ']': '[', '}': '{'}
stack = []
deepest = 0
for ch in text:
    if ch in pairs:
        if not stack or stack.pop() != pairs[ch]:
            return -1
    else:
        stack.append(ch)
        deepest = max(deepest, len(stack))
return deepest if not stack else -1'''),
     [('Example', ['([]{})'], 2), ('Flat', ['()()'], 1), ('Invalid', ['(]'], -1), ('Empty string', [''], 0), ('Deep', ['{[()]}'], 3)])))

LABS.append(lab(
    'daily-temperatures', 'Daily Temperatures', 'Stacks', 'temps',
    'For each day, return how many days you must wait for a warmer temperature. If no warmer day comes, that day\'s answer is 0.',
    'A list of daily temperatures.', 'For each day, find the next later day that is warmer.', 'Return a list of waiting times, one per day.',
    ([[73, 74, 75, 71, 69, 72, 76, 73]], [1, 1, 4, 2, 1, 1, 0, 0]),
    [('Rising', [[30, 40, 50, 60]], [1, 1, 1, 0]), ('Falling', [[60, 50, 40]], [0, 0, 0]), ('One day', [[50]], [0])],
    [('Equal is not warmer', [[70, 70, 71]], [2, 1, 0]), ('No days', [[]], [])],
    fn('temps', '''
answer = [0] * len(temps)
stack = []
for i, t in enumerate(temps):
    while stack and temps[stack[-1]] < t:
        j = stack.pop()
        answer[j] = i - j
    stack.append(i)
return answer'''),
    fn('temps', '''
answer = [0] * len(temps)
for i in range(len(temps)):
    for j in range(i + 1, len(temps)):
        if temps[j] > temps[i]:
            answer[i] = j - i
            break
return answer'''),
    ['For each day, scan forward until a warmer day appears.', 'Falling runs make each day rescan the same future days: O(n²) in the worst case.',
     'A day stays waiting until the first warmer day arrives, and the waiting days are always in non-increasing order of temperature.',
     'Keep the waiting days on a stack; a warmer day pops and answers every cooler day on top.'],
    ['Each answer is a distance between two positions.', 'Which days are still waiting for a warmer day when you reach day i?',
     'Why must the waiting days be in non-increasing order of temperature?', 'Store the waiting days\' indices on a stack.',
     'A new temperature pops every cooler waiting day and fills in its answer i − j.', 'Days still on the stack at the end never warm up: their answer stays 0.'],
    ['Why do the waiting days form a non-increasing stack?', 'Why is each index pushed and popped at most once?'], 'valid-parentheses', ('O(n)', 'O(n)'),
    (STACK, 'For each day, find the next later day with a higher temperature.',
     'A monotonic stack of unanswered days lets each new day answer every cooler waiting day at once; each index is pushed and popped once, O(n) in total.', {},
     [(r'waiting|unanswered|unresolved|pending|not yet', 'keeping the days that are still waiting', 'Which days are still waiting for an answer?'),
      (r'pop|stack|\btop\b|monoton|decreas|non.increasing', 'popping cooler days when a warmer one arrives', 'What happens to waiting days when a warmer day arrives?'),
      (r'index|indices|position|distance|i\s*-\s*j|difference', 'storing indices to measure the wait', 'What do you store so that you can compute how many days passed?')]),
    ('Previous warmer day', 'Now, for each day, return how many days have passed since the most recent earlier day that was warmer, or 0 if no earlier day was warmer.',
     'Return a list of distances, one per day.',
     'The stack answered days when a later warmer day arrived. Which earlier days are still candidates to be the previous warmer day?',
     'Before pushing day i, pop every day that is not warmer than it; whatever remains on top is the previous warmer day.',
     'The same monotonic stack answers the mirror question: popping now happens before the answer instead of producing it.',
     fn('temps', '''
answer = [0] * len(temps)
stack = []
for i, t in enumerate(temps):
    while stack and temps[stack[-1]] <= t:
        stack.pop()
    answer[i] = i - stack[-1] if stack else 0
    stack.append(i)
return answer'''),
     [('Example', [[73, 74, 75, 71, 69, 72, 76, 73]], [0, 0, 0, 1, 1, 3, 0, 1]), ('Falling', [[60, 50, 40]], [0, 1, 1]), ('Rising', [[30, 40, 50]], [0, 0, 0]),
      ('Equal is not warmer', [[70, 70, 69]], [0, 0, 1])]),
    level='Medium'))

# ----------------------------------------------------------------------------- Queues
LABS.append(lab(
    'recent-calls', 'Number of Recent Calls', 'Queues', 'operations, arguments',
    'Design RecentCounter. ping(t) records a request at time t, in milliseconds, and returns how many requests happened in the last 3000 ms: the window [t − 3000, t], inclusive. Times strictly increase.',
    DESIGN, 'For each ping, count the requests inside the last 3000 ms.', DESIGN_RETURNS,
    ([['RecentCounter', 'ping', 'ping', 'ping', 'ping'], [[], [1], [100], [3001], [3002]]], [None, 1, 2, 3, 3]),
    [('Far apart', [['RecentCounter', 'ping', 'ping'], [[], [1], [5000]]], [None, 1, 1]), ('Exactly 3000 apart', [['RecentCounter', 'ping', 'ping'], [[], [1000], [4000]]], [None, 1, 2]),
     ('Only the constructor', [['RecentCounter'], [[]]], [None])],
    [('Burst', [['RecentCounter', 'ping', 'ping', 'ping'], [[], [10], [11], [12]]], [None, 1, 2, 3]),
     ('Window slides past several', [['RecentCounter', 'ping', 'ping', 'ping', 'ping'], [[], [1], [2], [3], [3003]]], [None, 1, 2, 3, 2])],
    '''from collections import deque


class RecentCounter:
    def __init__(self):
        self.calls = deque()

    def ping(self, t):
        self.calls.append(t)
        while self.calls[0] < t - 3000:
            self.calls.popleft()
        return len(self.calls)
''',
    '''class RecentCounter:
    def __init__(self):
        self.calls = []

    def ping(self, t):
        self.calls.append(t)
        count = 0
        for c in self.calls:
            if c >= t - 3000:
                count += 1
        return count
''',
    ['Keep every ping and, for each new ping, count how many fall inside the window.', 'Every ping recounts the whole history, including requests that can never be in a window again: O(n) per ping.',
     'Times only increase, so a request that falls out of the window never comes back.', 'Keep a queue of recent times: append the new ping, pop old ones from the front, and the queue length is the answer.'],
    ['Times arrive in increasing order.', 'Once a request is older than t − 3000, can any later ping count it?', 'Old requests leave in the order they arrived: first in, first out.',
     'A deque appends at the back and pops from the front, both in O(1).', 'On each ping, append t, then pop from the front while the front is older than t − 3000.', 'The answer is the queue length.'],
    ['Why can an expired request be discarded forever?', 'Why does a queue, and not a stack, match the order requests expire in?'], 'window-max', ('O(1) amortized per ping', 'O(w) for the w requests in the window'),
    (QUEUE, 'On each ping, discard every request older than t − 3000 and count the rest.',
     'Requests expire in arrival order, so a FIFO queue drops them from the front; each request is appended once and removed once.',
     {SEARCH: ('alternative', 'Binary-searching the list of all times for t − 3000 also counts the window in O(log n), but it keeps every request forever.'),
      WINDOW: ('partial', "It is a sliding time window. The queue is how the window's left edge drops expired requests in order.")},
     [(r'expire|older|outside|out of the window|discard|drop|remove|too old', 'discarding requests that left the window', 'Which requests can never count again?'),
      (r'queue|deque|front|popleft|first in|fifo|arrival order', 'removing from the front in arrival order', 'At which end do expired requests leave?'),
      (r'length|len\(|size|count|how many', 'answering with the size of what remains', 'Once the old requests are gone, what is the answer?')]),
    ('Expired requests', 'Now ping(t) records the request and returns how many earlier requests fell out of the window because of this ping.', 'Return each operation\'s answer: None for the constructor, then one count per ping.',
     'Your queue already drops the expired requests. What if the answer is how many were dropped?',
     'Count the pops made during this ping instead of returning the queue length.',
     'The queue makes expiry visible as events: every popleft is one request leaving the window, so counting pops answers a new question with the same structure.',
     '''from collections import deque


class RecentCounter:
    def __init__(self):
        self.calls = deque()

    def ping(self, t):
        self.calls.append(t)
        dropped = 0
        while self.calls[0] < t - 3000:
            self.calls.popleft()
            dropped += 1
        return dropped
''',
     [('Example', [['RecentCounter', 'ping', 'ping', 'ping', 'ping'], [[], [1], [100], [3001], [3002]]], [None, 0, 0, 0, 1]),
      ('Far apart', [['RecentCounter', 'ping', 'ping'], [[], [1], [5000]]], [None, 0, 1]), ('Burst', [['RecentCounter', 'ping', 'ping', 'ping'], [[], [10], [11], [12]]], [None, 0, 0, 0]),
      ('Window slides past several', [['RecentCounter', 'ping', 'ping', 'ping', 'ping'], [[], [1], [2], [3], [3003]]], [None, 0, 0, 0, 2])]),
    entry='RecentCounter',
    starter='class RecentCounter:\n    def __init__(self):\n        # What do you need to remember about earlier requests?\n        pass\n\n    def ping(self, t):\n        # Record a request at time t; return how many requests are in [t - 3000, t].\n        pass\n'))

LABS.append(lab(
    'window-max', 'Sliding Window Maximum', 'Queues', 'nums, k',
    'A window of size k slides across the array one position at a time. Return the maximum of each window, from left to right.',
    'A list of numbers and a window size k.', 'Find the largest value in every window of k consecutive values.', 'Return the list of window maximums.',
    ([[1, 3, -1, -3, 5, 3, 6, 7], 3], [3, 3, 5, 5, 6, 7]),
    [('Window of one', [[4, 2, 8], 1], [4, 2, 8]), ('Whole array', [[4, 2, 8], 3], [8]), ('Falling values', [[9, 7, 5, 3], 2], [9, 7, 5])],
    [('Equal values', [[2, 2, 2], 2], [2, 2]), ('Negatives', [[-4, -2, -7, -1], 2], [-2, -2, -1])],
    fn('nums, k', '''
window = deque()
result = []
for i, x in enumerate(nums):
    while window and nums[window[-1]] <= x:
        window.pop()
    window.append(i)
    if window[0] <= i - k:
        window.popleft()
    if i >= k - 1:
        result.append(nums[window[0]])
return result''', 'from collections import deque'),
    fn('nums, k', '''
result = []
for i in range(len(nums) - k + 1):
    result.append(max(nums[i:i + k]))
return result'''),
    ['Take the maximum of every window separately.', 'Neighbouring windows share k − 1 values, yet each maximum rescans all k: O(n · k).',
     'A value with a larger value after it can never be a window maximum again.',
     'Keep a deque of candidate indices with decreasing values: drop smaller ones from the back, expired ones from the front; the front is the maximum.'],
    ['Unlike a sum, a maximum cannot be updated by subtracting the value that leaves.', 'When a larger value enters, what happens to the smaller values before it?',
     'Those smaller values can never be a maximum again: discard them.', 'Keep the remaining candidates in a deque, in decreasing order of value.',
     'Store indices, so you can tell when the front candidate has left the window.', 'Once i ≥ k − 1, the front of the deque is the current window\'s maximum.'],
    ['Why can a value with a larger value after it be discarded forever?', 'Why does the deque store indices rather than values?'], 'recent-calls', ('O(n)', 'O(k)'),
    (QUEUE, 'As the window moves, know the largest value inside it without rescanning the window.',
     'A monotonic deque keeps only indices that could still be a maximum, in decreasing order of value; each index enters and leaves once, so all windows take O(n).',
     {WINDOW: ('partial', 'It is a sliding window, but a maximum cannot be updated by adding and subtracting like a sum. The deque of candidates makes the update O(1).'),
      HEAP: ('alternative', 'A max-heap of (value, index) pairs with lazy removal of expired indices also works, in O(n log n).')},
     [(r'candidate|could (still )?be|useless|never (be )?(a |the )?max|dominat|smaller.{0,40}(before|behind|left)', 'discarding values that can never be a maximum', 'When a new value arrives, which older values can never be a window maximum again?'),
      (r'deque|decreas|monoton|front|both ends', 'a deque in decreasing order of value', 'In what order do you keep the candidates, and at which ends do they leave?'),
      (r'expire|out of (the )?window|i\s*-\s*k|left edge|old index|indices|index', 'removing indices that left the window', 'How do you know the front candidate is still inside the window?')]),
    ('Window spread', 'Now return, for each window, its largest value minus its smallest value.', 'Return the list of spreads, one per window.',
     'One deque tracks each window\'s maximum. What could track the minimum at the same time?',
     'Keep a second deque with increasing values for the minimum; both drop expired indices from the front.',
     'Monotonic deques compose: one per extreme, each updated in O(1) amortized per step.',
     fn('nums, k', '''
high = deque()
low = deque()
result = []
for i, x in enumerate(nums):
    while high and nums[high[-1]] <= x:
        high.pop()
    while low and nums[low[-1]] >= x:
        low.pop()
    high.append(i)
    low.append(i)
    if high[0] <= i - k:
        high.popleft()
    if low[0] <= i - k:
        low.popleft()
    if i >= k - 1:
        result.append(nums[high[0]] - nums[low[0]])
return result''', 'from collections import deque'),
     [('Example', [[1, 3, -1, -3, 5, 3, 6, 7], 3], [4, 6, 8, 8, 3, 4]), ('Window of one', [[4, 2, 8], 1], [0, 0, 0]), ('Whole array', [[4, 2, 8], 3], [6]),
      ('Equal values', [[2, 2, 2], 2], [0, 0])]),
    level='Medium'))

# ----------------------------------------------------------------------------- Heaps
LABS.append(lab(
    'kth-largest', 'Kth Largest Element', 'Heaps', 'nums, k',
    'Return the kth largest value in the array. Duplicates count separately: in [3, 3, 2] the 2nd largest value is 3.',
    'A list of numbers and k, with 1 ≤ k ≤ the list\'s length.', 'Find the value that would sit at position k if the list were sorted from largest to smallest.', 'Return that value.',
    ([[3, 2, 1, 5, 6, 4], 2], 5),
    [('Duplicates count', [[3, 3, 2], 2], 3), ('k is 1', [[7, 1, 9], 1], 9), ('Smallest value', [[7, 1, 9], 3], 1)],
    [('Negatives', [[-1, -5, -3], 2], -3), ('Single value', [[4], 1], 4)],
    fn('nums, k', '''
heap = []
for x in nums:
    heapq.heappush(heap, x)
    if len(heap) > k:
        heapq.heappop(heap)
return heap[0]''', 'import heapq'),
    fn('nums, k', '''
ordered = sorted(nums, reverse=True)
return ordered[k - 1]'''),
    ['Sort the whole list from largest to smallest and take position k − 1.', 'Sorting orders all n values although only the top k matter: O(n log n).',
     'Only the k largest values seen so far can contain the answer, and the smallest of them is the current kth largest.',
     'Keep a min-heap of size k: push each value, and pop the smallest whenever the heap grows past k.'],
    ['Duplicates count as separate values.', 'Do you need the full order, or only the top k values?', 'Among the k largest values so far, which one is the kth largest?',
     'A min-heap reads the smallest of a group in O(1) and removes it in O(log k).', 'Push each value; if the heap holds more than k values, pop the smallest.',
     'After every value, the heap\'s root heap[0] is the answer.'],
    ['Why a min-heap, and not a max-heap, for the kth largest?', 'Why does the heap never need more than k values?'], 'last-stone', ('O(n log k)', 'O(k)'),
    (HEAP, 'Keep the k largest values seen so far and know the smallest of them.',
     'A min-heap of size k holds exactly those values; its root is the kth largest, and each update costs O(log k).', {},
     [(r'\bk\b largest|top k|k (biggest|largest)|keep k|size k|at most k|k values', 'keeping only the k largest values', 'How many values do you need to keep at any time?'),
      (r'min.?heap|smallest of|heappop|pop the smallest|remove the smallest', 'removing the smallest of the kept values', 'When a new value makes too many, which one goes?'),
      (r'root|heap\[0\]|\btop\b|smallest kept|answer is', 'reading the answer at the root', 'After all values, where is the kth largest?')]),
    ('Kth largest distinct', 'Now duplicates count once: return the kth largest distinct value, or None if the list has fewer than k distinct values.', 'Return a value, or None.',
     'The heap counted every copy. What changes if equal values must count once?', 'Feed the heap each distinct value once, and check that k distinct values exist before answering.',
     'The heap is unchanged; what changes is what goes into it. Choosing the input (distinct values) is part of the algorithm.',
     fn('nums, k', '''
heap = []
for x in set(nums):
    heapq.heappush(heap, x)
    if len(heap) > k:
        heapq.heappop(heap)
return heap[0] if len(heap) == k else None''', 'import heapq'),
     [('Example', [[5, 5, 4, 3], 2], 4), ('Duplicates count once', [[3, 3, 2], 2], 2), ('Too few distinct', [[5, 5, 5], 2], None), ('Negatives', [[-1, -1, -3], 2], -3)]),
    level='Medium'))

LABS.append(lab(
    'last-stone', 'Last Stone Weight', 'Heaps', 'stones',
    'Each turn, smash the two heaviest stones together. Equal stones are both destroyed; otherwise the lighter one is destroyed and the heavier one loses that weight. Return the weight of the last stone, or 0 if none remain.',
    'A list of positive stone weights.', 'Repeat the smashing until at most one stone is left.', 'Return the last stone\'s weight, or 0.',
    ([[2, 7, 4, 1, 8, 1]], 1),
    [('One stone', [[5]], 5), ('Equal pair', [[3, 3]], 0), ('No stones', [[]], 0)],
    [('Three stones', [[10, 4, 4]], 2), ('All equal', [[2, 2, 2]], 2)],
    fn('stones', '''
heap = [-s for s in stones]
heapq.heapify(heap)
while len(heap) > 1:
    first = -heapq.heappop(heap)
    second = -heapq.heappop(heap)
    if first != second:
        heapq.heappush(heap, -(first - second))
return -heap[0] if heap else 0''', 'import heapq'),
    fn('stones', '''
stones = list(stones)
while len(stones) > 1:
    stones.sort()
    first = stones.pop()
    second = stones.pop()
    if first != second:
        stones.append(first - second)
return stones[0] if stones else 0'''),
    ['Sort the stones every turn and take the two heaviest.', 'Every turn re-sorts all the stones to find just two values: O(n² log n) over all turns.',
     'Each turn only needs the two largest values, and only one new value goes back in.',
     'A max-heap (negated values with heapq) returns the heaviest stone in O(log n) and accepts the remainder in O(log n).'],
    ['Each turn needs the two heaviest stones.', 'After a smash, at most one new stone goes back.', 'Which structure keeps the largest value available as values come and go?',
     'Python\'s heapq is a min-heap. Store negated weights to pop the heaviest first.', 'Pop twice; if the stones differ, push the difference back.', 'At the end, the heap holds one stone or none.'],
    ['Why store negated weights in heapq?', 'Why is re-sorting every turn wasteful?'], 'kth-largest', ('O(n log n)', 'O(n)'),
    (HEAP, 'Each turn, remove the two heaviest stones and insert what remains of them.',
     'A heap keeps the maximum available after every insertion and removal in O(log n), so no turn needs a full sort.', {},
     [(r'two (heaviest|largest|biggest)|heaviest|largest|\bmax', 'taking the two heaviest stones each turn', 'Which two stones does every turn need?'),
      (r'max.?heap|negat|minus|-s\b|heapq|priority', 'a max-heap built from negated weights', 'heapq is a min-heap. How do you get the heaviest stone first?'),
      (r'push|insert|put back|remainder|difference|first\s*-\s*second', 'putting the remainder back', 'What happens to the heavier stone when the two differ?')]),
    ('Count the smashes', 'Now return how many smashes happen before at most one stone remains.', 'Return an integer count.',
     'The heap already performs every smash. What do you need to record?', 'Count one smash per pair popped, whether or not a remainder goes back.',
     'The same simulation answers a different question; only what you record changes.',
     fn('stones', '''
heap = [-s for s in stones]
heapq.heapify(heap)
smashes = 0
while len(heap) > 1:
    first = -heapq.heappop(heap)
    second = -heapq.heappop(heap)
    smashes += 1
    if first != second:
        heapq.heappush(heap, -(first - second))
return smashes''', 'import heapq'),
     [('Example', [[2, 7, 4, 1, 8, 1]], 4), ('One stone', [[5]], 0), ('Equal pair', [[3, 3]], 1), ('No stones', [[]], 0), ('Three stones', [[10, 4, 4]], 2)])))

# ----------------------------------------------------------------------------- Recursion
LABS.append(lab(
    'subsets', 'All Subsets', 'Recursion', 'nums',
    'Return every subset of the distinct values in nums, including the empty subset. Each subset keeps its values in input order; the subsets may come in any order.',
    'A list of distinct numbers.', 'Build every possible selection of the values.', 'Return a list of subsets; their order does not matter.',
    ([[1, 2, 3]], subsets_of([1, 2, 3])),
    [('Empty input', [[]], [[]]), ('One value', [[5]], [[], [5]]), ('Two values', [[4, 9]], [[], [4], [9], [4, 9]])],
    [('Negatives', [[-1, 0]], [[], [-1], [0], [-1, 0]]), ('Four values', [[1, 2, 3, 4]], subsets_of([1, 2, 3, 4]))],
    fn('nums', '''
result = []
chosen = []

def explore(i):
    if i == len(nums):
        result.append(list(chosen))
        return
    explore(i + 1)
    chosen.append(nums[i])
    explore(i + 1)
    chosen.pop()

explore(0)
return result'''),
    fn('nums', '''
result = [[]]
for x in nums:
    result = result + [subset + [x] for subset in result]
return result'''),
    ['List the subsets by size by hand: easy for three values, hopeless for twenty.', 'Hand-written nested loops fix the depth in advance, but the number of decisions equals len(nums).',
     'Each value faces one decision: leave it out or put it in. Every subset is one sequence of decisions.',
     'Recurse on the position: explore without nums[i], then with it, and undo the choice afterwards.'],
    ['How many subsets does a list of n distinct values have?', 'For each value there are exactly two choices.', 'Decide for nums[0], then solve the same problem for the rest of the list.',
     'A helper explore(i) can decide for position i and call explore(i + 1).', 'Append before the second call and pop after it, so chosen is restored (backtracking).',
     'When i reaches len(nums), chosen is one complete subset: append a copy of it.'],
    ['Why must you append list(chosen) rather than chosen itself?', 'Why is chosen.pop() needed after the recursive call?'], 'permutations', ('O(n · 2ⁿ)', 'O(n) besides the output'),
    (RECURSION, 'Make one include-or-exclude decision per value and record every complete sequence of decisions.',
     'Recursion replaces an unknown number of nested loops with one call per decision; undoing each choice (backtracking) lets one list hold the current subset.',
     {BITS: ('alternative', 'Each subset is a binary number with one bit per value; looping over 0 … 2ⁿ − 1 builds the same subsets without recursion.')},
     [(r'include|exclude|in or out|take|skip|leave|two choices|choose', 'one include-or-exclude decision per value', 'What decision does each value face?'),
      (r'recurs|call itself|helper|explore|i\s*\+\s*1|next (index|position|value)', 'recursing to the next position', 'After deciding for one value, what is left to solve?'),
      (r'undo|pop|backtrack|restore|remove (it|the last)|copy|list\(', 'undoing the choice and recording copies', 'How do you reuse one list for every subset without changing earlier answers?')]),
    ('Count the even sums', 'Now return how many subsets have an even sum. The empty subset has sum 0, which is even.', 'Return an integer count.',
     'You recorded every subset. What would you need to carry through the recursion to judge each one without storing it?',
     'Pass the running sum as a parameter, explore(i, total); at the end, return 1 if total is even and 0 otherwise.',
     'Recursion can return answers instead of collecting them: each call returns the count for the decisions below it, and the caller adds both branches.',
     fn('nums', '''
def explore(i, total):
    if i == len(nums):
        return 1 if total % 2 == 0 else 0
    return explore(i + 1, total) + explore(i + 1, total + nums[i])

return explore(0, 0)'''),
     [('Example', [[1, 2, 3]], 4), ('Empty input', [[]], 1), ('One odd value', [[5]], 1), ('All even', [[2, 4]], 4)]),
    level='Medium', order='any'))

LABS.append(lab(
    'permutations', 'All Permutations', 'Recursion', 'nums',
    'Return every ordering of the distinct values in nums. The orderings may come in any order.',
    'A list of distinct numbers.', 'Build every way to arrange all the values.', 'Return a list of orderings; their order does not matter.',
    ([[1, 2, 3]], orderings([1, 2, 3])),
    [('Empty input', [[]], [[]]), ('One value', [[7]], [[7]]), ('Two values', [[0, 1]], [[0, 1], [1, 0]])],
    [('Negatives', [[-1, 2]], [[-1, 2], [2, -1]]), ('Four values', [[1, 2, 3, 4]], orderings([1, 2, 3, 4]))],
    fn('nums', '''
result = []
path = []
used = [False] * len(nums)

def build():
    if len(path) == len(nums):
        result.append(list(path))
        return
    for i in range(len(nums)):
        if not used[i]:
            used[i] = True
            path.append(nums[i])
            build()
            path.pop()
            used[i] = False

build()
return result'''),
    fn('nums', '''
result = [[]]
for x in nums:
    result = [p[:i] + [x] + p[i:] for p in result for i in range(len(p) + 1)]
return result'''),
    ['Write out the orderings by hand: the first position has n choices, the next n − 1, and so on.', 'A fixed number of nested loops only works for one list length, and there are n! orderings to reach.',
     'Filling one position leaves the same problem on the remaining values.', 'Recurse: choose an unused value for the next position, recurse, then undo the choice.'],
    ['How many orderings do n distinct values have?', 'What choices exist for the first position?', 'After placing one value, what smaller problem remains?',
     'Track which values are already used, for example with a list of booleans.', 'Mark a value used and append it before recursing; pop it and unmark it afterwards.',
     'When the path holds every value, record a copy of it.'],
    ['Why must used[i] be reset after the recursive call?', 'How many leaves does the recursion reach for n values?'], 'subsets', ('O(n · n!)', 'O(n) besides the output'),
    (RECURSION, 'Choose an unused value for the next position, then arrange the rest the same way.',
     'Each recursive call fills one position; marking a value used before the call and unmarking it after (backtracking) explores every ordering exactly once.', {},
     [(r'unused|not used|\bused\b|available|remaining|left over', 'choosing only values not used yet', 'Which values may fill the next position?'),
      (r'recurs|call|helper|build|next position|fill', 'recursing to fill the next position', 'After placing one value, what smaller problem remains?'),
      (r'undo|pop|backtrack|unmark|restore|false', 'undoing the choice afterwards', 'What must be restored after the recursive call returns?')]),
    ('Nothing stays in place', 'Now return how many orderings move every value away from its original position.', 'Return an integer count.',
     'The recursion already fills positions one at a time. Which choices does the new rule forbid at each position?',
     'When filling position pos, skip the value whose original index is pos; return counts instead of lists.',
     'A constraint on each choice prunes the recursion tree: the same backtracking shape, with fewer branches and a count instead of a list.',
     fn('nums', '''
used = [False] * len(nums)

def count(pos):
    if pos == len(nums):
        return 1
    total = 0
    for i in range(len(nums)):
        if not used[i] and i != pos:
            used[i] = True
            total += count(pos + 1)
            used[i] = False
    return total

return count(0)'''),
     [('Example', [[1, 2, 3]], 2), ('Two values', [[0, 1]], 1), ('One value', [[7]], 0), ('Empty input', [[]], 1), ('Four values', [[1, 2, 3, 4]], 9)]),
    level='Medium', order='any'))

# ----------------------------------------------------------------------------- Trees
LABS.append(lab(
    'max-depth', 'Maximum Depth of a Binary Tree', 'Trees', 'root',
    'Return the number of nodes on the longest path from the root down to a leaf. An empty tree has depth 0.',
    TREE, 'Find the longest path from the root down to a leaf.', 'Return the number of nodes on it.',
    ([[3, 9, 20, None, None, 15, 7]], 3),
    [('Empty tree', [[]], 0), ('Only a root', [[1]], 1), ('Leaning right', [[1, None, 2, None, 3]], 3)],
    [('Leaning left', [[1, 2, None, 3]], 3), ('Full tree', [[1, 2, 3, 4, 5, 6, 7]], 3)],
    fn('root', '''
if root is None:
    return 0
return 1 + max(solve(root.left), solve(root.right))'''),
    fn('root', '''
paths = []

def walk(node, path):
    if node is None:
        return
    path = path + [node.val]
    if node.left is None and node.right is None:
        paths.append(path)
    walk(node.left, path)
    walk(node.right, path)

walk(root, [])
best = 0
for p in paths:
    best = max(best, len(p))
return best'''),
    ['Write down every root-to-leaf path and measure the longest one.', 'Storing whole paths copies values again and again, although only their lengths matter.',
     'The depth of a tree is one more than the depth of its deeper subtree.', 'Recurse: depth(node) = 1 + max(depth(left), depth(right)), with depth(None) = 0.'],
    ['Depth counts nodes, not edges.', 'What is the depth of an empty tree?', 'If you knew the depths of the left and right subtrees, what is the depth of the whole tree?',
     'That is the same problem on smaller trees: recursion.', 'Base case: None has depth 0.', 'Return 1 + max(left depth, right depth).'],
    ['Why is None, rather than a leaf, the natural base case?', 'What does each call return to its caller?'], 'level-order', ('O(n)', 'O(h) for tree height h'),
    (DFS, 'For each node, know how deep its left and right subtrees go.',
     'A depth-first recursion answers each subtree once and combines two answers in O(1), so every node is visited once.',
     {BFS: ('alternative', 'Counting levels with a queue (breadth-first) also works in O(n); depth-first recursion states "1 + the deeper subtree" directly.'),
      RECURSION: ('partial', "It is recursion, over the tree's own structure: a depth-first traversal in which each call returns its subtree's depth.")},
     [(r'none|null|empty|base case|leaf', 'the empty tree as the base case', 'What should an empty subtree return?'),
      (r'left and right|both (subtrees|children|sides)|each subtree|left.{0,40}right', 'asking both subtrees', 'Which two smaller problems does each node depend on?'),
      (r'1\s*\+|one more|plus one|\bmax\b|deeper|larger', 'one plus the deeper subtree', 'How do the two subtree answers combine?')]),
    ('Minimum depth', 'Now return the number of nodes on the shortest path from the root down to a leaf, a node with no children. An empty tree has depth 0.', 'Return an integer depth.',
     'Is replacing max with min enough? Try a root with only a right child.',
     'A missing child is not a leaf: if one child is missing, the answer comes from the other side only.',
     'Changing max to min changes the base case too: the recursion must stop at real leaves, not at missing children.',
     fn('root', '''
if root is None:
    return 0
if root.left is None:
    return 1 + solve(root.right)
if root.right is None:
    return 1 + solve(root.left)
return 1 + min(solve(root.left), solve(root.right))'''),
     [('Example', [[3, 9, 20, None, None, 15, 7]], 2), ('Leaning right', [[1, None, 2, None, 3]], 3), ('Empty tree', [[]], 0), ('Only a root', [[1]], 1),
      ('Full tree', [[1, 2, 3, 4, 5, 6, 7]], 3)]),
    kinds={'root': 'tree'}))

LABS.append(lab(
    'level-order', 'Level Order Traversal', 'Trees', 'root',
    'Return the values of a binary tree level by level: a list of lists, top level first, each level from left to right.',
    TREE, 'Visit the nodes level by level, left to right.', 'Return one list of values per level.',
    ([[3, 9, 20, None, None, 15, 7]], [[3], [9, 20], [15, 7]]),
    [('Empty tree', [[]], []), ('Only a root', [[1]], [[1]]), ('Leaning right', [[1, None, 2, None, 3]], [[1], [2], [3]])],
    [('Full tree', [[1, 2, 3, 4, 5, 6, 7]], [[1], [2, 3], [4, 5, 6, 7]]), ('Negatives', [[0, -1, 1]], [[0], [-1, 1]])],
    fn('root', '''
if root is None:
    return []
levels = []
queue = deque([root])
while queue:
    level = []
    for _ in range(len(queue)):
        node = queue.popleft()
        level.append(node.val)
        if node.left:
            queue.append(node.left)
        if node.right:
            queue.append(node.right)
    levels.append(level)
return levels''', 'from collections import deque'),
    fn('root', '''
def collect(node, d, depth, found):
    if node is None:
        return
    if d == depth:
        found.append(node.val)
        return
    collect(node.left, d + 1, depth, found)
    collect(node.right, d + 1, depth, found)

levels = []
depth = 0
while True:
    found = []
    collect(root, 0, depth, found)
    if not found:
        return levels
    levels.append(found)
    depth += 1'''),
    ['For each depth, walk the whole tree again and collect the nodes at that depth.', 'Every level restarts from the root and re-walks all the levels above it: O(n · h).',
     'The nodes of the next level are exactly the children of the current level, in order.',
     'Use a queue: take len(queue) nodes as one level, appending their children for the next one.'],
    ['The answer lists depth 0, then depth 1, then depth 2.', 'Where do the nodes of the next level come from?', 'Nodes leave in the order they were discovered: first in, first out.',
     'A deque appends at the back and pops from the front.', 'At the start of each level, len(queue) is exactly the number of nodes on that level.',
     'Pop that many nodes, record their values, and append their children.'],
    ['Why does a queue produce left-to-right order?', 'Why is len(queue) read before the inner loop starts?'], 'max-depth', ('O(n)', 'O(w) for the widest level w'),
    (BFS, 'Visit the nodes level by level, left to right, knowing where each level ends.',
     'A FIFO queue releases nodes in the order their parents were visited; taking len(queue) nodes at a time separates the levels, and every node is handled once.',
     {DFS: ('alternative', 'A depth-first walk that passes the depth and appends to levels[depth] also works in O(n); breadth-first matches the level order directly.')},
     [(r'queue|deque|fifo|popleft|first in', 'a queue of nodes to visit', 'Which structure releases nodes in the order you discovered them?'),
      (r'len\(queue\)|level size|size of (the )?level|how many|one level at a time|per level|each level', 'knowing how many nodes form the current level', 'How do you know where one level ends and the next begins?'),
      (r'child|left and right|append (the )?(left|right)|enqueue|add (its|their)', "adding each node's children for the next level", 'What do you add to the queue when you take a node out?')]),
    ('Right side view', 'Now return only the last value of each level, top to bottom: what you see looking at the tree from the right.', 'Return one value per level.',
     'Your levels are complete lists. Which value of each level do you keep now?', 'Record only the last node popped on each level.',
     'Level separation is the reusable part: once you know where a level ends, any per-level question (last, first, largest) is one line.',
     fn('root', '''
if root is None:
    return []
view = []
queue = deque([root])
while queue:
    size = len(queue)
    for i in range(size):
        node = queue.popleft()
        if i == size - 1:
            view.append(node.val)
        if node.left:
            queue.append(node.left)
        if node.right:
            queue.append(node.right)
return view''', 'from collections import deque'),
     [('Example', [[3, 9, 20, None, None, 15, 7]], [3, 20, 7]), ('Empty tree', [[]], []), ('Leaning left', [[1, 2, None, 3]], [1, 2, 3]), ('Full tree', [[1, 2, 3, 4, 5, 6, 7]], [1, 3, 7])]),
    level='Medium', kinds={'root': 'tree'}))

# ----------------------------------------------------------------------------- Tries
TRIE_SOURCE = '''class TrieNode:
    def __init__(self):
        self.children = {}
        self.end = False


class Trie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, word):
        node = self.root
        for ch in word:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
        node.end = True

    def search(self, word):
        node = self.find(word)
        return node is not None and node.end

    def startsWith(self, prefix):
        return self.find(prefix) is not None

    def find(self, text):
        node = self.root
        for ch in text:
            if ch not in node.children:
                return None
            node = node.children[ch]
        return node
'''
LABS.append(lab(
    'implement-trie', 'Implement a Trie', 'Tries', 'operations, arguments',
    'Design Trie. insert(word) stores a word; search(word) returns True if that exact word was inserted; startsWith(prefix) returns True if any inserted word starts with prefix.',
    DESIGN, 'Store words so that whole words and prefixes can be checked quickly.', DESIGN_RETURNS,
    ([['Trie', 'insert', 'search', 'search', 'startsWith', 'insert', 'search'], [[], ['apple'], ['apple'], ['app'], ['app'], ['app'], ['app']]], [None, None, True, False, True, None, True]),
    [('Prefix is not a word', [['Trie', 'insert', 'search', 'startsWith'], [[], ['car'], ['ca'], ['ca']]], [None, None, False, True]),
     ('Empty trie', [['Trie', 'search', 'startsWith'], [[], ['a'], ['a']]], [None, False, False]),
     ('Shared prefix', [['Trie', 'insert', 'insert', 'search', 'search'], [[], ['cat'], ['car'], ['cat'], ['cab']]], [None, None, None, True, False])],
    [('Longer than any word', [['Trie', 'insert', 'search', 'startsWith'], [[], ['go'], ['gone'], ['gon']]], [None, None, False, False]),
     ('Same word twice', [['Trie', 'insert', 'insert', 'search'], [[], ['hi'], ['hi'], ['hi']]], [None, None, None, True])],
    TRIE_SOURCE,
    '''class Trie:
    def __init__(self):
        self.words = []

    def insert(self, word):
        self.words.append(word)

    def search(self, word):
        return word in self.words

    def startsWith(self, prefix):
        for w in self.words:
            if w.startswith(prefix):
                return True
        return False
''',
    ['Keep a list of words and compare against each one.', 'Every search and prefix check scans all stored words, character by character.',
     'Words that share a beginning could share the stored path for that beginning.',
     'Store the characters as a tree of nodes: each node maps a character to a child node and marks whether a word ends there.'],
    ['apple and app share their first three letters.', 'What if each letter were a step from one node to the next?', 'A node can map each next character to a child node: a dictionary.',
     'insert walks the word, creating missing children.', 'A node needs a flag saying whether a word ends there, or app could not be told apart from a prefix of apple.',
     'search needs the flag at the last node; startsWith only needs the path to exist.'],
    ['Why does search need an end-of-word flag but startsWith does not?', 'Why does the cost of search depend on the word length, not the number of words?'], 'prefix-counts',
    ('O(L) per operation for a word of length L', 'O(total characters inserted)'),
    (TRIE, 'Check whether a word or a prefix was inserted, without comparing against every stored word.',
     'A trie stores each shared prefix once; an operation walks one node per character, so its cost depends on the word length, not on how many words are stored.',
     {HASH: ('alternative', 'A set of words answers search in O(L) expected time, and a second set of every prefix answers startsWith, at the cost of storing every prefix separately.')},
     [(r'shar|common prefix|same (start|beginning)|prefix', 'sharing nodes for common prefixes', 'What do apple and app have in common, and how could you store it once?'),
      (r'node|child|children|dict|\bmap\b|per (character|letter)|each (character|letter)', 'a node per character, with children by letter', 'What does each node store, and how do you move to the next letter?'),
      (r'\bend\b|terminal|is.?word|word ends|mark|flag', 'marking where a word ends', 'How does search tell the word app apart from a prefix of apple?')]),
    ('Count by prefix', 'Now startsWith(prefix) returns how many inserted words start with prefix, counting repeated words, instead of True or False.', DESIGN_RETURNS,
     'Your trie walks to the node for a prefix. What could that node remember about the words below it?',
     'Give every node a count, and add one to each node a word passes through during insert.',
     'A trie node can carry any summary of the words beneath it; a count turns a yes-or-no prefix check into a number in the same O(L) walk.',
     '''class TrieNode:
    def __init__(self):
        self.children = {}
        self.end = False
        self.count = 0


class Trie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, word):
        node = self.root
        for ch in word:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
            node.count += 1
        node.end = True

    def search(self, word):
        node = self.find(word)
        return node is not None and node.end

    def startsWith(self, prefix):
        node = self.find(prefix)
        return node.count if node else 0

    def find(self, text):
        node = self.root
        for ch in text:
            if ch not in node.children:
                return None
            node = node.children[ch]
        return node
''',
     [('Example', [['Trie', 'insert', 'insert', 'startsWith', 'startsWith'], [[], ['apple'], ['app'], ['app'], ['b']]], [None, None, None, 2, 0]),
      ('Shared prefix', [['Trie', 'insert', 'insert', 'startsWith'], [[], ['cat'], ['car'], ['ca']]], [None, None, None, 2]),
      ('Same word twice', [['Trie', 'insert', 'insert', 'startsWith'], [[], ['hi'], ['hi'], ['h']]], [None, None, None, 2]),
      ('Empty trie', [['Trie', 'startsWith'], [[], ['a']]], [None, 0])]),
    level='Medium', entry='Trie',
    starter='class Trie:\n    def __init__(self):\n        # How will you store the words?\n        pass\n\n    def insert(self, word):\n        pass\n\n    def search(self, word):\n        # True if this exact word was inserted.\n        pass\n\n    def startsWith(self, prefix):\n        # True if any inserted word starts with prefix.\n        pass\n'))

COUNTING_NODE = '''class TrieNode:
    def __init__(self):
        self.children = {}
        self.count = 0'''
LABS.append(lab(
    'prefix-counts', 'Count Words by Prefix', 'Tries', 'words, queries',
    'For each query, count how many words in the list start with that query. Words may repeat, and each copy counts.',
    'A list of words and a list of non-empty queries, all lowercase.', 'For each query, count the words that begin with it.', 'Return one count per query, in order.',
    ([['apple', 'app', 'apply', 'bat'], ['app', 'ap', 'b', 'c']], [3, 3, 1, 0]),
    [('Whole word', [['car', 'cart'], ['car']], [2]), ('No words', [[], ['a']], [0]), ('Repeats count', [['hi', 'hi', 'him'], ['hi', 'him']], [3, 1])],
    [('Query longer than the words', [['go'], ['gone']], [0]), ('No queries', [['a', 'b'], []], [])],
    fn('words, queries', '''
root = TrieNode()
for word in words:
    node = root
    for ch in word:
        if ch not in node.children:
            node.children[ch] = TrieNode()
        node = node.children[ch]
        node.count += 1
answers = []
for query in queries:
    node = root
    for ch in query:
        node = node.children.get(ch)
        if node is None:
            break
    answers.append(node.count if node else 0)
return answers''', COUNTING_NODE),
    fn('words, queries', '''
answers = []
for query in queries:
    count = 0
    for word in words:
        if word.startswith(query):
            count += 1
    answers.append(count)
return answers'''),
    ['For each query, check every word with startswith.', 'Each query rescans every word, and words that share a prefix are compared again and again: O(q · n · L).',
     'All words that start with a prefix pass through the same trie node, so that node can remember how many did.',
     'Build a trie once, counting at every node the words that pass through it; each query walks its characters and reads the count.'],
    ['Many queries ask about the same words.', 'What could you build once, before answering any query?', 'In a trie, every word starting with "ap" passes through the node for "ap".',
     'Give each node a count, and add one to every node a word passes through.', 'A query walks its characters; the count at its last node is the answer.',
     'If the query leaves the trie, no word starts with it: the answer is 0.'],
    ['Why is the count stored on every node, not only where words end?', 'What does building the trie once save across many queries?'], 'implement-trie',
    ('O(total characters in words and queries)', 'O(total characters in words)'),
    (TRIE, 'For each query, know how many words pass through its prefix.',
     'A trie built once stores, at each node, how many words pass through it; each query then costs one step per character.',
     {HASH: ('alternative', 'A dictionary from every prefix of every word to a count also answers each query in O(L) expected time, using memory for every prefix.')},
     [(r'build (it |the trie )?once|preprocess|insert (all|every|each) word|before (the |any )?quer', 'building the trie once before the queries', 'What can you prepare once so that every query is cheap?'),
      (r'count|how many|pass(es)? through|tally', 'counting the words through each node', 'What should each node remember, so a query can read it directly?'),
      (r'walk|follow|each character|per character|missing|break|not found|leaves the trie', 'walking the query and stopping at a missing letter', 'What happens when the query leaves the trie?')]),
    ('Longest stored prefix', 'Now, for each query, return the length of the longest prefix of the query that is itself a word in the list, or 0 if there is none.', 'Return one length per query, in order.',
     'Counting through-traffic answered "how many start with this". What must a node know to say "a word ends here"?',
     'Mark where words end; while walking a query, remember the deepest marked node you passed.',
     'The walk is the same; the summary stored at each node and the value carried along the walk change with the question.',
     fn('words, queries', '''
root = TrieNode()
for word in words:
    node = root
    for ch in word:
        if ch not in node.children:
            node.children[ch] = TrieNode()
        node = node.children[ch]
    node.end = True
answers = []
for query in queries:
    node = root
    best = 0
    for depth, ch in enumerate(query, 1):
        node = node.children.get(ch)
        if node is None:
            break
        if node.end:
            best = depth
    answers.append(best)
return answers''', '''class TrieNode:
    def __init__(self):
        self.children = {}
        self.end = False'''),
     [('Example', [['apple', 'app', 'apply', 'bat'], ['app', 'ap', 'b', 'c']], [3, 0, 0, 0]), ('Nested words', [['a', 'app', 'apple'], ['applesauce', 'ax']], [5, 1]),
      ('No words', [[], ['a']], [0]), ('Repeats', [['hi', 'hi'], ['high']], [2])]),
    level='Medium'))

# ----------------------------------------------------------------------------- Graphs
LABS.append(lab(
    'count-components', 'Connected Groups', 'Graphs', 'graph',
    'graph[i] lists the neighbours of node i in an undirected graph. Return how many connected groups the nodes form; a node with no edges is a group by itself.',
    GRAPH, 'Count the groups of nodes that are connected to each other.', 'Return the number of groups.',
    ([[[1], [0], [3], [2], []]], 3),
    [('One group', [[[1, 2], [0, 2], [0, 1]]], 1), ('No edges', [[[], [], []]], 3), ('Empty graph', [[]], 0)],
    [('A chain', [[[1], [0, 2], [1, 3], [2]]], 1), ('Two triangles', [[[1, 2], [0, 2], [0, 1], [4, 5], [3, 5], [3, 4]]], 2)],
    fn('graph', '''
seen = [False] * len(graph)

def visit(node):
    seen[node] = True
    for nxt in graph[node]:
        if not seen[nxt]:
            visit(nxt)

groups = 0
for start in range(len(graph)):
    if not seen[start]:
        groups += 1
        visit(start)
return groups'''),
    fn('graph', '''
label = list(range(len(graph)))
changed = True
while changed:
    changed = False
    for node in range(len(graph)):
        for nxt in graph[node]:
            if label[nxt] < label[node]:
                label[node] = label[nxt]
                changed = True
return len(set(label))'''),
    ['Give every node its own label, and keep copying the smaller label across every edge until nothing changes.', 'Long chains need many full passes over every edge before the labels settle: O(n · e).',
     'Everything reachable from a node belongs to its group, so one exploration from a new node finds that whole group.',
     'Loop over the nodes; each unvisited node starts a new group, and a depth-first search marks everything it can reach.'],
    ['Two nodes are in the same group if a path of edges connects them.', 'Starting from one node, which nodes belong to its group?', 'Explore from a node and mark every node you reach.',
     'A depth-first search follows an edge to an unmarked neighbour, then continues from there.', 'A node that is still unmarked after earlier searches starts a new group.',
     'Count the searches you start.'],
    ['Why can a marked node be skipped forever?', 'Why does the count of searches equal the number of groups?'], 'shortest-path', ('O(n + e)', 'O(n)'),
    (DFS, 'From one node, mark everything reachable, so that every node is processed once.',
     'A depth-first search with visited marks explores a whole group the first time it is entered; counting the searches started counts the groups.',
     {BFS: ('alternative', 'A breadth-first search from each unvisited node marks the same groups; for counting, the visiting order does not matter.')},
     [(r'visited|seen|mark', 'marking visited nodes', 'How do you avoid exploring a node twice?'),
      (r'reach|explore|dfs|depth|neighbo|spread|travers', 'exploring everything reachable from a start', 'Starting from one node, which nodes belong to its group?'),
      (r'unvisited|new (group|component)|count|start (a|another)|each node', 'starting a new group at each unvisited node', 'When does a new group begin, and what do you count?')]),
    ('Largest group', 'Now return the number of nodes in the largest connected group, or 0 for an empty graph.', 'Return an integer size.',
     'Each search already visits exactly one group. What could it return?', 'Let the search return how many nodes it marked, and keep the largest.',
     'A traversal can compute a summary of what it visits; returning the size from each call turns "count the groups" into "measure them".',
     fn('graph', '''
seen = [False] * len(graph)

def visit(node):
    seen[node] = True
    size = 1
    for nxt in graph[node]:
        if not seen[nxt]:
            size += visit(nxt)
    return size

best = 0
for start in range(len(graph)):
    if not seen[start]:
        best = max(best, visit(start))
return best'''),
     [('Example', [[[1], [0], [3], [2], []]], 2), ('One group', [[[1, 2], [0, 2], [0, 1]]], 3), ('No edges', [[[], [], []]], 1), ('Empty graph', [[]], 0),
      ('Triangle and a pair', [[[1, 2], [0, 2], [0, 1], [4], [3]]], 3)]),
    level='Medium', kinds={'graph': 'graph'}))

LABS.append(lab(
    'shortest-path', 'Fewest Steps Between Nodes', 'Graphs', 'graph, start, goal',
    'In an undirected graph given as adjacency lists, return the fewest edges on a path from start to goal, or -1 if goal cannot be reached.',
    GRAPH + ' start and goal are node numbers.', 'Find the path from start to goal with the fewest edges.', 'Return its number of edges, or -1.',
    ([[[1, 2], [0, 3], [0, 3], [1, 2, 4], [3]], 0, 4], 3),
    [('Start is the goal', [[[1], [0]], 0, 0], 0), ('Unreachable', [[[1], [0], []], 0, 2], -1), ('Direct edge', [[[1], [0]], 0, 1], 1)],
    [('A shortcut', [[[1, 3], [0, 2], [1, 3], [2, 0]], 0, 3], 1), ('A long chain', [[[1], [0, 2], [1, 3], [2]], 0, 3], 3)],
    fn('graph, start, goal', '''
dist = [-1] * len(graph)
dist[start] = 0
queue = deque([start])
while queue:
    node = queue.popleft()
    if node == goal:
        return dist[node]
    for nxt in graph[node]:
        if dist[nxt] == -1:
            dist[nxt] = dist[node] + 1
            queue.append(nxt)
return -1''', 'from collections import deque'),
    fn('graph, start, goal', '''
dist = [-1] * len(graph)
dist[start] = 0
for _ in range(len(graph)):
    for node in range(len(graph)):
        if dist[node] == -1:
            continue
        for nxt in graph[node]:
            if dist[nxt] == -1 or dist[node] + 1 < dist[nxt]:
                dist[nxt] = dist[node] + 1
return dist[goal]'''),
    ['Keep improving every distance across every edge, round after round, until nothing changes.', 'Each round revisits every edge even where nothing can improve: O(n · e).',
     'Exploring in rings — every node 1 step away, then 2, then 3 — reaches each node first by a shortest path.',
     'Use a queue (breadth-first search): the first time a node is reached, its distance is final.'],
    ['Depth-first search can reach the goal by a long path first.', 'Which nodes are exactly one step from start? Two steps?', 'Explore all nodes at distance d before any at distance d + 1.',
     'A FIFO queue does that: nodes leave in the order they were discovered.', 'Record dist[node] when a node is first discovered, and never revisit it.',
     'Return dist[goal] the moment goal leaves the queue, or -1 if the queue empties first.'],
    ['Why is the first visit to a node in breadth-first search a shortest path?', 'Why can depth-first search not stop at its first visit to goal?'], 'count-components', ('O(n + e)', 'O(n)'),
    (BFS, 'Find the first time the goal is reached, exploring nearer nodes before farther ones.',
     'Breadth-first search with a queue visits nodes in order of distance, so the first visit to a node uses the fewest edges; every node and edge is handled once.', {},
     [(r'queue|deque|fifo|breadth|bfs|\blevel|ring|layer', 'exploring in order of distance with a queue', 'In what order must nodes be explored so that the first visit is the shortest?'),
      (r'dist|distance|steps|\+\s*1', "recording each node's distance when it is first reached", 'What do you record for a node when you first reach it?'),
      (r'visited|seen|-1|first time|already|mark', 'never revisiting a node', 'Why is the first visit to a node final?')]),
    ('Every distance', 'Now return the fewest edges from start to every node, as a list indexed by node, with -1 for nodes that cannot be reached.', 'Return a list of distances.',
     'Your search stopped at the goal. What would it learn if it kept going?', 'Do not return early: let the queue empty, then return the whole dist list.',
     'One breadth-first search answers every distance from the start at once; stopping at the goal was only an optimization for a single question.',
     fn('graph, start, goal', '''
dist = [-1] * len(graph)
dist[start] = 0
queue = deque([start])
while queue:
    node = queue.popleft()
    for nxt in graph[node]:
        if dist[nxt] == -1:
            dist[nxt] = dist[node] + 1
            queue.append(nxt)
return dist''', 'from collections import deque'),
     [('Example', [[[1, 2], [0, 3], [0, 3], [1, 2, 4], [3]], 0, 4], [0, 1, 1, 2, 3]), ('Unreachable', [[[1], [0], []], 0, 2], [0, 1, -1]),
      ('Start is the goal', [[[1], [0]], 0, 0], [0, 1]), ('A long chain', [[[1], [0, 2], [1, 3], [2]], 0, 3], [0, 1, 2, 3])]),
    level='Medium', kinds={'graph': 'graph'}))

# ----------------------------------------------------------------------------- Grids & matrices
LABS.append(lab(
    'count-islands', 'Number of Islands', 'Grids & matrices', 'grid',
    'grid is a rectangle of 1s (land) and 0s (water). An island is a group of land cells connected up, down, left or right. Return the number of islands.',
    'A non-empty rectangle of 0s and 1s, as a list of rows.', 'Count the groups of land cells connected through their four sides.', 'Return the number of islands.',
    ([[[1, 1, 0, 0], [1, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]], 3),
    [('All water', [[[0, 0], [0, 0]]], 0), ('One big island', [[[1, 1], [1, 1]]], 1), ('Diagonal is not connected', [[[1, 0], [0, 1]]], 2)],
    [('Single cell', [[[1]]], 1), ('A ring', [[[1, 1, 1], [1, 0, 1], [1, 1, 1]]], 1)],
    fn('grid', '''
rows, cols = len(grid), len(grid[0])

def sink(r, c):
    if r < 0 or r >= rows or c < 0 or c >= cols or grid[r][c] != 1:
        return
    grid[r][c] = 2
    sink(r + 1, c)
    sink(r - 1, c)
    sink(r, c + 1)
    sink(r, c - 1)

islands = 0
for r in range(rows):
    for c in range(cols):
        if grid[r][c] == 1:
            islands += 1
            sink(r, c)
return islands'''),
    fn('grid', '''
rows, cols = len(grid), len(grid[0])
label = [[r * cols + c if grid[r][c] == 1 else -1 for c in range(cols)] for r in range(rows)]
changed = True
while changed:
    changed = False
    for r in range(rows):
        for c in range(cols):
            if label[r][c] == -1:
                continue
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and label[nr][nc] != -1 and label[nr][nc] < label[r][c]:
                    label[r][c] = label[nr][nc]
                    changed = True
return len({x for row in label for x in row if x != -1})'''),
    ['Label every land cell, then keep copying the smaller label between neighbours until nothing changes; count the labels.', 'Winding islands need many full passes over the grid before the labels settle.',
     'When you find a land cell that is not part of a counted island yet, everything connected to it is that same island.',
     'Count a new island at each unvisited land cell and flood-fill it depth-first, marking cells so they are never counted again.'],
    ['Diagonal neighbours do not connect.', 'Scan the grid. When you meet land, is it a new island or one you already counted?', 'From one land cell, spread to its four neighbours, then theirs.',
     'Mark each cell you reach (for example, change 1 to 2) so it is never counted again.', 'Stop spreading at the grid\'s edges and at water.',
     'Every flood fill you start is one island.'],
    ['Why does marking cells prevent double counting?', 'Why must the fill check bounds before reading grid[r][c]?'], 'shortest-grid-path', ('O(rows · cols)', 'O(rows · cols) for the recursion in the worst case'),
    (DFS, 'From one land cell, mark every connected land cell exactly once.',
     'A depth-first flood fill visits each cell once and marks it, so counting the fills started counts the islands in O(rows · cols).',
     {BFS: ('alternative', 'A breadth-first flood fill with a queue marks the same cells; either traversal works.')},
     [(r'mark|visited|seen|sink|flip|set (it )?to|=\s*[02]', 'marking land cells as visited', 'How do you avoid counting the same island twice?'),
      (r'up|down|left|right|four|neighbo|adjacent|direction', 'spreading to the four neighbours', 'Which cells are connected to a land cell?'),
      (r'bound|edge|outside|in range|<\s*rows|>=\s*0|water', 'stopping at the grid edge and at water', 'Where must the flood fill stop?')]),
    ('Largest island', 'Now return the number of cells in the largest island, or 0 if there is no land.', 'Return an integer area.',
     'Each flood fill already visits one whole island. What could it return?', 'Make the fill return 1 plus the areas returned by its four neighbours, and keep the largest.',
     'A flood fill is a traversal that can measure what it visits: returning a size from each call turns counting islands into comparing them.',
     fn('grid', '''
rows, cols = len(grid), len(grid[0])

def area(r, c):
    if r < 0 or r >= rows or c < 0 or c >= cols or grid[r][c] != 1:
        return 0
    grid[r][c] = 2
    return 1 + area(r + 1, c) + area(r - 1, c) + area(r, c + 1) + area(r, c - 1)

best = 0
for r in range(rows):
    for c in range(cols):
        if grid[r][c] == 1:
            best = max(best, area(r, c))
return best'''),
     [('Example', [[[1, 1, 0, 0], [1, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]], 4), ('All water', [[[0, 0], [0, 0]]], 0), ('Diagonal', [[[1, 0], [0, 1]]], 1),
      ('A ring', [[[1, 1, 1], [1, 0, 1], [1, 1, 1]]], 8)]),
    level='Medium'))

LABS.append(lab(
    'shortest-grid-path', 'Shortest Path in a Grid', 'Grids & matrices', 'grid',
    'grid is a rectangle of 0s (open) and 1s (walls). Moving up, down, left or right through open cells, return the fewest moves from the top-left cell to the bottom-right cell, or -1 if it cannot be reached.',
    'A non-empty rectangle of 0s and 1s, as a list of rows.', 'Find the shortest route through open cells from the top-left corner to the bottom-right corner.', 'Return the number of moves, or -1.',
    ([[[0, 0, 0], [1, 1, 0], [0, 0, 0]]], 4),
    [('Blocked start', [[[1, 0], [0, 0]]], -1), ('Single open cell', [[[0]]], 0), ('Walled off', [[[0, 1], [1, 0]]], -1)],
    [('Open grid', [[[0, 0], [0, 0]]], 2), ('Winding path', [[[0, 1, 0, 0], [0, 1, 0, 1], [0, 0, 0, 0]]], 5)],
    fn('grid', '''
rows, cols = len(grid), len(grid[0])
if grid[0][0] == 1 or grid[rows - 1][cols - 1] == 1:
    return -1
dist = [[-1] * cols for _ in range(rows)]
dist[0][0] = 0
queue = deque([(0, 0)])
while queue:
    r, c = queue.popleft()
    if r == rows - 1 and c == cols - 1:
        return dist[r][c]
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == 0 and dist[nr][nc] == -1:
            dist[nr][nc] = dist[r][c] + 1
            queue.append((nr, nc))
return -1''', 'from collections import deque'),
    fn('grid', '''
rows, cols = len(grid), len(grid[0])
if grid[0][0] == 1:
    return -1
dist = [[-1] * cols for _ in range(rows)]
dist[0][0] = 0
changed = True
while changed:
    changed = False
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == 1 or dist[r][c] == -1:
                continue
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == 0 and (dist[nr][nc] == -1 or dist[r][c] + 1 < dist[nr][nc]):
                    dist[nr][nc] = dist[r][c] + 1
                    changed = True
return dist[rows - 1][cols - 1]'''),
    ['Keep improving every cell\'s distance from its neighbours, pass after pass, until nothing changes.', 'Each pass revisits the whole grid even where no distance can improve.',
     'Exploring in rings of equal distance reaches every cell first by a shortest route.',
     'Breadth-first search with a queue of cells: the first time the corner is reached, its distance is final.'],
    ['A move goes to one of four neighbouring open cells.', 'Which cells are one move from the start? Two moves?', 'Explore every cell at distance d before any cell at distance d + 1.',
     'A queue of (row, column) pairs does that.', 'Record a cell\'s distance when it is first discovered, and skip walls and cells already discovered.',
     'Return the distance when the bottom-right cell leaves the queue, or -1 if the queue empties.'],
    ['Why does breadth-first search find the fewest moves?', 'Why is a cell\'s distance final the first time it is discovered?'], 'count-islands', ('O(rows · cols)', 'O(rows · cols)'),
    (BFS, 'Reach the bottom-right corner exploring cells in order of their distance from the start.',
     'Breadth-first search expands the grid in rings, so the first time the corner is reached is by a shortest route; each cell enters the queue once.', {},
     [(r'queue|deque|fifo|breadth|bfs|\blevel|ring|layer', 'exploring cells in order of distance with a queue', 'In what order must cells be explored so the first arrival is the shortest?'),
      (r'dist|distance|steps|moves|\+\s*1', "recording each cell's distance when first reached", 'What do you record for a cell when you first reach it?'),
      (r'wall|visited|seen|-1|already|bound|edge|outside|in range', 'skipping walls, edges and cells already reached', 'Which neighbouring cells must you skip?')]),
    ('Diagonal moves', 'Now you may also move diagonally, to any of the eight neighbouring cells.', 'Return the number of moves, or -1.',
     'Your search tried four directions. What changes if a move can also go diagonally?', 'Add the four diagonal directions to the neighbours you try; nothing else in the search changes.',
     'Breadth-first search does not care what a move is: changing the neighbour rule changes the graph, and the same search still finds the fewest moves.',
     fn('grid', '''
rows, cols = len(grid), len(grid[0])
if grid[0][0] == 1 or grid[rows - 1][cols - 1] == 1:
    return -1
dist = [[-1] * cols for _ in range(rows)]
dist[0][0] = 0
queue = deque([(0, 0)])
while queue:
    r, c = queue.popleft()
    if r == rows - 1 and c == cols - 1:
        return dist[r][c]
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == 0 and dist[nr][nc] == -1:
                dist[nr][nc] = dist[r][c] + 1
                queue.append((nr, nc))
return -1''', 'from collections import deque'),
     [('Example', [[[0, 0, 0], [1, 1, 0], [0, 0, 0]]], 3), ('Walled off', [[[0, 1], [1, 0]]], 1), ('Open grid', [[[0, 0], [0, 0]]], 1), ('Blocked start', [[[1, 0], [0, 0]]], -1),
      ('Single open cell', [[[0]]], 0)]),
    level='Medium'))

# ----------------------------------------------------------------------------- Dynamic programming
LABS.append(lab(
    'climb-ways', 'Climbing Stairs', 'Dynamic programming', 'n',
    'You climb a staircase of n steps, taking 1 or 2 steps at a time. Return how many distinct ways reach the top. There is one way to climb 0 steps: do nothing.',
    'The number of steps n, from 0 to 40.', 'Count the distinct sequences of 1-step and 2-step moves that add up to n.', 'Return the number of ways.',
    ([5], 8),
    [('One step', [1], 1), ('Two steps', [2], 2), ('No steps', [0], 1)],
    [('Ten steps', [10], 89), ('Three steps', [3], 3)],
    fn('n', '''
ways = [1] * (n + 1)
for i in range(2, n + 1):
    ways[i] = ways[i - 1] + ways[i - 2]
return ways[n]'''),
    fn('n', '''
if n <= 1:
    return 1
return solve(n - 1) + solve(n - 2)'''),
    ['Recurse: the ways to reach n are the ways to reach n − 1 plus the ways to reach n − 2.', 'The plain recursion recomputes the same smaller staircases again and again: about 2ⁿ calls.',
     'Each smaller staircase has one fixed answer, needed many times.', 'Compute the answers from the bottom up in a table: ways[i] = ways[i − 1] + ways[i − 2].'],
    ['The last move onto step n was either 1 step or 2 steps.', 'So ways(n) = ways(n − 1) + ways(n − 2).', 'How many times does the plain recursion compute ways(2) for n = 6?',
     'Each smaller answer never changes: store it once.', 'Fill a list from the bottom: ways[0] = ways[1] = 1.', 'Then ways[i] = ways[i − 1] + ways[i − 2] for i from 2 to n.'],
    ['Why does the plain recursion take exponential time?', 'Which two answers does ways[i] need, and why are they ready in time?'], 'house-robber', ('O(n)', 'O(n), or O(1) keeping two values'),
    (DP, 'Know the number of ways to reach every smaller step without recomputing it.',
     "Each step's count depends only on the two below it; storing them in a table computes every count once, turning an exponential recursion into O(n).",
     {RECURSION: ('partial', 'The recursion states the right relation, ways(n) = ways(n − 1) + ways(n − 2); it becomes efficient only once each answer is stored and reused.')},
     [(r'n\s*-\s*1.{0,60}n\s*-\s*2|last (step|move)|1 or 2|previous two|two (below|before)', 'the relation ways(n) = ways(n − 1) + ways(n − 2)', 'What was the last move onto step n?'),
      (r'store|table|memo|cache|array|list|remember|reuse|bottom.up|tabul', 'storing each answer for reuse', 'How do you avoid recomputing the same smaller staircase?'),
      (r'base|ways\[0\]|ways\[1\]|n\s*==\s*0|n\s*<=\s*1|zero steps|one way', 'the base cases', 'How many ways are there to climb 0 or 1 steps?')]),
    ('Up to three steps', 'Now each move climbs 1, 2 or 3 steps.', 'Return the number of ways.',
     'The last move used to be 1 or 2 steps. What can it be now?', 'Add a third term: ways[i] = ways[i − 1] + ways[i − 2] + ways[i − 3], counting only terms that exist.',
     'A dynamic programme is its recurrence: when the allowed moves change, the relation gains a term and the table fills the same way.',
     fn('n', '''
ways = [0] * (n + 1)
ways[0] = 1
for i in range(1, n + 1):
    for step in (1, 2, 3):
        if i - step >= 0:
            ways[i] += ways[i - step]
return ways[n]'''),
     [('Example', [5], 13), ('One step', [1], 1), ('Three steps', [3], 4), ('No steps', [0], 1), ('Ten steps', [10], 274)])))

LABS.append(lab(
    'house-robber', 'House Robber', 'Dynamic programming', 'nums',
    'Houses stand in a row, and nums[i] is the money in house i. You may not take from two neighbouring houses. Return the most money you can take.',
    'A list of non-negative amounts, one per house.', 'Choose houses, never two side by side, to collect the most money.', 'Return the largest total.',
    ([[2, 7, 9, 3, 1]], 12),
    [('Two houses', [[5, 9]], 9), ('No houses', [[]], 0), ('Skip two in a row', [[2, 1, 1, 2]], 4)],
    [('One house', [[7]], 7), ('All equal', [[4, 4, 4, 4]], 8)],
    fn('nums', '''
if not nums:
    return 0
best = [0] * len(nums)
best[0] = nums[0]
for i in range(1, len(nums)):
    best[i] = max(best[i - 1], (best[i - 2] if i >= 2 else 0) + nums[i])
return best[-1]'''),
    fn('nums', '''
def rob(i):
    if i >= len(nums):
        return 0
    return max(rob(i + 1), nums[i] + rob(i + 2))

return rob(0)'''),
    ['Recurse: at each house, either skip it or take it and skip the next one.', 'The same suffix of houses is solved again and again: about 2ⁿ calls.',
     'The best total for the first i houses depends only on the best totals for the first i − 1 and i − 2 houses.',
     'Fill a table from left to right: best[i] = max(best[i − 1], best[i − 2] + nums[i]).'],
    ['At each house you have two choices.', 'If you take house i, you cannot take house i − 1.', 'What is the best total for the houses up to i if you skip house i? If you take it?',
     'Both answers come from shorter rows of houses that you may already have solved.', 'best[i] = max(best[i − 1], best[i − 2] + nums[i]).',
     'Mind the first two houses: best[0] = nums[0], and before house 0 the total is 0.'],
    ['Why is best[i − 2] the right total to add nums[i] to?', 'Why is greedily taking the largest house wrong?'], 'climb-ways', ('O(n)', 'O(n), or O(1) keeping two values'),
    (DP, 'Know the best total for every prefix of houses without recomputing it.',
     "Each prefix's best total is the better of two choices built from the two previous answers; a table computes each once in O(n).",
     {RECURSION: ('partial', 'The take-or-skip recursion is the right relation; it becomes efficient only once each answer is stored and reused.'),
      RUNNING: ('alternative', 'Carrying only the two previous best totals is the same recurrence with O(1) memory: a running summary of the prefix.')},
     [(r'take|skip|rob|choose|either', 'take this house or skip it', 'What are the two choices at house i?'),
      (r'adjacent|neighbo|i\s*-\s*2|two (back|before)|previous two|side by side', 'taking a house rules out the one before it', 'If you take house i, which earlier total can you add it to?'),
      (r'table|store|memo|best\[|array|list|remember|bottom.up|reuse', 'storing the best total for each prefix', 'How do you reuse answers for shorter rows of houses?')]),
    ('Houses in a circle', 'Now the houses stand in a circle: the first and the last house are neighbours too.', 'Return the largest total.',
     'Your row solution may take both the first and the last house. Which rows of houses never contain both?',
     'Solve the row twice, once without the last house and once without the first, and take the better answer.',
     'A circle breaks into two rows; the same dynamic programme runs on each, and the answer is the better of the two.',
     fn('nums', '''
def line(values):
    take, skip = 0, 0
    for x in values:
        take, skip = skip + x, max(take, skip)
    return max(take, skip)

if len(nums) == 1:
    return nums[0]
return max(line(nums[1:]), line(nums[:-1]))'''),
     [('Example', [[2, 3, 2]], 3), ('The original row', [[2, 7, 9, 3, 1]], 11), ('One house', [[7]], 7), ('No houses', [[]], 0), ('Four houses', [[1, 2, 3, 1]], 4)]),
    level='Medium'))

# ----------------------------------------------------------------------------- Bit manipulation
LABS.append(lab(
    'single-number', 'Single Number', 'Bit manipulation', 'nums',
    'Every value in nums appears exactly twice, except one value that appears once. Return that value.',
    'A list in which one value appears once and every other value appears exactly twice.', 'Find the value without a partner.', 'Return that value (not its position).',
    ([[4, 1, 2, 1, 2]], 4),
    [('One value', [[7]], 7), ('Negative single', [[-3, 5, 5]], -3), ('Zero is single', [[0, 9, 9]], 0)],
    [('Single at the end', [[2, 2, 8]], 8), ('Longer list', [[6, 1, 6, 3, 1]], 3)],
    fn('nums', '''
result = 0
for x in nums:
    result ^= x
return result'''),
    fn('nums', '''
for x in nums:
    if nums.count(x) == 1:
        return x
return None'''),
    ['For each value, count how many times it appears, and return the one that appears once.', 'Counting each value rescans the list: O(n²), or O(n) extra memory with a dictionary.',
     'x ^ x = 0 and x ^ 0 = x, and XOR gives the same result in any order.', 'XOR all the values together: every pair cancels out and only the single value remains.'],
    ['Pairs are the key: something should cancel two equal values.', 'What is x ^ x? What is x ^ 0?', 'Does a ^ b ^ a depend on the order of the operations?',
     'XOR is commutative and associative, so the two copies of a value cancel even when they are far apart.', 'Start with result = 0 and XOR every value into it.', 'What remains is the single value.'],
    ['Why do the two copies cancel even when they are far apart?', 'Why does this need only O(1) extra memory?'], 'count-bits', ('O(n)', 'O(1)'),
    (BITS, 'Cancel every value that appears twice, leaving the single one, without extra memory.',
     'XOR is its own inverse (x ^ x = 0) and does not depend on order, so XOR-ing everything cancels the pairs in one pass with O(1) memory.',
     {HASH: ('alternative', 'Counting with a dictionary, or adding and removing values from a set, finds it in O(n) time but O(n) memory; XOR uses O(1).')},
     [(r'xor|\^', 'combining the values with XOR', 'Which operation makes two equal values cancel?'),
      (r'cancel|pairs?|twice|x\s*\^\s*x|zero|\b0\b', 'pairs cancelling to zero', 'What is x ^ x?'),
      (r'order|commut|any order|associat|far apart', 'the order not mattering', 'Why does it not matter that the two copies are far apart?')]),
    ('Sum of the pairs', 'Now return the sum of the values that appear twice, counting each pair once.', 'Return an integer sum.',
     'XOR found the single value. What does the rest of the list add up to?', 'Every pair contributes twice to sum(nums): remove the single value and halve what is left.',
     'Once XOR isolates the single value, plain arithmetic recovers everything else: (sum(nums) − single) // 2.',
     fn('nums', '''
single = 0
for x in nums:
    single ^= x
return (sum(nums) - single) // 2'''),
     [('Example', [[4, 1, 2, 1, 2]], 3), ('One value', [[7]], 0), ('Negative single', [[-3, 5, 5]], 5), ('Zero is single', [[0, 9, 9]], 9)])))

LABS.append(lab(
    'count-bits', 'Counting Bits', 'Bit manipulation', 'n',
    'Return a list whose entry i is the number of 1 bits in the binary form of i, for every i from 0 to n.',
    'A number n from 0 to 150.', 'Count the 1 bits of every number from 0 to n.', 'Return a list of n + 1 counts.',
    ([5], [0, 1, 1, 2, 1, 2]),
    [('Zero', [0], [0]), ('Up to eight', [8], [0, 1, 1, 2, 1, 2, 2, 3, 1]), ('Two', [2], [0, 1, 1])],
    [('Fifteen', [15], [0, 1, 1, 2, 1, 2, 2, 3, 1, 2, 2, 3, 2, 3, 3, 4]), ('One', [1], [0, 1])],
    fn('n', '''
bits = [0] * (n + 1)
for i in range(1, n + 1):
    bits[i] = bits[i >> 1] + (i & 1)
return bits'''),
    fn('n', '''
bits = []
for i in range(n + 1):
    count = 0
    x = i
    while x:
        count += x & 1
        x >>= 1
    bits.append(count)
return bits'''),
    ['For every i, shift it right bit by bit and count the 1s.', 'Each number is taken apart from scratch, although i >> 1 was counted already: O(n log n).',
     'i has the same bits as i >> 1, plus its lowest bit, i & 1.', 'Fill the list in order: bits[i] = bits[i >> 1] + (i & 1).'],
    ['5 is 101 in binary and 2 is 10. What is 5 >> 1?', 'Shifting right drops exactly the lowest bit.', 'So bits(i) = bits(i >> 1) + (the lowest bit of i).',
     'i & 1 is the lowest bit: 1 for odd i, 0 for even i.', 'i >> 1 is smaller than i, so its count is already in the list.', 'Fill bits[i] = bits[i >> 1] + (i & 1) for i from 1 to n.'],
    ['Why is bits[i >> 1] always ready when you compute bits[i]?', 'What does i & 1 tell you about i?'], 'single-number', ('O(n)', 'O(n) for the output'),
    (BITS, 'Count the 1 bits of i using a count already computed for a smaller number.',
     'Shifting right drops exactly the lowest bit, so bits[i] = bits[i >> 1] + (i & 1) reuses an earlier answer: one O(1) step per number.',
     {DP: ('partial', 'Reusing bits[i >> 1] is dynamic programming; the bit observation is what makes i >> 1 the right smaller problem.')},
     [(r'>>|shift|half|i\s*//\s*2|divide by 2', 'relating i to i >> 1', 'Which smaller number has almost the same bits as i?'),
      (r'&\s*1|lowest bit|last bit|odd|even|%\s*2', 'adding the lowest bit', 'Which bit is lost when you shift right?'),
      (r'reuse|earlier|already|table|bits\[|previous|stored', 'reusing earlier counts', 'Which earlier answer can you build on?')]),
    ('Odd or even ones', 'Now return, for each i from 0 to n, True if i has an odd number of 1 bits and False otherwise.', 'Return a list of n + 1 booleans.',
     'You counted the 1 bits. What decides whether a count is odd?', 'Reuse the same relation with XOR: odd[i] = odd[i >> 1] ^ (i & 1), stored as booleans.',
     'Parity follows the same recurrence as the count; only the combining step changes, from + to ^.',
     fn('n', '''
odd = [False] * (n + 1)
for i in range(1, n + 1):
    odd[i] = odd[i >> 1] ^ bool(i & 1)
return odd'''),
     [('Example', [5], [False, True, True, False, True, False]), ('Zero', [0], [False]), ('Two', [2], [False, True, True]),
      ('Up to eight', [8], [False, True, True, False, True, False, False, True, True])])))
