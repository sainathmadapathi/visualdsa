"""A learner's own sheet: reading files, links and recognised text; matching rows to built-in labs;
and labs the learner defines, which run, judge and record progress only against their own cases."""
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DSA_DATABASE"] = str(Path(tempfile.mkdtemp()) / "sheets-test.sqlite3")
import app  # noqa: E402
import sheets  # noqa: E402


def titles(rows):
    return [r["title"] for r in rows]


class ReadingSheets(unittest.TestCase):
    def test_csv_with_headers_sections_and_links(self):
        text = ("S.No,Problem,Link,Difficulty,Done\n,Arrays,,,\n"
                "1,Two Sum,https://leetcode.com/problems/two-sum/,Easy,TRUE\n"
                "2,3Sum,https://leetcode.com/problems/3sum/,Medium,\n"
                ",Strings,,,\n3,Valid Palindrome,https://leetcode.com/problems/valid-palindrome/,Easy,\n")
        rows = sheets.finish(sheets.rows_from_csv(text))
        self.assertEqual(titles(rows), ["Two Sum", "3Sum", "Valid Palindrome"])
        self.assertEqual([r["topic"] for r in rows], ["Arrays", "Arrays", "Strings"])
        self.assertEqual([(r["match"], r["fit"]) for r in rows], [("two-sum", "same"), (None, None), ("palindrome", "close")])
        self.assertEqual(rows[1]["difficulty"], "Medium")

    def test_pasted_spreadsheet_range_and_hyperlink_formulas(self):
        rows = sheets.finish(app.read_text("Question\tTopic\tLevel\nTwo Sum\tHashing\tEasy\nTrapping Rain Water\tTwo Pointers\tHard\n"))
        self.assertEqual([(r["title"], r["topic"], r["difficulty"]) for r in rows], [("Two Sum", "Hashing", "Easy"), ("Trapping Rain Water", "Two Pointers", "Hard")])
        rows = sheets.finish(sheets.rows_from_csv('Problem,Level\n"=HYPERLINK(""https://leetcode.com/problems/move-zeroes/"",""Move Zeroes"")",Easy\nJump Game,Medium\n'))
        self.assertEqual((rows[0]["title"], rows[0]["url"], rows[0]["match"]), ("Move Zeroes", "https://leetcode.com/problems/move-zeroes/", "move-zeroes"))

    def test_plain_and_markdown_lists(self):
        text = ("## Arrays\n- [ ] [Two Sum](https://leetcode.com/problems/two-sum/) - Easy\n- [x] Kadane's Algorithm (Medium)\n"
                "1. Merge Intervals https://leetcode.com/problems/merge-intervals/\nSliding window:\n"
                "* https://www.geeksforgeeks.org/problems/max-sum-subarray-of-size-k5313/1\nTRUE\n42\n")
        rows = sheets.finish(sheets.rows_from_text(text))
        self.assertEqual(titles(rows), ["Two Sum", "Kadane's Algorithm", "Merge Intervals", "Max Sum Subarray Of Size K"])
        self.assertEqual([r["match"] for r in rows], ["two-sum", "max-subarray", None, "max-window-sum"])
        self.assertEqual(rows[3]["topic"], "Sliding window")
        table = "| # | Problem | Difficulty |\n|---|---|---|\n| 1 | [Binary Search](https://leetcode.com/problems/binary-search/) | Easy |\n| 2 | Koko Eating Bananas | Medium |\n"
        rows = sheets.finish(sheets.rows_from_text(table))
        self.assertEqual([(r["title"], r["url"], r["difficulty"]) for r in rows], [("Binary Search", "https://leetcode.com/problems/binary-search/", "Easy"), ("Koko Eating Bananas", "", "Medium")])

    def test_text_read_from_a_photo_of_a_table(self):
        ocr = "S.No Problem Difficulty Status\n1 Two Sum Easy Done\n4 Trapping Rain Water Hard TODO 12/04\n6 3Sum Medium\n"
        rows = sheets.finish(sheets.rows_from_text(ocr, ocr=True))
        self.assertEqual([(r["title"], r["difficulty"]) for r in rows], [("Two Sum", "Easy"), ("Trapping Rain Water", "Hard"), ("3Sum", "Medium")])

    def test_excel_tabs_hyperlinks_and_json(self):
        import openpyxl
        book = openpyxl.Workbook()
        first = book.active
        first.title = "Arrays"
        first.append(["Problem", "Difficulty"])
        first.append(["Best Time to Buy and Sell Stock", "Easy"])
        first["A2"].hyperlink = "https://leetcode.com/problems/best-time-to-buy-and-sell-stock/"
        second = book.create_sheet("Binary Search")
        second.append(["Problem", "Difficulty"])
        second.append(["Search Insert Position", "Easy"])
        blob = io.BytesIO()
        book.save(blob)
        rows, name = sheets.read_upload("Striver A2Z.xlsx", blob.getvalue())
        rows = sheets.finish(rows)
        self.assertEqual(name, "Striver A2Z")
        self.assertEqual([(r["title"], r["topic"], r["match"]) for r in rows], [("Best Time to Buy and Sell Stock", "Arrays", "best-profit"), ("Search Insert Position", "Binary Search", "search-insert")])
        self.assertEqual(rows[0]["url"], "https://leetcode.com/problems/best-time-to-buy-and-sell-stock/")
        rows, _ = sheets.read_upload("list.json", json.dumps({"problems": [{"Title": "Valid Anagram", "Link": "https://leetcode.com/problems/valid-anagram/"}, "Two Sum"]}).encode())
        self.assertEqual([r["match"] for r in sheets.finish(rows)], ["valid-anagram", "two-sum"])
        with self.assertRaisesRegex(ValueError, "Image option"):
            sheets.read_upload("sheet.png", b"\x89PNG")

    def test_web_pages_tables_and_judge_links(self):
        page = """<html><head><title>My DSA Sheet</title><script>var x = "<a href='https://leetcode.com/problems/fake/'>x</a>";</script></head><body>
            <table><tr><th>Problem</th><th>Level</th></tr>
            <tr><td><a href="https://leetcode.com/problems/two-sum/">Two Sum</a></td><td>Easy</td></tr>
            <tr><td><a href="https://leetcode.com/problems/3sum/">3Sum</a></td><td>Medium</td></tr>
            <tr><td><a href="https://leetcode.com/problems/move-zeroes/">Move Zeroes</a></td><td>Easy</td></tr></table></body></html>"""
        rows, title = sheets.rows_from_html(page)
        self.assertEqual(title, "My DSA Sheet")
        self.assertEqual([(r["title"], r["difficulty"]) for r in rows], [("Two Sum", "Easy"), ("3Sum", "Medium"), ("Move Zeroes", "Easy")])
        listing = """<h2>Hashing</h2><ul><li><a href="https://leetcode.com/problems/contains-duplicate/">Contains Duplicate</a></li>
            <li><a href="https://example.com/about">About us</a></li><li><a href="https://www.geeksforgeeks.org/problems/count-pairs-with-given-sum5022/1">Count pairs</a></li></ul>"""
        rows = sheets.finish(sheets.rows_from_html(listing)[0])
        self.assertEqual([(r["title"], r["topic"], r["match"]) for r in rows], [("Contains Duplicate", "Hashing", "contains-duplicate"), ("Count pairs", "Hashing", "pair-count")])


