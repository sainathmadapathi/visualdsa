"""Problem pages are read faithfully: everything the page says about the problem, structured as the page
structures it, and nothing it doesn't say. The API answers in JSON even when it fails."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DSA_DATABASE"] = str(Path(tempfile.mkdtemp()) / "extraction-test.sqlite3")  # Never the real database.
import app  # noqa: E402
import sheets  # noqa: E402

PAGE = """<html><head><title>Rotate | Site</title></head><body><nav><a href="/">Home</a> Login</nav><header><h1>12. Rotate Array</h1><button>Companies</button></header>
<div><p>Given an array <code>nums</code>, rotate it to the right by <strong>k</strong> steps.</p><p>Do it in place.</p><img src="d.png" alt="diagram"/>
<pre>def rotate(nums, k):
    # nums is changed in place
    pass</pre></div>
<p><strong>Input Format:</strong> The first argument is the array, the second is k.</p>
<p><strong>Output Format:</strong> Return the rotated array.</p>
<section><h3>Example 1:</h3><p><strong>Input</strong>: nums = [1, 2, 3, 4], k = 1</p><p><strong>Output</strong>: [4, 1, 2, 3]</p><p><strong>Explanation</strong>: </p><p>Every value moves one step right; 4 wraps to the front.</p></section>
<section><h3>Example 2:</h3><p><strong>Input</strong>: nums = [7], k = 3</p><p><strong>Output</strong>: [7]</p></section>
<section><h3>Example 3:</h3><p><strong>Input</strong>: nums = [1, 2, 3, 4], k = 1</p><p><strong>Output</strong>: [4, 1, 2, 3]</p></section>
<p><strong>Note:</strong> k can be larger than the length of the array.</p>
<p><strong>Expected Time Complexity:</strong> O(n)</p>
<section><h3>Now Your Turn!</h3><p><strong>Input</strong>: nums = [5, 6], k = 1</p><label>[6, 5]</label></section>
<p>Still unsure what the problem is asking ?</p><p>Let’s go through a few more examples.</p><p><strong>Note:</strong> a walkthrough note, not part of the problem.</p>
<section><h3>Constraints:</h3><li>1 &lt;= nums.length &lt;= 10<sup>5</sup></li><li>arr<sub>i</sub> fits in 32 bits</li></section>
<section><h3>Editorial</h3><p>Reverse the whole array, then reverse each part.</p><p><strong>Note:</strong> this is the trick.</p></section>
<footer>© Site 2026 · Sign up</footer></body></html>"""


class FaithfulExtraction(unittest.TestCase):
    def setUp(self):
        self.problem = sheets.problem_from_page(PAGE, "https://example.org/problems/rotate-array")

    def test_title_statement_and_code_blocks_as_written(self):
        p = self.problem
        self.assertEqual(p["title"], "Rotate Array")
        self.assertIn("Given an array nums, rotate it to the right by k steps.", p["description"])
        self.assertIn("def rotate(nums, k):\n    # nums is changed in place\n    pass", p["description"])  # Indentation kept.
        self.assertNotIn("Companies", p["statement"])
        self.assertNotIn("Login", p["statement"])
        self.assertNotIn("Sign up", p["statement"])
        self.assertEqual(p["source"], "https://example.org/problems/rotate-array")

    def test_labelled_sections_and_constraints_are_kept_with_their_headings(self):
        sections = {s["heading"]: s["text"] for s in self.problem["sections"]}
        self.assertEqual(sections["Input Format"], "The first argument is the array, the second is k.")
        self.assertEqual(sections["Output Format"], "Return the rotated array.")
        self.assertEqual(sections["Note"], "k can be larger than the length of the array.")
        self.assertEqual(sections["Expected Time Complexity"], "O(n)")
        self.assertEqual(self.problem["constraints"], ["1 <= nums.length <= 10^5", "arr_i fits in 32 bits"])
        self.assertIn("Note:\nk can be larger", self.problem["statement"])
        self.assertIn("Constraints:\n- 1 <= nums.length <= 10^5", self.problem["statement"])

    def test_each_example_keeps_its_own_input_output_and_explanation(self):
        records = self.problem["examples"]
        self.assertEqual([r["name"] for r in records], ["Example 1", "Example 2", "Example 3"])
        self.assertEqual((records[0]["input"], records[0]["output"]), ("nums = [1, 2, 3, 4], k = 1", "[4, 1, 2, 3]"))
        self.assertEqual(records[0]["explanation"], "Every value moves one step right; 4 wraps to the front.")
        self.assertEqual(records[1]["explanation"], "")  # Example 2's input is never paired with example 1's text.
        self.assertEqual(records[2]["status"], "duplicate")
        cases = self.problem["cases"]
        self.assertEqual([(c["args"], c["expected"]) for c in cases], [([[1, 2, 3, 4], 1], [4, 1, 2, 3]), ([[7], 3], [7])])
        self.assertEqual(cases[0]["explanation"], "Every value moves one step right; 4 wraps to the front.")

    def test_quizzes_page_prompts_and_editorials_are_not_imported(self):
        text = json.dumps(self.problem)
        self.assertNotIn("[5, 6]", text)
        self.assertNotIn("Still unsure", text)
        self.assertNotIn("Reverse the whole array", text)
        self.assertNotIn("this is the trick", text)
        self.assertNotIn("walkthrough note", text)

    def test_what_could_not_be_imported_is_said(self):
        notes = " ".join(self.problem["notes"])
        self.assertIn("1 image", notes)
        self.assertEqual(self.problem["images"], 1)

    def test_examples_that_cannot_be_read_are_kept_word_for_word(self):
        page = ("<h1>Sum</h1><p>Read n numbers and print their sum.</p><h3>Sample Input 0</h3><pre>3\n1 2 3</pre><h3>Sample Output 0</h3><pre>6</pre>"
                "<h3>Example 2</h3><p>Input: s = “don’t”</p><p>Output: 5</p>")
        p = sheets.problem_from_page(page)
        sample, quoted = p["examples"]
        self.assertEqual((sample["status"], sample["input"], sample["output"]), ("unparsed", "3\n1 2 3", "6"))
        self.assertIn("standard input", sample["issue"])
        self.assertIn("Sample 1, as written on the page:\nInput: 3\n1 2 3\nOutput: 6", p["statement"])
        self.assertEqual(p["cases"][0]["args"], ["don’t"])  # The apostrophe inside the value is kept as written.

    def test_long_statements_are_cut_with_a_note_never_silently(self):
        page = "<h1>Long</h1>" + "".join(f"<p>Line {i} " + "x" * 200 + "</p>" for i in range(80)) + "<p>Input: n = 1</p><p>Output: 1</p>"
        p = sheets.problem_from_page(page)
        self.assertTrue(p["truncated"])
        self.assertLessEqual(len(p["statement"]), sheets.MAX_STATEMENT)
        self.assertTrue(any("longer than" in n for n in p["notes"]))

    def test_markdown_problem_pages(self):
        readme = ("# [1. Two Sum](https://leetcode.com/problems/two-sum)\n\n## Description\n\n<!-- description:start -->\n\n"
                  "<p>Given an array of integers <code>nums</code> and an integer <code>target</code>, return indices.</p>\n\n"
                  "<p><strong class=\"example\">Example 1:</strong></p>\n\n<pre>\n<strong>Input:</strong> nums = [2,7,11,15], target = 9\n"
                  "<strong>Output:</strong> [0,1]\n<strong>Explanation:</strong> Because nums[0] + nums[1] == 9, we return [0, 1].\n</pre>\n\n"
                  "## Solutions\n\n```python\ndef twoSum(nums, target):\n    pass\n```\n")
        p = sheets.problem_from_page(sheets.markdown_page(readme), "https://example.org/README.md")
        self.assertEqual(p["title"], "1. Two Sum".split(". ", 1)[1])
        self.assertEqual(p["cases"][0]["args"], [[2, 7, 11, 15], 9])
        self.assertEqual(p["cases"][0]["explanation"], "Because nums[0] + nums[1] == 9, we return [0, 1].")
        self.assertNotIn("twoSum", p["statement"])  # The Solutions section is not the problem.

    def test_pages_without_a_problem_fail_clearly(self):
        with self.assertRaisesRegex(ValueError, "No problem"):
            sheets.problem_from_page("<html><body><div>Welcome to our site</div></body></html>")
        with self.assertRaisesRegex(ValueError, "No problem statement"):
            sheets.problem_from_page("<h1>Title only</h1><h2>Editorial</h2><p>Spoilers.</p>")

    def test_page_furniture_is_dropped_but_a_problems_own_words_are_kept(self):
        page = ("<h1>Cookies</h1><p>Login to save your progress</p><p>Each cookie j has a size; users subscribe to topics.</p>"
                "<p>Implementation must run in O(n).</p><h3>Example 1:</h3><p>Input: g = [1, 2]</p><p>Output: 1</p>"
                "<h3>Constraints:</h3><li>1 &lt;= g.length</li><p>Input:</p><p>You haven’t submitted yet</p><p>Submit your code to run against hidden test cases</p>")
        p = sheets.problem_from_page(page)
        self.assertEqual(p["description"], "Each cookie j has a size; users subscribe to topics.\nImplementation must run in O(n).")
        self.assertEqual(p["constraints"], ["1 <= g.length"])  # The judge's custom-input box is neither a constraint nor an example.
        self.assertEqual([e["name"] for e in p["examples"]], ["Example 1"])
        self.assertTrue(any("Left out 3 lines" in n for n in p["notes"]))

    def test_an_output_drawn_as_an_image_is_said_never_guessed(self):
        page = ("<h1>Pattern</h1><p>Print the pattern.</p><section><h3>Example 1:</h3><p>Input: n = 4</p><p>Output:</p><p><img src='p.webp'/></p></section>"
                "<p>Still unsure what the problem is asking ?</p><p><img src='quiz.png' alt='quiz'/></p>")
        p = sheets.problem_from_page(page)
        (record,) = p["examples"]
        self.assertEqual((record["status"], record["output"]), ("partial", ""))
        self.assertIn("as an image", record["issue"])
        self.assertIn("Example 1, as written on the page:\nInput: n = 4\nOutput: (shown as an image on the page)", p["statement"])
        self.assertEqual((p["cases"][0]["args"], p["cases"][0]["missing"], p["images"]), ([4], True, 1))  # The quiz's image isn't counted.

    def test_example_text_stops_at_the_page_s_table_of_contents_and_icons_are_not_figures(self):
        page = ("<h1>Valid Parentheses</h1><p>Given a string s, decide whether it is balanced.</p><p>Example:</p>"
                "<p>Input: s = \"[()]\"<br>Output: true<br>Explanation: All the brackets are well-formed.</p><img alt='redirect icon'/>"
                "<p>Table of Content</p><li>Using Stack - O(n) Time</li><h3>Using Stack - O(n) Time</h3><p>We push each opening.</p>")
        p = sheets.problem_from_page(page)
        self.assertEqual(p["examples"][0]["explanation"], "All the brackets are well-formed.")
        self.assertEqual(p["images"], 0)
        self.assertNotIn("Using Stack", json.dumps(p))

    def test_an_output_ends_at_a_labelled_line_even_a_misspelled_one(self):
        page = ("<h1>First and last</h1><p>Find the first and last index of target.</p><h3>Example 1:</h3>"
                "<p>Input: nums = [5, 7, 8], target = 6<br>Output: [-1, -1]<br>Expalantion: The target is 6, which is not present.</p>")
        record = sheets.problem_from_page(page)["examples"][0]
        self.assertEqual((record["status"], record["output"], record["explanation"]), ("parsed", "[-1, -1]", "The target is 6, which is not present."))

    def test_a_tree_s_missing_nodes_written_as_n_are_read_as_null_and_said(self):
        page = ("<h1>Nodes at distance K</h1><p>Given the root of a binary tree, a target and k, return the nodes at distance k.</p>"
                "<h3>Example 1:</h3><p>Input: root = [3, 5, 1, N, N, 7, 4] , target = 5, k = 2</p><p>Output: [1, 4, 7]</p>"
                "<h3>Example 2:</h3><p>Input: grid = [N, 1]</p><p>Output: 1</p>")
        p = sheets.problem_from_page(page)
        self.assertEqual(p["cases"][0]["args"], [[3, 5, 1, None, None, 7, 4], 5, 2])
        self.assertEqual(p["examples"][0]["input"], "root = [3, 5, 1, N, N, 7, 4] , target = 5, k = 2")  # The record keeps what the page wrote.
        self.assertTrue(any("read as null" in n for n in p["notes"]))
        self.assertEqual(p["examples"][1]["status"], "unparsed")  # N is only a missing node in a tree.
        self.assertIn("couldn't be read as values", p["examples"][1]["issue"])

    def test_an_output_labelled_result_and_design_operations_written_as_calls(self):
        page = ("<h1>Bridges</h1><p>Return the bridges of the graph.</p><h3>Example 1:</h3><p>Input: V = 3, E = [[0,1],[1,2],[2,0]]</p>"
                "<p>Result: []</p><p>Explanation: There no bridges in the graph.</p>")
        record = sheets.problem_from_page(page)["examples"][0]
        self.assertEqual((record["status"], record["input"], record["output"]), ("parsed", "V = 3, E = [[0,1],[1,2],[2,0]]", "[]"))
        page = ("<h1>Find Median from Data Stream</h1><p>Implement the MedianFinder class.</p><h3>Example 1:</h3>"
                "<p>Input: [MedianFinder(), addNum(1), addNum(2), findMedian()]</p><p>Output: [null, null, null, 1.5]</p>")
        p = sheets.problem_from_page(page)
        self.assertEqual((p["entry"], p["cases"][0]["args"]), ("MedianFinder", [["MedianFinder", "addNum", "addNum", "findMedian"], [[], [1], [2], []]]))

    def test_an_output_written_as_an_assignment_is_its_value(self):
        page = ("<h1>Delete Tail of Doubly Linked List</h1><p>Given the head of a doubly linked list, remove its tail.</p>"
                "<h3>Example 1:</h3><p>Input: head = [1, 2, 3]</p><p>Output: head = [1, 2]</p><p>Explanation: The node with value 3 was removed.</p>"
                "<h3>Example 2:</h3><p>Input: head = [7]</p><p>Output: head = [ ]</p>"
                "<h3>Example 3:</h3><p>Input: head = [4]</p><p>Output: a = 1, b = 2</p>")
        p = sheets.problem_from_page(page)
        self.assertEqual([(c['args'], c['expected'], c['missing']) for c in p['cases']], [([[1, 2, 3]], [1, 2], False), ([[7]], [], False)])
        self.assertEqual(p['examples'][0]['output'], 'head = [1, 2]')  # The record keeps what the page wrote.
        self.assertEqual(p['examples'][2]['status'], 'partial')  # Two named values (not the inputs) are not one output...
        self.assertTrue(any('Example 3 was not added' in n for n in p['notes']))  # ...so it stays listed, not a blank case.

    def test_judges_output_notations_are_read_and_said(self):
        page = ("<h1>Floor and Ceil</h1><p>Return the floor and the ceil of x.</p>"
                "<h3>Example 1:</h3><p>Input: nums = [3, 4, 7], x = 5</p><p>Output: 4 7</p>"
                "<h3>Example 2:</h3><p>Input: nums = [3, 4, 7], x = 3</p><p>Output: 3</p>")
        p = sheets.problem_from_page(page)
        self.assertEqual([c['expected'] for c in p['cases']], [[4, 7], [3]])  # One list contract across examples.
        self.assertTrue(any('separated by spaces' in n for n in p['notes']))
        page = ("<h1>Subsequence with sum K</h1><p>Return Yes or No.</p><h3>Example 1:</h3><p>Input: nums = [1, 2], k = 3</p><p>Output: Yes</p>"
                "<h3>Example 2:</h3><p>Input: 2</p><p>Output: No</p>")
        p = sheets.problem_from_page(page)
        self.assertEqual(p['cases'][0]['expected'], 'Yes')
        page = ("<h1>Swap</h1><p>Swap a and b.</p><h3>Example 1:</h3><p>Input: a = 5, b = 10</p><p>Output: a = 10, b = 5</p>"
                "<h3>Example 2:</h3><p>Input: n = 6</p><p>Output = [1, 2]</p>")
        p = sheets.problem_from_page(page)
        self.assertEqual((p['cases'][0]['expected'], p['examples'][0]['read']), ([10, 5], 'named'))
        page = ("<h1>Generate</h1><p>Return all strings.</p><h3>Example 1:</h3><p>Input: n = 3</p><p>Output: [\"a\"]</p>"
                "<h3>Example 2:</h3><p>Input: 2</p><p>Output: [\"b\"]</p><h3>Example 3:</h3><p>Input: N = 4, M = 2 edge = [1]</p><p>Output: 1</p>")
        p = sheets.problem_from_page(page)
        self.assertEqual([c['args'] for c in p['cases']], [[3], [2]])  # An unnamed one-input example is that input.

    def test_node_values_cycles_and_patterns_from_the_page(self):
        page = ("<h1>Find the starting point in LL</h1><p>Return the node where the loop starts in the linked list, or null.</p>"
                "<h3>Example 1:</h3><p>Input: head -> 1 -> 2 -> 3, pos = 1</p><p>Output(value of the returned node is displayed): 2</p>"
                "<h3>Example 2:</h3><p>Input: head -> 1 -> 3, pos = -1</p><p>Output(value of the returned node is displayed): null</p>")
        p = sheets.problem_from_page(page)
        self.assertEqual(([c['expected'] for c in p['cases']], p['answer'], p['kinds']), ([2, None], 'node-value', {'head': 'linkedlist', 'pos': 'cycle'}))
        page = ("<h1>Pattern 7</h1><p>Given an integer n. Let's say for N = 3, the pattern should look like as below:</p>"
                "<pre>  *\n ***\n*****</pre><p>Print the pattern in the function given to you.</p>"
                "<h3>Example 1:</h3><p>Input: n = 4</p><p>Output:</p><p><img src='a.png'/></p>")
        p = sheets.problem_from_page(page)
        self.assertEqual([(c['name'], c['args'], c['expected']) for c in p['cases']], [('From the statement', [3], ['  *', ' ***', '*****'])])
        self.assertEqual(p['answer'], 'lines')
        self.assertEqual(p['examples'][0]['status'], 'partial')  # The drawn example is still listed, as an image.

    def test_empty_subscripts_and_invisible_characters_add_nothing(self):
        p = sheets.problem_from_page("<h1>K</h1><p>Sum.</p><pre>Input: k = 2\nOutput: ﻿700\nExplanation: arr<sub>2</sub><sub> </sub>+ arr<sub>3</sub> = 700</pre>")
        self.assertEqual(p["examples"][0]["explanation"], "arr_2 + arr_3 = 700")
        self.assertEqual(p["cases"][0]["expected"], 700)

    def test_constraints_a_page_draws_from_its_data_are_written_out_exactly(self):
        data = {"props": {"pageProps": {"problem": {
            "problem_name": "Max Sum Subarray of size K",
            "problem_question": "<p>Given an array <strong>arr[]</strong> and a number <strong>k</strong>, return the maximum sum of a subarray of size k.</p>"
                                "<pre><strong>Input:</strong> arr[] = [100, 200, 300, 400], k = 2\n<strong>Output: </strong>700</pre>",
            "input_format": {"arguments": "arr[] = &!//!&k = ", "datatype": "INTEGER_ARRAY&!//!&INTEGER", "show_constraints_in_problem": True,
                             "constraints": [{"min_size": "1", "max_size": "10^6", "element_min_value": "0", "element_max_value": "10^6"},
                                             {"min_value": "1", "cross_argument_constraints": [{"sourceProperty": "value", "operator": "≤", "targetArg": "arr", "targetProperty": "size"}]},
                                             {"element_allowed_characters": "custom:LW"}]}}}}}
        page = f'<html><body><div id="app"></div><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>'
        p = sheets.problem_from_page(page)
        self.assertEqual(p["constraints"], ["1 ≤ arr.size() ≤ 10^6", "0 ≤ arr[i] ≤ 10^6", "1 ≤ k ≤ arr.size()"])
        notes = " ".join(p["notes"])
        self.assertIn("from the page's data", notes)
        self.assertIn("1 constraint field", notes)  # What isn't understood is said, not guessed.
        self.assertEqual(p["cases"][0]["args"], [[100, 200, 300, 400], 2])

    def test_a_readme_with_front_matter_and_a_description_heading(self):
        readme = ("---\ncomments: true\ntags:\n    - Array\n---\n\n# [1. Two Sum](https://leetcode.com/problems/two-sum)\n\n[中文文档](/README.md)\n\n## Description\n\n"
                  "<p>Return indices of the two numbers that add up to <code>target</code>.</p>\n\n<p><strong class=\"example\">Example 1:</strong></p>\n\n"
                  "<pre>\nnums = [2,7,11,15], target = 9 is the input\n<strong>Input:</strong> nums = [2,7,11,15], target = 9\n<strong>Output:</strong> [0,1]\n</pre>\n\n"
                  "<p><strong>Constraints:</strong></p>\n\n<ul>\n\t<li><code>2 &lt;= nums.length &lt;= 10<sup>4</sup></code></li>\n</ul>\n\n"
                  "<strong>Follow-up:&nbsp;</strong>Can you do better than <code>O(n<sup>2</sup>)</code>?\n\n![tree](images/tree.png)\n\n## Solutions\n\nUse a hash table.\n")
        p = sheets.problem_from_page(sheets.markdown_page(readme), "https://example.org/README_EN.md")
        self.assertEqual(p["title"], "Two Sum")
        self.assertEqual(p["description"], "Return indices of the two numbers that add up to target.")
        self.assertEqual(p["constraints"], ["2 <= nums.length <= 10^4"])
        self.assertEqual([(s["heading"], s["text"]) for s in p["sections"]], [("Follow-up", "Can you do better than O(n^2)?")])
        self.assertEqual(p["cases"][0]["args"], [[2, 7, 11, 15], 9])
        self.assertEqual(p["images"], 1)
        self.assertNotIn("中文", json.dumps(p, ensure_ascii=False))
        self.assertNotIn("comments: true", p["statement"])
        self.assertNotIn("hash table", p["statement"])

    def test_a_single_problem_link_pasted_as_a_sheet_is_one_problem(self):
        rows, name = sheets.read_link("https://example.org/problems/rotate-array", lambda url: (PAGE.encode(), url, "text/html", "utf-8"))
        self.assertEqual((name, [(r["title"], r["url"], r["source"]) for r in rows]), ("Rotate Array", [("Rotate Array", "https://example.org/problems/rotate-array", "https://example.org/problems/rotate-array")]))

    def test_a_judge_s_problem_link_takes_the_page_s_own_title_or_falls_back_to_the_link(self):
        page = "<h1>Kadane's Algorithm</h1><p>Find the largest subarray sum.</p><p>Input: nums = [1, -2, 3]</p><p>Output: 3</p>"
        served = lambda url: (b"", url, "text/plain", "utf-8") if url.endswith("robots.txt") else (page.encode(), url, "text/html", "utf-8")
        rows, name = sheets.read_link("https://www.geeksforgeeks.org/problems/kadanes-algorithm-1587115620/1", served)
        self.assertEqual((name, rows[0]["title"], rows[0]["source"]), ("Kadane's Algorithm", "Kadane's Algorithm", "https://www.geeksforgeeks.org/problems/kadanes-algorithm-1587115620/1"))

        def unreachable(url):
            raise ValueError("Couldn't reach the site.")
        rows, name = sheets.read_link("https://www.geeksforgeeks.org/problems/kadanes-algorithm-1587115620/1", unreachable)
        self.assertEqual((name, rows[0]["title"], rows[0].get("source")), ("My sheet", "Kadanes Algorithm", None))
        rows, _ = sheets.read_link("https://leetcode.com/problems/two-sum/", lambda url: self.fail("LeetCode is never fetched"))
        self.assertEqual(rows[0]["title"], "Two Sum")


class NotationsAreReadOnlyWhereTheyAre(unittest.TestCase):
    """Arrows, missing commas and JSON words are notation only outside quoted strings; a value's own text comes
    through exactly as written, and every reading beyond the page's notation is said in the notes."""

    def test_arrows_inside_quoted_strings_are_text(self):
        for output, value in [('["0->2","4->5","7"]', ["0->2", "4->5", "7"]), ('["1->2","1->3"]', ["1->2", "1->3"]), ('"0->2"', "0->2"), ('"x->y"', "x->y"),
                              ("'x->y'", "x->y"), ("['a->b', \"c\"]", ["a->b", "c"]), ('"a -> b means a points to b"', "a -> b means a points to b")]:
            self.assertEqual(sheets.read_output(output, ["nums"]), (value, None), output)
        self.assertEqual(sheets.assignments("s = 'x->y'"), (["s"], ["x->y"], {}))  # Text, with no linked-list kind.
        self.assertEqual(sheets.assignments('words = ["a->b", "c"]'), (["words"], [["a->b", "c"]], {}))
        parsed = sheets.parse_examples('Input: nums = [0,1,2,4,5,7]\nOutput: ["0->2","4->5","7"]\nExplanation: [0,2] --> "0->2"')
        self.assertEqual((parsed["cases"][0]["expected"], parsed["kinds"]), (["0->2", "4->5", "7"], {}))
        page = ("<h1>Summary Ranges</h1><p>Return the ranges as strings \"a->b\".</p><h3>Example 1:</h3><p>Input: nums = [0,1,2,4,5,7]</p>"
                "<p>Output: [\"0->2\",\"4->5\",\"7\"]</p><p>Explanation: The ranges are: [0,2] --> \"0->2\", [4,5] --> \"4->5\"</p>")
        p = sheets.problem_from_page(page)
        self.assertEqual(p["cases"][0]["expected"], json.loads(p["examples"][0]["output"]))  # Exactly the page's strings.
        self.assertEqual(p["cases"][0]["explanation"], 'The ranges are: [0,2] --> "0->2", [4,5] --> "4->5"')
        self.assertEqual(p["kinds"], {})

    def test_arrow_chains_are_still_linked_lists(self):
        for given, names, values, kinds in [
                ("head = 1 -> 2 -> 3 -> NULL", ["head"], [[1, 2, 3]], {"head": "linkedlist"}),
                ("head = 1->2->3->NULL", ["head"], [[1, 2, 3]], {"head": "linkedlist"}),  # Was '[1, "2-"]>[3]'.
                ("head = 1->2->3->4, k = 2", ["head", "k"], [[1, 2, 3, 4], 2], {"head": "linkedlist"}),
                ("head = [1 -> 2]", ["head"], [[1, 2]], {"head": "linkedlist"}),
                ("head -> 1 -> 2", ["head"], [[1, 2]], {"head": "linkedlist"}),
                ("head = 1 <-> 2 <-> 3", ["head"], [[1, 2, 3]], {"head": "dll"}),
                ("list1 = 1 -> 2 -> 4, list2 = 1 -> 3 -> 4", ["list1", "list2"], [[1, 2, 4], [1, 3, 4]], {"list1": "linkedlist", "list2": "linkedlist"}),
                ("head = a -> e -> b", ["head"], [["a", "e", "b"]], {"head": "linkedlist"}),  # Was ['e', 'b']: a value isn't a label.
                ("head = a -> b -> x", ["head"], [["a", "b", "x"]], {"head": "linkedlist"}),  # x after letters is a value.
                ("head = 1 -> 2 -> X", ["head"], [[1, 2]], {"head": "linkedlist"}),  # x after numbers ends the list.
                ("head = -1 -> -2 -> 3", ["head"], [[-1, -2, 3]], {"head": "linkedlist"}),
                ("head = -1->-2", ["head"], [[-1, -2]], {"head": "linkedlist"})]:
            self.assertEqual(sheets.assignments(given), (names, values, kinds), given)
        self.assertEqual(sheets.chains("1->2->3->NULL"), ("[1, 2, 3]", "linkedlist"))
        self.assertEqual(sheets.read_output("b -> e -> a", ["head"]), (["b", "e", "a"], None))  # Was ['e', 'a'].
        self.assertEqual(sheets.read_output("head -> 3 -> 2 -> 1", ["head"]), ([3, 2, 1], None))  # head is a list's label.
        gfg = sheets.parse_examples("Input: head = 1->2->3->4\nOutput: 4->3->2->1\nExplanation: 1 -> 2 becomes 2 -> 1")
        self.assertEqual((gfg["cases"][0]["args"], gfg["cases"][0]["expected"], gfg["kinds"]), ([[1, 2, 3, 4]], [4, 3, 2, 1], {"head": "linkedlist"}))

    def test_commas_and_json_words_never_reach_into_text(self):
        self.assertEqual(sheets.assignments('s = "let a = 5"')[:2], (["s"], ["let a = 5"]))  # Was 'let, a = 5'.
        self.assertEqual(sheets.assignments('s = "end. x = 1"')[:2], (["s"], ["end. x = 1"]))  # Was 'end, x = 1'.
        said = []
        self.assertEqual(sheets.assignments('s = "ab" t = 1', said)[:2], (["s", "t"], ["ab", 1]))  # Outside quotes it is still read...
        self.assertIn("without a comma", said[0])  # ...and said.
        self.assertEqual(sheets.literal("'the statement is true'"), "the statement is true")  # Was '... is True'.
        self.assertEqual(sheets.literal("['null','false',1]"), ["null", "false", 1])  # Was ['None', 'False', 1].
        self.assertEqual(sheets.literal("[true, 'null', null]"), [True, "null", None])

    def test_every_reading_is_said(self):
        def notes(page):
            return " ".join(sheets.problem_from_page("<h1>P</h1><p>Solve it.</p>" + page)["notes"])
        self.assertIn("Example 2: The page doesn't name this input, so it was read as n",
                      notes("<h3>Example 1:</h3><p>Input: n = 3</p><p>Output: 3</p><h3>Example 2:</h3><p>Input: 2</p><p>Output: 2</p>"))
        self.assertIn("without a comma", notes("<h3>Example 1:</h3><p>Input: M = 2 edge = [1, 2]</p><p>Output: 1</p>"))
        self.assertIn("s is written without quotes, so it was read as the text (*))", notes("<h3>Example 1:</h3><p>Input: s = (*))</p><p>Output: true</p>"))
        self.assertIn("written as an assignment", notes("<h3>Example 1:</h3><p>Input: nums = [1, 2, 3]</p><p>Output: nums = [1, 2]</p>"))
        self.assertIn("called value here", notes("<h3>Example 1:</h3><p>Input: 5</p><p>Output: 5</p>"))
        self.assertEqual(sheets.parse_examples("Input: N = 4 M = [1, 2]\nOutput: 3")["notes"],
                         ["Example 1: The page separates two named inputs without a comma (by a space or a full stop), so they were read as separate inputs."])
        self.assertNotIn("notes", sheets.parse_examples("Input: n = 4\nOutput: 3"))  # Nothing beyond the notation: nothing to say.

    def test_a_pattern_outside_a_code_block_keeps_its_drawn_spacing_or_is_not_read(self):
        intro = "<h1>Pattern 7</h1><p>Given an integer n. Let's say for N = 3, the pattern should look like as below:</p>"
        example = "<p>Print the pattern.</p><h3>Example 1:</h3><p>Input: n = 4</p><p>Output:</p><p><img src='a.png'/></p>"
        p = sheets.problem_from_page(intro + "<p>&nbsp;&nbsp;*<br>&nbsp;***<br>*****</p>" + example)
        self.assertEqual([(c["args"], c["expected"]) for c in p["cases"]], [([3], ["  *", " ***", "*****"])])  # Was ['*', '***', '*****'].
        self.assertIn("  *\n ***\n*****", p["statement"])  # The statement shows it as drawn, too.
        p = sheets.problem_from_page(intro + "<p>  *<br> ***<br>*****</p>" + example)  # Plain spaces: a browser drops them.
        self.assertFalse(any(c["name"] == "From the statement" for c in p["cases"]))
        self.assertTrue(any("exact spacing can't be read" in n for n in p["notes"]))

    def test_an_unnamed_input_is_named_only_when_the_structure_is_unambiguous(self):
        def read(statement):
            p = sheets.problem_from_page(f"<h1>P</h1><p>{statement}</p><h3>Example 1:</h3><p>Input: [-10, -3, 0, 5, 9]</p><p>Output: [0, -3, 9]</p>")
            return p["params"], p["kinds"], " ".join(p["notes"])
        params, kinds, notes = read("Given the head of a singly linked list sorted in ascending order, convert it to a height-balanced BST.")
        self.assertEqual((params, kinds), (["value"], {}))  # Was root, read as a tree.
        self.assertIn("both a linked list and a tree", notes)
        params, kinds, notes = read("Given the root of a binary tree, return its level order.")
        self.assertEqual((params, kinds), (["root"], {"root": "tree"}))
        self.assertIn("That is an inference", notes)
        params, kinds, _ = read("Given a linked list, reverse it.")
        self.assertEqual((params, kinds), (["head"], {"head": "linkedlist"}))

    def test_unclosed_list_items_and_paragraphs_are_kept_in_order(self):
        reader = sheets.PageBlocks()
        reader.feed("<h1>T</h1><p>Given n.<p>Constraints:<ul><li>n is even<li>n is positive</ul><p>tail")
        reader.close()
        self.assertEqual(reader.blocks, [("h1", "T"), ("p", "Given n."), ("p", "Constraints:"), ("li", "n is even"), ("li", "n is positive"), ("p", "tail")])
        reader = sheets.PageBlocks()
        reader.feed("<ul><li>a<ul><li>b<li>c</ul>d<li>e</ul>")  # A nested list's items don't close the outer item.
        reader.close()
        self.assertEqual(reader.blocks, [("li", "b"), ("li", "c"), ("li", "ad"), ("li", "e")])
        reader = sheets.PageBlocks()
        reader.feed("<p>Text <ul><li>a</li></ul> more</p><p>next</p>")  # A list inside a paragraph: the text after it is still shown.
        reader.close()
        self.assertEqual(reader.blocks, [("p", "Text"), ("li", "a"), ("p", "more"), ("p", "next")])
        p = sheets.problem_from_page("<h1>T</h1><p>Find n.</p><p>Input: n = 2</p><p>Output: 2</p><h3>Constraints:</h3><ul><li>1 &lt;= n<li>n &lt;= 10</ul>")
        self.assertEqual(p["constraints"], ["1 <= n", "n <= 10"])  # Were dropped.


class JsonContract(unittest.TestCase):
    def test_every_api_failure_is_json(self):
        client = app.app.test_client()
        for response, status in [(client.get("/api/does-not-exist"), 404), (client.post("/api/sheets/read", json={}), 400),
                                 (client.post("/api/sheets/read", data="x" * 500000, content_type="application/json"), 413),
                                 (client.post("/api/labs/fetch", json={"sheetId": "nope", "row": 0}), 400)]:
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.content_type, "application/json")
            body = response.get_json()
            self.assertIs(body["ok"], False)
            self.assertTrue(body["error"])

    def test_an_unexpected_crash_is_json_too(self):
        original = sheets.read_link
        sheets.read_link = lambda url: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            response = app.app.test_client().post("/api/sheets/read", json={"url": "https://example.org/x"})
        finally:
            sheets.read_link = original
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["details"], "RuntimeError: boom")


if __name__ == "__main__":
    unittest.main()
