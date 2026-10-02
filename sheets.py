"""Your own practice sheet: read a list of problems from a file, a link or recognised text,
match each row to a built-in lab, and validate the labs a learner builds for the rest.

Nothing here invents problem content. A row carries only what the sheet says (a title, a link,
a difficulty, a topic); statements, parameters and expected outputs come from the learner."""
import ast
import csv
import html.parser
import io
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

MAX_ROWS = 1000  # Large public sheets (Striver's A2Z has about 450 problems) must fit.
MAX_CASES = 8
MAX_FETCH = 3_000_000
AGENT = "VisualDSA-sheet-import/1.0"
JUDGES = ("leetcode.com", "geeksforgeeks.org", "naukri.com", "codingninjas.com", "hackerrank.com", "codeforces.com",
          "interviewbit.com", "spoj.com", "codechef.com", "takeuforward.org", "neetcode.io", "atcoder.jp", "cses.fi")
URL = re.compile(r"https?://[^\s<>\"'\])]+", re.I)

# Built-in labs and the sheet titles that name the same contract ("same") or a close relative whose
# details differ ("close": e.g. LeetCode's in-place or 1-indexed version). Matching is exact on
# normalised titles and link slugs; anything else stays unmatched for the learner to decide.
ALIASES = {
    "two-sum": (["two sum", "2 sum", "pair with given sum", "two sum problem"], []),
    "contains-duplicate": (["contains duplicate", "check for duplicates"], []),
    "pair-count": (["count matching pairs", "count pairs with given sum", "number of pairs with given sum"], []),
    "frequency-map": (["count frequencies", "frequency of array elements", "count frequency of each element", "frequencies of array elements"], []),
    "unique-values": (["keep unique values", "distinct elements"], []),
    "intersection": (["array intersection", "intersection of two arrays"], ["intersection of two arrays ii"]),
    "first-unique": (["first unique character", "first unique character in a string", "first non repeating character"], []),
    "valid-anagram": (["valid anagram", "check anagram", "anagram"], []),
    "palindrome": (["is it a palindrome", "palindrome string", "check palindrome"], ["valid palindrome", "palindrome"]),
    "reverse-string": (["reverse a string", "reverse string"], []),
    "move-zeroes": (["move zeroes", "move zeros", "move all zeroes to end", "move all zeros to end of array"], []),
    "remove-duplicates": (["remove sorted duplicates"], ["remove duplicates from sorted array", "remove duplicates"]),
    "sorted-squares": (["squares in sorted order", "squares of a sorted array", "sorted squares"], []),
    "merge-sorted": (["merge sorted arrays", "merge two sorted arrays"], ["merge sorted array"]),
    "two-sum-sorted": (["two sum sorted"], ["two sum ii input array is sorted", "two sum ii"]),
    "binary-search": (["binary search", "find in a sorted array"], []),
    "search-insert": (["search insert position"], []),
    "first-occurrence": (["first occurrence", "first occurrence in sorted array"], ["find first and last position of element in sorted array", "first and last occurrences of x", "first and last occurrence"]),
    "last-occurrence": (["last occurrence", "last occurrence in sorted array"], []),
    "max-window-sum": (["maximum window sum", "max sum subarray of size k", "maximum sum subarray of size k"], []),
    "average-window": (["maximum window average", "maximum average subarray i", "maximum average subarray"], []),
    "longest-unique": (["longest unique substring", "longest substring without repeating characters"], []),
    "best-profit": (["best time to buy and sell", "best time to buy and sell stock", "stock buy and sell"], []),
    "max-subarray": (["maximum subarray", "maximum subarray sum", "kadanes algorithm", "kadane algorithm", "largest sum contiguous subarray"], []),
}


def normal(text):
    text = str(text).lower().replace("&", " and ").replace("’", "'").replace("'", "")
    text = re.sub(r"^\s*(?:lc|leetcode|q|problem)?\s*#?\d+\s*[.):\-]\s*", "", text)  # "1. Two Sum", "LC 1 - Two Sum"
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


INDEX = {}
for lab, (same, close) in ALIASES.items():
    for name in same:
        INDEX[normal(name)] = (lab, "same")
    for name in close:
        INDEX.setdefault(normal(name), (lab, "close"))


def slug_of(url):
    """The problem slug of a judge link: leetcode.com/problems/two-sum → 'two sum'."""
    if not url:
        return ""
    parts = [p for p in urllib.parse.urlsplit(url).path.split("/") if p]
    for marker in ("problems", "problem", "challenges", "practice"):
        if marker in parts and parts.index(marker) + 1 < len(parts):
            slug = parts[parts.index(marker) + 1]
            return normal(re.sub(r"\d+$", "", slug.replace("-", " ").replace("_", " ")))  # GfG adds digits to slugs
    return ""


def match_row(title, url):
    """(lab id, 'same' | 'close') when a title or link names a built-in lab exactly, else (None, None)."""
    for key in (normal(title), slug_of(url)):
        if key and key in INDEX:
            return INDEX[key]
    return None, None


def title_from_url(url):
    slug = slug_of(url)
    if slug:
        return slug.title()
    parts = urllib.parse.urlsplit(url or "")
    tail = " ".join(p for p in parts.path.split("/") if p)[-60:]
    return f"{(parts.hostname or '').removeprefix('www.')} {tail}".strip() if parts.hostname else ""


# ----------------------------- reading a sheet -----------------------------
HEADERS = {
    "title": ("problem", "question", "title", "name", "task", "problems", "questions", "problem name", "question name"),
    "url": ("link", "url", "href", "problem link", "question link", "practice link", "leetcode", "gfg", "links", "problem url"),
    "difficulty": ("difficulty", "level", "diff"),
    "topic": ("topic", "category", "pattern", "tag", "tags", "section", "concept", "step", "type"),
}
# takeUforward grades its sheets basic / core / pro.
DIFFICULTY = {"easy": "Easy", "e": "Easy", "basic": "Easy", "school": "Easy", "beginner": "Easy", "core": "Medium", "pro": "Hard",
              "medium": "Medium", "m": "Medium", "med": "Medium", "hard": "Hard", "h": "Hard", "difficult": "Hard"}
NOISE = re.compile(r"^(?:true|false|yes|no|done|todo|pending|solved|unsolved|revision|revise|[✓✔✗✘x☐☑✅❌\-–—*•#.]+|\d+(?:\.\d+)?)$", re.I)


