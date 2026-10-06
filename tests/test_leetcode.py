"""LeetCode's version of a problem, read from its open mirror: it completes only what the problem's own page leaves
out, only when the two provably describe the same problem, and every value says where it came from."""
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

# Importing app initializes its database: isolate it before the import, never touch learning.sqlite3.
os.environ['DSA_DATABASE'] = os.path.join(tempfile.mkdtemp(), 'import.sqlite3')  # Never the real database.
import app  # noqa: E402
import leetcode  # noqa: E402
import sheets  # noqa: E402

INDEX = """| # | Solution | Tags | Difficulty | Remark |
|  0001  |  [Two Sum](/solution/0000-0099/0001.Two%20Sum/README_EN.md)  |  `Array`  |  Easy  |    |
|  0189  |  [Rotate Array](/solution/0100-0199/0189.Rotate%20Array/README_EN.md)  |  `Array`  |  Medium  |    |
|  0170  |  [Two Sum III - Data structure design](/solution/0100-0199/0170.Two%20Sum%20III/README_EN.md)  |  `Design`  |  Easy  |  🔒  |
"""
TWO_SUM = """# [1. Two Sum](https://leetcode.com/problems/two-sum)

<!-- description:start -->
<p>Given an array of integers <code>nums</code> and an integer <code>target</code>, return indices of the two numbers such that they add up to <code>target</code>.</p>
<p><strong class="example">Example 1:</strong></p>
<pre><strong>Input:</strong> nums = [2,7,11,15], target = 9
<strong>Output:</strong> [0,1]</pre>
<p><strong class="example">Example 2:</strong></p>
<pre><strong>Input:</strong> nums = [3,2,4], target = 6
<strong>Output:</strong> [1,2]</pre>
<!-- description:end -->

## Solutions

#### Python3

```python
class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:
        d = {}
        for i, x in enumerate(nums):
            if (y := target - x) in d:
                return [d[y], i]
            d[x] = i
```
"""
ROTATE = """# [189. Rotate Array](https://leetcode.com/problems/rotate-array)

<!-- description:start -->
<p>Given an integer array <code>nums</code>, rotate the array to the right by <code>k</code> steps.</p>
<p><strong class="example">Example 1:</strong></p>
<pre><strong>Input:</strong> nums = [1,2,3,4,5,6,7], k = 3
<strong>Output:</strong> [5,6,7,1,2,3,4]</pre>
<!-- description:end -->

#### Python3

```python
class Solution:
    def rotate(self, nums: List[int], k: int) -> None:
        k %= len(nums)
        nums[:] = nums[-k:] + nums[:-k]
```
"""
PAGES = {leetcode.INDEX: INDEX, leetcode.ORIGIN + "/solution/0000-0099/0001.Two%20Sum/README_EN.md": TWO_SUM,
         leetcode.ORIGIN + "/solution/0100-0199/0189.Rotate%20Array/README_EN.md": ROTATE}


def fetcher(pages):
    def fetch(url):
        if url.endswith("/robots.txt"):
            raise sheets.FetchError("no robots.txt", 404)
        if url not in pages:
            raise sheets.FetchError("not found", 404)
        return pages[url].encode(), url, "text/markdown" if url.endswith(".md") else "text/html", "utf-8"
    return fetch


