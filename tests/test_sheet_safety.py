"""Reading sheets and problem pages stays bounded however a page or a paste is crafted: no pattern backtracks for
seconds, embedded data can't expand without end, a fetch has a deadline and reaches only public addresses, and
robots.txt is respected even when it can't be read. Only sheets.py is imported: no database is touched."""
import io
import ipaddress
import json
import socket
import sys
import threading
import time
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sheets  # noqa: E402


class Quick:
    """Each call must finish well under a second; before these fixes the same inputs took seconds to minutes."""
    LIMIT = 1.0

    def quick(self, fn, *args):
        start = time.perf_counter()
        try:
            return fn(*args)
        finally:
            self.assertLess(time.perf_counter() - start, self.LIMIT, f"{getattr(fn, '__name__', fn)} took too long")


class Backtracking(Quick, unittest.TestCase):
    def test_design_calls_fail_fast_and_still_read(self):
        for n in (40, 200):  # Was 2^n: n=26 took 14 s.
            with self.assertRaises(ValueError):
                self.quick(sheets.parse_examples, "Input: [" + " ".join(["a()"] * n) + "\nOutput: 1")
        calls = [["MedianFinder", "addNum", "addNum", "findMedian"], [[], [1], [2], []]]
        self.assertEqual(sheets.assignments("[MedianFinder(), addNum(1), addNum(2), findMedian()]")[:2], (["operations", "arguments"], calls))
        self.assertEqual(sheets.assignments("[MedianFinder(),addNum(1),addNum(2),findMedian()]")[1], calls)
        self.assertEqual(sheets.assignments('["MinStack", "push", "getMin"]\n[[], [3], []]')[:2], (["operations", "arguments"], [["MinStack", "push", "getMin"], [[], [3], []]]))

    def test_long_runs_of_spaces_dashes_and_brackets(self):
        dashes = "-".join(["1"] * 4500)
        self.assertEqual(self.quick(sheets.chains, dashes), (dashes, None))  # No arrow: nothing read, nothing changed.
        rows, _ = self.quick(sheets.read_photo_text, "Two" + " " * 20000 + "Sum")
        self.assertEqual([r["title"] for r in rows], ["Two Sum"])
        self.assertEqual(self.quick(sheets.read_photo_text, " " * 20000 + "Problem Difficulty\nTwo Sum")[0][0]["title"], "Two Sum")
        self.assertEqual(self.quick(sheets.rows_from_text, "a" + " " * 20000 + "b"), [])
        self.assertEqual([r["title"] for r in self.quick(sheets.rows_from_json, [{" " * 20000 + "title": "Two Sum"}])], ["Two Sum"])
        self.assertEqual(self.quick(sheets.slug_of, "https://leetcode.com/problems/" + "-" * 10000), "")
        self.assertEqual(self.quick(sheets.slug_of, "https://leetcode.com/problems/" + "1" * 10000 + "a"), sheets.normal("1" * 10000 + "a"))
        self.assertEqual(self.quick(sheets.embedded_json, '<script type="application/json">' * 4000), [])
        self.assertEqual(self.quick(sheets.rows_from_text, "[" * 20000 + "]x"), [])
        self.assertEqual(self.quick(sheets.rows_from_html, "<title>a" + " " * 20000 + "b</title>")[1], "a b")
        self.assertEqual(self.quick(sheets.straighten, " ‘" * 10000), " ‘" * 10000)
        self.assertTrue(self.quick(sheets.markdown_page, "[" * 20000 + "](x"))

    def test_example_text_with_long_gaps(self):
        for text in ("Input: a" + " " * 16000 + "b", "Input: " * 2285):
            with self.assertRaisesRegex(ValueError, "No “Input"):
                self.quick(sheets.parse_examples, text)
        given, output, _, _ = self.quick(sheets.split_example, ["Input: 1"] + [""] * 10000 + ["Output: 2"])
        self.assertEqual((given, output), ("1", "2"))

    def test_pages_with_unclosed_or_deeply_nested_blocks(self):
        tail = "<p>Input: n = 1</p><p>Output: 1</p>"
        unclosed = self.quick(sheets.problem_from_page, "<h1>P</h1>" + "<p>x" * 10000 + "</li>" * 5000 + tail)  # Was 19 s at 180 KB.
        self.assertEqual(unclosed["cases"][0]["args"], [1])
        nested = self.quick(sheets.problem_from_page, "<h1>P</h1>" + "<blockquote>x" * 10000 + "</blockquote>" * 10000 + tail)
        self.assertEqual(nested["cases"][0]["expected"], 1)
        self.quick(sheets.problem_from_page, "<h1>P</h1><pre>" + "n = 1 following " * 2000 + "</pre>" + tail)
        self.quick(sheets.problem_from_page, "<h1>P</h1><p>x</p><pre>constraints" + " " * 20000 + "x</pre>" + tail)