def clean_title(text):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    text = re.sub(r"^(?:(?:[-*•▪◦·>]|\[[ xX✓]?\]|[☐☑✅✓✔❌]|\d{1,4}\s*[.)\]:]|[qQ]\d+[.):])\s*)+", "", text)
    return text.strip(" -–—|:\t")[:160]


def difficulty_of(text):
    return DIFFICULTY.get(str(text or "").strip().lower(), "")


def column_roles(header):
    roles = {}
    for i, cell in enumerate(header):
        key = normal(cell)
        for role, names in HEADERS.items():
            if role not in roles and (key in names or any(key.startswith(n + " ") for n in names)):
                roles[role] = i
                break
    return roles if "title" in roles or "url" in roles else {}


def is_header(texts):
    """A header row names columns: short cells, no links, and at least two roles or one exact column name."""
    roles = column_roles(texts)
    if not roles or any(URL.search(t) or len(t) > 40 for t in texts):
        return False
    return len(roles) >= 2 or any(normal(t) in HEADERS[role] for role in roles for t in [texts[roles[role]]])


def rows_from_table(table, default_topic=""):
    """Rows of cells (with optional hyperlinks) → sheet rows. A header row assigns roles; without
    one, the first text cell is the title and any link cell the link. A text-only row in a sheet of
    links is a section heading and becomes the topic of the rows below it."""
    table = [[(str(c[0]).strip() if c[0] is not None else "", c[1]) for c in row] for row in table]
    table = [row for row in table if any(text or link for text, link in row)]
    if not table:
        return []
    header_at = next((i for i, row in enumerate(table[:8]) if is_header([text for text, _ in row])), None)
    roles = column_roles([text for text, _ in table[header_at]]) if header_at is not None else {}
    body = table[header_at + 1:] if header_at is not None else table
    linked = sum(1 for row in body if any(link or URL.search(text) for text, link in row))
    rows, topic = [], default_topic
    for row in body:
        texts = [text for text, _ in row]
        link = next((link for _, link in row if link), "") or next((URL.search(t).group(0) for t in texts if URL.search(t)), "")
        if roles:
            pick = lambda role: texts[roles[role]] if role in roles and roles[role] < len(texts) else ""
            title = clean_title(pick("title")) if "title" in roles else ""
            if "url" in roles and URL.search(pick("url") or ""):
                link = URL.search(pick("url")).group(0)
            elif "url" in roles and roles["url"] < len(row) and row[roles["url"]][1]:
                link = row[roles["url"]][1]
            if "title" in roles and roles["title"] < len(row) and row[roles["title"]][1]:
                link = link or row[roles["title"]][1]
            level, row_topic = difficulty_of(pick("difficulty")), clean_title(pick("topic"))
        else:
            title = next((clean_title(t) for t in texts if t and not URL.fullmatch(t) and not NOISE.match(t.strip()) and not difficulty_of(t) and len(clean_title(t)) > 1), "")
            level, row_topic = next((difficulty_of(t) for t in texts if difficulty_of(t)), ""), ""
        title = title if title and not NOISE.match(title) else ""
        if not link and title and linked >= max(2, len(body) // 3) and sum(1 for t in texts if t) == 1:
            topic = title  # A heading row inside a sheet of links.
            continue
        title = title or title_from_url(link)
        if title:
            rows.append(dict(title=title, url=link[:500], difficulty=level, topic=(row_topic or topic)[:80]))
    return rows


STATUS_TAIL = re.compile(r"(?:\s+(?:done|todo|to do|solved|unsolved|pending|revise|revision|yes|no|true|false|[✓✔✗✘☐☑✅❌xX]|\d{1,2}/\d{1,2}(?:/\d{2,4})?))+\s*$", re.I)
HEADER_WORDS = {"s", "no", "sno", "sr", "problem", "problems", "question", "questions", "title", "name", "link", "links", "url", "difficulty", "level",
                "topic", "topics", "status", "done", "practice", "solution", "notes", "category", "pattern", "tags", "day", "date", "revision"}


def ocr_line(raw):
    """Text recognised from a photo of a table: drop serial numbers, status columns and a header row."""
    if set(normal(raw).split()) <= HEADER_WORDS:
        return ""
    raw = re.sub(r"^\s*\d{1,4}\s*[.)|:]?\s+(?=\S*[A-Za-z])", "", raw)
    level = re.search(r"\b(easy|medium|hard)\b", raw, re.I)
    if level:  # The difficulty column ends the useful part of a row; status and notes follow it.
        raw = raw[:level.start()].rstrip(" |") + " - " + level.group(1)
    return STATUS_TAIL.sub("", raw.replace("|", " ")).strip()


def read_photo_text(text):
    """(rows, title) from text recognised in a picture: a line above the table's header row is the
    sheet's title rather than a problem."""
    lines = [line for line in text.replace("\r", "\n").split("\n") if line.strip()]
    header = next((i for i, line in enumerate(lines[:12]) if not ocr_line(line.strip()) and len(normal(line).split()) >= 2), None)
    title = clean_title(lines[0]) if header else ""
    return rows_from_text("\n".join(lines[header + 1:] if header is not None else lines), ocr=True), title[:80]


def rows_from_text(text, ocr=False):
    """Lines of a list, a markdown document, or text recognised from an image."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if sum(1 for line in lines if line.strip().startswith("|")) >= 3:  # A markdown table.
        table = [[(cell.strip(), "") for cell in line.strip().strip("|").split("|")] for line in lines if line.strip().startswith("|") and not re.fullmatch(r"[\s|:\-]+", line)]
        for row in table:
            for i, (cell, _) in enumerate(row):
                found = re.search(r"\[([^\]]+)\]\((https?://[^)]+)\)", cell)
                if found:
                    row[i] = (found.group(1), found.group(2))
        return rows_from_table(table)
    rows, topic = [], ""
    for line in lines:
        raw = ocr_line(line.strip()) if ocr else line.strip()
        if not raw:
            continue
        if re.match(r"^\[[^\]]+\]:\s*\S+", raw) or raw.startswith(("```", "<!--", "![")):
            continue  # Markdown link definitions, code fences, comments and images.
        heading = re.match(r"^(?:#{1,6}\s+(.+)|(.{2,60}):\s*$)", raw)
        if heading and not URL.search(raw):
            topic = clean_title(heading.group(1) or heading.group(2))
            continue
        link = ""
        found = re.search(r"\[([^\]]+)\]\((https?://[^)]+)\)", raw)
        if found:
            raw, link = raw.replace(found.group(0), found.group(1)), found.group(2)
        elif URL.search(raw):
            link = URL.search(raw).group(0)
            raw = raw.replace(link, " ")
        level = ""
        tag = re.search(r"[\s(\[|,–-]+(easy|medium|hard)[\s)\]|,]*$", raw, re.I)
        if tag:
            level, raw = DIFFICULTY[tag.group(1).lower()], raw[:tag.start()]
        title = clean_title(raw)
        if (not title or NOISE.match(title) or len(title) < 3) and link:
            title = title_from_url(link)
        words = len(title.split())
        prose = not link and (words > 14 or (words > 7 and title.endswith((".", ",", ";"))))  # A sentence, not a problem name.
        if title and not prose and not NOISE.match(title) and len(title) >= 3 and re.search(r"[A-Za-z]{2}", title):
            rows.append(dict(title=title, url=link[:500], difficulty=level, topic=topic[:80]))
    return rows


def rows_from_json(data):
    items = data.get("problems") or data.get("rows") or data.get("questions") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("A JSON sheet is a list of problems, or an object with a \"problems\" list.")
    rows = []
    for item in items:
        if isinstance(item, str):
            rows.extend(rows_from_text(item))
        elif isinstance(item, dict):
            lower = {normal(k): v for k, v in item.items()}
            title = next((lower[k] for k in HEADERS["title"] if isinstance(lower.get(k), str)), "")
            link = next((lower[k] for k in HEADERS["url"] if isinstance(lower.get(k), str) and URL.match(lower[k])), "")
            level = next((difficulty_of(lower[k]) for k in HEADERS["difficulty"] if isinstance(lower.get(k), str)), "")
            topic = next((lower[k] for k in HEADERS["topic"] if isinstance(lower.get(k), str)), "")
            title = clean_title(title) or title_from_url(link)
            if title:
                rows.append(dict(title=title, url=link[:500], difficulty=level, topic=clean_title(topic)[:80]))
    return rows


def rows_from_xlsx(blob):
    try:
        import openpyxl
    except ImportError:
        raise ValueError("Reading Excel files needs openpyxl (pip install openpyxl). You can also save the sheet as CSV and upload that.")
    try:
        book = openpyxl.load_workbook(io.BytesIO(blob), data_only=True)
    except Exception:
        raise ValueError("This Excel file could not be read. Save it as .xlsx or CSV and try again.")
    rows = []
    for sheet in book.worksheets:  # Many sheets keep one tab per topic: the tab name is the topic.
        table = [[(cell.value, cell.hyperlink.target if cell.hyperlink and cell.hyperlink.target else "") for cell in row] for row in sheet.iter_rows(max_row=2000, max_col=30)]
        topic = "" if len(book.worksheets) == 1 or re.fullmatch(r"sheet\s*\d*", sheet.title, re.I) else sheet.title
        rows.extend(rows_from_table(table, topic))
    return rows


def rows_from_csv(text):
    sample = text[:5000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel_tab if sample.count("\t") > sample.count(",") else csv.excel
    table = [[(cell, "") for cell in row] for row in csv.reader(io.StringIO(text), dialect)]
    if max((len(row) for row in table), default=0) <= 1:
        return rows_from_text(text)
    for row in table:
        for i, (cell, _) in enumerate(row):
            formula = re.match(r'=HYPERLINK\("([^"]+)"\s*[,;]\s*"([^"]*)"\)', cell, re.I)
            if formula:
                row[i] = (formula.group(2), formula.group(1))
    return rows_from_table(table)


class PageLinks(html.parser.HTMLParser):
    """Tables, headings and links of a web page, as plain data."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.links, self.title = [], [], ""
        self._table = self._row = self._cell = None
        self._href, self._text, self._heading, self._heading_text, self._in_title, self._skip = None, [], "", "", False, 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        elif tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = [[], ""]
        elif tag == "a":
            self._href, self._text = attrs.get("href") or "", []
        elif tag in ("h1", "h2", "h3", "h4"):
            self._heading = tag
            self._text = []
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip = max(0, self._skip - 1)
        elif tag == "a" and self._href is not None:
            text = clean_title(" ".join(self._text))
            if self._href.startswith("http"):
                self.links.append((text, self._href, self._heading_text))
                if self._cell is not None and not self._cell[1]:
                    self._cell[1] = self._href
            self._href = None
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append((" ".join(" ".join(self._cell[0]).split()), self._cell[1]))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None
        elif tag == self._heading:
            self._heading_text, self._heading = clean_title(" ".join(self._text)), ""
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        if self._cell is not None:
            self._cell[0].append(data)
        if self._href is not None or self._heading:
            self._text.append(data)


# ----------------------------- data a page embeds -----------------------------
# Many sheet sites render their list in the browser from data embedded in the page: Next.js page
# data, React server-component payloads, or JSON script tags. That data is read as plain JSON.
TITLE_KEYS = {"title", "label", "name", "problem", "question", "problem name", "problemname", "problem title", "problemtitle",
              "question name", "questionname", "question title", "questiontitle", "display name", "displayname"}
CHILD_KEYS = {"children", "items", "problems", "questions", "subsections", "sections", "topics", "steps", "lectures", "subtopics",
              "modules", "chapters", "categories", "entries", "nodes", "list"}
KIND_KEYS = {"type", "layouttype", "kind", "contenttype", "itemtype", "item type", "content type", "category type"}
NOT_PROBLEMS = {"learning", "article", "lesson", "video", "contest", "blog", "theory", "note", "notes", "quiz", "editorial", "reading", "course", "mcq"}
PROBLEM_KINDS = {"practice", "problem", "question", "exercise", "challenge", "coding"}


def embedded_json(page):
    """JSON values a page embeds for its own scripts."""
    values = []
    for body in re.findall(r"<script[^>]*type=[\"']application/(?:ld\+)?json[\"'][^>]*>(.*?)</script>", page, re.S | re.I):
        try:
            values.append(json.loads(body))
        except ValueError:
            pass
    pushes = re.findall(r'self\.__next_f\.push\(\[\d+,("(?:[^"\\]|\\.)*")\]\)', page)
    try:
        flight = "".join(json.loads(chunk) for chunk in pushes)
    except ValueError:
        flight = ""
    for line in flight.split("\n"):  # Server-component payload: one "id:JSON" record per line.
        found = re.match(r"[0-9a-f]+:([\[{].*)", line, re.S)
        if found:
            try:
                values.append(json.loads(found.group(1)))
            except ValueError:
                pass
    return values


def expand_columns(value, depth=0):
    """Expand schema-indexed tables ({"fields": [[names…]…], "rows": [[schema, values…]…], "roots": […]})
    into ordinary objects, resolving child row indices into nested objects."""
    if depth > 80:
        return None
    if isinstance(value, list):
        return [expand_columns(v, depth + 1) for v in value]
    if not isinstance(value, dict):
        return value
    schemas, rows = value.get("fields", value.get("columns")), value.get("rows")
    if (isinstance(schemas, list) and schemas and all(isinstance(f, list) and all(isinstance(k, str) for k in f) for f in schemas)
            and isinstance(rows, list) and rows and all(isinstance(r, list) and r and type(r[0]) is int and 0 <= r[0] < len(schemas) for r in rows)):
        def build(index, level=0):
            row = rows[index]
            item = dict(zip(schemas[row[0]], row[1:]))
            for key, child in item.items():
                if normal(key) in CHILD_KEYS and isinstance(child, list) and all(type(c) is int and 0 <= c < len(rows) for c in child):
                    item[key] = [build(c, level + 1) for c in child] if level < 12 else []
            return item
        roots = value.get("roots")
        if isinstance(roots, list) and roots and all(type(r) is int and 0 <= r < len(rows) for r in roots):
            return [build(r) for r in roots]
        return [build(i) for i in range(len(rows))]
    return {k: expand_columns(v, depth + 1) for k, v in value.items()}


def is_judge(url):
    host = urllib.parse.urlsplit(url).hostname or ""
    return any(host == j or host.endswith("." + j) for j in JUDGES)


def site_page(node, base):
    """The problem's own page on the sheet's site, when the site's data names it. takeUforward's rows carry
    redirectTo {layoutType, contentType, itemSlug}; its scripts route that to /{layoutType}/{contentType}/{itemSlug}."""
    host = urllib.parse.urlsplit(base).hostname or ""
    target = node.get("redirectTo")
    if (host != "takeuforward.org" and not host.endswith(".takeuforward.org")) or not isinstance(target, dict):
        return ""
    layout, content, slug = target.get("layoutType"), target.get("contentType") or "dsa", target.get("itemSlug")
    if layout != "practice" or not isinstance(content, str) or not re.fullmatch(r"[a-z-]{1,30}", content) or not isinstance(slug, str) or not slug.strip():
        return ""
    quoted = urllib.parse.quote(slug.strip(), safe="'()*!~")  # As the site's encodeURIComponent writes it.
    return f"https://takeuforward.org/{layout}/{content}/{quoted}"[:500]


def json_rows(values, base=""):
    """Problems inside embedded data: an object with a title and evidence of being a problem (a link to a
    coding judge, a difficulty, or a practice kind). Objects with a title and a list of children are
    sections; their titles become the topic. Lessons, articles and contests are skipped."""
    rows = []

    def title_of(node):
        for key, value in node.items():
            if normal(key) in TITLE_KEYS and isinstance(value, str) and 2 <= len(value.strip()) <= 160 and not URL.match(value.strip()):
                return clean_title(value)
        return ""

    def links_of(node):
        found = []
        for key, value in node.items():
            if isinstance(value, str) and URL.fullmatch(value.strip()):
                found.append(value.strip())
            elif isinstance(value, dict):
                found.extend(v.strip() for v in value.values() if isinstance(v, str) and URL.fullmatch(v.strip()))
        return found

    def visit(node, trail, depth):
        if depth > 80:
            return
        if isinstance(node, list):
            for item in node:
                visit(item, trail, depth + 1)
            return
        if not isinstance(node, dict):
            return
        title = title_of(node)
        children = [v for k, v in node.items() if normal(k) in CHILD_KEYS and isinstance(v, list) and any(isinstance(c, dict) for c in v)]
        if title and children:
            for child in children:
                visit(child, trail + [title], depth + 1)
            return
        kinds = {normal(v) for k, v in node.items() if normal(k) in KIND_KEYS and isinstance(v, str)}
        links = links_of(node)
        judge = next((u for u in links if is_judge(u) and slug_of(u)), "")
        level = next((difficulty_of(v) for k, v in node.items() if normal(k) in HEADERS["difficulty"] and isinstance(v, str) and difficulty_of(v)), "")
        if title and not kinds & NOT_PROBLEMS and (judge or level or kinds & PROBLEM_KINDS):
            source = site_page(node, base)
            url = judge or next((u for u in links if is_judge(u)), "") or source
            rows.append(dict(title=title, url=url[:500], source=source, difficulty=level, topic=" · ".join(trail[-2:])[:80]))
            return
        for value in node.values():
            if isinstance(value, (dict, list)):
                visit(value, trail, depth + 1)

    for value in values:
        visit(expand_columns(value), [], 0)
    return rows


def rows_from_html(text, base=""):
    page = PageLinks()
    page.feed(text)
    rows = []
    for table in page.tables:
        if sum(1 for row in table if any(link for _, link in row)) >= 3:
            rows.extend(rows_from_table(table))
    embedded = json_rows(embedded_json(text), base)
    if len(embedded) >= 3 and len(embedded) > len(rows):  # The page's own data is the fuller list.
        rows = embedded
    if not rows:  # No table of links: take links to coding judges, in page order.
        seen = set()
        for text, href, heading in page.links:
            if is_judge(href) and slug_of(href) and href not in seen:
                seen.add(href)
                rows.append(dict(title=text if len(text) >= 3 and not NOISE.match(text) else title_from_url(href), url=href[:500], difficulty="", topic=heading[:80]))
    return rows, clean_title(re.split(r"\s+[|–—-]\s+", page.title.strip())[0])[:80]


def read_upload(filename, blob):
    """(rows, name) from an uploaded file's bytes."""
    name = re.sub(r"\.[A-Za-z0-9]+$", "", filename or "My sheet")[:80] or "My sheet"
    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    if ext in ("xlsx", "xlsm"):
        return rows_from_xlsx(blob), name
    if ext == "xls":
        raise ValueError("Old .xls files can't be read. Save the sheet as .xlsx or CSV and upload that.")
    if ext in ("png", "jpg", "jpeg", "webp", "gif", "bmp", "pdf"):
        raise ValueError("Use the Image option for a photo or screenshot of your sheet.")
    text = blob.decode("utf-8-sig", errors="replace")
    if ext == "json":
        try:
            return rows_from_json(json.loads(text)), name
        except json.JSONDecodeError:
            raise ValueError("This JSON file could not be read.")
    if ext in ("html", "htm"):
        return rows_from_html(text)[0], name
    if ext in ("csv", "tsv"):
        return rows_from_csv(text), name
    return rows_from_text(text), name


# ----------------------------- reading a link -----------------------------
def sheet_export_url(url):
    """A Google Sheets link → its CSV export for the same tab."""
    parts = urllib.parse.urlsplit(url)
    found = re.match(r"/spreadsheets/d/(?:e/)?([A-Za-z0-9_-]+)", parts.path)
    if parts.hostname != "docs.google.com" or not found:
        return None
    gid = re.search(r"gid=(\d+)", parts.fragment + "&" + parts.query)
    if "/d/e/" in parts.path:  # A "Publish to the web" link.
        return f"https://docs.google.com/spreadsheets/d/e/{found.group(1)}/pub?output=csv" + (f"&gid={gid.group(1)}" if gid else "")
    return f"https://docs.google.com/spreadsheets/d/{found.group(1)}/export?format=csv" + (f"&gid={gid.group(1)}" if gid else "")


def public_host(host):
    """Only public internet addresses: a sheet link must never reach this machine or its network."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ValueError(f"Couldn't find {host}. Check the link and your connection.")
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if not address.is_global:
            raise ValueError("Links to private or local addresses can't be imported.")


class CheckedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urllib.parse.urlsplit(newurl)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("The link redirected somewhere that can't be imported.")
        public_host(parts.hostname)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    """(body bytes, final URL, content type, charset), refusing private addresses and large or slow responses."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Paste a full link that starts with https://")
    public_host(parts.hostname)
    opener = urllib.request.build_opener(CheckedRedirects)
    request = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "text/csv,text/html,text/plain,application/json;q=0.9,*/*;q=0.5"})
    try:
        with opener.open(request, timeout=10) as response:
            body = response.read(MAX_FETCH + 1)
            final, kind = response.geturl(), response.headers.get_content_type()
            charset = response.headers.get_content_charset() or "utf-8"
    except ValueError:
        raise
    except urllib.error.HTTPError as error:
        if error.code in (404, 410):
            raise ValueError(f"That page wasn't found ({error.code}). Check the link.")
        if error.code in (401, 403):
            raise ValueError(f"The site refused to share that page ({error.code}). If the sheet is private, share it publicly, or download it and upload the file.")
        raise ValueError(f"The site answered with an error ({error.code}). Try again later, or download the sheet and upload the file.")
    except Exception:
        raise ValueError("The link couldn't be reached. Check it, or download the sheet and upload the file instead.")
    if len(body) > MAX_FETCH:
        raise ValueError("That page is larger than 3 MB. Download the sheet and upload the file instead.")
    return body, final, kind, charset


