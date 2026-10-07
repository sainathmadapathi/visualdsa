"""
Reference solutions this platform wrote for problems learners bring from their sheets, keyed by the problem page.

A learner's own lab is judged by its cases, which come from the problem's page. A reference adds what the page
can't: the expected result for an input the learner types, and edge cases. It is used for a lab only when it
reproduces every one of that lab's cases exactly (app.attach_reference), and everything it computes is labelled as
computed, never as from the page. It never leaves the server.

Edge cases are inputs only, chosen inside each page's stated constraints; their expected results are what the
checked reference returns for them. `answer` is how the page's contract is judged ("in-place": solve changes its
first input and returns nothing). `version` changes whenever a reference or its edge cases change.
"""
import copy
from urllib.parse import urlsplit


def key(url):
    """A problem page's address without scheme, www, query, fragment or trailing slash."""
    if not isinstance(url, str) or not url.strip():
        return ""
    parts = urlsplit(url.strip() if "://" in url else "https://" + url.strip())
    return (parts.netloc.lower().removeprefix("www.") + parts.path.rstrip("/")).lower()


PRIME = """def solve(num):
    if num < 2:
        return False
    d = 2
    while d * d <= num:
        if num % d == 0:
            return False
        d += 1
    return True
"""

DEPTH = """def solve(root):
    if root is None:
        return 0
    return 1 + max(solve(root.left), solve(root.right))
"""

SORTED = """def solve(nums):
    return sorted(nums)
"""

SUDOKU = """def solve(board):
    def fits(r, c, d):
        for i in range(9):
            if board[r][i] == d or board[i][c] == d:
                return False
        top, left = r // 3 * 3, c // 3 * 3
        for i in range(top, top + 3):
            for j in range(left, left + 3):
                if board[i][j] == d:
                    return False
        return True

    def fill():
        for r in range(9):
            for c in range(9):
                if board[r][c] == '.':
                    for d in '123456789':
                        if fits(r, c, d):
                            board[r][c] = d
                            if fill():
                                return True
                            board[r][c] = '.'
                    return False
        return True

    fill()
"""

# Example 1's solved board on the Sudoku page; each edge case empties cells of it, and has exactly one solution.
SOLVED = [list("534678912"), list("672195348"), list("198342567"), list("859761423"), list("426853791"),
          list("713924856"), list("961537284"), list("287419635"), list("345286179")]


def emptied(cells):
    board = copy.deepcopy(SOLVED)
    for r, c in cells:
        board[r][c] = "."
    return board


SORT_EDGES = [("One value", [[42]]), ("Two values, reversed", [[2, 1]]), ("All equal", [[3, 3, 3]]),
              ("Negatives and duplicates", [[-5, 0, -10, 10, -10]]), ("Already sorted", [[1, 2, 3, 4, 5]]),
              ("Reverse sorted", [[9, 7, 5, 3, 1]]), ("The value limits", [[10000, -10000, 0]])]

REFERENCES = {
    "takeuforward.org/practice/dsa/check-if-a-number-is-prime-or-not": dict(version=1, solution=PRIME, edges=[
        ("One", [1]), ("Two, the smallest prime", [2]), ("Four, the smallest composite", [4]), ("A prime squared", [49]),
        ("A large prime", [9973]), ("The upper limit", [10000])]),
    "takeuforward.org/practice/dsa/maximum-depth-in-bt": dict(version=1, solution=DEPTH, edges=[
        ("A single node", [[1]]), ("Leaning left", [[1, 2, None, 3, None, 4]]), ("Leaning right", [[1, None, 2, None, 3]]),
        ("A full tree", [[1, 2, 3, 4, 5, 6, 7]])]),
    "takeuforward.org/practice/dsa/merge-sorting": dict(version=1, solution=SORTED, edges=SORT_EDGES),
    "takeuforward.org/practice/dsa/insertion-sorting": dict(version=1, solution=SORTED, edges=SORT_EDGES),
    "takeuforward.org/practice/dsa/sudoko-solver": dict(version=1, solution=SUDOKU, answer="in-place", edges=[
        ("Already solved", [emptied([])]), ("One empty cell", [emptied([(4, 4)])]),
        ("Empty main diagonal", [emptied([(i, i) for i in range(9)])]), ("One empty row", [emptied([(0, c) for c in range(9)])]),
        ("One empty column", [emptied([(r, 8) for r in range(9)])])]),
}


def find(url):
    """The reference for a problem page, if this platform has one."""
    return REFERENCES.get(key(url))