class MirrorTests(unittest.TestCase):
    def setUp(self):
        leetcode._pages.clear()
        leetcode._index.update(at=0.0, paths={}, locked=set())

    def test_slugs_are_exact(self):
        self.assertEqual(leetcode.slug_of("https://leetcode.com/problems/two-sum/description/"), "two-sum")
        self.assertIsNone(leetcode.slug_of("https://example.org/problems/two-sum"))
        self.assertEqual(leetcode.slug_for("Two Sum II - Input Array Is Sorted"), "two-sum-ii-input-array-is-sorted")
        self.assertEqual(leetcode.slug_for("Pow(x, n)"), "powx-n")

    def test_a_problem_is_used_only_if_the_mirror_page_is_that_exact_problem(self):
        pages = dict(PAGES)
        pages[leetcode.ORIGIN + "/solution/0000-0099/0001.Two%20Sum/README_EN.md"] = TWO_SUM.replace("problems/two-sum", "problems/two-sum-ii")
        self.assertIsNone(leetcode.page("two-sum", fetcher(pages), sheets.decode))
        self.assertIsNone(leetcode.page("two-sum-iii-data-structure-design", fetcher(PAGES), sheets.decode), "premium problems have no statement")
        self.assertIsNone(leetcode.page("no-such-problem", fetcher(PAGES), sheets.decode))

    def test_the_signature_gives_names_kinds_and_in_place_answers(self):
        found = leetcode.page("rotate-array", fetcher(PAGES), sheets.decode)
        self.assertEqual(found["signature"], {"method": "rotate", "params": [("nums", "List[int]"), ("k", "int")], "returns": "None"})
        read = leetcode.problem(found, sheets.problem_from_page)
        self.assertEqual((read["params"], read["answer"], read["leetcode"]), (["nums", "k"], "in-place", "rotate-array"))
        self.assertEqual([(c["args"], c["expected"], c["source"]) for c in read["cases"]], [([[1, 2, 3, 4, 5, 6, 7], 3], [5, 6, 7, 1, 2, 3, 4], "leetcode")])
        self.assertIn("CC BY-SA 4.0", read["notes"][0])
        self.assertEqual(leetcode.kind_of("Optional[ListNode]"), "linkedlist")
        self.assertEqual(leetcode.kind_of("List[Optional[ListNode]]"), "linkedlists")
        self.assertEqual(leetcode.kind_of("Optional[TreeNode]"), "tree")


class CompletingAPage(unittest.TestCase):
    """The row's own page first; LeetCode only where the page leaves something out."""

    def setUp(self):
        leetcode._pages.clear()
        leetcode._index.update(at=0.0, paths={}, locked=set())

    def read(self, page, links=("https://leetcode.com/problems/two-sum/",)):
        pages = {**PAGES, "https://example.org/two-sum": page}
        return sheets.read_problem({"url": "https://example.org/two-sum", "links": list(links)}, fetcher(pages))

    def test_an_output_the_page_shows_as_an_image_is_filled_from_the_same_input_on_leetcode(self):
        page = """<h1>Two Sum</h1><p>Return the indices of the two numbers that add up to target.</p>
          <h3>Example 1:</h3><p>Input: nums = [2,7,11,15], target = 9</p><p>Output: <img src="out.png"></p>
          <h3>Example 2:</h3><p>Input: nums = [3,2,4], target = 6</p><p>Output: [1,2]</p>
          <h3>Example 3:</h3><p>Input: nums = [1,5], target = 6</p><p>Output: <img src="out3.png"></p>"""
        read = self.read(page)
        self.assertEqual([(c["name"], c["expected"], c["source"]) for c in read["cases"]], [("Example 2", [1, 2], "page"), ("Example 1", [0, 1], "leetcode")])
        self.assertTrue(any("Example 1 is LeetCode's" in n for n in read["notes"]))
        # Example 3's input isn't one LeetCode states: it stays without an output, never guessed.
        self.assertNotIn("Example 3", [c["name"] for c in read["cases"]])
        self.assertEqual(read["leetcode"], "two-sum")

    def test_a_page_that_disagrees_with_leetcode_is_a_different_contract(self):
        page = """<h1>Two Sum (1-indexed)</h1><p>Return the 1-based positions of the two numbers.</p>
          <h3>Example 1:</h3><p>Input: nums = [2,7,11,15], target = 9</p><p>Output: [1,2]</p>
          <h3>Example 2:</h3><p>Input: nums = [3,2,4], target = 6</p><p>Output: <img src="x.png"></p>"""
        read = self.read(page)
        self.assertEqual([(c["name"], c["source"]) for c in read["cases"]], [("Example 1", "page")])
        self.assertNotIn("leetcode", read)
        self.assertTrue(any("different output" in n for n in read["notes"]))

    def test_a_page_without_examples_gets_leetcodes_marked_as_such(self):
        read = self.read("<h1>Two Sum</h1><p>Return the indices of the two numbers in nums that add up to target. Each input has exactly one solution.</p>")
        self.assertEqual([(c["name"], c["source"]) for c in read["cases"]], [("Example 1", "leetcode"), ("Example 2", "leetcode")])
        self.assertTrue(any("LeetCode's examples of the same problem" in n for n in read["notes"]))

    def test_a_row_that_only_links_leetcode_is_read_from_its_mirror(self):
        read = sheets.read_problem({"url": "https://leetcode.com/problems/rotate-array/", "links": []}, fetcher(PAGES))
        self.assertEqual((read["title"], read["answer"], read["source"]), ("Rotate Array", "in-place", "https://leetcode.com/problems/rotate-array/"))

    def test_without_a_leetcode_link_nothing_is_added(self):
        page = "<h1>Two Sum</h1><p>Return the indices.</p><h3>Example 1:</h3><p>Input: nums = [2,7,11,15], target = 9</p><p>Output: <img src='o.png'></p>"
        read = self.read(page, links=())
        self.assertEqual([(c["missing"], c.get("source")) for c in read["cases"]], [(True, "page")])
        self.assertNotIn("leetcode", read)