def read_link(url, fetcher=fetch):
    """(rows, name) for a sheet link: Google Sheets, a CSV/JSON/text file, or a web page that lists problems."""
    url = url.strip()
    export = sheet_export_url(url)
    given = urllib.parse.urlsplit(url).hostname or ""
    if not export and slug_of(url) and any(given == j or given.endswith("." + j) for j in JUDGES):
        # A single problem's page: the link itself is the row, so there is nothing to fetch.
        return [dict(title=title_from_url(url), url=url[:500], difficulty="", topic="")], "My sheet"
    body, final, kind, charset = fetcher(export or url)
    host = urllib.parse.urlsplit(final).hostname or ""
    if export and (host == "accounts.google.com" or kind == "text/html"):
        raise ValueError("This Google Sheet isn't public. In Google Sheets choose Share → General access → Anyone with the link, then paste the link again. Or use File → Download → CSV and upload the file.")
    text = body.decode(charset, errors="replace")
    path = urllib.parse.urlsplit(final).path.lower()
    name = urllib.parse.unquote(path.rstrip("/").rsplit("/", 1)[-1] or host)[:80]
    if export or kind in ("text/csv", "text/tab-separated-values") or path.endswith((".csv", ".tsv")):
        return rows_from_csv(text), "My Google Sheet" if export else re.sub(r"\.[a-z]+$", "", name)
    if kind == "application/json" or path.endswith(".json"):
        try:
            return rows_from_json(json.loads(text)), re.sub(r"\.[a-z]+$", "", name)
        except json.JSONDecodeError:
            raise ValueError("The link returned JSON that couldn't be read.")
    if kind == "text/html":
        rows, title = rows_from_html(text, final)
        if not rows:
            raise ValueError("No problem list was found on that page. Some sites load their list only after the page opens in a browser: take a screenshot of the list (or download it as a file) and import that instead.")
        return rows, title or host
    return rows_from_text(text), re.sub(r"\.[a-z]+$", "", name) or host