class EmbeddedPageData(unittest.TestCase):
    """Sheet sites that render their list from data embedded in the page (e.g. takeuforward.org)."""

    def flight_page(self, record):
        flight = '0:{"P":null}\n1a:T12,not json at all\n2b:' + json.dumps(record) + "\n"
        return ("<html><head><title>Striver's A2Z DSA Sheet &amp; Course | takeUforward</title></head><body><div id='root'></div>"
                f"<script>self.__next_f.push([1,{json.dumps(flight)}])</script></body></html>")

    def test_a_server_component_payload_with_schema_indexed_rows(self):
        syllabus = {
            "fields": [["id", "slug", "type", "label", "children"],
                       ["id", "type", "layoutType", "label", "leetcode_link", "difficulty"],
                       ["id", "type", "layoutType", "label", "free_blog_link"],
                       ["id", "type", "layoutType", "label", "redirectTo", "leetcode_link", "difficulty"]],
            "rows": [[0, 1, "arrays", "category", "Arrays", [1, 5]],
                     [0, 2, "faqs", "category", "FAQs(Medium)", [2, 3, 4]],
                     [1, 3, "item", "practice", "Two Sum", "https://leetcode.com/problems/two-sum/", "basic"],
                     [3, 4, "item", "practice", "Sort an array of 0's 1's and 2's", {"layoutType": "practice", "contentType": "dsa", "itemSlug": "sort-an-array-of-0's-1's-and-2's"}, "https://leetcode.com/problems/sort-colors/", "core"],
                     [2, 5, "item", "learning", "What is an array?", "/blogs/arrays"],
                     [0, 6, "contest", "contest", "Arrays contest", []],
                     [0, 7, "binary", "category", "Binary Search", [7]],
                     [3, 8, "item", "practice", "Pattern 1", {"layoutType": "practice", "contentType": "dsa", "itemSlug": "pattern-1"}, None, "pro"]],
            "roots": [0, 6],
        }
        page = self.flight_page({"data": {"next_problem": {"label": "Breaking The Myth", "state": "not_started"}, "sheet_syllabus": syllabus}})
        rows, name = sheets.rows_from_html(page, "https://takeuforward.org/prep-hub/strivers-a2z-dsa-sheet?page=sheet")
        rows = sheets.finish(rows)
        self.assertEqual(name, "Striver's A2Z DSA Sheet & Course")
        self.assertEqual([(r["title"], r["difficulty"], r["topic"], r["match"]) for r in rows],
                         [("Two Sum", "Easy", "Arrays · FAQs(Medium)", "two-sum"),
                          ("Sort an array of 0's 1's and 2's", "Medium", "Arrays · FAQs(Medium)", None),
                          ("Pattern 1", "Hard", "Binary Search", None)])
        # A problem opens where the sheet lists it: its page on the sheet's site. Judge links stay attached.
        self.assertEqual([(r["url"], r["links"], r["source"]) for r in rows[1:]],
                         [("https://takeuforward.org/practice/dsa/sort-an-array-of-0's-1's-and-2's", ["https://leetcode.com/problems/sort-colors/"], "https://takeuforward.org/practice/dsa/sort-an-array-of-0's-1's-and-2's"),
                          ("https://takeuforward.org/practice/dsa/pattern-1", [], "https://takeuforward.org/practice/dsa/pattern-1")])
        elsewhere, _ = sheets.rows_from_html(page, "https://example.com/sheet")
        self.assertEqual([r["source"] for r in elsewhere], ["", "", ""])  # Routes are known only for takeUforward.

    def test_next_data_and_json_script_tags(self):
        data = {"props": {"pageProps": {"menu": [{"label": "Home", "link": "https://example.com/"}, {"label": "Blog", "link": "https://example.com/blog"}, {"label": "About", "link": "https://example.com/about"}],
                                        "problems": [{"title": "Valid Anagram", "difficulty": "Easy", "url": "https://leetcode.com/problems/valid-anagram/"},
                                                     {"title": "Group Anagrams", "difficulty": "Medium", "url": "https://leetcode.com/problems/group-anagrams/"},
                                                     {"title": "Top K Frequent Elements", "difficulty": "Medium"}]}}}
        page = f'<html><title>NeetCode-ish</title><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'
        rows, _ = sheets.rows_from_html(page)
        self.assertEqual([(r["title"], r["difficulty"]) for r in rows], [("Valid Anagram", "Easy"), ("Group Anagrams", "Medium"), ("Top K Frequent Elements", "Medium")])
        nav_only = f'<html><script type="application/json">{json.dumps(data["props"]["pageProps"]["menu"])}</script></html>'
        self.assertEqual(sheets.rows_from_html(nav_only)[0], [])