def table_page(rows):
    return '<script type="application/json">' + json.dumps({"fields": [["label", "children"]], "rows": rows}) + "</script>"


class EmbeddedData(Quick, unittest.TestCase):
    def test_rows_that_name_themselves_as_children(self):
        for k in (3, 4, 8):  # k=3 took 22 s; k=4 needed gigabytes.
            self.assertEqual(self.quick(sheets.rows_from_html, table_page([[0, "x", [0] * k]]), "https://example.com/"), ([], ""))
            self.assertEqual(sheets.expand_columns({"fields": [["label", "children"]], "rows": [[0, "x", [0] * k]]}), [{"label": "x", "children": []}])

    def test_rows_shared_by_many_parents(self):
        rows = [[0, f"x{i}", [i + 1] * 4 if i < 29 else []] for i in range(30)]  # 4^12 paths through 30 rows.
        self.assertEqual(self.quick(sheets.rows_from_html, table_page(rows), "https://example.com/"), ([], ""))
        self.assertIsNone(sheets.expand_columns({"fields": [["label", "children"]], "rows": rows}))  # Skipped whole, not cut short.

    def test_a_row_listed_under_two_sections_is_kept_under_both(self):
        table = {"fields": [["label", "children"], ["label", "leetcode_link", "difficulty"]],
                 "rows": [[0, "Arrays", [2]], [0, "Hashing", [2]], [1, "Two Sum", "https://leetcode.com/problems/two-sum/", "Easy"]], "roots": [0, 1]}
        self.assertEqual(sheets.expand_columns(table), [{"label": "Arrays", "children": [{"label": "Two Sum", "leetcode_link": "https://leetcode.com/problems/two-sum/", "difficulty": "Easy"}]},
                                                        {"label": "Hashing", "children": [{"label": "Two Sum", "leetcode_link": "https://leetcode.com/problems/two-sum/", "difficulty": "Easy"}]}])

    def test_visiting_data_is_bounded(self):
        # Data from a page is a tree once expanded, so this budget is a backstop: it is checked on its own here,
        # with the same objects reached by a million paths and expansion left out.
        node = {"label": "leaf", "children": []}
        for _ in range(20):
            node = {"label": "section", "children": [node, node]}
        saved = sheets.MAX_VISITS, sheets.expand_columns
        sheets.MAX_VISITS, sheets.expand_columns = 5000, lambda value, depth=0: value
        try:
            self.assertEqual(self.quick(sheets.json_rows, [node]), [])
        finally:
            sheets.MAX_VISITS, sheets.expand_columns = saved


def workbook(sheet_xml):
    files = {
        "[Content_Types].xml": '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": sheet_xml,
    }
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return blob.getvalue()