def finish(rows):
    """De-duplicate, cap and match rows to built-in labs."""
    seen, result = set(), []
    for row in rows:
        key = (normal(row["title"]), row.get("url", ""))
        if key in seen:
            continue
        seen.add(key)
        lab, fit = match_row(row["title"], row.get("url", ""))
        result.append(dict(title=row["title"][:160], url=row.get("url", "")[:500], source=row.get("source", "")[:500], difficulty=row.get("difficulty", ""), topic=row.get("topic", "")[:80], match=lab, fit=fit, lab=None))
        if len(result) >= MAX_ROWS:
            break
    return result


def clean_rows(rows, known_labs):
    """Rows sent back by the learner after review: plain fields only; matches are re-derived or
    must name a real built-in lab when chosen by hand."""
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError(f"A sheet has between 1 and {MAX_ROWS} problems.")
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("title"), str) or not clean_title(row["title"]):
            raise ValueError("Every problem needs a title.")
        url = row.get("url") or ""
        if not isinstance(url, str) or (url and not re.match(r"https?://", url)):
            raise ValueError(f"“{row['title'][:40]}” has a link that doesn't start with http(s)://.")
        chosen = row.get("match")
        if chosen is not None and chosen not in known_labs:
            raise ValueError("Choose a lab from the library.")
        lab, fit = match_row(row["title"], url)
        fit = fit if chosen == lab and chosen else "manual" if chosen else None
        lab_id = row.get("lab") if isinstance(row.get("lab"), str) and re.fullmatch(r"custom-[0-9a-f]{12}", row.get("lab") or "") else None
        source = row.get("source") if isinstance(row.get("source"), str) and re.match(r"https?://", row.get("source") or "") else ""
        result.append(dict(title=clean_title(row["title"]), url=url[:500], source=source[:500], difficulty=difficulty_of(row.get("difficulty")) or "",
                           topic=clean_title(row.get("topic") or "")[:80], match=chosen, fit=fit, lab=lab_id))
    return result