class ReadingProblemPages(unittest.TestCase):
    """Building a lab reads the problem from its own page: statement, constraints and examples as stated."""

    TUF = """<html><head><title>Kadane's Algorithm - Practice | takeUforward</title></head><body><nav><a href="/">Home</a></nav>
      <header><h1>124. Kadane's Algorithm</h1><button><span>Hints</span></button><button><span>Companies</span></button></header>
      <div><p>Given an integer array <strong>nums</strong>, find the subarray with the largest sum and return the sum.</p><p>A subarray is contiguous.</p></div>
      <section><h3>Example 1:</h3><div><p><strong>Input</strong>: nums = [2, 3, 5, -2, 7, -4]</p><p><strong>Output</strong>: 15</p><p><strong>Explanation</strong>: </p><p>Index 0 to 4.</p></div></section>
      <section><h3>Example 2:</h3><div><p><strong>Input</strong>: nums = [-2, -3]</p><p><strong>Output</strong>: -2</p></div></section>
      <section><h3>Now Your Turn!</h3><p><strong>Input</strong>: nums = [-1, 2, 3]</p><label>4</label><label>5</label></section>
      <section><h3>Constraints:</h3><li>1 &lt;= nums.length &lt;= 10<sup>5</sup></li><li>-10<sup>4</sup> &lt;= nums[i] &lt;= 10<sup>4</sup></li></section>
      <script>self.__next_f.push([1,"0:{}"])</script></body></html>"""

    def test_a_rendered_problem_page(self):
        problem = sheets.problem_from_page(self.TUF, "https://takeuforward.org/practice/dsa/kadane's-algorithm")
        self.assertEqual(problem["title"], "Kadane's Algorithm")
        self.assertEqual(problem["params"], ["nums"])
        self.assertEqual([(c["args"], c["expected"], c["missing"]) for c in problem["cases"]], [([[2, 3, 5, -2, 7, -4]], 15, False), ([[-2, -3]], -2, False)])
        self.assertIn("A subarray is contiguous.", problem["statement"])
        self.assertIn("- 1 <= nums.length <= 10^5\n- -10^4 <= nums[i] <= 10^4", problem["statement"])
        self.assertNotIn("Hints", problem["statement"])
        self.assertNotIn("-1, 2, 3", json.dumps(problem))  # The quiz is not an example.
        self.assertEqual(problem["notes"], [])

    def test_outputs_that_are_not_values_are_left_for_the_learner(self):
        page = """<h1>896. Pattern 1</h1><p>Given an integer n, print the pattern:</p><p>*****</p><p>*****</p>
          <section><h3>Example 1:</h3><p><strong>Input</strong>: n = 4</p><p><strong>Output</strong>:</p><p></p></section>
          <section><h3>Example 2:</h3><p>Input: n = 2</p><p>Output: ** **</p></section>"""
        problem = sheets.problem_from_page(page)
        self.assertEqual(problem["title"], "Pattern 1")
        self.assertIn("*****\n*****", problem["statement"])
        self.assertEqual([(c["args"], c["expected"], c["missing"]) for c in problem["cases"]], [([4], None, True), ([2], None, True)])
        self.assertEqual(len(problem["notes"]), 3)
        self.assertIn("no output value", problem["notes"][0])
        self.assertIn("isn't a single value", problem["notes"][1])
        self.assertIn("prints its answer", problem["notes"][2])

    def test_a_problem_kept_in_page_data_with_several_examples_under_one_heading(self):
        statement = ("<p>Given an array <strong>arr[]</strong> and a number <strong>k</strong>, return the maximum sum of a subarray of size k.</p>"
                     "<p><strong>Examples:</strong></p><pre><strong>Input:</strong> arr[] = [100, 200, 300, 400], k = 2\n<strong>Output: </strong>700\n<strong>Explanation: </strong>200 + 300</pre>"
                     "<pre><strong>Input: </strong>arr[] = {1, 4, 2}, k = 1\n<strong>Output: </strong>4</pre><p><strong>Constraints:</strong><br>1 ≤ k ≤ arr.size()</p>")
        data = {"props": {"pageProps": {"initialState": {"problemData": {"problem_name": "Max Sum Subarray of size K", "problem_question": statement}}}}}
        page = f'<html><body><div id="__next"></div><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>'
        problem = sheets.problem_from_page(page)
        self.assertEqual((problem["title"], problem["params"]), ("Max Sum Subarray of size K", ["arr", "k"]))
        self.assertEqual([(c["args"], c["expected"]) for c in problem["cases"]], [([[100, 200, 300, 400], 2], 700), ([[1, 4, 2], 1], 4)])
        self.assertTrue(problem["statement"].endswith("Constraints:\n- 1 ≤ k ≤ arr.size()"))

    def test_leetcode_style_examples(self):
        page = ("<h1>1. Two Sum</h1><p>Return indices of the two numbers that add up to target.</p><p><strong class='example'>Example 1:</strong></p>"
                "<pre><strong>Input:</strong> nums = [2,7,11,15], target = 9\n<strong>Output:</strong> [0,1]\n<strong>Explanation:</strong> 2 + 7 == 9.</pre>"
                "<p><strong>Example 2:</strong></p><pre><strong>Input:</strong> nums = [3,3], target = 6\n<strong>Output:</strong> [0,1]</pre>")
        problem = sheets.problem_from_page(page)
        self.assertEqual([(c["args"], c["expected"]) for c in problem["cases"]], [([[2, 7, 11, 15], 9], [0, 1]), ([[3, 3], 6], [0, 1])])

    def test_what_is_never_fetched(self):
        sheets.ROBOTS.clear()
        with self.assertRaisesRegex(ValueError, "no link"):
            sheets.read_problem({"title": "Pattern 1", "url": "", "source": ""})
        with self.assertRaisesRegex(ValueError, "builds its pages in the browser"):
            sheets.read_problem({"url": "https://leetcode.com/problems/two-sum/"}, lambda url: self.fail("LeetCode is never fetched"))
        fetched = []

        def site(url):
            fetched.append(url)
            if url.endswith("/robots.txt"):
                return b"User-agent: *\nDisallow: /private/\n", url, "text/plain", "utf-8"
            return self.TUF.encode(), url, "text/html", "utf-8"
        with self.assertRaisesRegex(ValueError, "robots.txt"):
            sheets.read_problem({"source": "https://example.org/private/kadane"}, site)
        self.assertEqual(fetched, ["https://example.org/robots.txt"])
        problem = sheets.read_problem({"source": "https://example.org/practice/kadane"}, site)
        self.assertEqual((problem["title"], problem["source"]), ("Kadane's Algorithm", "https://example.org/practice/kadane"))
        self.assertEqual(fetched, ["https://example.org/robots.txt", "https://example.org/practice/kadane"])  # robots.txt is read once per site.
        with self.assertRaisesRegex(ValueError, "isn't a problem page"):
            sheets.read_problem({"source": "https://example.org/sheet.csv"}, lambda url: (b"a,b", url, "text/csv", "utf-8"))

    def test_the_sheets_site_first_then_attached_links(self):
        sheets.ROBOTS.clear()
        fetched = []

        def web(url):
            fetched.append(url)
            if url.endswith("/robots.txt"):
                return b"", url, "text/plain", "utf-8"
            if "takeuforward.org" in url:  # The sheet's site has no readable statement for this one.
                return b"<html><h1>Sign in to continue</h1><button>Log in</button></html>", url, "text/html", "utf-8"
            return self.TUF.encode(), url, "text/html", "utf-8"
        row = {"title": "Kadane's Algorithm", "url": "https://takeuforward.org/practice/dsa/kadane's-algorithm", "source": "https://takeuforward.org/practice/dsa/kadane's-algorithm",
               "links": ["https://leetcode.com/problems/maximum-subarray/", "https://www.geeksforgeeks.org/problems/kadanes-algorithm-1587115620/1"]}
        problem = sheets.read_problem(row, web)
        pages = [u for u in fetched if not u.endswith("robots.txt")]
        self.assertEqual(pages, ["https://takeuforward.org/practice/dsa/kadane's-algorithm", "https://www.geeksforgeeks.org/problems/kadanes-algorithm-1587115620/1"])  # LeetCode skipped.
        self.assertEqual(len(problem["cases"]), 2)
        self.assertIn("couldn't be read on takeuforward.org", problem["notes"][0])
        self.assertIn("geeksforgeeks.org", problem["notes"][0])
        fetched.clear()
        sheets.ROBOTS.clear()
        readable = {**row, "url": "https://example.org/kadane", "source": "https://example.org/kadane"}
        self.assertEqual(sheets.read_problem(readable, web)["notes"], [])  # Read on the sheet's site: no detour.
        self.assertEqual([u for u in fetched if not u.endswith("robots.txt")], ["https://example.org/kadane"])

    def test_links_belong_to_the_sheets_own_site(self):
        page = ("<html><title>My list</title><table><tr><th>Problem</th><th>Practice</th></tr>"
                + "".join(f'<tr><td><a href="/problems/{slug}">{name}</a></td><td><a href="https://leetcode.com/problems/{slug}/">LC</a></td></tr>' for slug, name in [("two-sum", "Two Sum"), ("3sum", "3Sum"), ("move-zeroes", "Move Zeroes")])
                + "</table></html>")
        rows = sheets.finish(sheets.rows_from_html(page, "https://dsa.example.com/sheet")[0])
        self.assertEqual([(r["url"], r["links"], r["match"]) for r in rows],
                         [("https://dsa.example.com/problems/two-sum", ["https://leetcode.com/problems/two-sum/"], "two-sum"),
                          ("https://dsa.example.com/problems/3sum", ["https://leetcode.com/problems/3sum/"], None),
                          ("https://dsa.example.com/problems/move-zeroes", ["https://leetcode.com/problems/move-zeroes/"], "move-zeroes")])
        # A file has no site of its own: its link column stays the main link.
        rows = sheets.finish(sheets.rows_from_csv("Problem,Link,LeetCode\nKadane,https://takeuforward.org/practice/dsa/kadane's-algorithm,https://leetcode.com/problems/maximum-subarray/\n"))
        self.assertEqual((rows[0]["url"], rows[0]["links"], rows[0]["match"]), ("https://takeuforward.org/practice/dsa/kadane's-algorithm", ["https://leetcode.com/problems/maximum-subarray/"], "max-subarray"))

    def test_the_endpoint_reads_a_saved_row(self):
        client = app.app.test_client()
        rows = [{"title": "Kadane's Algorithm", "url": "https://leetcode.com/problems/maximum-subarray/", "source": "https://takeuforward.org/practice/dsa/kadane's-algorithm", "difficulty": "", "topic": "", "match": None}]
        sheet_id = client.post("/api/sheets", json={"name": "A2Z", "rows": rows}).get_json()["id"]
        saved = next(s for s in client.get("/api/sheets").get_json()["sheets"] if s["id"] == sheet_id)
        self.assertEqual(saved["rows"][0]["source"], "https://takeuforward.org/practice/dsa/kadane's-algorithm")
        original, sheets.fetch = sheets.fetch, lambda url: ((b"" if url.endswith("robots.txt") else self.TUF.encode()), url, "text/html", "utf-8")
        try:
            sheets.ROBOTS.clear()
            problem = client.post("/api/labs/fetch", json={"sheetId": sheet_id, "row": 0}).get_json()
        finally:
            sheets.fetch = original
        self.assertEqual(problem["params"], ["nums"])
        self.assertEqual(len(problem["cases"]), 2)
        self.assertIn("error", client.post("/api/labs/fetch", json={"sheetId": sheet_id, "row": 5}).get_json())
        self.assertIn("error", client.post("/api/labs/fetch", json={"sheetId": "nope", "row": 0}).get_json())


