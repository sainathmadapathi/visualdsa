"""Every data structure of a DSA sheet runs as written and is recorded for the visual stage:
linked lists, trees, tries, graphs, grids and DP tables, stacks, queues, heaps, recursion, bits,
and design problems (classes driven by a list of operations)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DSA_DATABASE"] = str(Path(tempfile.mkdtemp()) / "structures-test.sqlite3")  # Never the real database.
import app  # noqa: E402
import sheets  # noqa: E402


def run(code, args, kinds=None, entry="solve"):
    return app.run_cases(code, [args], kinds, entry)[0]


def structures(out, kind):
    return [s for e in out["events"] for s in e["state"]["structures"] if s["type"] == kind]


class LinkedListsAndTrees(unittest.TestCase):
    REVERSE = ("def solve(head):\n    prev = None\n    curr = head\n    while curr:\n        nxt = curr.next\n        curr.next = prev\n"
               "        prev = curr\n        curr = nxt\n    return prev\n")

    def test_a_list_input_arrives_as_nodes_and_a_returned_head_is_compared_as_values(self):
        out = run(self.REVERSE, [[1, 2, 3, 4]], ["linkedlist"])
        self.assertIsNone(out["error"])
        self.assertEqual(out["result"], [4, 3, 2, 1])
        relinks = [e for e in out["events"] if e["type"] == "LINK_WRITE"]
        self.assertEqual(len(relinks), 4)
        nodes = next(s for s in relinks[1]["state"]["structures"] if s["type"] == "nodes")
        links = {n["id"]: n["links"]["next"] for n in nodes["nodes"]}
        self.assertEqual(links[1], None)  # The first node now ends the reversed part...
        self.assertEqual(links[2], 1)     # ...and the second points back at it.
        self.assertEqual(nodes["refs"]["curr"], 2)
        self.assertEqual(nodes["refs"]["prev"], 1)
        last = next(s for s in out["events"][-1]["state"]["structures"] if s["type"] == "nodes")
        self.assertIsNone(last["refs"]["curr"])  # A pointer that ran off the end is shown as None.

    def test_doubly_linked_lists_and_lists_of_lists(self):
        out = run("def solve(head):\n    return head.next.prev.val\n", [[5, 6]], ["dll"])
        self.assertEqual(out["result"], 5)
        merge = ("import heapq\ndef solve(heads):\n    heap = []\n    for i, node in enumerate(heads):\n        if node:\n            heapq.heappush(heap, (node.val, i, node))\n"
                 "    dummy = tail = ListNode(0)\n    while heap:\n        val, i, node = heapq.heappop(heap)\n        tail.next = node\n        tail = node\n        if node.next:\n"
                 "            heapq.heappush(heap, (node.next.val, i, node.next))\n    return dummy.next\n")
        out = run(merge, [[[1, 4], [2, 3], []]], ["linkedlists"])
        self.assertIsNone(out["error"], out["error"])
        self.assertEqual(out["result"], [1, 2, 3, 4])
        self.assertTrue(any(s.get("kind") == "heap" for s in structures(out, "array")))
        self.assertIn("HEAP_POP", {e["type"] for e in out["events"]})

    def test_trees_recursion_and_the_calls_made(self):
        code = "from typing import Optional\ndef solve(root: Optional[TreeNode]) -> int:\n    if not root:\n        return 0\n    return 1 + max(solve(root.left), solve(root.right))\n"
        out = run(code, [[3, 9, 20, None, None, 15, 7]], ["tree"])
        self.assertEqual(out["result"], 3)
        calls = [e["meta"]["call"] for e in out["events"] if e["type"] == "RECURSION_CALL"]
        self.assertEqual(calls[0]["args"], {"root": "TreeNode(3)"})
        self.assertEqual(calls[1]["depth"], 2)
        returns = [e["meta"]["ret"] for e in out["events"] if e["type"] == "RECURSION_RETURN"]
        self.assertEqual(returns[-1]["value"], 3)
        tree = next(s for s in out["events"][0]["state"]["structures"] if s["type"] == "nodes")
        root = next(n for n in tree["nodes"] if n["label"] == 3)
        self.assertEqual({"left", "right"} <= set(root["links"]), True)
        invert = ("def solve(root):\n    if root:\n        root.left, root.right = solve(root.right), solve(root.left)\n    return root\n")
        self.assertEqual(run(invert, [[4, 2, 7, 1, 3]], ["tree"])["result"], [4, 7, 2, None, None, 3, 1])

    def test_a_loop_that_never_advances_on_a_list_is_proven_infinite(self):
        out = run("def solve(head):\n    curr = head\n    while curr:\n        total = curr.val\n    return head\n", [[1, 2]], ["linkedlist"])
        self.assertIn("Infinite loop", out["error"]["message"])
        self.assertTrue(out["events"][-1]["meta"].get("cycle"))

    def test_a_returned_cycle_is_reported(self):
        out = run("def solve(head):\n    head.next.next = head\n    return head\n", [[1, 2]], ["linkedlist"])
        self.assertIn("cycle", out["error"]["message"])


class GridsGraphsAndQueues(unittest.TestCase):
    def test_grid_bfs_records_the_cell_read_the_queue_and_visited(self):
        code = ("from collections import deque\ndef solve(grid):\n    seen = set()\n    q = deque([(0, 0)])\n    seen.add((0, 0))\n    while q:\n        r, c = q.popleft()\n"
                "        for dr, dc in ((1, 0), (0, 1)):\n            nr, nc = r + dr, c + dc\n            if nr < len(grid) and nc < len(grid[0]) and grid[nr][nc] == 1 and (nr, nc) not in seen:\n"
                "                seen.add((nr, nc))\n                q.append((nr, nc))\n    return len(seen)\n")
        out = run(code, [[[1, 1], [0, 1]]])
        self.assertEqual(out["result"], 3)
        grids = structures(out, "matrix")
        self.assertEqual(grids[0]["shape"], [2, 2])
        self.assertIn([0, 1], [cell for g in grids for cell in g["hot"]])
        self.assertTrue(any(s.get("kind") == "queue" for s in structures(out, "array")))
        self.assertIn("QUEUE_POP", {e["type"] for e in out["events"]})

    def test_dp_tables_are_grids(self):
        code = "def solve(m, n):\n    dp = [[1] * n for _ in range(m)]\n    for i in range(1, m):\n        for j in range(1, n):\n            dp[i][j] = dp[i - 1][j] + dp[i][j - 1]\n    return dp[m - 1][n - 1]\n"
        out = run(code, [3, 3])
        self.assertEqual(out["result"], 6)
        self.assertEqual(structures(out, "matrix")[-1]["rows"], [[1, 1, 1], [1, 2, 3], [1, 3, 6]])

    def test_a_structure_is_a_graph_when_the_code_walks_it_whatever_its_name(self):
        # Walking: read a node's row, then the row of a neighbour it held, looping over rows.
        dfs = "def solve(V, links):\n    seen = {0}\n    stack = [0]\n    while stack:\n        u = stack.pop()\n        for v in links[u]:\n            if v not in seen:\n                seen.add(v)\n                stack.append(v)\n    return len(seen)\n"
        graph = structures(run(dfs, [3, [[1, 2], [0], [0]]]), "graph")[0]
        self.assertEqual((graph["id"], graph["labels"], graph["directed"], sorted(map(tuple, graph["edges"]))), ("links", [0, 1, 2], False, [(0, 1, None), (0, 2, None)]))
        # A dict of neighbours, and (neighbour, weight) pairs, oriented by how the walk used them.
        dijkstra = "def solve(g):\n    out = []\n    todo = ['a']\n    while todo:\n        u = todo.pop()\n        out.append(u)\n        for v, w in g[u]:\n            todo.append(v)\n    return out\n"
        graph = structures(run(dijkstra, [{"a": [["b", 5]], "b": []}]), "graph")[0]
        self.assertEqual((graph["labels"], graph["edges"]), (["a", "b"], [[0, 1, 5]]))
        weight_first = "def solve(adj):\n    out = []\n    todo = [0]\n    while todo:\n        u = todo.pop()\n        out.append(u)\n        for w, v in adj[u]:\n            todo.append(v)\n    return out\n"
        graph = structures(run(weight_first, [[[[5, 1]], []]]), "graph")[0]
        self.assertEqual(graph["edges"], [[0, 1, 5]])
        # Adjacency-shaped data the code never walks is drawn as what it is, never called a graph by its name.
        for code, args in [("def solve(V, adj):\n    return sum(1 for x in adj[0])\n", [3, [[1, 2], [0], [0]]]),
                           ("def solve(isConnected):\n    return len(isConnected)\n", [[[1, 0, 1], [0, 1, 0], [1, 0, 1]]]),
                           ("def solve(V, edges):\n    return V\n", [4, [[0, 1], [1, 2], [2, 3]]])]:
            self.assertEqual(structures(run(code, args), "graph"), [], code)

    def test_stacks_and_heaps_are_named_by_how_the_code_uses_them(self):
        code = "def solve(s):\n    stack = []\n    for ch in s:\n        if ch == '(':\n            stack.append(ch)\n        elif stack:\n            stack.pop()\n        else:\n            return False\n    return not stack\n"
        out = run(code, ["(())"])
        self.assertEqual(out["result"], True)
        self.assertTrue(any(s.get("kind") == "stack" for s in structures(out, "array")))
        heap = "from heapq import heappush, heappop\ndef solve(nums, k):\n    h = []\n    for x in nums:\n        heappush(h, x)\n        if len(h) > k:\n            heappop(h)\n    return h[0]\n"
        out = run(heap, [[3, 1, 5, 4], 2])
        self.assertEqual(out["result"], 4)
        self.assertTrue(any(s.get("kind") == "heap" for s in structures(out, "array")))


class DesignBitsAndSafety(unittest.TestCase):
    def test_design_problems_run_their_operations_in_order(self):
        stack = ("class MinStack:\n    def __init__(self):\n        self.stack = []\n    def push(self, x: int) -> None:\n        low = min(x, self.stack[-1][1]) if self.stack else x\n"
                 "        self.stack.append((x, low))\n    def pop(self) -> None:\n        self.stack.pop()\n    def getMin(self) -> int:\n        return self.stack[-1][1]\n")
        out = run(stack, [["MinStack", "push", "push", "getMin", "pop", "getMin"], [[], [5], [2], [], [], []]], entry="MinStack")
        self.assertIsNone(out["error"], out["error"])
        self.assertEqual(out["result"], [None, None, None, 2, None, 5])
        self.assertTrue(any(s["id"] == "self.stack" and s.get("kind") == "stack" for s in structures(out, "array")))
        calls = [e["meta"]["call"]["fn"] for e in out["events"] if e["type"] == "RECURSION_CALL"]
        self.assertEqual(calls[:2], ["MinStack.__init__", "MinStack.push"])
        with self.assertRaisesRegex(ValueError, "define class MinStack"):
            app.validate_source("def solve(x):\n    return x\n", "MinStack")

    def test_tries_are_drawn_from_their_children(self):
        trie = ("class TrieNode:\n    def __init__(self):\n        self.children = {}\n        self.end = False\nclass Trie:\n    def __init__(self):\n        self.root = TrieNode()\n"
                "    def insert(self, word):\n        node = self.root\n        for ch in word:\n            node = node.children.setdefault(ch, TrieNode())\n        node.end = True\n"
                "    def search(self, word):\n        node = self.root\n        for ch in word:\n            if ch not in node.children:\n                return False\n            node = node.children[ch]\n        return node.end\n")
        out = run(trie, [["Trie", "insert", "search", "search"], [[], "ab", "ab", "a"]], entry="Trie")
        self.assertEqual(out["result"], [None, None, True, False])
        nodes = structures(out, "nodes")[-1]["nodes"]
        root = next(n for n in nodes if any(k[0] == "a" for k in n["kids"]))
        self.assertEqual(sorted(k[0] for k in root["kids"]), ["a"])  # "ab": the root's only child is a.
        self.assertEqual(next(n for n in nodes if n["kids"] == [] and n["attrs"].get("end") is True)["cls"], "TrieNode")

    def test_bit_operations_are_recorded_with_their_operands(self):
        out = run("def solve(nums):\n    x = 0\n    for n in nums:\n        x = x ^ n\n    return x\n", [[4, 1, 4]])
        bits = [e["meta"] for e in out["events"] if e["type"] == "BIT_OP"]
        self.assertEqual(bits[-1], {"op": "^", "left": 5, "right": 4, "result": 1})

    def test_memoised_recursion_with_lru_cache(self):
        code = "from functools import lru_cache\n@lru_cache(None)\ndef ways(n):\n    if n <= 1:\n        return 1\n    return ways(n - 1) + ways(n - 2)\ndef solve(n):\n    return ways(n)\n"
        out = run(code, [10])
        self.assertEqual(out["result"], 89)
        self.assertEqual(sum(1 for e in out["events"] if e["type"] == "RECURSION_CALL" and e["meta"]["call"]["fn"] == "ways"), 11)  # Each n once.

    def test_the_runner_stays_closed(self):
        for code in ["import os\ndef solve(x):\n    return x", "from collections import abc\ndef solve(x):\n    return x",
                     "def solve(x):\n    return x.__class__", "def solve(x):\n    return '{0.__class__}'.format(x)",
                     "def solve(x):\n    g = (i for i in x)\n    return g.gi_frame", "class A:\n    def __getattr__(self, n):\n        pass\ndef solve(x):\n    return x",
                     "class A:\n    def f(self):\n        return super().__class__\ndef solve(x):\n    return x",
                     "def solve(x):\n    return eval('1')", "def solve(x):\n    return open('f')"]:
            with self.assertRaises(ValueError, msg=code):
                app.validate_source(code)
        out = run("def solve(x):\n    return 'a'.encode()\n", [[1]])
        self.assertIn("not available", out["error"]["message"])  # Built-in values expose only their safe methods.
        # The built-ins that reach into objects stay on the program's own, plain fields.
        self.assertIn("can't read", run("def solve(x):\n    return getattr(x, '__class__')\n", [[1]])["error"]["message"])
        self.assertIn("can only set", run("def solve(x):\n    setattr(x, 'y', 1)\n    return x\n", [[1]])["error"]["message"])
        self.assertIn("three arguments", run("def solve(x):\n    return type('X', (), {})\n", [[1]])["error"]["message"])
        self.assertIn("limit", run("def solve(x):\n    return pow(2, 100000)\n", [1])["error"]["message"])


class SheetLabsWithStructures(unittest.TestCase):
    def test_a_sheet_lab_of_linked_lists_runs_on_nodes(self):
        client = app.app.test_client()
        sheet_id = client.post("/api/sheets", json={"name": "LL", "rows": [{"title": "Reverse a LL", "url": "", "difficulty": "", "topic": "", "match": None}]}).get_json()["id"]
        built = client.post("/api/labs", json={"sheetId": sheet_id, "row": 0, "title": "Reverse a LL", "statement": "Reverse the given singly linked list.", "params": "head",
                                               "kinds": {"head": "linkedlist"}, "cases": [{"args": ["[1, 2, 3]"], "expected": "[3, 2, 1]"}, {"name": "Empty", "args": ["[]"], "expected": "[]"}]}).get_json()
        lab = built["lab"]
        self.assertEqual(lab["kinds"], {"head": "linkedlist"})
        self.assertIn("head is a linked list", lab["starter"])
        preview = client.post("/api/preview", json={"problemId": lab["id"], "code": LinkedListsAndTrees.REVERSE, "args": [[1, 2, 3]]}).get_json()
        self.assertEqual([(c["name"], c["goal"]["matches"]) for c in preview["cases"]], [("Case 1", True), ("Empty", True)])
        design = client.post("/api/labs", json={"sheetId": sheet_id, "row": 0, "title": "Stack", "statement": "Implement push(int x) and top().", "params": "operations, nums",
                                                "entry": "ArrayStack", "methods": {"push": ["x"], "top": []}, "cases": [{"args": ['["ArrayStack", "push", "top"]', "[[], [4], []]"], "expected": "[null, null, 4]"}]}).get_json()["lab"]
        self.assertTrue(design["starter"].startswith("class ArrayStack:"))
        self.assertIn("def push(self, x):", design["starter"])
        code = "class ArrayStack:\n    def __init__(self):\n        self.items = []\n    def push(self, x):\n        self.items.append(x)\n    def top(self):\n        return self.items[-1]\n"
        run_ = client.post("/api/execute", json={"problemId": design["id"], "code": code, "args": [["ArrayStack", "push", "top"], [[], [4], []]]}).get_json()
        self.assertTrue(run_["passed"], run_)

    def test_kinds_are_guessed_from_names_arrows_and_the_statement(self):
        self.assertEqual(sheets.guess_kinds(["linkedList", "X"], "Insert at the head of a linked list.", [[1, 2], 7]), {"linkedList": "linkedlist"})
        self.assertEqual(sheets.guess_kinds(["root"], "Find the maximum depth of a binary tree.", [[3, 9]]), {"root": "tree"})
        self.assertEqual(sheets.guess_kinds(["head"], "Delete a node of a doubly linked list.", [[1]]), {"head": "dll"})
        self.assertEqual(sheets.guess_kinds(["nums"], "An array.", [[1]]), {})


if __name__ == "__main__":
    unittest.main()


class MeaningFromBehaviour(unittest.TestCase):
    """What a structure is comes from what the code does with it, decided over the whole run, never from its name."""

    def kinds(self, code, args):
        out = run(code, args)
        self.assertIsNone(out["error"], out["error"])
        found = {}
        for e in out["events"]:
            for s in e["state"]["structures"]:
                found.setdefault(s["id"], s.get("kind"))
        return found

    def test_the_end_items_leave_from_decides_stack_or_queue(self):
        code = ("from collections import deque\ndef solve(nums):\n    a = deque(nums)\n    a.append(9)\n    a.pop()\n"
                "    b = list(nums)\n    b.pop(0)\n    stack = []\n    stack.append(1)\n    q = deque([1, 2])\n    q.popleft()\n    return 0\n")
        kinds = self.kinds(code, [[1, 2, 3]])
        self.assertEqual(kinds["a"], "stack", "a deque used from one end is a stack")
        self.assertEqual(kinds["b"], "queue", "a list served from its front is a queue")
        self.assertIsNone(kinds["stack"], "a list only pushed to is a list, whatever it is called")
        self.assertEqual(kinds["q"], "queue")

    def test_heapq_makes_a_heap_and_a_sorted_insert_does_not(self):
        code = "import heapq, bisect\ndef solve(nums):\n    pq = []\n    for x in nums:\n        heapq.heappush(pq, x)\n    srt = []\n    for x in nums:\n        bisect.insort(srt, x)\n    return [pq[0], srt[0]]\n"
        kinds = self.kinds(code, [[3, 1, 2]])
        self.assertEqual((kinds["pq"], kinds["srt"]), ("heap", None))

    def test_a_kind_holds_from_the_first_step(self):
        # The queue is a queue in every snapshot, including those before its first pop.
        out = run("def solve(nums):\n    todo = [1, 2]\n    todo.append(3)\n    todo.pop(0)\n    return todo\n", [[1]])
        self.assertEqual({s.get("kind") for e in out["events"] for s in e["state"]["structures"] if s["id"] == "todo"}, {"queue"})

    def test_a_design_object_shows_its_own_fields_whatever_they_are_called(self):
        code = "class MyQueue:\n    def __init__(self):\n        self.left = []\n        self.parent = [0, 1]\n    def push(self, x):\n        self.left.append(x)\n        return None\n"
        out = run(code, [["MyQueue", "push"], [[], [5]]], entry="MyQueue")
        ids = {s["id"] for e in out["events"] for s in e["state"]["structures"]}
        self.assertTrue({"self.left", "self.parent"} <= ids, ids)
        # self.parent = [...] is a field set to a list, not a re-link of a linked structure.
        self.assertFalse(any(e["type"] == "LINK_WRITE" for e in out["events"]))

    def test_a_link_write_puts_a_node_in_a_field(self):
        code = "class N:\n    def __init__(self, v):\n        self.v = v\n        self.after = None\n\ndef solve(nums):\n    a, b = N(1), N(2)\n    a.after = b\n    a.after = None\n    a.v = 5\n    return 0\n"
        types = [(e["type"], e["detail"]) for e in run(code, [[1]])["events"] if "updated" in e["detail"] and e["detail"].startswith("a.")]
        self.assertEqual(types, [("LINK_WRITE", "a.after updated."), ("LINK_WRITE", "a.after updated."), ("STATE_CHANGE", "a.v updated.")])