# ----------------------------- the learner's own lab -----------------------------
def literal(text):
    """A plain value written as JSON or Python: [2, 7], "abc", 'abc', True, null, (1, 2)."""
    text = text.strip()
    if not text:
        raise ValueError("Write a value, e.g. [2, 7, 11] or \"abc\" or 9.")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        try:
            value = ast.literal_eval(re.sub(r"\btrue\b", "True", re.sub(r"\bfalse\b", "False", re.sub(r"\bnull\b", "None", text))))
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            raise ValueError(f"“{text[:40]}” isn't a value. Use a number, \"text\", a [list], True/False or None.")
    return plain(value)


def plain(value, depth=0):
    """Plain data the tracer can show: numbers, text, booleans, None, lists and string-keyed dicts."""
    if depth > 3:
        raise ValueError("Values may nest at most three levels deep.")
    if isinstance(value, tuple):
        value = list(value)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if abs(value) > 10 ** 9:
            raise ValueError("Use numbers between -1,000,000,000 and 1,000,000,000.")
        return value
    if isinstance(value, float):
        if value != value or abs(value) > 1e9:
            raise ValueError("Use finite numbers up to 1,000,000,000.")
        return value
    if isinstance(value, str):
        if len(value) > 200:
            raise ValueError("Use at most 200 characters per string.")
        return value
    if isinstance(value, list):
        if len(value) > 200:
            raise ValueError("Use at most 200 items per list.")
        return [plain(v, depth + 1) for v in value]
    if isinstance(value, dict):
        if len(value) > 100 or any(not isinstance(k, str) for k in value):
            raise ValueError("Dictionaries may have at most 100 string keys.")
        return {k: plain(v, depth + 1) for k, v in value.items()}
    raise ValueError("Use numbers, text, True/False, None, lists or dictionaries.")