class ReadingLinks(unittest.TestCase):
    def test_google_sheets_links_become_csv_exports(self):
        self.assertEqual(sheets.sheet_export_url("https://docs.google.com/spreadsheets/d/1AbC_dEf-123/edit#gid=456"),
                         "https://docs.google.com/spreadsheets/d/1AbC_dEf-123/export?format=csv&gid=456")
        self.assertEqual(sheets.sheet_export_url("https://docs.google.com/spreadsheets/d/e/2PACX-1vXYZ/pubhtml?gid=0&single=true"),
                         "https://docs.google.com/spreadsheets/d/e/2PACX-1vXYZ/pub?output=csv&gid=0")
        self.assertIsNone(sheets.sheet_export_url("https://example.com/spreadsheets/d/1/edit"))

    def test_links_are_read_through_the_fetcher(self):
        seen = []

        def fetcher(url):
            seen.append(url)
            return b"Problem,Level\nTwo Sum,Easy\n", url, "text/csv", "utf-8"
        rows, name = sheets.read_link("https://docs.google.com/spreadsheets/d/abc/edit", fetcher)
        self.assertEqual((seen, titles(rows), name), (["https://docs.google.com/spreadsheets/d/abc/export?format=csv"], ["Two Sum"], "My Google Sheet"))

        def private(url):
            return b"<html>Sign in</html>", "https://accounts.google.com/ServiceLogin", "text/html", "utf-8"
        with self.assertRaisesRegex(ValueError, "isn't public"):
            sheets.read_link("https://docs.google.com/spreadsheets/d/abc/edit", private)
        def unreachable(url):
            raise AssertionError("A single problem's link needs no fetch.")
        rows, _ = sheets.read_link("https://leetcode.com/problems/two-sum/description/", unreachable)
        self.assertEqual([(r["title"], r["url"]) for r in rows], [("Two Sum", "https://leetcode.com/problems/two-sum/description/")])

    def test_local_and_private_addresses_are_refused(self):
        for url in ("http://127.0.0.1:5000/api/health", "http://localhost/x", "http://10.0.0.8/sheet.csv", "file:///C:/secret.csv", "ftp://example.com/a"):
            with self.assertRaises(ValueError):
                sheets.fetch(url)


