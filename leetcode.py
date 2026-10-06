"""LeetCode's own version of a problem: its statement, examples with outputs, and Python signature.

LeetCode's pages are built in the browser behind a bot check, and its robots.txt closes /graphql and /api/, so the
platform never reads leetcode.com itself. It reads LeetCode's problem text from doocs/leetcode, an open mirror that
keeps each problem's LeetCode statement verbatim with accepted solutions (CC BY-SA 4.0, credited wherever its text
is shown). A problem is identified only by its exact LeetCode slug: the mirror page must link to that same
leetcode.com/problems/<slug>, or nothing from it is used.

What it gives:
- the statement and examples, read by the same reader as any problem page (sheets.problem_from_page);
- the signature of the accepted Python solution: exact parameter names, and what they are (Optional[ListNode] is a
  linked list, Optional[TreeNode] a tree), and `-> None` when the problem changes its input in place;
- that solution's code, which the server may use as a reference only after it reproduces every example the
  problem's own page gives (never shown to the learner).
"""
import ast
import collections
import re
import threading
import time
import urllib.parse

ORIGIN = "https://raw.githubusercontent.com/doocs/leetcode/main"
INDEX = ORIGIN + "/solution/README_EN.md"
CREDIT = "LeetCode's statement, via doocs/leetcode (CC BY-SA 4.0)"
INDEX_SECONDS = 24 * 3600
_lock = threading.Lock()
_index = {"at": 0.0, "paths": {}, "locked": set()}
_pages = collections.OrderedDict()


def slug_of(url):
    """The problem slug of a leetcode.com link: leetcode.com/problems/two-sum/description → two-sum."""
    if not isinstance(url, str):
        return None
    parts = urllib.parse.urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if not (host == "leetcode.com" or host.endswith(".leetcode.com")):
        return None
    path = [p for p in parts.path.split("/") if p]
    if len(path) >= 2 and path[0] == "problems" and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", path[1].lower()):
        return path[1].lower()
    return None


def slug_for(title):
    """The slug LeetCode gives a title: lowercase, punctuation dropped, words joined by hyphens."""
    text = re.sub(r"[^a-z0-9\s-]", "", title.lower())
    return re.sub(r"-{2,}", "-", re.sub(r"\s+", "-", text.strip())).strip("-")


def row_slug(row):
    """The LeetCode problem a sheet row links to, if any of its links is a LeetCode problem."""
    for link in [row.get("source"), row.get("url"), *(row.get("links") or [])]:
        slug = slug_of(link)
        if slug:
            return slug
    return None


def index(fetcher, decode):
    """slug -> the mirror's page path, from the mirror's own table of problems (read at most once a day)."""
    with _lock:
        if _index["paths"] and time.time() - _index["at"] < INDEX_SECONDS:
            return _index
    body, _, _, charset = fetcher(INDEX)
    paths, locked = {}, set()
    for line in decode(body, charset).splitlines():
        match = re.match(r"\|\s*\d+\s*\|\s*\[(.+?)\]\((/solution/[^)]+?/README_EN\.md)\)", line)
        if match:
            slug = slug_for(match.group(1))
            paths.setdefault(slug, match.group(2))
            if "🔒" in line:
                locked.add(slug)
    if not paths:
        raise ValueError("the mirror's list of problems couldn't be read")
    with _lock:
        _index.update(at=time.time(), paths=paths, locked=locked)
        return _index


def python_entry(code):
    """The signature of a solution's entry: class Solution's method that no other method calls (as the runner picks
    it), with each parameter's annotation, and the return annotation."""
    tree = ast.parse(code)
    solution = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Solution"), None)
    if solution is None:
        return None
    methods = [n for n in solution.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]
    # A helper is a method another method calls through self; a method calling itself (recursion) is not one.
    called = {n.func.attr for m in methods for n in ast.walk(m) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == "self" and n.func.attr != m.name}
    roots = [m for m in methods if m.name not in called]
    if len(roots) != 1:
        return None
    method = roots[0]
    params = [(a.arg, ast.unparse(a.annotation) if a.annotation else "") for a in method.args.args[1:]]
    return {"method": method.name, "params": params, "returns": ast.unparse(method.returns) if method.returns else ""}


def kind_of(annotation):
    """What a parameter is, from its type in LeetCode's signature."""
    text = annotation.replace(" ", "")
    if re.search(r"List\[(Optional\[)?ListNode", text):
        return "linkedlists"
    if "ListNode" in text:
        return "linkedlist"
    if "TreeNode" in text:
        return "tree"
    return None


def page(slug, fetcher, decode):
    """LeetCode's version of the problem with this slug, or None when the mirror has no matching problem."""
    with _lock:
        if slug in _pages:
            _pages.move_to_end(slug)
            return _pages[slug]
    found = index(fetcher, decode)
    path = found["paths"].get(slug)
    if not path or slug in found["locked"]:
        return None
    url = ORIGIN + path
    body, _, _, charset = fetcher(url)
    text = decode(body, charset)
    header = re.search(r"^# \[(\d+)\.\s+(.+?)\]\(https://leetcode\.com/problems/([a-z0-9-]+)/?\)", text, re.M)
    if not header or header.group(3) != slug:  # The page must be LeetCode's problem with exactly this slug.
        return None
    described = re.search(r"<!-- description:start -->(.*?)<!-- description:end -->", text, re.S)
    code = re.search(r"#### Python3\s*```python\n(.*?)```", text, re.S)
    if not described:
        return None
    python = code.group(1) if code else ""
    try:
        signature = python_entry(python) if python else None
    except SyntaxError:
        signature = None
    found = {"number": int(header.group(1)), "title": header.group(2).strip(), "slug": slug, "url": f"https://leetcode.com/problems/{slug}/", "mirror": url,
             "description": described.group(1).strip(), "python": python, "signature": signature}
    with _lock:
        _pages[slug] = found
        while len(_pages) > 64:
            _pages.popitem(last=False)
    return found


def problem(found, reader):
    """LeetCode's version as a fetched problem (the shape sheets.read_problem gives), read by `reader` (the same
    problem-page reader every page goes through), with the signature's names and kinds, and every case marked as
    LeetCode's."""
    read = reader(f"<html><body><h1>{found['title']}</h1>\n{found['description']}\n</body></html>", found["url"])
    apply_signature(read, found)
    for case in read["cases"]:
        case["source"] = "leetcode"
    read["source"] = found["url"]
    read["leetcode"] = found["slug"]
    read["notes"].insert(0, f"Read from {CREDIT}: LeetCode's own pages can't be read by automated tools.")
    return read


def apply_signature(read, found):
    """Exact names and kinds from LeetCode's signature, where the problem's own examples name the same parameters
    (or name none): its types say what each input is, and `-> None` that the answer is the changed input."""
    signature = found.get("signature")
    if not signature:
        return False
    names = [name for name, _ in signature["params"]]
    if read["params"] != names and not (read["params"] in ([], ["value"]) and len(names) == max(1, len(read["params"]))):
        return False
    read["params"] = names
    kinds = {name: kind_of(annotation) for name, annotation in signature["params"] if kind_of(annotation)}
    read["kinds"] = {**{k: v for k, v in read.get("kinds", {}).items() if k in names and k not in kinds}, **kinds}
    if signature["returns"] == "None":
        read["answer"] = "in-place"
    read["signature"] = {"method": signature["method"], "params": signature["params"], "returns": signature["returns"]}
    return True