def split_top(text, sep=","):
    """Split on separators outside brackets and quotes."""
    parts, depth, quote, start = [], 0, None, 0
    for i, ch in enumerate(text):
        if quote:
            if ch == quote and text[i - 1] != "\\":
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def assignments(given):
    """An example's input ("nums = [2, 7], target = 9") → parameter names and values. Judges' notations are
    read as written: GfG's "arr[] = {1, 2}" is the list arr = [1, 2]."""
    given = " ".join(given.split())
    pairs = [part.strip() for part in split_top(given) if part.strip()]
    if not pairs or not all(re.match(r"^[A-Za-z_]\w*\s*(?:\[\s*\])?\s*=", part) for part in pairs):
        return ["value"], [literal(braced(given))]
    names, values = [], []
    for part in pairs:
        name, value = part.split("=", 1)
        names.append(re.sub(r"\s*\[\s*\]$", "", name.strip()))
        values.append(literal(braced(value)))
    return names, values


def braced(value):
    """{1, 2, 3} in a C-style example is a list, not a set (a dictionary keeps its braces)."""
    value = value.strip()
    if value.startswith("{") and value.endswith("}") and ":" not in value:
        return "[" + value[1:-1] + "]"
    return value


def parse_examples(text):
    """Examples as judges print them ("Input: nums = [2,7], target = 9 / Output: [0,1]") → parameter
    names and cases. Only what the text states is read; nothing is completed or guessed."""
    if not isinstance(text, str) or len(text) > 20000:
        raise ValueError("Paste up to 20,000 characters of examples.")
    blocks = re.findall(r"Input\s*[:：]\s*(.+?)\s*(?:\n\s*)?Output\s*[:：]\s*(.+?)(?=\n|$|\s+Explanation\s*:)", text, re.I | re.S)
    if not blocks:
        raise ValueError("No “Input: … Output: …” pairs were found. Paste examples in that form, or add cases by hand.")
    params, cases = None, []
    for number, (given, output) in enumerate(blocks[:MAX_CASES], 1):
        names, values = assignments(given)
        if params is None:
            params = names
        elif names != params:
            raise ValueError(f"Example {number} names different parameters ({', '.join(names)}) than example 1 ({', '.join(params)}).")
        cases.append(dict(name=f"Example {number}", args=values, expected=literal(" ".join(output.split()))))
    return dict(params=params, cases=cases)