class OwnLabs(unittest.TestCase):
    def test_examples_are_read_as_written(self):
        parsed = sheets.parse_examples("Example 1:\nInput: nums = [2,7,11,15], target = 9\nOutput: [0,1]\nExplanation: Because nums[0] + nums[1] == 9.\n"
                                       "Example 2:\nInput: nums = [3,2,4], target = 6\nOutput: [1,2]")
        self.assertEqual(parsed, {"params": ["nums", "target"], "cases": [{"name": "Example 1", "args": [[2, 7, 11, 15], 9], "expected": [0, 1]}, {"name": "Example 2", "args": [[3, 2, 4], 6], "expected": [1, 2]}], "kinds": {}, "entry": "solve"})
        chained = sheets.parse_examples("Input: head -> 1 -> 2 -> 3\nOutput: head -> 3 -> 2 -> 1\nInput: head -> null\nOutput: head -> null")
        self.assertEqual((chained["params"], chained["kinds"], [(c["args"], c["expected"]) for c in chained["cases"]]), (["head"], {"head": "linkedlist"}, [([[1, 2, 3]], [3, 2, 1]), ([[]], [])]))
        quoted = sheets.parse_examples("Input: str = “()[{}()]”\nOutput: True")
        self.assertEqual(quoted["cases"][0]["args"], ["()[{}()]"])
        design = sheets.parse_examples('Input: operations = ["MinStack", "push", "getMin"]\nnums = [[], [3], []]\nOutput: [null, null, 3]')
        self.assertEqual((design["entry"], design["params"], design["cases"][0]["expected"]), ("MinStack", ["operations", "nums"], [None, None, 3]))
        parsed = sheets.parse_examples('Input: s = "anagram", t = "nagaram"\nOutput: true\nInput: intervals = [[1,3]]\nOutput: [[1,3]]'.split("\nInput: intervals")[0])
        self.assertEqual(parsed["cases"][0], {"name": "Example 1", "args": ["anagram", "nagaram"], "expected": True})
        with self.assertRaisesRegex(ValueError, "different parameters"):
            sheets.parse_examples("Input: a = 1\nOutput: 1\nInput: b = 2\nOutput: 2")
        with self.assertRaisesRegex(ValueError, "No “Input"):
            sheets.parse_examples("Two Sum is a classic problem.")

    def test_a_lab_needs_every_expected_output_and_consistent_types(self):
        base = {"title": "Window", "statement": "Find the best window of size k.", "params": "nums, k"}
        with self.assertRaisesRegex(ValueError, "One element — it needs an expected output"):
            sheets.build_lab({**base, "cases": [{"name": "One element", "args": ["[1]", "1"], "expected": ""}]})
        with self.assertRaisesRegex(ValueError, "Case 1 — k: "):
            sheets.build_lab({**base, "cases": [{"name": "Case 1", "args": ["[1]", "abc"], "expected": "1"}]})
        with self.assertRaisesRegex(ValueError, "keep each parameter's type|Keep each parameter's type"):
            sheets.build_lab({**base, "cases": [{"args": ["[1]", "1"], "expected": "1"}, {"args": ['"x"', "1"], "expected": "1"}]})
        with self.assertRaisesRegex(ValueError, "Parameters|parameters"):
            sheets.build_lab({**base, "params": "nums, 1k", "cases": [{"args": ["[1]", "1"], "expected": "1"}]})
        lab = sheets.build_lab({**base, "order": "any", "cases": [{"args": ["[1, 2]", "1"], "expected": "[2]"}, {"name": "Floats", "args": ["[1.5]", "1"], "expected": "1.5"}]})
        self.assertEqual((lab["params"], lab["order"], lab["cases"][0]["name"]), (["nums", "k"], "any", "Case 1"))