class VerifiedReference(unittest.TestCase):
    """LeetCode's accepted solution answers the learner's own inputs only if it reproduces every case of the lab."""

    def setUp(self):
        leetcode._pages.clear()
        leetcode._index.update(at=0.0, paths={}, locked=set())
        for slug in ("two-sum", "rotate-array"):
            leetcode.page(slug, fetcher(PAGES), sheets.decode)  # As if read in the background earlier.

    def lab(self, slug, params, tests, answer=None):
        return {"id": f"lab-{slug}-{time.time_ns()}", "custom": True, "params": params, "tests": tests, "kinds": {}, "entry": "solve", "answer": answer, "leetcode": slug, "order": "exact"}

    def test_a_reference_that_reproduces_the_lab_answers_the_learners_own_input(self):
        p = app.attach_reference(self.lab("two-sum", ["nums", "target"], [{"name": "Example 1", "args": [[2, 7, 11, 15], 9], "expected": [0, 1]}]))
        self.assertTrue(p.get("reference") and p.get("sandboxed"))
        self.assertEqual(app.reference_result(p, [[1, 5, 9, 4], 13]), (True, [2, 3]))
        rotate = app.attach_reference(self.lab("rotate-array", ["nums", "k"], [{"name": "Example 1", "args": [[1, 2, 3, 4, 5, 6, 7], 3], "expected": [5, 6, 7, 1, 2, 3, 4]}], "in-place"))
        self.assertEqual(app.reference_result(rotate, [[1, 2, 3], 1]), (True, [3, 1, 2]))

    def test_a_lab_whose_cases_leetcode_does_not_reproduce_gets_none(self):
        p = app.attach_reference(self.lab("two-sum", ["nums", "target"], [{"name": "Mine", "args": [[2, 7, 11, 15], 9], "expected": [1, 2]}]))
        self.assertIsNone(p.get("reference"))

    def test_an_unread_mirror_never_holds_up_a_request(self):
        leetcode._pages.clear()
        with patch.object(leetcode, "page", side_effect=lambda *a: time.sleep(0.5)):
            started = time.time()
            p = app.attach_reference(self.lab("two-sum", ["nums", "target"], [{"name": "Example 1", "args": [[2, 7, 11, 15], 9], "expected": [0, 1]}]))
            self.assertLess(time.time() - started, 0.3)
        self.assertIsNone(p.get("reference"))


class LabsKeepTheirSources(unittest.TestCase):
    def test_each_case_keeps_where_its_output_came_from(self):
        lab = sheets.build_lab({"title": "Rotate Array", "statement": "Rotate the array to the right by k steps.", "params": "nums, k", "answer": "in-place", "leetcode": "rotate-array",
                                "cases": [{"args": ["[1, 2, 3]", "1"], "expected": "[3, 1, 2]", "source": "leetcode"}, {"args": ["[1, 2]", "1"], "expected": "[2, 1]", "source": "made-up"}, {"args": ["[1]", "0"], "expected": "[1]"}]})
        self.assertEqual([c.get("source") for c in lab["cases"]], ["leetcode", None, None])
        self.assertEqual((lab["answer"], lab["leetcode"]), ("in-place", "rotate-array"))
        problem = sheets.as_problem("lab-1", lab, "sheet", "Sheet", 1)
        self.assertEqual(problem["leetcode"], "rotate-array")
        self.assertEqual(problem["tests"][0]["source"], "leetcode")


if __name__ == "__main__":
    unittest.main()