class PageBlocks(html.parser.HTMLParser):
    """A page as text blocks (headings, paragraphs, list items, preformatted text), skipping scripts,
    controls, forms and navigation."""
    BLOCKS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "dt", "dd", "blockquote"}
    SKIP = {"script", "style", "noscript", "svg", "button", "nav", "footer", "select", "option", "label", "textarea", "form", "template", "iframe", "math"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self._open, self._skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "br" and self._open and not self._skip:
            self._open[-1][1].append("\n")
        elif tag == "sup" and self._open and not self._skip:
            self._open[-1][1].append("^")  # 10<sup>5</sup> is 10^5, not 105.
        elif tag in self.BLOCKS and not self._skip:
            self._open.append((tag, []))

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and self._open and not self._skip:
            self._open[-1][1].append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCKS and not self._skip and any(t == tag for t, _ in self._open):
            while self._open:
                name, parts = self._open.pop()
                text = "".join(parts)
                text = "\n".join(" ".join(line.split()) for line in text.split("\n")).strip() if name == "pre" or "\n" in text else " ".join(text.split())
                if text:
                    self.blocks.append((name, text))
                if name == tag:
                    break

    def handle_data(self, data):
        if self._open and not self._skip:
            self._open[-1][1].append(data)


EXAMPLE_HEAD = re.compile(r"^example\s*\d*\s*:?$", re.I)
SECTION_HEAD = re.compile(r"^(examples?|constraints?|notes?|input format|output format|expected\b.*|your task|hints?|follow[- ]?up|approach|solution|editorial)\s*\d*\s*:?$", re.I)


def example_case(lines, number):
    """One example's lines → (case, note). The input is read as written; an output that isn't a value
    (a printed pattern, prose) is left for the learner, never guessed."""
    text = "\n".join(lines)
    given = re.search(r"input\s*[:：]\s*(.*?)(?=\n\s*output\s*[:：]|\Z)", text, re.I | re.S)
    if not given:
        return None, f"Example {number} has no input to read."
    try:
        names, values = assignments(given.group(1))
    except ValueError:
        return None, f"Example {number}'s input “{' '.join(given.group(1).split())[:50]}” couldn't be read as values."
    shown = re.search(r"output\s*[:：][ \t]*([^\n]*)", text, re.I)
    output = re.split(r"\s+explanation\s*[:：]", shown.group(1).strip(), flags=re.I)[0].strip() if shown else ""
    expected, note = None, ""
    if not output:
        note = f"Example {number}: the page shows no output value. Write the expected output yourself."
    else:
        try:
            expected = literal(output)
        except ValueError:
            note = f"Example {number}: its output “{output[:40]}” isn't a value. Write the expected output yourself."
    return dict(name=f"Example {number}", params=names, args=values, expected=expected, missing=bool(note)), note


STATEMENT_KEYS = {"problem question", "problemquestion", "problem statement", "problemstatement", "statement", "description", "content", "question", "body", "question content", "questioncontent"}


def embedded_problem(page):
    """A problem a page keeps in its embedded data rather than its markup (GeeksforGeeks' Next.js page data:
    problem_name plus problem_question as HTML), rebuilt as a small page to read the same way."""
    best = None

    def visit(node, depth=0):
        nonlocal best
        if depth > 60 or best:
            return
        if isinstance(node, list):
            for item in node:
                visit(item, depth + 1)
        elif isinstance(node, dict):
            title = next((v for k, v in node.items() if normal(k) in TITLE_KEYS and isinstance(v, str) and 2 <= len(v.strip()) <= 160), "")
            body = next((v for k, v in node.items() if normal(k) in STATEMENT_KEYS and isinstance(v, str) and len(v) > 60 and re.search(r"<(p|div|pre|span|strong)\b", v)), "")
            if title and body:
                best = f"<h1>{html.escape(title)}</h1>{body}"
                return
            for value in node.values():
                visit(value, depth + 1)

    for value in embedded_json(page):
        visit(value)
    return best


def problem_from_page(page, url=""):
    """A problem page → its title, statement, constraints and example cases, as the page states them.
    The statement runs from the page's main heading to its first example; any section other than
    examples and constraints (hints, quizzes, editorials, comments) is not read."""
    try:
        return problem_from_blocks(page, url)
    except ValueError:
        stored = embedded_problem(page)
        if not stored:
            raise
        return problem_from_blocks(stored, url)


def problem_from_blocks(page, url):
    reader = PageBlocks()
    reader.feed(page)
    blocks = reader.blocks
    start = next((i for i, (tag, _) in enumerate(blocks) if tag == "h1"), None)
    if start is None:
        raise ValueError("No problem was found on that page.")
    title = clean_title(blocks[start][1])
    statement, examples, constraints, mode = [], [], [], "statement"
    starts_input = lambda text: re.match(r"input\s*[:：]", text, re.I)
    for tag, line in blocks[start + 1:]:
        first, _, rest = line.partition("\n")
        # A short paragraph acts as a heading only when it names a section; "…print the pattern:" is statement text.
        heading = tag in {"h2", "h3", "h4", "h5", "h6"} or bool(EXAMPLE_HEAD.match(line)) or (
            tag in {"p", "dt"} and len(line) <= 40 and line.endswith(":") and bool(SECTION_HEAD.match(line)))
        if heading and re.match(r"examples?\b", line, re.I):
            examples.append([])
            mode = "example"
        elif heading and re.match(r"constraints?\b", line, re.I):
            mode = "constraints"
        elif re.fullmatch(r"constraints?\s*:?", first.strip(), re.I) and rest.strip():
            mode = "constraints"  # "Constraints:" and its lines in one block.
            constraints.extend(c.strip() for c in rest.split("\n") if c.strip())
        elif heading:
            if statement or examples:
                mode = "other"  # Hints, quizzes, editorials and comments are not part of the problem.
        elif mode == "statement" and starts_input(line):
            examples.append([line])  # Examples written without a heading.
            mode = "example"
        elif mode == "statement":
            statement.append(("- " if tag == "li" else "") + line)
        elif mode == "example":
            if not examples:
                examples.append([])
            if starts_input(line) and any(starts_input(seen) for seen in examples[-1]):
                examples.append([])  # Several examples under one "Examples" heading.
            examples[-1].append(line)
        elif mode == "constraints":
            constraints.append(line)
    if not statement and not examples:
        raise ValueError("No problem statement was found on that page.")
    params, cases, notes = None, [], []
    for number, lines in enumerate(examples[:MAX_CASES], 1):
        case, note = example_case(lines, number)
        if note:
            notes.append(note)
        if not case:
            continue
        if params is None:
            params = case["params"]
        elif case["params"] != params:
            notes.append(f"Example {number} names different parameters than example 1, so it was left out.")
            continue
        cases.append(dict(name=case["name"], args=case["args"], expected=case["expected"], missing=case["missing"]))
    text = "\n".join(statement)
    if constraints:
        text += "\n\nConstraints:\n" + "\n".join("- " + re.sub(r"^(?:[-•*]\s+)", "", c) for c in constraints)
    if not cases:
        notes.append("No example could be read as cases. Add cases by hand.")
    elif any(case["missing"] for case in cases) and re.search(r"\bprint", text, re.I):
        notes.append("This problem prints its answer, but a lab checks what solve returns: return the printed lines "
                     "(for example a list of strings) and write that list as each expected output.")
    return dict(title=title, statement=text[:6000], params=params or [], cases=cases, notes=notes, source=url)


ROBOTS = {}


def allowed(url, fetcher):
    """Respect the site's robots.txt for this page (cached per site). No robots.txt allows everything."""
    parts = urllib.parse.urlsplit(url)
    root = f"{parts.scheme}://{parts.netloc}"
    rules = ROBOTS.get(root)
    if rules is None:
        rules = urllib.robotparser.RobotFileParser()
        try:
            body, _, _, charset = fetcher(root + "/robots.txt")
            rules.parse(body.decode(charset, errors="replace").splitlines())
        except ValueError:
            rules.parse([])
        ROBOTS[root] = rules
        while len(ROBOTS) > 64:
            ROBOTS.pop(next(iter(ROBOTS)))
    return rules.can_fetch(AGENT, url)


def read_problem(row, fetcher=None):
    """Read one sheet row's problem from its own page, on request. Nothing is completed or guessed."""
    fetcher = fetcher or fetch
    target = (row.get("source") or row.get("url") or "").strip()
    if not target:
        raise ValueError("This problem has no link to read it from. Paste its statement and examples instead.")
    host = urllib.parse.urlsplit(target).hostname or ""
    if host == "leetcode.com" or host.endswith(".leetcode.com"):
        raise ValueError("LeetCode builds its problem pages in the browser, so they can't be read here. Open the problem and paste its examples.")
    if not allowed(target, fetcher):
        raise ValueError(f"{host} asks automated tools not to read that page (robots.txt). Open it and paste the statement and examples instead.")
    body, final, kind, charset = fetcher(target)
    if kind not in ("text/html", "application/xhtml+xml"):
        raise ValueError("That link isn't a problem page.")
    return problem_from_page(body.decode(charset, errors="replace"), final)


def describe(value):
    return {bool: "true/false", int: "an integer", float: "a number", str: "text", list: "a list", dict: "a dictionary"}.get(type(value), "None")


def build_lab(data):
    """Validate a learner-defined lab. Its cases are the learner's own: the expected outputs are
    their specification, and the lab says so wherever it judges against them."""
    if not isinstance(data, dict):
        raise ValueError("Send the lab as an object.")
    title = clean_title(data.get("title") if isinstance(data.get("title"), str) else "")
    statement = data.get("statement") if isinstance(data.get("statement"), str) else ""
    returns = data.get("returns") if isinstance(data.get("returns"), str) else ""
    if len(title) < 2:
        raise ValueError("Give the lab a title.")
    if len(statement.strip()) < 10 or len(statement) > 6000:
        raise ValueError("Describe the problem in 10 to 6,000 characters.")
    if len(returns) > 400:
        raise ValueError("Keep the return description under 400 characters.")
    params = data.get("params")
    if isinstance(params, str):
        params = [p.strip() for p in params.split(",") if p.strip()]
    if not isinstance(params, list) or not 1 <= len(params) <= 5 or any(not isinstance(p, str) or not re.fullmatch(r"[A-Za-z_]\w{0,24}", p) for p in params):
        raise ValueError("Name 1 to 5 parameters, separated by commas, e.g. nums, target.")
    if len(set(params)) != len(params) or any(p in {"solve", "self", "print", "len", "range", "list", "dict", "set", "str", "int", "sum", "min", "max"} for p in params):
        raise ValueError("Use distinct parameter names that aren't Python built-ins.")
    cases = data.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError(f"Add 1 to {MAX_CASES} cases.")
    clean = []
    for number, case in enumerate(cases, 1):
        if not isinstance(case, dict) or not isinstance(case.get("args"), list) or len(case["args"]) != len(params):
            raise ValueError(f"Case {number} needs one value for each parameter ({', '.join(params)}).")
        name = clean_title(case.get("name") if isinstance(case.get("name"), str) else "") or f"Case {number}"
        try:
            args = []
            for param, value in zip(params, case["args"]):
                try:
                    args.append(literal(value) if isinstance(value, str) else plain(value))
                except ValueError as error:
                    raise ValueError(f"{param}: {error}")
            if "expected" not in case or case["expected"] is None or (isinstance(case["expected"], str) and not case["expected"].strip()):
                raise ValueError("it needs an expected output, which is how the lab knows when your code is on target.")
            try:
                expected = literal(case["expected"]) if isinstance(case["expected"], str) else plain(case["expected"])
            except ValueError as error:
                raise ValueError(f"expected output: {error}")
        except ValueError as error:
            raise ValueError(f"{name} — {error}")
        clean.append(dict(name=name[:40], args=args, expected=expected))
    shapes = [type(v) for v in clean[0]["args"]]
    for number, case in enumerate(clean[1:], 2):
        for name, value, shape in zip(params, case["args"], shapes):
            if type(value) is not shape and not ({type(value), shape} <= {int, float}):
                raise ValueError(f"Case {number}: {name} is {describe(value)}, but case 1 gives {describe(clean[0]['args'][params.index(name)])}. Keep each parameter's type.")
    names = [c["name"] for c in clean]
    for i, name in enumerate(names):
        if names.count(name) > 1:
            clean[i]["name"] = f"{name} ({i + 1})"
    order = "any" if data.get("order") == "any" else "exact"
    difficulty = difficulty_of(data.get("difficulty")) or ""
    topic = clean_title(data.get("topic") if isinstance(data.get("topic"), str) else "")[:80]
    return dict(title=title, statement=statement.strip(), returns=returns.strip(), params=params, cases=clean, order=order, difficulty=difficulty, topic=topic)


RECALL = ["Without looking at your code: what does your solution keep track of as it moves through the input?",
          "Which of your cases was the hardest to get right, and what did it teach you about the problem?",
          "Name an input none of your cases covers. What should your solution return for it, and why?"]


def as_problem(lab_id, lab, sheet_id, sheet_name, number):
    """A learner-defined lab in the shape every part of the laboratory reads."""
    params, first = lab["params"], lab["cases"][0]
    given = "; ".join(f"{name}: {describe(value)}" for name, value in zip(params, first["args"]))
    returns = lab["returns"] or f"Return {describe(first['expected'])}, compared with the expected output of each of your cases."
    if lab["order"] == "any":
        returns += " The order of the returned items doesn't matter."
    starter = f"def solve({', '.join(params)}):\n    # {lab['title']}\n    # Write your approach here.\n    \n    pass\n"
    return dict(id=lab_id, custom=True, sheetId=sheet_id, sheetName=sheet_name, number=number, title=lab["title"],
                category=lab["topic"] or "Your sheet", difficulty=lab["difficulty"] or "Your lab", params=params,
                statement=lab["statement"], decoder=dict(given=given, find=lab["statement"][:400], returns=returns),
                example=dict(args=first["args"], expected=first["expected"]), tests=lab["cases"], cases=lab["cases"], order=lab["order"],
                returnsNote=lab["returns"], starter=starter, discovery=[], hints=[], recall=RECALL, transfer=None, complexity=None,
                solution=None, brute=None)