class SheetPractice(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def sheet(self, text="Two Sum\nTrapping Rain Water - Hard\nhttps://leetcode.com/problems/3sum/\n"):
        read = self.client.post("/api/sheets/read", json={"text": text, "source": "paste"}).get_json()
        saved = self.client.post("/api/sheets", json={"name": "Blind 3", "source": "paste", "rows": read["rows"]}).get_json()
        return saved["id"]

    def lab(self, sheet_id, row=1, cases=None, **extra):
        cases = cases or [{"name": "Example 1", "args": ["[0,1,0,2,1,0,1,3,2,1,2,1]"], "expected": "6"}, {"name": "Example 2", "args": ["[4,2,0,3,2,5]"], "expected": "9"}, {"name": "Empty input", "args": ["[]"], "expected": "0"}]
        return self.client.post("/api/labs", json={"sheetId": sheet_id, "row": row, "title": "Trapping Rain Water", "statement": "Compute how much rain water the elevation map traps.", "params": "height", "cases": cases, **extra}).get_json()

    def test_reading_never_saves_and_saving_recomputes_matches(self):
        before = self.client.get("/api/sheets").get_json()
        read = self.client.post("/api/sheets/read", json={"text": "Two Sum\nGroup Anagrams\n"}).get_json()
        self.assertEqual(self.client.get("/api/sheets").get_json(), before)
        forged = [dict(read["rows"][0], match="not-a-lab")]
        self.assertIn("error", self.client.post("/api/sheets", json={"name": "x", "rows": forged}).get_json())
        rows = [dict(read["rows"][0], fit="manual", lab="custom-000000000000"), dict(read["rows"][1], match="valid-anagram")]
        saved = self.client.post("/api/sheets", json={"name": "Mine", "rows": rows}).get_json()
        sheet = next(s for s in saved["sheets"] if s["id"] == saved["id"])
        self.assertEqual([(r["match"], r["fit"], r["lab"]) for r in sheet["rows"]], [("two-sum", "same", None), ("valid-anagram", "manual", None)])
        self.assertIn("error", self.client.post("/api/sheets/read", json={"text": "TRUE\n42\n"}).get_json())

    def test_an_own_lab_traces_every_case_and_judges_only_against_them(self):
        sheet_id = self.sheet()
        built = self.lab(sheet_id)
        lab = built["lab"]
        self.assertTrue(lab["id"].startswith("custom-") and lab["custom"])
        self.assertNotIn("tests", lab)
        self.assertNotIn("solution", lab)
        self.assertEqual((lab["params"], lab["number"], lab["sheetName"]), (["height"], 2, "Blind 3"))
        row = next(s for s in built["sheets"] if s["id"] == sheet_id)["rows"][1]
        self.assertEqual(row["lab"], lab["id"])

        slow = "def solve(height):\n    total = 0\n    for i in range(len(height)):\n        total += min(max(height[:i + 1]), max(height[i:])) - height[i]\n    return total\n"
        preview = self.client.post("/api/preview", json={"problemId": lab["id"], "code": slow, "args": [[4, 2, 0, 3, 2, 5]]}).get_json()
        self.assertEqual([(c["name"], c["goal"]) for c in preview["cases"]], [("Example 1", {"expected": 6, "matches": True}), ("Example 2", {"expected": 9, "matches": True}), ("Empty input", {"expected": 0, "matches": True})])
        self.assertEqual(preview["caseId"], "case-1")

        wrong = "def solve(height):\n    return len(height)\n"
        run = self.client.post("/api/execute", json={"problemId": lab["id"], "code": wrong, "args": [[4, 2, 0, 3, 2, 5]]}).get_json()
        self.assertFalse(run["passed"])
        self.assertEqual(run["divergence"]["kind"], "Observed result mismatch")
        self.assertIn("your case expects 9", run["divergence"]["message"])
        self.assertIn("error", self.client.post("/api/progress", json={"problemId": lab["id"], "stage": "Independent", "attemptId": run["attemptId"]}).get_json())

        run = self.client.post("/api/execute", json={"problemId": lab["id"], "code": slow, "args": [[4, 2, 0, 3, 2, 5]]}).get_json()
        self.assertTrue(run["passed"] and all(t["passed"] for t in run["tests"]))
        saved = self.client.post("/api/progress", json={"problemId": lab["id"], "stage": "Independent", "attemptId": run["attemptId"]}).get_json()
        self.assertEqual(saved["stage"], "Independent")

        # An input outside the learner's cases has no known answer: no goal, judged by the cases alone.
        own = self.client.post("/api/execute", json={"problemId": lab["id"], "code": slow, "args": [[5, 0, 5]]}).get_json()
        self.assertIsNone(own["goal"])
        self.assertEqual(next(c for c in own["cases"] if c["custom"])["goal"], None)
        self.assertIn("same type", self.client.post("/api/preview", json={"problemId": lab["id"], "code": slow, "args": ["abc"]}).get_json()["error"])

    def test_own_labs_have_no_reference_hints_or_approach_and_stay_private(self):
        sheet_id = self.sheet()
        lab = self.lab(sheet_id)["lab"]
        self.assertEqual(self.client.get(f"/api/problems/{lab['id']}/solution").status_code, 404)
        self.assertIn("error", self.client.post("/api/hint", json={"problemId": lab["id"], "level": 1}).get_json())
        self.assertIn("no authored approach", self.client.post("/api/approach", json={"problemId": lab["id"], "technique": "Two pointers", "operation": "find both maxima quickly"}).get_json()["error"])
        self.assertIn("error", self.client.post("/api/progress", json={"problemId": lab["id"], "stage": "Modified", "attemptId": "x", "evidence": "x" * 30}).get_json())
        hint = self.client.post("/api/chat", json={"message": "give me a hint", "context": {"problemId": lab["id"], "stage": "code"}}).get_json()
        self.assertIn("no authored hints", hint["text"])
        growth = self.client.post("/api/chat", json={"message": "what is the time complexity?", "context": {"problemId": lab["id"], "stage": "discover"}}).get_json()
        self.assertNotIn("Reference comparison", growth["text"])
        self.assertIsNone(app.problem_by_id(lab["id"], "someone-else"))
        self.assertIsNone(app.problem_by_id(lab["id"]))

    def test_any_order_and_float_answers(self):
        sheet_id = self.sheet("Unique Values Anywhere\n")
        lab = self.lab(sheet_id, row=0, order="any", cases=[{"args": ["[3, 1, 3, 2]"], "expected": "[1, 2, 3]"}])["lab"]
        run = self.client.post("/api/execute", json={"problemId": lab["id"], "code": "def solve(height):\n    return list(set(height))[::-1]\n", "args": [[3, 1, 3, 2]]}).get_json()
        self.assertTrue(run["passed"])
        lab = self.lab(sheet_id, row=0, cases=[{"args": ["[1, 2]"], "expected": "1.5"}])["lab"]
        run = self.client.post("/api/execute", json={"problemId": lab["id"], "code": "def solve(height):\n    return sum(height) / len(height)\n", "args": [[1, 2]]}).get_json()
        self.assertTrue(run["passed"])

    def test_editing_cases_updates_the_same_lab_and_deleting_removes_it(self):
        sheet_id = self.sheet()
        first = self.lab(sheet_id)["lab"]
        second = self.lab(sheet_id, cases=[{"args": ["[2, 0, 2]"], "expected": "2"}])["lab"]
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(second["cases"]), 1)
        listing = self.client.delete(f"/api/sheets/{sheet_id}").get_json()
        self.assertNotIn(sheet_id, [s["id"] for s in listing["sheets"]])
        self.assertNotIn(first["id"], [l["id"] for l in listing["labs"]])
        self.assertIsNone(app.problem_by_id(first["id"], "local-learner"))


if __name__ == "__main__":
    unittest.main()