class Workbooks(Quick, unittest.TestCase):
    def test_a_zip_bomb_is_refused_before_it_is_parsed(self):
        cells = '<row><c t="inlineStr"><is><t>x</t></is></c></row>' * 240_000  # 12 MB of XML in a 34 KB file: was 14 s.
        bomb = workbook(f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{cells}</sheetData></worksheet>')
        self.assertLess(len(bomb), 100_000)
        with self.assertRaisesRegex(ValueError, "unpacks to more than"):
            self.quick(sheets.rows_from_xlsx, bomb)

    def test_a_small_workbook_with_links_is_read_in_read_only_mode(self):
        import openpyxl
        book = openpyxl.Workbook()
        book.active.append(["Problem", "Level"])
        book.active.append(["Two Sum", "Easy"])
        book.active["A2"].hyperlink = "https://leetcode.com/problems/two-sum/"
        blob = io.BytesIO()
        book.save(blob)
        rows = self.quick(sheets.rows_from_xlsx, blob.getvalue())
        self.assertEqual([(r["title"], r["url"], r["difficulty"]) for r in rows], [("Two Sum", "https://leetcode.com/problems/two-sum/", "Easy")])
        with self.assertRaisesRegex(ValueError, "could not be read"):
            sheets.rows_from_xlsx(b"PK\x03\x04 not really a zip")


class ClearFailures(unittest.TestCase):
    """What used to escape as a 500 (LookupError, RecursionError, TypeError, csv.Error) is now a clear ValueError."""

    def test_unknown_charsets_fall_back_to_utf8(self):
        rows, _ = sheets.read_link("https://example.org/list.txt", lambda url: ("Two Sum\nValid Anagram\n".encode(), url, "text/plain", "utf8mb4"))
        self.assertEqual([r["title"] for r in rows], ["Two Sum", "Valid Anagram"])
        page = "<h1>Two</h1><p>Find it.</p><p>Input: n = 1</p><p>Output: 1</p>".encode()

        def site(charset):
            return lambda url: (b"", url, "text/plain", "utf-8") if url.endswith("robots.txt") else (page, url, "text/html", charset)
        sheets.ROBOTS.clear()
        self.assertEqual(sheets.read_problem({"source": "https://a.example/p"}, site("utf8mb4"))["notes"], [])  # UTF-8 by another name.
        sheets.ROBOTS.clear()
        notes = sheets.read_problem({"source": "https://a.example/p"}, site("x-made-up"))["notes"]
        self.assertIn("read as UTF-8", notes[0])

    def test_deep_or_odd_values_are_not_values(self):
        for text in ("[" * 100000, "{{1}}", "{[1]: 2}"):
            with self.assertRaisesRegex(ValueError, "isn't a value"):
                sheets.literal(text)
        self.assertEqual(sheets.embedded_json('<script type="application/json">' + "[" * 100000 + "</script>"), [])
        with self.assertRaisesRegex(ValueError, "could not be read"):
            sheets.read_upload("deep.json", ("[" * 100000).encode())
        with self.assertRaisesRegex(ValueError, "couldn't be read"):
            sheets.read_link("https://example.org/deep.json", lambda url: (("[" * 100000).encode(), url, "application/json", "utf-8"))

    def test_an_oversized_csv_cell(self):
        with self.assertRaisesRegex(ValueError, "longer than"):
            sheets.rows_from_csv('Problem,Link\n"' + "x" * 140000 + '",y\n')


def serve(handler):
    """A local server for one test: handler(connection, request line) answers each connection."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    seen = []

    def loop():
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            request = conn.recv(65536).decode("latin-1").split("\r\n")[0]
            seen.append(request)
            threading.Thread(target=handler, args=(conn, request), daemon=True).start()
    threading.Thread(target=loop, daemon=True).start()
    return listener, listener.getsockname()[1], seen


def answer(conn, status, headers="", body=b""):
    conn.sendall(f"HTTP/1.1 {status}\r\n{headers}Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
    conn.close()


class LoopbackAllowed:
    """Tests that need the local server let loopback through the address check, and restore it after."""
    def setUp(self):
        self.saved = sheets.is_public, sheets.FETCH_SECONDS
        sheets.is_public = lambda address: True

    def tearDown(self):
        sheets.is_public, sheets.FETCH_SECONDS = self.saved


class Addresses(unittest.TestCase):
    def test_ipv6_forms_of_private_ipv4_are_refused(self):
        for text in ("::127.0.0.1", "64:ff9b::7f00:1", "64:ff9b::a00:8", "64:ff9b:1::a00:8", "::ffff:127.0.0.1", "::ffff:10.0.0.1", "2002:7f00:1::", "::1", "fe80::1"):
            self.assertFalse(sheets.is_public(ipaddress.ip_address(text)), text)
        for text in ("93.184.216.34", "64:ff9b::808:808", "2606:4700:4700::1111"):
            self.assertTrue(sheets.is_public(ipaddress.ip_address(text)), text)
        with self.assertRaisesRegex(ValueError, "private or local"):
            sheets.public_host("::127.0.0.1")
        with self.assertRaisesRegex(ValueError, "Couldn't find"):
            sheets.public_host("a" * 100 + ".com")  # Was a UnicodeError.

    def test_the_connection_goes_to_the_address_that_was_checked(self):
        listener, port, seen = serve(lambda conn, request: answer(conn, "200 OK", "Content-Type: text/plain\r\n", b"private"))
        lookups = []

        def rebinding(host, port_, *args, **kwargs):  # Public when checked, this machine when looked up again.
            lookups.append(host)
            address = "93.184.216.34" if len(lookups) == 1 else "127.0.0.1"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port_ or 0))]
        original, socket.getaddrinfo = socket.getaddrinfo, rebinding
        try:
            with self.assertRaisesRegex(ValueError, "private or local"):
                sheets.fetch(f"http://rebind.example:{port}/sheet.csv")
        finally:
            socket.getaddrinfo = original
            listener.close()
        self.assertEqual(seen, [])  # The private server was never reached.


class Fetching(LoopbackAllowed, unittest.TestCase):
    def test_a_site_that_drips_is_cut_off_at_the_deadline(self):
        def drip_body(conn, request):
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 100000\r\n\r\n")
            try:
                while True:
                    conn.sendall(b"x")
                    time.sleep(0.1)
            except OSError:
                pass

        def drip_headers(conn, request):
            conn.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
            try:
                while True:
                    conn.sendall(b"a")
                    time.sleep(0.1)
            except OSError:
                pass
        sheets.FETCH_SECONDS = 0.6
        for handler in (drip_body, drip_headers):
            listener, port, _ = serve(handler)
            start = time.perf_counter()
            with self.assertRaisesRegex(ValueError, "took too long"):
                sheets.fetch(f"http://127.0.0.1:{port}/")
            self.assertLess(time.perf_counter() - start, 3)  # Each byte came within the per-read timeout: it used to read for hours.
            listener.close()

    def test_an_ordinary_page_and_redirects_into_leetcode(self):
        def site(conn, request):
            if request.startswith("GET /moved"):
                answer(conn, "302 Found", "Location: https://leetcode.com/problems/two-sum/\r\n")
            else:
                answer(conn, "200 OK", "Content-Type: text/html; charset=utf-8\r\n", b"<h1>Sheet</h1>")
        listener, port, _ = serve(site)
        try:
            self.assertEqual(sheets.fetch(f"http://127.0.0.1:{port}/page")[0], b"<h1>Sheet</h1>")
            with self.assertRaisesRegex(ValueError, "LeetCode"):
                sheets.fetch(f"http://127.0.0.1:{port}/moved")
        finally:
            listener.close()

    def test_a_redirect_must_be_allowed_by_robots_txt(self):
        def site(conn, request):
            if request.startswith("GET /robots.txt"):
                answer(conn, "200 OK", "Content-Type: text/plain\r\n", b"User-agent: *\nDisallow: /private/\n")
            elif request.startswith("GET /problems/a"):
                answer(conn, "302 Found", "Location: /private/b\r\n")
            else:
                answer(conn, "200 OK", "Content-Type: text/html\r\n", b"<h1>Secret</h1><p>Input: n = 1</p><p>Output: 1</p>")
        listener, port, seen = serve(site)
        sheets.ROBOTS.clear()
        try:
            with self.assertRaisesRegex(ValueError, "robots.txt"):
                sheets.read_problem({"source": f"http://127.0.0.1:{port}/problems/a"})
        finally:
            listener.close()
        self.assertNotIn("GET /private/b HTTP/1.1", seen)


class Robots(unittest.TestCase):
    def read(self, status):
        sheets.ROBOTS.clear()
        fetched = []

        def site(url):
            fetched.append(url)
            if url.endswith("/robots.txt"):
                raise sheets.FetchError("The site answered with an error.", status) if status else sheets.FetchError("The link couldn't be reached.")
            return b"<h1>Two</h1><p>Find it.</p><p>Input: n = 1</p><p>Output: 1</p>", url, "text/html", "utf-8"
        try:
            sheets.read_problem({"source": "https://example.org/p"}, site)
            outcome = "read"
        except ValueError as error:
            outcome = str(error)
        return outcome, [u for u in fetched if not u.endswith("robots.txt")], "https://example.org" in sheets.ROBOTS

    def test_unreadable_robots_txt_means_the_page_is_not_read(self):
        for status in (500, 503, None):  # A server error or no connection: whether the page may be read is unknown.
            outcome, pages, cached = self.read(status)
            self.assertIn("robots.txt couldn't be read", outcome)
            self.assertEqual((pages, cached), ([], False))
        for status in (401, 403):  # As Python's robot parser reads them: everything is disallowed.
            outcome, pages, cached = self.read(status)
            self.assertIn("asks automated tools not to read", outcome)
            self.assertEqual((pages, cached), ([], True))
        self.assertEqual(self.read(404), ("read", ["https://example.org/p"], True))  # No robots.txt: everything is allowed.

    def test_a_page_that_ends_up_on_leetcode_is_not_used(self):
        sheets.ROBOTS.clear()

        def site(url):
            if url.endswith("robots.txt"):
                return b"", url, "text/plain", "utf-8"
            return b"<h1>Two Sum</h1><p>x</p><p>Input: n = 1</p><p>Output: 1</p>", "https://leetcode.com/problems/two-sum/", "text/html", "utf-8"
        with self.assertRaisesRegex(ValueError, "redirected to leetcode.com"):
            sheets.read_problem({"source": "https://example.org/p"}, site)


if __name__ == "__main__":
    unittest.main()
