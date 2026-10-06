"""Visual DSA: API, persistence, AST instrumentation and isolated trace worker.

The local worker accepts a deliberately restricted Python subset. It is a
development runner, not an OS security boundary. Public mode requires Docker.
"""
import ast
import builtins
import collections
import copy
import difflib
import hashlib
import io
import itertools
import json
import math
import operator
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parent
MAX_EVENTS = 1200
MAX_ITEMS = 200
MAX_TICKS = 15000
# A quiet run (a verdict for a case its trace couldn't finish) records no steps, so it can afford far more of them
# within its own time budget; the same guards and the worker's CPU, memory and wall-clock limits still apply.
QUIET_TICKS, QUIET_SECONDS = 4_000_000, 5
MAX_SECONDS = 3
BIG_BITS = 1 << 18  # Library calls refuse results bounded above this size: their C loops cannot be stepped.
LIMIT_MESSAGE = "Execution limit reached. Check loop boundaries or try a smaller input."
# A batch's case budgets add up to at most 6 seconds; the OS CPU limit and the parent's wall-clock limit sit
# above that as backstops for work inside built-in code that the tracer cannot step through.
WORKER_CPU_SECONDS, WORKER_SECONDS, WORKER_INPUT = 7, 9, 80000


class ExecutionLimit(BaseException):
    """A runner limit stopped the program. A BaseException, so a learner's `except Exception:` can't swallow it (and
    every except block re-raises it, see Instrument.visit_ExceptHandler)."""


class Unsupported(ValueError):
    """Code the learning runner refuses before running it: the line it is on, and a plain title and question
    for the learner (errors.refused turns these into the shown explanation)."""

    def __init__(self, message, line=None, title=None, hint=""):
        super().__init__(message)
        self.lineno, self.title, self.hint = line, title, hint


LABEL_ATTRS = ("val", "value", "data", "key")


def is_node_object(value):
    """A node of the learner's own data structure (or a provided ListNode/TreeNode/Node)."""
    return type(value).__module__ == "student" or isinstance(value, (ListNode, TreeNode, Node))


def node_label(value):
    attrs = getattr(value, "__dict__", {})
    for name in LABEL_ATTRS:
        if name in attrs and (attrs[name] is None or isinstance(attrs[name], (bool, int, float, str))):
            return attrs[name]
    return None


def node_text(value):
    label = node_label(value)
    return f"{type(value).__name__}({label})" if label is not None else type(value).__name__


def bounded(value, depth=0):
    """Only JSON primitives cross the worker boundary; snapshots never alias."""
    if depth > 5:
        return "…"
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if value is None or isinstance(value, (bool, float)):
        return value
    if isinstance(value, int):
        return value if value.bit_length() < 1024 else "<large integer>"
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, (list, tuple, range, set, frozenset, collections.deque)):
        return [bounded(v, depth + 1) for v in list(value)[:MAX_ITEMS]]
    if isinstance(value, dict):
        return {str(k)[:100]: bounded(v, depth + 1) for k, v in list(value.items())[:MAX_ITEMS]}
    if is_node_object(value):
        return node_text(value)
    return "<function>"


def state_digest(locals_):
    """Digest of a frame's plain data, including which names share an object. None when unsure."""
    ids, budget = {}, [20000]

    def walk(value, depth):
        budget[0] -= 1
        if budget[0] < 0 or depth > 30:
            raise ValueError
        if value is None or isinstance(value, (bool, int, float, str, range)):
            return (type(value).__name__, value)
        if isinstance(value, tuple):
            return ("tuple", tuple(walk(v, depth + 1) for v in value))
        if isinstance(value, (list, dict, set, collections.deque)) or is_node_object(value):
            if id(value) in ids:
                return ("ref", ids[id(value)])
            ids[id(value)] = len(ids)
            if isinstance(value, dict):
                return ("dict", ids[id(value)], tuple((walk(k, depth + 1), walk(v, depth + 1)) for k, v in value.items()))
            if is_node_object(value):  # A node's fields, including which node each link points to.
                return ("node", ids[id(value)], tuple((k, walk(v, depth + 1)) for k, v in sorted(vars(value).items()) if not callable(v)))
            return (type(value).__name__, ids[id(value)], tuple(walk(v, depth + 1) for v in value))  # Iteration order is state.
        raise ValueError  # Iterators and other objects carry hidden state.

    try:
        items = sorted(((k, v) for k, v in locals_.items() if not k.startswith("_") and not callable(v)), key=lambda kv: kv[0])
        return hashlib.sha256(repr(tuple((k, walk(v, 0)) for k, v in items)).encode()).hexdigest()
    except (ValueError, RecursionError):
        return None


def node_result(value):
    """A returned head or root, as judges compare it: a list of values (level order for a tree)."""
    if hasattr(value, "left") or hasattr(value, "right"):
        out, queue, seen = [], [value], set()
        while queue:
            node = queue.pop(0)
            if node is None:
                out.append(None)
                continue
            if id(node) in seen or len(out) > 10000:
                raise ValueError("The returned tree has a cycle or is too large.")
            seen.add(id(node))
            out.append(node_label(node))
            queue += [getattr(node, "left", None), getattr(node, "right", None)]
        while out and out[-1] is None:
            out.pop()
        return out
    if hasattr(value, "next"):
        out, seen, node = [], set(), value
        while node is not None:
            if id(node) in seen or len(out) > 10000:
                raise ValueError("The returned linked list has a cycle, so it never ends.")
            seen.add(id(node))
            out.append(node_label(node))
            node = getattr(node, "next", None)
        return out
    raise ValueError("Return a value, a list, or the head or root node of your structure.")


def result_value(value, depth=0):
    """Results are never clipped like snapshots: grading compares the whole value."""
    if depth > 20:
        raise ValueError("The returned value is nested too deeply or contains a cycle.")
    if value is None or isinstance(value, (bool, int, str)):
        if isinstance(value, str) and len(value) > 10000:
            raise ExecutionLimit("The returned string exceeds 10,000 characters.")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Return a finite number.")
        return value
    if is_node_object(value):
        return result_value(node_result(value), depth + 1)
    if isinstance(value, (list, tuple, set, frozenset, range, dict, collections.deque)):
        if len(value) > 10000:
            raise ExecutionLimit("The returned collection exceeds 10,000 items.")
        if isinstance(value, dict):
            return {str(k): result_value(v, depth + 1) for k, v in value.items()}
        return [result_value(v, depth + 1) for v in value]
    raise ValueError("Return a number, boolean, string, or collection of values.")


# ----------------------------- the learner's program -----------------------------
class ListNode:
    """A linked-list node as judges define it (prev is used by doubly linked lists)."""
    def __init__(self, val=0, next=None, prev=None):
        self.val, self.next, self.prev = val, next, prev


class TreeNode:
    """A binary-tree node as judges define it."""
    def __init__(self, val=0, left=None, right=None):
        self.val, self.left, self.right = val, left, right


class Node:
    """A general node: graph neighbors, n-ary children, or next/prev links."""
    def __init__(self, val=0, neighbors=None, children=None, next=None, prev=None):
        self.val, self.neighbors, self.children, self.next, self.prev = val, neighbors if neighbors is not None else [], children if children is not None else [], next, prev


PROVIDED_NAMES = {"ListNode", "TreeNode", "Node"}


def build_input(kind, value):
    """Judges write linked lists and trees as lists; the learner's code receives real nodes."""
    def chain(values, doubly=False):
        head = tail = None
        for v in values:
            node = ListNode(v)
            if tail is None:
                head = node
            else:
                tail.next = node
                if doubly:
                    node.prev = tail
            tail = node
        return head

    if kind in ("linkedlist", "dll") and isinstance(value, list):
        return chain(value, kind == "dll")
    if kind == "linkedlists" and isinstance(value, list):
        return [chain(v) if isinstance(v, list) else v for v in value]
    if kind == "tree" and isinstance(value, list):
        if not value or value[0] is None:
            return None
        root = TreeNode(value[0])
        queue, i = [root], 1
        while queue and i < len(value):
            node = queue.pop(0)
            for side in ("left", "right"):
                if i < len(value) and value[i] is not None:
                    child = TreeNode(value[i])
                    setattr(node, side, child)
                    queue.append(child)
                i += 1
        return root
    return value


def link_cycles(args, kinds):
    """A cycle position (pos) links the linked list's tail back to node pos (-1: no cycle), as judges describe
    a loop; it only builds the input, so it is not passed to the learner's function."""
    if "cycle" not in kinds:
        return args
    head = next((a for a, k in zip(args, kinds) if k in ("linkedlist", "dll")), None)
    for a, k in zip(args, kinds):
        if k == "cycle" and type(a) is int and a >= 0 and head is not None:
            nodes, node = [], head
            while node is not None and len(nodes) <= 10000:
                nodes.append(node)
                node = node.next
            if a < len(nodes):
                nodes[-1].next = nodes[a]
    kinds = list(kinds) + [None] * (len(args) - len(kinds))
    return [a for a, k in zip(args, kinds) if k != "cycle"]


SAFE_CALLS = {"len", "range", "enumerate", "zip", "min", "max", "sum", "abs", "sorted", "reversed", "list", "dict", "set", "tuple", "int", "str", "bool", "float", "print", "all", "any", "round",
              "map", "filter", "chr", "ord", "bin", "divmod", "pow", "isinstance", "iter", "next", "frozenset", "hash", "object", "hex", "oct",
              "type", "callable", "repr", "id", "hasattr", "getattr", "setattr", "super", "staticmethod", "classmethod", "property", "issubclass", "slice", "ascii"}
# Exceptions a program may raise, catch or subclass.
EXCEPTIONS = {"BaseException", "Exception", "ValueError", "TypeError", "IndexError", "KeyError", "ZeroDivisionError", "ArithmeticError", "LookupError", "RuntimeError",
              "StopIteration", "NotImplementedError", "AssertionError", "AttributeError", "OverflowError", "RecursionError", "NameError", "UnboundLocalError"}
SAFE_CALLS |= EXCEPTIONS
SAFE_METHODS = {"append", "pop", "get", "keys", "values", "items", "add", "remove", "discard", "clear", "copy", "sort", "reverse", "count", "index", "lower", "upper", "strip", "split", "join", "isalnum", "isalpha", "isdigit", "startswith", "endswith",
                "appendleft", "popleft", "extend", "extendleft", "insert", "rotate", "update", "setdefault", "popitem", "most_common", "elements", "subtract", "total",
                "union", "intersection", "difference", "symmetric_difference", "issubset", "issuperset", "isdisjoint", "intersection_update", "difference_update",
                "find", "rfind", "rindex", "replace", "lstrip", "rstrip", "isupper", "islower", "isspace", "isnumeric", "isdecimal", "zfill", "partition", "rpartition", "splitlines",
                "title", "capitalize", "swapcase", "center", "ljust", "rjust", "casefold", "removeprefix", "removesuffix", "bit_length", "bit_count", "is_integer", "fromkeys", "maketrans", "translate"}
# Attributes of built-in values a program may use; everything else is reachable only on its own objects.
SAFE_ATTRS = SAFE_METHODS | {"real", "imag", "numerator", "denominator", "maxlen", "default_factory"}
BLOCKED_ATTRS = {"format", "format_map", "mro", "gi_frame", "gi_code", "gi_yieldfrom", "cr_frame", "cr_code", "ag_frame", "f_globals", "f_locals", "f_back", "f_builtins", "f_code", "tb_frame", "tb_next", "co_code"}
MODULES = {
    "math": {"inf", "pi", "e", "sqrt", "isqrt", "ceil", "floor", "gcd", "lcm", "log", "log2", "log10", "exp", "comb", "perm", "factorial", "fabs", "hypot", "prod", "trunc", "isinf", "isnan", "copysign", "dist", "fsum"},
    "heapq": {"heappush", "heappop", "heapify", "heappushpop", "heapreplace", "nlargest", "nsmallest", "merge"},
    "collections": {"deque", "defaultdict", "Counter", "OrderedDict"},
    "bisect": {"bisect", "bisect_left", "bisect_right", "insort", "insort_left", "insort_right"},
    "functools": {"lru_cache", "cache", "reduce", "cmp_to_key"},
    "itertools": {"accumulate", "combinations", "combinations_with_replacement", "permutations", "product", "chain", "groupby", "zip_longest", "islice", "pairwise", "count"},
    "typing": {"List", "Optional", "Dict", "Tuple", "Set", "Deque", "Any", "Union"},
    "string": {"ascii_lowercase", "ascii_uppercase", "ascii_letters", "digits"},
    "sys": {"setrecursionlimit", "maxsize"},
}
LEETCODE_NAMES = {name for module, names in MODULES.items() if module != "sys" for name in names} | {"math", "heapq", "collections", "bisect", "functools", "itertools", "string", "typing"}
DECORATORS = {"cache", "lru_cache", "staticmethod", "classmethod", "property", "setter", "getter", "deleter"}
# Special methods a class may define: comparisons, arithmetic, containers and iteration. Hooks into attribute access,
# object creation and destruction stay closed.
DUNDER_METHODS = {"__init__", "__lt__", "__le__", "__gt__", "__ge__", "__eq__", "__ne__", "__hash__", "__repr__", "__str__", "__len__", "__bool__",
                  "__add__", "__radd__", "__iadd__", "__sub__", "__rsub__", "__isub__", "__mul__", "__rmul__", "__imul__", "__truediv__", "__floordiv__", "__mod__",
                  "__neg__", "__pos__", "__abs__", "__and__", "__or__", "__xor__", "__lshift__", "__rshift__", "__invert__",
                  "__iter__", "__next__", "__getitem__", "__setitem__", "__delitem__", "__contains__", "__reversed__", "__call__"}
EVENT_CALLS = {"heappush", "heappop", "heapify", "heappushpop", "heapreplace", "insort", "insort_left", "insort_right"}


REFUSED = {
    "AsyncFunctionDef": ("async code isn't supported", "`async def` runs code concurrently, which the learning runner doesn't trace.", "Can this be a plain def?"),
    "Await": ("async code isn't supported", "`await` belongs to async code, which the learning runner doesn't trace.", "Can this be a plain call?"),
    "AsyncWith": ("async code isn't supported", "`async with` belongs to async code, which the learning runner doesn't trace.", ""),
    "AsyncFor": ("async code isn't supported", "`async for` belongs to async code, which the learning runner doesn't trace.", "Can this be a plain for loop?"),
    "With": ("`with` isn't supported", "`with` manages files and other resources, and there are none in the learning runner.", "Can the body of the with block run on its own?"),
    "Yield": ("Generators aren't supported yet", "`yield` makes a generator; the learning runner can't trace a generator's steps yet.", "Can this function build and return a list instead?"),
    "YieldFrom": ("Generators aren't supported yet", "`yield from` makes a generator; the learning runner can't trace a generator's steps yet.", "Can this function build and return a list instead?"),
    "TryStar": ("except* isn't supported", "`except*` handles exception groups, which the learning runner doesn't trace.", "Can a plain except handle this?"),
}
SUPPORTED_IMPORTS = ", ".join(sorted(MODULES))


def is_main_block(node):
    """`if __name__ == "__main__":` at the top: test code that never runs when the program is loaded, as here."""
    test = node.test if isinstance(node, ast.If) else None
    return isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "__name__" and len(test.comparators) == 1 \
        and isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value == "__main__"


def is_super_init(node):
    """`super().__init__`: the one special attribute a program reaches, to run its parent class's constructor."""
    return node.attr in DUNDER_METHODS and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == "super"


def refusal(n, message, title, hint=""):
    return Unsupported(message, getattr(n, "lineno", None), title, hint)


def solution_method(tree, arity=None):
    """In LeetCode's form (class Solution, no def solve), the method that solves the problem: a public method of
    Solution that no other method calls through self (helpers are called), with as many parameters as the problem
    has inputs when more than one is left. Refused, never guessed, when that still leaves none or several."""
    solution = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Solution"), None)
    if solution is None:
        return None
    methods = [n for n in solution.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]
    # A helper is a method another method calls through self; a method calling itself (recursion) is not one.
    called = {n.func.attr for m in methods for n in ast.walk(m) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == "self" and n.func.attr != m.name}
    roots = [m for m in methods if m.name not in called] or methods
    if len(roots) > 1 and arity is not None:
        fits = [m for m in roots if len(m.args.args) - 1 - len(m.args.defaults) <= arity <= len(m.args.args) - 1]
        roots = fits or roots
    if len(roots) == 1:
        return roots[0].name
    names = ", ".join(m.name for m in roots) or "none"
    raise Unsupported(f"class Solution has {'no public method' if not roots else f'several methods that could solve the problem ({names})'}, so the runner can't tell which one to call with each input.",
                      solution.lineno, "Which method solves the problem?", "Can the other methods be called from the main one (self.helper(...)), or start with an underscore?" if roots else "Add the method the problem asks for.")


def validate_source(source, entry="solve", arity=None):
    """Refuse code the learning runner can't run, with the line, a plain title and a question to look into.
    Constructs are checked in source order, so the first refusal is the first one in the code."""
    if not isinstance(source, str) or len(source) > 12000:
        raise Unsupported("The learning runner reads programs of up to 12,000 characters.", None, "The program is too long", "Can helper code that isn't used be removed?")
    tree = ast.parse(source, filename="<student>")
    defined = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    # Every name the program binds (assignments, parameters, loop and comprehension targets, except ... as): calling
    # one calls whatever it holds, a function passed in or kept in a variable.
    lambdas = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)} | {n.arg for n in ast.walk(tree) if isinstance(n, ast.arg)} \
        | {n.name for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.name}
    main_blocks = [top for top in tree.body if is_main_block(top)]
    # LeetCode's form (class Solution, no def solve) runs with LeetCode's standard imports, as it does there.
    leetcode_form = entry == "solve" and not any(isinstance(n, ast.FunctionDef) and n.name == "solve" for n in tree.body) and any(isinstance(n, ast.ClassDef) and n.name == "Solution" for n in tree.body)
    allowed_underscore = {id(n) for top in main_blocks for n in ast.walk(top.test)} | {id(n) for n in ast.walk(tree) if isinstance(n, ast.Attribute) and is_super_init(n)}
    if entry == "solve":
        # A plain `def solve`, or LeetCode's `class Solution` with the method that solves the problem.
        if "solve" not in {n.name for n in tree.body if isinstance(n, ast.FunctionDef)} and solution_method(tree, arity) is None:
            raise Unsupported("This problem runs a function named solve (or, in LeetCode's form, a method of class Solution) with its inputs, and your code defines neither at the top level.", None, "No solve function",
                              "Is the function named exactly `solve`, and not indented inside something else?")
    elif entry not in {n.name for n in tree.body if isinstance(n, ast.ClassDef)}:
        raise Unsupported(f"This problem builds a {entry} object and calls its methods, and your code doesn't define class {entry} at the top level.", None, f"No class {entry}",
                          f"Is the class named exactly `{entry}`?")
    for top in tree.body:
        names = lambda t: isinstance(t, ast.Name) or (isinstance(t, (ast.Tuple, ast.List)) and all(isinstance(e, ast.Name) for e in t.elts))
        simple = isinstance(top, (ast.Assign, ast.AnnAssign)) and all(names(t) for t in (top.targets if isinstance(top, ast.Assign) else [top.target]))
        # `sys.setrecursionlimit(...)` at the top is common in competitive code: allowed, and a no-op here.
        setup = isinstance(top, ast.Expr) and isinstance(top.value, ast.Call) and isinstance(top.value.func, ast.Attribute) and top.value.func.attr == "setrecursionlimit"
        if not (isinstance(top, (ast.FunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)) or simple or setup or top in main_blocks or (isinstance(top, ast.Expr) and isinstance(top.value, ast.Constant) and isinstance(top.value.value, str))):
            raise refusal(top, f"Line {top.lineno} runs outside any function. The runner calls {entry} with each input itself, so test code such as `print({entry}(…))` isn't needed here.",
                          "Code outside a function", f"Can this line move inside {entry}, or be removed?")
    imported = set(LEETCODE_NAMES) if leetcode_form else set()
    nodes = sorted((n for n in ast.walk(tree) if hasattr(n, "lineno")), key=lambda n: (n.lineno, n.col_offset))
    for n in nodes + [n for n in ast.walk(tree) if not hasattr(n, "lineno")]:
        refused = REFUSED.get(type(n).__name__, False)
        if refused:
            raise refusal(n, refused[1], refused[0], refused[2])
        if isinstance(n, ast.Import):
            for alias in n.names:
                if alias.name not in MODULES:
                    raise refusal(n, f"`{alias.name}` isn't available in the learning runner. It offers {SUPPORTED_IMPORTS}.", f"`import {alias.name}` isn't available", "Can one of those modules, or plain Python, do this?")
                imported.add(alias.asname or alias.name)
        if isinstance(n, ast.ImportFrom):
            if n.level or n.module not in MODULES:
                raise refusal(n, f"`{'.' * n.level}{n.module or ''}` isn't available in the learning runner. It offers {SUPPORTED_IMPORTS}.", f"`from {'.' * n.level}{n.module or ''} import …` isn't available", "Can one of those modules, or plain Python, do this?")
            for alias in n.names:
                if alias.name not in MODULES[n.module]:
                    offered = ", ".join(sorted(MODULES[n.module]))
                    raise refusal(n, f"The runner's {n.module} offers {offered}, but not `{alias.name}`.", f"`{n.module}.{alias.name}` isn't available", "Can one of those, or plain Python, do this?")
                imported.add(alias.asname or alias.name)
        if isinstance(n, ast.alias) and (n.asname or "").startswith("_"):
            raise refusal(n, f"`{n.asname}`: names starting with _ are reserved for the runner's own tracing.", "Names can't start with _", f"Can it be called `{n.asname.lstrip('_') or 'x'}` instead?")
        if isinstance(n, (ast.Name, ast.arg)) and (n.id if isinstance(n, ast.Name) else n.arg).startswith("_") and (n.id if isinstance(n, ast.Name) else n.arg) != "_" and id(n) not in allowed_underscore:
            name = n.id if isinstance(n, ast.Name) else n.arg
            raise refusal(n, f"`{name}`: names starting with _ are reserved for the runner's own tracing.", "Names can't start with _", f"Can it be called `{name.lstrip('_') or 'x'}` instead?")
        if isinstance(n, ast.FunctionDef):
            if n.name.startswith("_") and n.name not in DUNDER_METHODS:
                raise refusal(n, f"`{n.name}`: the runner supports these special methods: {', '.join(sorted(DUNDER_METHODS))}. Other names starting with _ are reserved for its tracing.",
                              f"`{n.name}` isn't supported", "Can this be a plain method with a name of its own?")
            for decorator in n.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
                if name not in DECORATORS:
                    raise refusal(decorator, f"`@{name}`: the runner supports {', '.join('@' + d for d in sorted(DECORATORS))}.", "Unsupported decorator", "Can the function work without it?")
        if isinstance(n, ast.ClassDef) and (n.name.startswith("_") or n.decorator_list or n.keywords or any(not isinstance(b, ast.Name) for b in n.bases)):
            raise refusal(n, f"class {n.name}: classes here are plain: no decorators, metaclasses or computed base classes.", "Unsupported class form", "Can it be a plain class?")
        if isinstance(n, ast.Attribute) and (n.attr.startswith("__") or n.attr in BLOCKED_ATTRS) and id(n) not in allowed_underscore:
            raise refusal(n, f"`.{n.attr}` reaches into Python's internals, which the learning runner keeps closed.", f"`.{n.attr}` isn't available", "Is there a plainer way to do this?")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id not in SAFE_CALLS | defined | imported | lambdas | PROVIDED_NAMES:
            name = n.func.id
            close = difflib.get_close_matches(name, sorted(SAFE_CALLS | defined | imported | lambdas | PROVIDED_NAMES), n=1, cutoff=0.75)
            if close:
                raise refusal(n, f"`{name}(…)` on line {n.lineno} calls a name that isn't defined in your code or the runner.", f"`{name}` isn't defined", f"Did you mean `{close[0]}`?")
            if hasattr(builtins, name):
                raise refusal(n, f"`{name}()` is a Python built-in the learning runner doesn't offer.", f"`{name}()` isn't available", "Is there another way to do this with the common built-ins?")
            raise refusal(n, f"`{name}(…)` calls a name that isn't defined in your code or the runner.", f"`{name}` isn't defined", "Is it defined somewhere, or spelled differently?")
    if sum(1 for _ in ast.walk(tree)) > 3000:
        raise Unsupported("The program has more parts than the learning runner traces (3,000 syntax nodes).", None, "The program is too large", "Can unused helper code be removed?")
    return tree


def iterated(node):
    """The structure whose row a for loop walks: `graph` in `for v in graph[u]` or `graph.get(u, [])`."""
    if isinstance(node, ast.Subscript):
        return ast.unparse(node.value)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
        return ast.unparse(node.func.value)
    return ""


def plain_chain(node):
    """`curr` or `curr.next.left`: a name and fields only, so evaluating it twice changes nothing."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return isinstance(node, ast.Name)


def helper(name, args, original):
    return ast.copy_location(ast.Call(func=ast.Name(id=name, ctx=ast.Load()), args=args, keywords=[]), original)


NODE_LINKS = {"next", "prev", "left", "right", "random", "child", "parent", "back", "bottom", "down", "up"}


class Instrument(ast.NodeTransformer):
    """Instrument evaluated expressions without evaluating operands twice."""
    def emit(self, kind, node, detail="", root="", targets=()):
        return ast.copy_location(ast.Expr(helper("_mark", [ast.Constant(kind), ast.Constant(node.lineno), ast.Constant(detail), ast.Constant(root), ast.Constant(tuple(targets))], node)), node)

    def visit_Assign(self, node):
        # Classify each element of a tuple target: `a[i], a[j] = a[j], a[i]` writes two elements.
        target = node.targets[0]
        # Setting a field on None (`curr.next = x` when curr is None) is checked first, so the failure can name
        # `curr`. Only plain name chains are checked: evaluating them again has no effect.
        checks = [helper("_store", [copy.deepcopy(t.value), ast.Constant(t.attr), ast.Constant(ast.unparse(t.value))], node)
                  for t in (target.elts if isinstance(target, (ast.Tuple, ast.List)) else [target]) if isinstance(t, ast.Attribute) and plain_chain(t.value)]
        parts = target.elts if isinstance(target, (ast.Tuple, ast.List)) else [target]
        names = [ast.unparse(t) for t in parts]
        written = next((t for t in parts if isinstance(t, ast.Subscript)), None)
        kind, root = "STATE_CHANGE", ""
        if written:
            kind = "WRITE"
            while isinstance(written, ast.Subscript):
                written = written.value
            root = ast.unparse(written)
        elif any(isinstance(t, ast.Attribute) and plain_chain(t.value) for t in parts):
            kind = "ATTR_WRITE"  # Settled by what was written: a node (or None on a link field) re-links the structure.
            root = ast.unparse(next(t for t in parts if isinstance(t, ast.Attribute) and plain_chain(t.value)))
        elif all(isinstance(t, ast.Name) for t in parts):
            kind = "POINTER_MOVE"  # Settled after the run: a pointer only if the code uses these names as positions.
        self.generic_visit(node)
        return [*(ast.copy_location(ast.Expr(self.visit(check)), node) for check in checks), node, self.emit(kind, node, ", ".join(names), root, names if len(names) > 1 else ())]

    def visit_AugAssign(self, node):
        """`x op= v` as Python runs it: the target's parts are evaluated once, and the operation is in place (a list
        `+=` extends the same list, so every name for it sees the change), through the same allocation guards."""
        op, line = ast.Constant(type(node.op).__name__), ast.Constant(node.lineno)
        target = node.target
        texts = ast.Constant((ast.unparse(node), ast.unparse(target), ast.unparse(node.value)))
        names = [ast.unparse(target)]
        if isinstance(target, ast.Name):
            load = ast.copy_location(ast.Name(id=target.id, ctx=ast.Load()), target)
            assign = ast.copy_location(ast.Assign(targets=[target], value=helper("_augment", [load, node.value, op, line, texts], node)), node)
            return self.visit_Assign(assign)
        if isinstance(target, ast.Subscript):
            root = target.value
            while isinstance(root, ast.Subscript):
                root = root.value
            key = target.slice
            if isinstance(key, ast.Slice):
                key = helper("_slice", [key.lower or ast.Constant(None), key.upper or ast.Constant(None), key.step or ast.Constant(None)], target)
            call = helper("_augitem", [self.visit(target.value), self.visit(key), self.visit(node.value), op, line, texts, ast.Constant(ast.unparse(target.value)), ast.Constant(ast.unparse(target.slice))], node)
            return [ast.copy_location(ast.Expr(call), node), self.emit("WRITE", node, names[0], ast.unparse(root))]
        # obj.field op= v
        call = helper("_augattr", [self.visit(target.value), ast.Constant(target.attr), self.visit(node.value), op, line, texts, ast.Constant(ast.unparse(target.value))], node)
        return [ast.copy_location(ast.Expr(call), node), self.emit("LINK_WRITE" if target.attr in NODE_LINKS else "STATE_CHANGE", node, names[0])]

    def visit_ExceptHandler(self, node):
        # An except block first hands back a runner limit (never the program's to catch), then clears what the
        # failure it handled recorded, so a later error is explained by its own facts.
        self.generic_visit(node)
        node.body.insert(0, ast.copy_location(ast.Expr(helper("_handled", [], node)), node))
        return node

    def visit_Raise(self, node):
        self.generic_visit(node)
        if node.exc is not None:
            node.exc = helper("_raising", [node.exc, ast.Constant(node.lineno)], node)
        return node

    def visit_match_case(self, node):
        # Patterns are matched as written (an attribute in a pattern is a constant, not a read to trace).
        if node.guard is not None:
            node.guard = self.visit(node.guard)
        body = []
        for statement in node.body:
            visited = self.visit(statement)
            body.extend(visited if isinstance(visited, list) else [visited])
        node.body = body
        return node

    def visit_Subscript(self, node):
        name, index = ast.unparse(node.value), ast.unparse(node.slice)
        self.generic_visit(node)
        if isinstance(node.ctx, ast.Load):
            key = node.slice
            if isinstance(key, ast.Slice):
                key = helper("_slice", [key.lower or ast.Constant(None), key.upper or ast.Constant(None), key.step or ast.Constant(None)], node)
            return helper("_access", [node.value, key, ast.Constant(name), ast.Constant(node.lineno), ast.Constant(index)], node)
        return node

    def visit_Compare(self, node):
        text = ast.unparse(node)
        sides = (ast.unparse(node.left), ast.unparse(node.comparators[0]))
        self.generic_visit(node)
        if len(node.ops) == 1:
            return helper("_compare", [node.left, node.comparators[0], ast.Constant(type(node.ops[0]).__name__), ast.Constant(text), ast.Constant(node.lineno), ast.Constant(sides)], node)
        return node  # Python's chained comparison short-circuit semantics remain intact.

    def visit_BinOp(self, node):
        texts = (ast.unparse(node), ast.unparse(node.left), ast.unparse(node.right))
        self.generic_visit(node)
        return helper("_binary", [node.left, node.right, ast.Constant(type(node.op).__name__), ast.Constant(node.lineno), ast.Constant(texts)], node)

    def visit_FunctionDef(self, node):
        # Type hints are documentation: they are never evaluated.
        node.returns = None
        for arg in node.args.args + node.args.kwonlyargs + node.args.posonlyargs + [x for x in (node.args.vararg, node.args.kwarg) if x]:
            arg.annotation = None
        self.generic_visit(node)
        return node

    def visit_AnnAssign(self, node):
        if node.value is None:
            return ast.copy_location(ast.Pass(), node)  # `x: int` declares, assigns nothing (a class body may hold only these).
        return self.visit_Assign(ast.copy_location(ast.Assign(targets=[node.target], value=node.value), node))

    def visit_Attribute(self, node):
        text = ast.unparse(node.value)
        self.generic_visit(node)
        if isinstance(node.ctx, ast.Load):
            return helper("_attr", [node.value, ast.Constant(node.attr), ast.Constant(text)], node)
        return node

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            # obj.method(...): one guarded call that also records what it did to a structure.
            texts = (ast.unparse(node.func.value), ast.unparse(node.args[0]) if node.args else "")
            args = [self.visit(a) for a in node.args]
            keywords = [ast.keyword(arg=k.arg, value=self.visit(k.value)) for k in node.keywords]
            call = ast.Call(func=ast.Name(id="_method", ctx=ast.Load()), args=[self.visit(node.func.value), ast.Constant(node.func.attr), ast.Constant(node.lineno), ast.Constant(texts), *args], keywords=keywords)
            return ast.copy_location(call, node)
        first = ast.unparse(node.args[0]) if node.args else ""
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id in EVENT_CALLS:
            call = ast.Call(func=ast.Name(id="_fcall", ctx=ast.Load()), args=[node.func, ast.Constant(node.func.id), ast.Constant(node.lineno), ast.Constant(first), *node.args], keywords=node.keywords)
            return ast.copy_location(call, node)
        return node

    def visit_For(self, node):
        over = iterated(node.iter)  # `for v in graph[u]`: the loop walks a row of graph
        self.generic_visit(node)
        names = node.target.elts if isinstance(node.target, (ast.Tuple, ast.List)) else [node.target]
        node.body.insert(0, self.emit("LOOP_START", node, ", ".join(ast.unparse(t) for t in names), over))
        return [node, self.emit("LOOP_END", node)]

    def visit_While(self, node):
        self.generic_visit(node)
        node.body.insert(0, self.emit("WHILE_START", node))  # Recorded as LOOP_START; also checked for repeated states.
        return [node, self.emit("LOOP_END", node)]

    def visit_Return(self, node):
        self.generic_visit(node)
        node.value = helper("_returned", [node.value or ast.Constant(None), ast.Constant(node.lineno)], node)
        return node


MAX_NODES = 60
BIT_OPS = {"BitAnd": "&", "BitOr": "|", "BitXor": "^", "LShift": "<<", "RShift": ">>"}
OP_SYMBOLS = {"Add": "+", "Sub": "-", "Mult": "*", "Div": "/", "FloorDiv": "//", "Mod": "%", "Pow": "**", "MatMult": "@", **BIT_OPS}
COMPARE_SYMBOLS = {"Eq": "==", "NotEq": "!=", "Lt": "<", "LtE": "<=", "Gt": ">", "GtE": ">=", "In": "in", "NotIn": "not in", "Is": "is", "IsNot": "is not"}
METHOD_EVENTS = {"append": "STACK_PUSH", "pop": "STACK_POP", "appendleft": "QUEUE_PUSH", "popleft": "QUEUE_POP", "add": "HASHMAP_INSERT", "remove": "HASHMAP_DELETE",
                 "discard": "HASHMAP_DELETE", "get": "HASHMAP_LOOKUP", "heappush": "HEAP_PUSH", "heappop": "HEAP_POP", "heappushpop": "HEAP_PUSH", "heapreplace": "HEAP_POP",
                 "heapify": "HEAP_BUILD", "insort": "ARRAY_WRITE", "insort_left": "ARRAY_WRITE", "insort_right": "ARRAY_WRITE"}


class ModuleView:
    """An allowed module, holding only the names a learning program may use."""
    def __init__(self, values):
        for key, value in values.items():
            setattr(self, key, value)


def module_views():
    import bisect, functools, heapq, itertools as tools, string, typing
    real = {"math": math, "heapq": heapq, "collections": collections, "bisect": bisect, "functools": functools, "itertools": tools, "typing": typing, "string": string}
    views = {name: ModuleView({k: getattr(real[name], k) for k in names if hasattr(real[name], k)}) for name, names in MODULES.items() if name in real}
    views["sys"] = ModuleView({"setrecursionlimit": lambda limit: None, "maxsize": sys.maxsize})
    return views


def execute_worker(payload):
    source = payload["code"]
    seconds = payload.get("budget", MAX_SECONDS)
    events, output = [], io.StringIO()
    truncated = False
    started, ticks = time.monotonic(), 0
    hot = {}
    lines = source.splitlines()
    callstack, call_ids = [], []
    activations = [0]
    line_counts = collections.Counter()  # Exact executions per line, from the line tracer.
    failure = {}  # What a failing read attempted, or the repeated loop state, for the error snapshot.
    stopped_in = [None]  # The learner's frame a limit stopped.
    loop_states = {}  # (activation, line) -> {state digest: first step}
    entry, kinds = payload.get("entry", "solve"), payload.get("kinds") or []
    quiet = bool(payload.get("quiet"))  # A verdict run: the same program and guards, no steps recorded.
    tick_limit = QUIET_TICKS if quiet else MAX_TICKS
    node_ids, keepalive, node_names = {}, [], set()  # Stable node numbers for this run.
    row_of, hot_cells = {}, {}
    tracing = [False]
    objects, kept = {}, []  # Stable numbers for the containers the run touches (kept alive, so ids aren't reused).
    uses = collections.defaultdict(set)  # object number -> how the code used it: push/pop at either end, heap calls
    walks = {}  # object number -> elements of its rows the code read, and whether it then read a row by one of them
    link_fields = {(cls.__name__, field) for cls, fields in ((ListNode, ("next",)), (TreeNode, ("left", "right"))) for field in fields}

    def number(obj):
        if id(obj) not in objects:
            objects[id(obj)] = len(objects) + 1
            kept.append(obj)
        return objects[id(obj)]

    def used(obj, name, args):
        """A list or deque's push or pop: which end it worked on decides, after the run, what the code made of it."""
        if not isinstance(obj, (list, collections.deque)):
            return
        if name == "popleft":
            uses[number(obj)].add("front")
        elif name == "pop" and len(obj) > 1:  # Popping a lone item takes from both ends at once: no evidence either way.
            uses[number(obj)].add("back" if not args or args[0] in (-1, len(obj) - 1) else "front" if args[0] in (0, -len(obj)) else "middle")
        elif name in ("append", "appendleft", "insert", "extend"):
            uses[number(obj)].add("push")

    def walked(obj, key, value):
        """A read of row `key` of obj: a graph is walked when a row is read by a key that an earlier row held."""
        if not isinstance(obj, (dict, list)):
            return
        w = walks.setdefault(number(obj), {"firsts": set(), "seconds": set(), "hit": None})
        if w["hit"] is None:
            try:
                w["hit"] = 0 if key in w["firsts"] else 1 if key in w["seconds"] else None
            except TypeError:
                pass
        if isinstance(value, (list, tuple, set)) and len(value) <= MAX_ITEMS:
            for x in value:
                try:
                    if isinstance(x, (list, tuple)) and len(x) == 2:
                        w["firsts"].add(x[0]); w["seconds"].add(x[1])
                    elif not isinstance(x, (list, dict, set)):
                        w["firsts"].add(x)
                except TypeError:
                    pass

    def node_id(obj):
        if id(obj) not in node_ids:
            node_ids[id(obj)] = len(node_ids) + 1
            keepalive.append(obj)  # Keep ids from being reused while the run lasts.
        return node_ids[id(obj)]

    def linked(obj):
        """An object that is part of a linked structure: a field of it holds a node, or is a link field (one that
        has held a node in this run) now set to None. A design object holding only lists and numbers is not."""
        return any(is_node_object(v) or (v is None and (type(obj).__name__, k) in link_fields) for k, v in vars(obj).items() if not k.startswith("_"))

    def capture(roots):
        """The learner's nodes reachable from this frame: labels, links (next/left/...), children."""
        out, seen, queue = [], set(), list(roots)
        while queue and len(out) < MAX_NODES:
            obj = queue.pop(0)
            if id(obj) in seen:
                continue
            seen.add(id(obj))
            links, kids, attrs = {}, [], {}
            for key, value in list(vars(obj).items())[:24]:
                if key.startswith("_"):
                    continue
                if is_node_object(value):
                    links[key] = node_id(value)
                    link_fields.add((type(obj).__name__, key))
                    queue.append(value)
                elif value is None and (type(obj).__name__, key) in link_fields:
                    links[key] = None  # A link field (it has held a node in this run) that ends here.
                elif isinstance(value, (list, tuple)) and any(is_node_object(x) for x in value[:64]):
                    for i, x in enumerate(value[:64]):
                        if is_node_object(x):
                            kids.append([chr(97 + i) if len(value) == 26 else i, node_id(x)])
                            queue.append(x)
                elif isinstance(value, dict) and any(is_node_object(x) for x in list(value.values())[:64]):
                    for k, x in list(value.items())[:64]:
                        if is_node_object(x):
                            kids.append([bounded(k), node_id(x)])
                            queue.append(x)
                elif key not in LABEL_ATTRS and len(attrs) < 3 and (value is None or isinstance(value, (bool, int, float, str))):
                    attrs[key] = bounded(value)
            out.append({"id": node_id(obj), "label": bounded(node_label(obj)), "cls": type(obj).__name__, "links": links, "kids": kids, "attrs": attrs})
        return out

    def as_matrix(value):
        return (isinstance(value, list) and 0 < len(value) <= 40 and all(isinstance(r, list) for r in value) and 0 < len(value[0]) <= 40
                and all(len(r) == len(value[0]) for r in value) and all(x is None or isinstance(x, (bool, int, float, str)) for r in value for x in r))

    def as_graph(value, second=False):
        """An adjacency list (a dict of neighbour collections, or a list of rows of node numbers or (neighbour,
        weight) pairs) as a drawn graph. Only a candidate: it is drawn as a graph only if the run walks it (see
        walked); `second`: pairs are (weight, neighbour), as the walk showed."""
        edges, labels = [], None
        if isinstance(value, dict) and all(isinstance(v, (list, set, tuple)) for v in value.values()):
            labels = list(value.keys())
            for u, vs in value.items():
                for v in list(vs):
                    pair = isinstance(v, (list, tuple)) and len(v) == 2
                    target = (v[1] if second else v[0]) if pair else v
                    if isinstance(target, (list, dict, set)):
                        return None
                    if target not in labels and len(labels) < MAX_NODES:
                        labels.append(target)
                    if target in labels:
                        edges.append([labels.index(u), labels.index(target), (v[0] if second else v[1]) if pair else None])
        elif isinstance(value, list) and value and all(isinstance(r, (list, tuple)) for r in value):
            n = len(value)
            ints = lambda r: all(isinstance(x, int) and not isinstance(x, bool) for x in r)
            if all(ints(r) and all(0 <= x < n for x in r) for r in value):
                labels = list(range(n))
                edges = [[u, v, None] for u, r in enumerate(value) for v in r]
            elif all(all(isinstance(x, (list, tuple)) and len(x) == 2 and ints(x) and 0 <= x[1 if second else 0] < n for x in r) for r in value):
                labels = list(range(n))
                edges = [[u, x[1], x[0]] if second else [u, x[0], x[1]] for u, r in enumerate(value) for x in r]
        if labels is None or not labels or len(labels) > MAX_NODES:
            return None
        pairs = {(e[0], e[1]) for e in edges}
        directed = any((v, u) not in pairs for u, v in pairs)
        if not directed:  # Draw each undirected edge once.
            edges = [e for e in edges if e[0] <= e[1] or (e[1], e[0]) not in pairs]
        return {"type": "graph", "labels": [bounded(x) for x in labels], "edges": edges[:240], "directed": directed}

    def state(locals_):
        structures, variables, refs, roots = [], [], {}, []
        items = []
        for name, value in locals_.items():
            if name.startswith("_") or callable(value) or isinstance(value, ModuleView):
                continue
            if name == "self" and type(value).__module__ == "student" and not isinstance(value, type):
                # The object a method runs on: its own fields are what it holds (a stack's list, a cache's map, a
                # node's value and links). It is a node in the drawing only if it is linked into a structure.
                items += [(f"self.{k}", v) for k, v in list(vars(value).items())[:16] if not k.startswith("_") and not callable(v)]
                if not linked(value):
                    continue
            items.append((name, value))
        for name, value in items:
            if is_node_object(value):
                roots.append(value)
                refs[name] = node_id(value)
                node_names.add(name)
                continue
            if value is None and name in node_names:
                refs[name] = None  # A node pointer that has run off the end.
                continue
            if isinstance(value, (list, tuple, collections.deque)) and any(is_node_object(x) for x in list(value)[:MAX_ITEMS]):
                seq = list(value)[:MAX_ITEMS]
                roots += [x for x in seq if is_node_object(x)]
                structures.append({"id": name, "type": "array", "oid": number(value), "values": [node_text(x) if is_node_object(x) else bounded(x) for x in seq],
                                   "nodeRefs": [node_id(x) if is_node_object(x) else None for x in seq], "length": len(value), "highlights": hot.get(name, [])})
                continue
            # An adjacency-shaped dict or list also carries its graph drawing, used if the run turns out to walk it.
            graph = [as_graph(value), as_graph(value, True)] if isinstance(value, (dict, list)) and value else None
            graph = {"graph": graph, "oid": number(value)} if graph and (graph[0] or graph[1]) else {}
            if as_matrix(value):  # A grid, a DP table, a board: rows of equal length.
                structures.append({"id": name, "type": "matrix", "rows": [[bounded(x) for x in row[:24]] for row in value[:24]], "shape": [len(value), len(value[0])], "hot": hot_cells.get(name, []), **graph})
                continue
            if isinstance(value, str) and len(value) <= 1:
                variables.append({"id": name, "value": value})  # One character is a value, not a sequence.
            elif isinstance(value, (list, tuple, str, collections.deque)):
                values = bounded(value) if not isinstance(value, str) else list(value[:MAX_ITEMS])
                entry_ = {"id": name, "type": "string" if isinstance(value, str) else "array", "values": values, "length": len(value), "highlights": hot.get(name, []), **graph}
                if not isinstance(value, str):
                    entry_["oid"] = number(value)
                structures.append(entry_)
            elif isinstance(value, dict):
                objects = [v for v in list(value.values())[:MAX_ITEMS] if is_node_object(v)]
                roots += objects
                structures.append({"id": name, "type": "hashmap", "entries": [{"key": bounded(k), "value": node_text(v) if is_node_object(v) else bounded(v)} for k, v in list(value.items())[:MAX_ITEMS]], **graph})
            elif isinstance(value, (set, frozenset)):
                structures.append({"id": name, "type": "hashset", "values": bounded(value)})
            else:
                variables.append({"id": name, "value": bounded(value)})
        # Nodes the calls below this one are holding: a recursive call still sees the whole tree or list.
        frame, hops = sys._getframe(1), 0
        while frame is not None and hops < 450:
            if frame.f_code.co_filename == "<student>":
                held = []
                for key, value in list(frame.f_locals.items()):
                    if key == "self" and type(value).__module__ == "student" and not isinstance(value, type):
                        held += [v for k, v in vars(value).items() if not k.startswith("_")]  # Its fields, and itself if linked.
                        if linked(value):
                            held.append(value)
                    else:
                        held.append(value)
                for value in held:
                    if is_node_object(value):
                        roots.append(value)
                    elif isinstance(value, (list, tuple, collections.deque)) and value and any(is_node_object(x) for x in list(value)[:20]):
                        roots += [x for x in list(value)[:MAX_ITEMS] if is_node_object(x)]
            frame, hops = frame.f_back, hops + 1
        if roots or refs:
            structures.append({"id": "@nodes", "type": "nodes", "nodes": capture(roots), "refs": refs})
        return {"structures": structures, "variables": variables, "callstack": list(callstack)}

    def stopping(**what):
        """A limit stops the program: note it, and the learner's frame it stopped in (a limit raised by the line
        tracer leaves that frame out of the exception's traceback)."""
        failure.update(what)
        frame = sys._getframe(2)
        while frame and frame.f_code.co_filename != "<student>":
            frame = frame.f_back
        stopped_in[0] = frame
        raise ExecutionLimit(LIMIT_MESSAGE)

    def check():
        nonlocal ticks
        ticks += 1
        if ticks > tick_limit:
            stopping(limit="steps", steps=tick_limit)
        check_time()

    def check_time():
        if time.monotonic() - started > seconds:
            stopping(limit="time", seconds=round(seconds, 2))

    def emit(kind, line, locals_, detail="", metadata=None):
        nonlocal truncated
        check()
        if not tracing[0]:
            return  # Definitions run before the traced program starts.
        if len(events) >= MAX_EVENTS:
            truncated = True
            return
        events.append({"id": len(events), "type": kind, "line": line, "source": lines[line - 1].strip() if 0 < line <= len(lines) else "", "detail": detail, "meta": metadata or {}, "state": state(locals_)})

    def written_field(loc, chain):
        """The object and field `curr.next` names, and the value now in it."""
        names = chain.split(".")
        owner = loc.get(names[0], frame_globals.get(names[0])) if names[0] != "self" or "self" in loc else None
        for name in names[1:-1]:
            owner = getattr(owner, name, None)
        return owner, names[-1], getattr(owner, names[-1], None) if owner is not None else None

    def mark(kind, line, detail, root, targets):
        if quiet:  # Every loop iteration passes here: the step and time limits hold without recording anything.
            check()
            return
        frame = sys._getframe(1)
        loc = frame.f_locals
        if kind == "WRITE":
            kind = "HASHMAP_INSERT" if isinstance(loc.get(root), dict) else "ARRAY_WRITE"
        if kind == "ATTR_WRITE":
            # A link write is one that puts a node in a field, or ends a link field (one that has held a node) with None.
            owner, field, value = written_field({**frame.f_globals, **loc}, root)
            if is_node_object(value):
                link_fields.add((type(owner).__name__, field))
            kind = "LINK_WRITE" if is_node_object(value) or (value is None and (type(owner).__name__, field) in link_fields) else "STATE_CHANGE"
        if kind == "LOOP_START" and root:
            emit(kind, line, loc, f"{detail} updated." if detail else "The loop state changed.", {"over": root})
            return
        if kind == "WHILE_START":
            emit("LOOP_START", line, loc, "The loop state changed.", {"loop": "while"})
            # The proof compares everything the loop can depend on: the frame's own names and the program's globals.
            shared = {f"global {k}": v for k, v in frame.f_globals.items() if not k.startswith("_") and k not in loc and not callable(v) and not isinstance(v, ModuleView)} if frame.f_globals is not loc else {}
            repeat_check({**shared, **loc}, line)
            return
        emit(kind, line, loc, f"{detail} updated." if detail else "The loop state changed.", {"targets": list(targets)} if targets else None)

    def repeat_check(loc, line):
        """A while loop whose local state repeats exactly can never finish: the subset is deterministic."""
        digest = state_digest(loc)
        if digest is None:
            return
        step = len(events) - 1 if events and events[-1]["type"] == "LOOP_START" and events[-1]["line"] == line else None
        seen = loop_states.setdefault((call_ids[-1] if call_ids else 0, line), {})
        if digest in seen:
            failure.update(cycle={"line": line, "first": seen[digest], "repeat": step})
            first = f"step {seen[digest] + 1}" if seen[digest] is not None else "an earlier iteration"
            raise ExecutionLimit(f"Infinite loop: the while loop on line {line} came back to exactly the state it had at {first}. Nothing changed between those iterations, so it would repeat forever.")
        seen[digest] = step

    compares = {"Eq": operator.eq, "NotEq": operator.ne, "Lt": operator.lt, "LtE": operator.le, "Gt": operator.gt, "GtE": operator.ge, "In": lambda a, b: a in b, "NotIn": lambda a, b: a not in b, "Is": operator.is_, "IsNot": operator.is_not}
    def compare(a, b, op, text, line, sides=("", "")):
        try:
            result = compares[op](a, b)
        except TypeError:
            failure.update(compare={"text": text, "op": COMPARE_SYMBOLS[op], "ltext": sides[0], "rtext": sides[1], "ltype": type(a).__name__, "rtype": type(b).__name__})
            raise
        if quiet:
            return result
        kind = "HASHMAP_LOOKUP" if op in {"In", "NotIn"} and isinstance(b, (dict, set)) else "COMPARE"
        # Membership presence and branch result differ for `not in`.
        emit(kind, line, sys._getframe(1).f_locals, f"{text} is {result}.", {"expression": text, "left": bounded(a), "right": bounded(b), "result": bool(result), "found": a in b if kind == "HASHMAP_LOOKUP" else None})
        return result

    def access(obj, key, name, line, index, loc=None):
        loc = sys._getframe(1).f_locals if loc is None else loc
        # A defaultdict or Counter answers a missing key (and a defaultdict stores it): the read says it wasn't there.
        present = key in obj if isinstance(obj, dict) else True
        try:
            value = obj[key]
        except (IndexError, KeyError, TypeError) as exc:
            # Record what was attempted; the exception still stops the program.
            sized = isinstance(obj, (list, tuple, str, dict, collections.deque, range))
            kind = ("none" if obj is None else "dict" if isinstance(obj, dict) and isinstance(exc, KeyError) else "badkey" if sized and isinstance(exc, TypeError)
                    else "type" if isinstance(exc, TypeError) else "sequence")
            failure.update(access={"structure": name, "key": bounded(key), "index": index, "size": len(obj) if sized else None, "kind": kind, "of": type(obj).__name__, "keytype": type(key).__name__})
            raise
        if quiet:
            return value
        if isinstance(key, int) and not isinstance(key, bool):
            hot[name] = [key if key >= 0 else len(obj) + key]
            if isinstance(value, list):
                row_of[id(value)] = (name, key if key >= 0 else len(obj) + key)  # grid[i] → the row of grid
            if id(obj) in row_of:
                grid, row = row_of[id(obj)]
                hot_cells[grid] = [[row, key if key >= 0 else len(obj) + key]]  # grid[i][j]
        walked(obj, key, value)
        emit("HASHMAP_LOOKUP" if isinstance(obj, dict) else "ARRAY_ACCESS", line, loc, f"Read {name}[{key}] → {bounded(value)}." if present else f"Read {name}[{key}] → {bounded(value)}: the key wasn't there, so {name} supplied its default.",
             {"structure": name, "key": bounded(key), "value": bounded(value), "found": present, "index": index})
        hot_cells.clear()  # A grid cell is "just read" only at the step that read it.
        return value

    binops = {"Add": operator.add, "Sub": operator.sub, "Mult": operator.mul, "Div": operator.truediv, "FloorDiv": operator.floordiv, "Mod": operator.mod, "Pow": operator.pow, "BitAnd": operator.and_, "BitOr": operator.or_, "BitXor": operator.xor, "LShift": operator.lshift, "RShift": operator.rshift}
    def binary(a, b, op, line, texts=("", "", "")):
        return operate(a, b, op, line, texts, False, sys._getframe(1).f_locals)

    def operate(a, b, op, line, texts, inplace, loc):
        """One arithmetic operation, in place for `op=` (a list's += extends that same list), within the runner's limits."""
        check()
        if op == "Pow" and type(a) is int and type(b) is int and b > 0 and (abs(a).bit_length() - 1) * b > 4096:
            raise ExecutionLimit("The integer exceeds the learning limit.")  # Refused before the big power is computed.
        if op == "Mult" and ((isinstance(a, (str, list, tuple)) and isinstance(b, int) and len(a) * max(0, b) > 10000) or (isinstance(b, (str, list, tuple)) and isinstance(a, int) and len(b) * max(0, a) > 10000)):
            raise ExecutionLimit("That allocation is too large for the learning runner.")
        if op in {"Pow", "LShift", "RShift"} and (not isinstance(b, int) or abs(b) > 1024):
            raise ExecutionLimit("That arithmetic operation exceeds the learning limit.")
        if op == "Add" and isinstance(a, (str, list, tuple, collections.deque)) and hasattr(b, "__len__") and len(a) + len(b) > 10000:
            raise ExecutionLimit("The collection is too large for the learning runner.")
        try:
            result = (inplace_ops if inplace else binops)[op](a, b)
        except (TypeError, ZeroDivisionError):
            failure.update(op={"op": OP_SYMBOLS.get(op, op), "text": texts[0], "ltext": texts[1], "rtext": texts[2], "ltype": type(a).__name__, "rtype": type(b).__name__})
            raise
        if isinstance(result, int) and result.bit_length() > 4096:
            raise ExecutionLimit("The integer exceeds the learning limit.")
        if op in BIT_OPS and type(a) is int and type(b) is int and tracing[0]:
            emit("BIT_OP", line, loc, f"{a} {BIT_OPS[op]} {b} → {result}.", {"op": BIT_OPS[op], "left": a, "right": b, "result": result})
        return result

    inplace_ops = {"Add": operator.iadd, "Sub": operator.isub, "Mult": operator.imul, "Div": operator.itruediv, "FloorDiv": operator.ifloordiv, "Mod": operator.imod, "Pow": operator.ipow,
                   "BitAnd": operator.iand, "BitOr": operator.ior, "BitXor": operator.ixor, "LShift": operator.ilshift, "RShift": operator.irshift, "MatMult": operator.imatmul}

    def augment(value, operand, op, line, texts):
        """`name op= operand`: the new value for name."""
        return operate(value, operand, op, line, texts, True, sys._getframe(1).f_locals)

    def augitem(obj, key, operand, op, line, texts, name, index):
        """`obj[key] op= operand`, obj and key evaluated once: read the item (a recorded read), operate, write it back."""
        loc = sys._getframe(1).f_locals
        current = access(obj, key, name, line, index, loc)
        obj[key] = operate(current, operand, op, line, texts, True, loc)

    def augattr(obj, name, operand, op, line, texts, text):
        """`obj.name op= operand`, obj evaluated once."""
        store(obj, name, text)
        setattr(obj, name, operate(attr(obj, name, text), operand, op, line, texts, True, sys._getframe(1).f_locals))

    def handled():
        """The first step of every except block: a runner limit is never the program's to catch; any other failure
        is now handled, so what it recorded no longer explains anything."""
        caught = sys.exc_info()[1]
        if isinstance(caught, ExecutionLimit):
            raise caught
        failure.clear()

    def raising(exc, line):
        """`raise X(...)`: the program's own exception, noted so its explanation says the program raised it."""
        failure.update(raised={"type": exc.__name__ if isinstance(exc, type) else type(exc).__name__, "line": line})
        return exc

    def attr(obj, name, text=""):
        """Attribute reads: anything on the learner's own objects; on built-in values only their safe methods."""
        if obj is None:
            failure.update(attr={"text": text, "name": name, "none": True})
            raise AttributeError(f"'NoneType' object has no attribute '{name}'")
        if isinstance(obj, super) and (name in DUNDER_METHODS or not name.startswith("_")):
            return getattr(obj, name)  # super().__init__(...) and a parent class's own methods.
        if is_node_object(obj) or (isinstance(obj, type) and obj.__module__ == "student") or isinstance(obj, ModuleView) or name in SAFE_ATTRS:
            try:
                return getattr(obj, name)
            except AttributeError:
                failure.update(attr={"text": text, "name": name, "of": type(obj).__name__ if not isinstance(obj, ModuleView) else "module"})
                raise
        if hasattr(type(obj), name):
            failure.update(attr={"text": text, "name": name, "of": type(obj).__name__, "blocked": True})
            raise AttributeError(f"'{name}' is not available on {type(obj).__name__} in the learning runner.")
        failure.update(attr={"text": text, "name": name, "of": type(obj).__name__})
        raise AttributeError(f"'{type(obj).__name__}' object has no attribute '{name}'")

    def store(obj, name, text):
        """Before `x.field = value`: setting a field on None fails here, where the failure can name x."""
        if obj is None:
            failure.update(attr={"text": text, "name": name, "none": True, "store": True})
            raise AttributeError(f"'NoneType' object has no attribute '{name}'")

    def record(kind, name, line, args, result, loc):
        shown = ", ".join(node_text(a) if is_node_object(a) else str(bounded(a)) for a in args)
        emit(kind, line, loc, f"{name}({shown}) → {node_text(result) if is_node_object(result) else bounded(result)}.")

    def failed_call(name, text, target, args):
        """A built-in method or heap call that raised: what it was called on, its size and first argument."""
        sized = isinstance(target, (list, tuple, str, dict, set, collections.deque))
        failure.update(method={"text": text, "name": name, "size": len(target) if sized else None, "args": [bounded(a) for a in args[:1]]})

    def method(obj, name, line, texts, *args, **kwargs):
        check()
        if obj is None:
            failure.update(method={"text": texts[0], "name": name, "none": True})
            raise AttributeError(f"'NoneType' object has no attribute '{name}'")
        if name in {"append", "add", "appendleft", "insert", "extend"} and hasattr(obj, "__len__") and len(obj) >= 10000:
            raise ExecutionLimit("The collection is too large for the learning runner.")
        bound = attr(obj, name, texts[0])
        own = is_node_object(obj) or isinstance(obj, (type, super)) or type(obj).__module__ == "student"
        used(obj, name, args)
        if isinstance(obj, ModuleView) and name in HEAP_CALLS and args and isinstance(args[0], list):
            uses[number(args[0])].add("heap")
        try:
            result = bound(*args, **kwargs)
        except (IndexError, KeyError, ValueError, TypeError):
            if not own and not failure:  # A failure inside the learner's own method was recorded where it happened.
                module = isinstance(obj, ModuleView)
                failed_call(name, texts[1] if module else texts[0], args[0] if module and args else obj, args[1:] if module else args)
            raise
        if name == "elements" and isinstance(obj, collections.Counter):
            return stepped(result)  # Counter({1: 10**9}).elements() is a C iterator: each item is a step.
        if quiet or own or (isinstance(obj, ModuleView) and name not in EVENT_CALLS):
            return result  # Calls into the learner's own methods are recorded by the call tracer.
        record(METHOD_EVENTS.get(name, "STATE_CHANGE"), name, line, args, result, sys._getframe(1).f_locals)
        return result

    def fcall(fn, name, line, text, *args, **kwargs):
        check()
        if name in HEAP_CALLS and args and isinstance(args[0], list):
            uses[number(args[0])].add("heap")
        try:
            result = fn(*args, **kwargs)
        except (IndexError, KeyError, ValueError, TypeError):
            if not failure:
                failed_call(name, text, args[0] if args else None, args[1:])
            raise
        if quiet:
            return result
        record(METHOD_EVENTS.get(name, "STATE_CHANGE"), name, line, args, result, sys._getframe(1).f_locals)
        return result

    def returned(value, line):
        emit("RETURN", line, sys._getframe(1).f_locals, f"Returned {bounded(value)}.", {"value": bounded(value)})
        return value

    def brief(value):
        if is_node_object(value):
            return node_text(value)
        if isinstance(value, (list, tuple, collections.deque)) and len(value) > 6:
            return bounded(list(value)[:6]) + ["…"]
        return bounded(value)

    def budget(frame, event, arg):
        check()
        return budget

    def trace(frame, event, arg):
        code = frame.f_code
        if code.co_filename != "<student>":
            check_time()  # Library code (heapq.merge, Counter) is not stepped, but it cannot outlast the budget.
            return None
        if code.co_name.startswith("<") or not tracing[0]:
            # Module code, lambdas, generator expressions and the definitions run are not calls worth
            # showing, but every one of their steps counts against the same execution budget.
            return budget(frame, event, arg)
        check()
        name = re.sub(r"^.*<locals>\.", "", code.co_qualname)  # A nested helper is just "pick", a method "Trie.insert".
        if event == "call":
            callstack.append(name)
            activations[0] += 1
            call_ids.append(activations[0])  # Each call is its own activation for loop-state comparison.
            count = code.co_argcount + code.co_kwonlyargcount
            params = list(code.co_varnames[:count]) + [code.co_varnames[count + k] for k, flag in enumerate(f for f in (0x04, 0x08) if code.co_flags & f)]  # with *args, **kwargs
            args = {p: brief(frame.f_locals.get(p)) for p in params if p != "self"}
            # `order` keeps the parameters' order: the API's JSON sorts object keys, so args alone would arrive alphabetised.
            emit("RECURSION_CALL", frame.f_lineno, frame.f_locals, f"Enter {name}({', '.join(f'{k}={v}' for k, v in args.items())}).", {"call": {"id": call_ids[-1], "fn": name, "args": args, "order": list(args), "depth": len(callstack)}})
        if event == "return":
            emit("RECURSION_RETURN", frame.f_lineno, frame.f_locals, f"Leave {name} → {brief(arg)}.", {"ret": {"id": call_ids[-1] if call_ids else 0, "value": brief(arg)}})
            if callstack:
                callstack.pop()
                call_ids.pop()
        if event == "line" and frame.f_code.co_name != "<module>":
            # Line events precede execution: they count how often each line ran, never its effect.
            line_counts[frame.f_lineno] += 1
        return trace

    def safe_range(*args):
        result = range(*args)
        if len(result) > 10000:
            raise ExecutionLimit("Use a range of at most 10,000 items.")
        return result

    def safe_print(*args, sep=" ", end="\n", **kwargs):
        """print as Python prints (sep, end, a value's own str), into the run's console, at most 4,000 characters."""
        if output.tell() > 4000:
            raise ExecutionLimit("Console output limit reached.")
        print(*(str(a)[:500] for a in args), sep=sep if isinstance(sep, str) else " ", end=end if isinstance(end, str) else "\n", file=output)

    def safe_type(value, *rest):
        if rest:
            raise TypeError("type() with three arguments makes a class, which the learning runner doesn't support; use class instead.")
        return type(value)

    def safe_getattr(obj, name, *default):
        if not isinstance(name, str) or name.startswith("_") or name in BLOCKED_ATTRS:
            raise AttributeError(f"getattr can't read '{name}' in the learning runner.")
        try:
            return attr(obj, name, "")
        except AttributeError:
            if default:
                failure.pop("attr", None)
                return default[0]
            raise

    def safe_hasattr(obj, name):
        try:
            safe_getattr(obj, name)
            return True
        except AttributeError:
            failure.pop("attr", None)
            return False

    def safe_setattr(obj, name, value):
        if not (is_node_object(obj) or type(obj).__module__ == "student") or not isinstance(name, str) or name.startswith("_"):
            raise AttributeError(f"setattr can only set plain fields on your own objects, not '{name}'.")
        setattr(obj, name, value)

    def safe_pow(base, exponent, mod=None):
        if mod is None and isinstance(exponent, int) and abs(exponent) > 4096:
            raise ExecutionLimit("That power exceeds the learning limit. Use pow(base, exp, mod).")
        if mod is None and type(base) is int and type(exponent) is int and exponent > 0 and abs(base).bit_length() * exponent > BIG_BITS:
            raise ExecutionLimit("The integer exceeds the learning limit.")
        return pow(base, exponent, mod) if mod is not None else pow(base, exponent)

    def safe_sum(iterable, start=0):
        if isinstance(start, (int, float, str)):
            return sum(iterable, start)  # Numbers add in C at no growing cost; sum(strs, "") raises as usual.
        # sum(lists, []) copies the growing total at every item: added in Python so each item is a step.
        total = start
        for item in iterable:
            check()
            if isinstance(total, (str, list, tuple)) and hasattr(item, "__len__") and len(total) + len(item) > 10000:
                raise ExecutionLimit("The collection is too large for the learning runner.")
            total = total + item
        return total

    def stepped(source):
        """Items of an iterator that C code may consume (sum, max, sorted): each item is a step."""
        for item in source:
            check()
            yield item

    def stepped_call(make):
        return lambda *args, **kwargs: stepped(make(*args, **kwargs))

    def safe_iter(*args):
        if len(args) != 2:
            return iter(*args)
        call, sentinel = args  # iter(callable, sentinel) calls until the sentinel: without steps, iter(int, 1) never stops.
        if not callable(call):
            raise TypeError("iter(v, w): v must be callable")
        def calls():
            while True:
                check()
                value = call()
                if value == sentinel:
                    return
                yield value
        return calls()

    def sized(limit_bits, compute):
        """Big-integer library calls whose cost grows with the result: refused, before computing, when
        a bound on the result's size passes BIG_BITS."""
        def call(*args):
            if all(type(a) is int for a in args) and limit_bits(*args) > BIG_BITS:
                raise ExecutionLimit("The integer exceeds the learning limit.")
            return compute(*args)
        return call

    def safe_prod(iterable, *, start=1):
        total = start
        for item in iterable:
            check()
            total = total * item
            if type(total) is int and total.bit_length() > BIG_BITS:
                raise ExecutionLimit("The integer exceeds the learning limit.")
        return total

    views = module_views()
    for name in MODULES["itertools"]:
        if hasattr(views["itertools"], name):
            setattr(views["itertools"], name, stepped_call(getattr(views["itertools"], name)))
    smaller = lambda n, k=None: n if k is None else max(0, min(k, n - k))
    views["math"].comb = sized(lambda n, k: smaller(n, k) * n.bit_length(), math.comb)
    views["math"].perm = sized(lambda n, k=None: (n if k is None else max(0, min(k, n))) * n.bit_length(), math.perm)
    views["math"].factorial = sized(lambda n: n * n.bit_length(), math.factorial)
    views["math"].lcm = sized(lambda *ints: sum(i.bit_length() for i in ints), math.lcm)
    views["math"].prod = safe_prod

    def guarded_import(name, globals_=None, locals_=None, fromlist=(), level=0):
        if level or name not in views:
            raise ImportError(f"{name} isn't available in the learning runner.")
        return views[name]

    safe = {name: getattr(builtins, name) for name in SAFE_CALLS}
    safe.update({"range": safe_range, "print": safe_print, "pow": safe_pow, "sum": safe_sum, "iter": safe_iter, "__import__": guarded_import, "__build_class__": builtins.__build_class__,
                 "type": safe_type, "getattr": safe_getattr, "hasattr": safe_hasattr, "setattr": safe_setattr, "ListNode": ListNode, "TreeNode": TreeNode, "Node": Node})
    env = frame_globals = {"__builtins__": safe, "__name__": "student", "_mark": mark, "_access": access, "_compare": compare, "_binary": binary, "_method": method,
           "_fcall": fcall, "_attr": attr, "_store": store, "_returned": returned, "_slice": slice,
           "_augment": augment, "_augitem": augitem, "_augattr": augattr, "_handled": handled, "_raising": raising}
    error, result = None, None
    try:
        original = validate_source(source, entry)
        method = solution_method(original, len(payload["args"])) if entry == "solve" and not any(isinstance(n, ast.FunctionDef) and n.name == "solve" for n in original.body) else None
        tree = Instrument().visit(original)
        ast.fix_missing_locations(tree)
        sys.setrecursionlimit(400)
        sys.settrace(None if quiet else trace)  # Definitions and top-level values run within the budget, but are not shown.
        if method:  # LeetCode's form: LeetCode's standard imports, from the runner's own modules.
            views = module_views()
            env.update({name: getattr(views[module], name) for module, names in MODULES.items() if module != "sys" for name in names if hasattr(views[module], name)})
            env.update({module: views[module] for module in ("math", "heapq", "collections", "bisect", "functools", "itertools", "string", "typing")})
        exec(compile(tree, "<student>", "exec"), env, env)  # Only in the dedicated worker.
        target = getattr(env["Solution"](), method) if method else env.get("solve")
        tracing[0] = not quiet
        if entry == "solve":
            args = [build_input(kind, value) for kind, value in itertools.zip_longest(kinds, payload["args"])][:len(payload["args"])]
            args = link_cycles(args, kinds)
            returned = target(*args)
            result = answer_of(returned, args, payload.get("answer"))
        else:
            # A design problem: build the class, then call each operation in order and collect the answers.
            operations, arguments = payload["args"][0], payload["args"][1]
            spread = lambda value: value if isinstance(value, list) else [value]
            instance = env[entry](*spread(arguments[0] if arguments else []))
            answers = [None]
            for operation, value in zip(operations[1:], arguments[1:]):
                if not isinstance(operation, str) or operation.startswith("_") or not callable(getattr(instance, operation, None)):
                    raise AttributeError(f"{entry} has no method {operation}.")
                answers.append(getattr(instance, operation)(*spread(value)))
            result = result_value(answers)
    except BaseException as exc:
        sys.settrace(None)
        tb = exc.__traceback__
        line, loc = getattr(exc, "lineno", None), {}
        while tb:
            if tb.tb_frame.f_code.co_filename == "<student>":
                line, loc = tb.tb_lineno, tb.tb_frame.f_locals
            tb = tb.tb_next
        if line is None and stopped_in[0] is not None:
            line, loc = stopped_in[0].f_lineno, stopped_in[0].f_locals
        error = {"type": type(exc).__name__, "message": str(exc)[:700], "line": line, "failure": dict(failure)}
        if len(events) < MAX_EVENTS:
            events.append({"id": len(events), "type": "ERROR", "line": line or 1, "source": lines[line - 1].strip() if line and 0 < line <= len(lines) else "", "detail": error["message"], "meta": dict(failure), "state": state(loc)})
    finally:
        sys.settrace(None)
    settle(events, uses, walks)
    return {"events": events, "truncated": truncated, "result": result, "error": error, "stdout": output.getvalue()[:4000], "durationMs": round((time.monotonic() - started) * 1000, 2),
            "lines": {str(k): v for k, v in sorted(line_counts.items())}}


HEAP_CALLS = {"heappush", "heappop", "heapify", "heappushpop", "heapreplace"}


def settle(events, uses, walks):
    """What the whole run showed each structure to be, written into every snapshot so a view never changes mid-run:
    - a list or deque is a heap if heapq kept it, a queue if items left from its front, a stack if they left from
      its back (pushes alone make neither: it is a list);
    - an adjacency-shaped dict or list is a graph if the code walked it: read a row by a key an earlier row held,
      and looped over its rows;
    - an assignment to plain names is a pointer move only if the code uses those names as positions."""
    def kind(use):
        return "heap" if "heap" in use else "queue" if "front" in use else "stack" if "back" in use else None
    over = {e["meta"].get("over") for e in events if e["type"] == "LOOP_START" and e["meta"].get("over")}
    indexers = set()
    for e in events:
        index = e["meta"].get("index") or (e["meta"].get("access") or {}).get("index")
        if e["type"] in ("ARRAY_ACCESS", "HASHMAP_LOOKUP", "ERROR") and isinstance(index, str):
            indexers.update(re.findall(r"[A-Za-z_]\w*", index))
    for e in events:
        for s in e["state"]["structures"]:
            oid, graph = s.pop("oid", None), s.pop("graph", None)
            hit = walks.get(oid, {}).get("hit") if oid else None
            if graph and hit is not None and graph[hit] and s["id"] in over:
                ident = s["id"]
                s.clear()
                s.update({"id": ident, **graph[hit]})
            elif oid and kind(uses.get(oid, ())):
                s["kind"] = kind(uses[oid])
        if e["type"] == "POINTER_MOVE":
            names = e["detail"].removesuffix(" updated.").split(", ")
            held = {v["id"]: v["value"] for v in e["state"]["variables"]}
            if not all(n in indexers and isinstance(held.get(n), int) and not isinstance(held.get(n), bool) for n in names):
                e["type"] = "STATE_CHANGE"


def answer_of(returned, args, answer):
    """What a call of solve answered: the returned node's value (node-value); for an in-place contract (the board
    or list is changed and nothing is returned), the first input as solve left it; otherwise what it returned."""
    if answer == "in-place" and returned is None and args:
        returned = args[0]
    return node_label(returned) if answer == "node-value" and is_node_object(returned) else result_value(returned)


def reference_worker(payload):
    """A reference solution this platform wrote, run once for its answer: not instrumented and not traced, so a
    long search (a whole Sudoku) finishes, but in the same isolated worker with the same builtins and limits.
    Only a server-side reference is ever run this way, never a learner's code."""
    started, error, result = time.monotonic(), None, None
    safe = {name: getattr(builtins, name) for name in SAFE_CALLS}
    safe.update({"__build_class__": builtins.__build_class__, "ListNode": ListNode, "TreeNode": TreeNode, "Node": Node})
    env = {"__builtins__": safe, "__name__": "reference"}
    try:
        exec(compile(payload["code"], "<reference>", "exec"), env, env)
        kinds = payload.get("kinds") or []
        args = link_cycles([build_input(kind, value) for kind, value in itertools.zip_longest(kinds, payload["args"])][:len(payload["args"])], kinds)
        result = answer_of(env["solve"](*args), args, payload.get("answer"))
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc)[:300], "line": None}
    return {"events": [], "truncated": False, "result": result, "error": error, "stdout": "", "durationMs": round((time.monotonic() - started) * 1000, 2), "lines": {}}


def run_reference(code, inputs, kinds=None, entry="solve", answer=None):
    """A reference solution's answers for several inputs, untraced, in one isolated worker."""
    if entry != "solve":
        raise ValueError("A reference runs a solve function.")
    runs = run_worker(code, {"code": code, "cases": inputs, "budget": MAX_SECONDS, "kinds": kinds or [], "entry": entry, "answer": answer, "reference": True})
    return runs + [not_run_trace(len(runs)) for _ in inputs[len(runs):]]


def stopped_trace(seconds):
    """The case a worker was running when it was stopped from outside (its CPU, memory or wall-clock limit):
    the work ran in built-in code the line tracer cannot step through, so only the limit itself is known."""
    return {"events": [], "result": None, "error": {"type": "ExecutionLimit", "message": "Execution limit reached: the runner stopped this case at its time or memory limit, inside a built-in operation the tracer cannot step through. Check loop boundaries or try a smaller input.", "line": None, "failure": {"limit": "stopped"}}, "stdout": "", "durationMs": round(seconds * 1000, 2), "lines": {}}


def not_run_trace(number):
    return {"events": [], "result": None, "error": {"type": "NotRun", "message": f"Not traced: the runner stopped on case {number} before reaching this one.", "line": None}, "stdout": "", "durationMs": 0, "lines": {}}


def run_quiet(code, inputs, kinds=None, entry="solve", answer=None):
    """Answers for inputs whose traces stopped at the trace's limits: the learner's own program in the same isolated
    worker, with the same validation and guards, but recording no steps, so a long search can finish. A verdict
    only: the trace still shows what it recorded."""
    budget = max(1.0, min(QUIET_SECONDS, 7.0 / max(1, len(inputs))))
    runs = run_worker(code, {"code": code, "cases": inputs, "budget": budget, "kinds": kinds or [], "entry": entry, "answer": answer, "quiet": True})
    if len(runs) < len(inputs):
        runs.append(stopped_trace(budget))
        runs += [not_run_trace(len(runs)) for _ in inputs[len(runs):]]
    return runs


def run_isolated(code, args):
    return run_cases(code, [args])[0]


def run_cases(code, inputs, kinds=None, entry="solve", answer=None):
    """Trace several inputs in one worker process. Each case is executed in a fresh namespace
    with its own share of the time budget, so one runaway case cannot starve the others. The worker
    reports each case as it finishes: if it is stopped from outside, the finished cases keep their
    traces and the case it was running reports the execution limit."""
    budget = max(0.6, min(MAX_SECONDS, 6.0 / max(1, len(inputs))))
    runs = run_worker(code, {"code": code, "cases": inputs, "budget": budget, "kinds": kinds or [], "entry": entry, "answer": answer})
    if len(runs) < len(inputs):
        runs.append(stopped_trace(budget))
        runs += [not_run_trace(len(runs)) for _ in inputs[len(runs):]]
    return runs


def run_worker(code, payload):
    """The worker's finished case traces, in order. Raises when the worker could not start the run at all."""
    validate_source(code, payload.get("entry", "solve"))
    mode = os.environ.get("EXECUTION_MODE", "local")
    if os.environ.get("APP_ENV") == "production" and mode != "docker":
        raise ValueError("Public execution requires EXECUTION_MODE=docker.")
    body = json.dumps(payload)
    if len(body) > WORKER_INPUT:
        raise ValueError("These inputs are too large for the learning runner. Use smaller cases.")
    if mode == "docker":
        container = "visual-dsa-" + uuid.uuid4().hex
        command = ["docker", "run", "--name", container, "--rm", "-i", "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--memory=192m", "--cpus=0.5", "--pids-limit=16", "--user=65534:65534", os.environ.get("EXECUTION_IMAGE", "visual-dsa-worker"), "python", "-I", "app.py", "--worker"]
    else:
        command = [sys.executable, "-I", str(ROOT / "app.py"), "--worker"]
    try:
        proc = subprocess.run(command, input=body, capture_output=True, text=True, timeout=WORKER_SECONDS, cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        out = proc.stdout
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        out = out.decode("utf-8", "replace") if isinstance(out, bytes) else out
    finally:
        if mode == "docker":
            try:
                subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
    records = []
    for line in out.splitlines():
        try:
            records.append(json.loads(line))
        except ValueError:
            break  # A line cut off when the worker was stopped.
    if not records or records[0] != {"ready": True}:
        raise ValueError("Execution worker stopped. Check the runner configuration or reduce memory use.")
    return records[1:]


def windows_worker_limits():
    """Per-worker memory/CPU/process caps on Windows, independent of Python guards."""
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class IOCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IOCounters), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    limits = ExtendedLimits()
    limits.BasicLimitInformation.PerProcessUserTimeLimit = WORKER_CPU_SECONDS * 10000000
    limits.BasicLimitInformation.ActiveProcessLimit = 1
    limits.BasicLimitInformation.LimitFlags = 0x2 | 0x8 | 0x100 | 0x2000
    limits.ProcessMemoryLimit = 192 * 1024 * 1024
    job = kernel.CreateJobObjectW(None, None)
    if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        raise RuntimeError("Cannot apply Windows worker resource limits.")
    return job  # Keep this handle alive until the process exits.


# Worker exits before importing Flask or loading any credentials/database.
if __name__ == "__main__" and "--worker" in sys.argv:
    if os.name == "nt":
        worker_job = windows_worker_limits()
    else:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (192 * 1024 * 1024, 192 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (WORKER_CPU_SECONDS, WORKER_CPU_SECONDS))
    request_ = json.loads(sys.stdin.read(WORKER_INPUT))
    print(json.dumps({"ready": True}), flush=True)
    run_case = reference_worker if request_.get("reference") else execute_worker  # A platform reference runs untraced.
    for args in request_["cases"]:  # One line per finished case, so a stopped worker still reports the cases it finished.
        print(json.dumps(run_case({"code": request_["code"], "args": args, "budget": request_["budget"], "kinds": request_.get("kinds"), "entry": request_.get("entry", "solve"), "answer": request_.get("answer"), "quiet": request_.get("quiet")})), flush=True)
    sys.exit(0)


# ----------------------------- HTTP + SQLite -----------------------------
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException
import errors
import leetcode
import references
import sheets

app = Flask(__name__, static_folder="dist", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 32000
DB = os.environ.get("DSA_DATABASE", str(ROOT / "learning.sqlite3"))
RUNNERS = threading.BoundedSemaphore(2)
GUIDE_REQUESTS = threading.BoundedSemaphore(2)
PROBLEMS = []
VARIANTS = {}  # Changed-requirement problems, keyed by id; never listed in the library.
STAGES = ["Seen", "Understood", "Reproduced", "Explained", "Modified", "Independent", "Transferred"]
TECHNIQUES = ["Direct iteration / brute force", "Hash map / set", "Two pointers", "Sliding window", "Binary search", "Running best / running total",
              "Linked-list pointer rewiring", "Stack", "Queue / deque", "Breadth-first search", "Depth-first search", "Recursion / backtracking",
              "Heap / priority queue", "Trie (prefix tree)", "Dynamic programming", "Bit manipulation"]
TECHNIQUE_NEEDS = {
    "Hash map / set": "remembering earlier information so that a later step can look it up by key instead of searching again",
    "Two pointers": "two positions whose movement is decided by order or symmetry: sorted values, mirrored ends, or a read/write split",
    "Sliding window": "a contiguous range whose summary can be updated as elements enter and leave",
    "Binary search": "a sorted (monotonic) order in which one comparison rules out half of the remaining positions",
    "Running best / running total": "one pass in which a small summary of the prefix (a best value, a minimum or a total) is enough for each next step",
    "Linked-list pointer rewiring": "changing which node a next pointer refers to, in place, while keeping hold of the rest of the list",
    "Stack": "work that must be finished in last-in, first-out order: the most recent unfinished item is the one to resolve next",
    "Queue / deque": "items that are handled or expire in the order they arrived, removed from the front as new ones join at the back",
    "Breadth-first search": "exploring outward in rings of equal distance, so the first arrival at a node or cell is by a shortest path",
    "Depth-first search": "following one path as far as it goes before backing up, to visit everything reachable or combine answers from below",
    "Recursion / backtracking": "a sequence of decisions where each choice leaves a smaller problem of the same shape, undone after it is explored",
    "Heap / priority queue": "repeatedly needing the smallest or largest of a changing collection, with insertions and removals in between",
    "Trie (prefix tree)": "many words or queries that share beginnings, stored once per shared prefix and walked one character at a time",
    "Dynamic programming": "overlapping smaller problems whose answers are reused, stored once and combined by a recurrence",
    "Bit manipulation": "facts about the binary form of numbers that let bitwise operations replace counting, searching or extra memory",
}
firebase = None


@contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def variant_of(p):
    """A changed requirement runs through the same execution, grading and attempt paths."""
    m = p["modification"]
    hidden = {"approach", "modification", "solution", "brute", "tests", "example", "number"}
    return {**{k: v for k, v in p.items() if k not in hidden}, "id": m["id"], "parent": p["id"],
            "title": p["title"] + ": " + m["title"], "statement": m["statement"],
            "decoder": {**p["decoder"], "find": m["statement"], "returns": m["returns"]},
            "example": m["example"], "tests": m["tests"], "solution": m["solution"], "brute": None,
            "hints": [m["question"], m["clue"]], "recall": [m["question"]], "insight": m["insight"]}


def initialize():
    global PROBLEMS, VARIANTS, firebase
    PROBLEMS = json.loads((ROOT / "data" / "problems.json").read_text(encoding="utf-8"))
    VARIANTS = {p["modification"]["id"]: variant_of(p) for p in PROBLEMS if "modification" in p}
    with connect() as db:
        db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY, user_id TEXT, problem_id TEXT, code TEXT, input TEXT, result TEXT, passed INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS execution_sessions(id TEXT PRIMARY KEY, attempt_id TEXT, trace TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS learning_progress(user_id TEXT, problem_id TEXT, stage TEXT, evidence TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id, problem_id));
        CREATE TABLE IF NOT EXISTS saved_code(user_id TEXT, problem_id TEXT, code TEXT, PRIMARY KEY(user_id,problem_id));
        CREATE TABLE IF NOT EXISTS bookmarks(user_id TEXT, problem_id TEXT, PRIMARY KEY(user_id,problem_id));
        -- What the server gave the learner before a commitment: hints, a reference, reasoning prompts (clues: the
        -- highest prompt revealed), the problem's topic, and a live preview that already met every case's goal.
        CREATE TABLE IF NOT EXISTS learning_support(user_id TEXT, problem_id TEXT, hint_level INTEGER DEFAULT 0, revealed INTEGER DEFAULT 0, clues INTEGER DEFAULT 0, topic INTEGER DEFAULT 0, preview_solved INTEGER DEFAULT 0, PRIMARY KEY(user_id,problem_id));
        -- Distinct kinds of evidence (approach commitment, modification, transfer); the first record of each kind is kept,
        -- except a reflection, where the latest written one is kept.
        CREATE TABLE IF NOT EXISTS learning_evidence(user_id TEXT, problem_id TEXT, kind TEXT, detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id,problem_id,kind));
        -- A learner's own practice sheets, and the labs they define for rows without a built-in lab.
        CREATE TABLE IF NOT EXISTS sheets(id TEXT PRIMARY KEY, user_id TEXT, name TEXT, source TEXT, origin TEXT, rows TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS custom_labs(id TEXT PRIMARY KEY, user_id TEXT, sheet_id TEXT, data TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        columns = {row[1] for row in db.execute("PRAGMA table_info(learning_support)")}
        for column in SUPPORT_EVENTS - columns:  # Databases created before these events were recorded.
            db.execute(f"ALTER TABLE learning_support ADD COLUMN {column} INTEGER DEFAULT 0")
    if os.environ.get("FIREBASE_PROJECT_ID"):
        import firebase_admin
        firebase = firebase_admin.initialize_app(options={"projectId": os.environ["FIREBASE_PROJECT_ID"]})


def identity():
    if firebase:
        from firebase_admin import auth
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        try:
            return auth.verify_id_token(token, app=firebase)["uid"]
        except Exception:
            raise PermissionError("Sign in to save your learning progress.")
    if os.environ.get("APP_ENV") == "production":
        raise PermissionError("Firebase authentication must be configured for public use.")
    return "local-learner"


def problem_by_id(id_, uid=None):
    """A built-in lab, a changed requirement, or (for its owner) a lab defined from their own sheet."""
    found = next((p for p in PROBLEMS if p["id"] == id_), None) or VARIANTS.get(id_)
    if found or uid is None or not isinstance(id_, str) or not id_.startswith("custom-"):
        return found
    with connect() as db:
        lab = lab_problem(db, uid, id_)
    return attach_reference(lab) if lab else None


# Whether a page's reference reproduces a lab's own cases, and what it answers for the page's edge cases: worked
# out once per lab content and reference version.
REFERENCE_CHECKS = collections.OrderedDict()


def attach_reference(p):
    """A learner's own lab with the reference this platform wrote for its problem page, when there is one and it
    reproduces every one of the lab's own cases exactly (a lab whose cases the learner changed may not). The reference
    then gives the expected result for the learner's own input, and the page's edge cases join the lab's tests with
    the results it computes, each marked computed. The reference stays on the server: only its results are sent."""
    ref = references.find(p.get("sourceUrl"))
    if not ref or p.get("entry", "solve") != "solve":
        mirrored = mirror_reference(p)  # Otherwise LeetCode's accepted solution, verified the same way.
        return {**p, "reference": mirrored, "sandboxed": True} if mirrored else p
    answer = p.get("answer") or ref.get("answer")
    kinds = [p.get("kinds", {}).get(name) for name in p["params"]]
    check = json.dumps([references.key(p["sourceUrl"]), ref["version"], answer, p["params"], kinds, p["tests"]], sort_keys=True)
    with REFERENCE_LOCK:
        known = REFERENCE_CHECKS.get(check)
    if known is None:
        own = [copy.deepcopy(case["args"]) for case in p["tests"]]
        runs = run_reference(ref["solution"], own + [copy.deepcopy(args) for _, args in ref["edges"]], kinds, "solve", answer)
        judged = {**p, "answer": answer}
        verified = all(not run["error"] and correct(judged, run["result"], case["args"], case["expected"]) for run, case in zip(runs, p["tests"]))
        edges = [dict(name=name, args=args, expected=run["result"], computed=True) for (name, args), run in zip(ref["edges"], runs[len(own):])
                 if verified and not run["error"] and all(args != case["args"] for case in p["tests"])]
        known = (verified, edges)
        with REFERENCE_LOCK:
            REFERENCE_CHECKS[check] = known
            while len(REFERENCE_CHECKS) > 64:
                REFERENCE_CHECKS.popitem(last=False)
    verified, edges = known
    if not verified:
        return p
    # A new list: the lab's own cases (sent to the learner as theirs) stay exactly as they wrote them.
    return {**p, "answer": answer, "reference": ref["solution"], "tests": [*p["tests"], *copy.deepcopy(edges)]}


MIRROR_PENDING = set()


def mirror_reference(p):
    """LeetCode's accepted Python solution for the lab's LeetCode problem (leetcode.py), as the lab's reference only
    if it reproduces every one of the lab's own cases: then it gives the expected result for the learner's own input
    (marked computed). It runs as learner code does: validated, guarded and isolated, never trusted. Reading the
    mirror happens in the background the first time, so no request waits on the network; until then, and whenever
    it can't be read or doesn't reproduce the cases, the lab has no reference."""
    slug = p.get("leetcode")
    if not slug or p.get("entry", "solve") != "solve":
        return None
    found = leetcode._pages.get(slug)
    if found is None:
        with REFERENCE_LOCK:
            start = slug not in MIRROR_PENDING
            MIRROR_PENDING.add(slug)
        if start:
            def read():
                try:
                    leetcode.page(slug, sheets.fetch, sheets.decode)
                except Exception:  # Offline or changed: the lab simply has no reference.
                    pass
                finally:
                    with REFERENCE_LOCK:
                        MIRROR_PENDING.discard(slug)
            threading.Thread(target=read, daemon=True).start()
        return None
    code = found.get("python")
    if not code:
        return None
    kinds = [p.get("kinds", {}).get(name) for name in p["params"]]
    check = json.dumps(["leetcode", slug, hashlib.sha256(code.encode()).hexdigest(), p.get("answer"), p["params"], kinds, p["tests"]], sort_keys=True)
    with REFERENCE_LOCK:
        known = REFERENCE_CHECKS.get(check)
    if known is None:
        try:
            runs = run_quiet(code, [copy.deepcopy(case["args"]) for case in p["tests"]], kinds, "solve", p.get("answer"))
            known = all(not run["error"] and correct(p, run["result"], case["args"], case["expected"]) for run, case in zip(runs, p["tests"]))
        except ValueError:  # Outside what the runner runs: no reference.
            known = False
        with REFERENCE_LOCK:
            REFERENCE_CHECKS[check] = known
            while len(REFERENCE_CHECKS) > 64:
                REFERENCE_CHECKS.popitem(last=False)
    return code if known else None


def lab_problem(db, uid, id_):
    row = db.execute("SELECT l.data,l.sheet_id,s.name,s.rows FROM custom_labs l LEFT JOIN sheets s ON s.id=l.sheet_id AND s.user_id=l.user_id WHERE l.id=? AND l.user_id=?", (id_, uid)).fetchone()
    if not row:
        return None
    rows = json.loads(row["rows"]) if row["rows"] else []
    number = next((i + 1 for i, r in enumerate(rows) if r.get("lab") == id_), 1)
    data = json.loads(row["data"])
    if not data.get("leetcode") and rows[number - 1:number] and rows[number - 1].get("lab") == id_:
        # A lab built before labs recorded it: the LeetCode problem its own sheet row links, if any.
        data["leetcode"] = leetcode.row_slug(rows[number - 1])
    return sheets.as_problem(id_, data, row["sheet_id"], row["name"] or "Your sheet", number)


def valid_args(problem, args):
    exemplar = problem["tests"][0]["args"]
    if not isinstance(args, list) or len(args) != len(exemplar):
        raise ValueError(f"Expected {len(exemplar)} problem parameters.")
    if problem.get("custom"):  # The learner's own lab: plain data shaped like their first case.
        for value, sample in zip(args, exemplar):
            sheets.plain(value)
            if type(value) is not type(sample) and not ({type(value), type(sample)} <= {int, float}):
                raise ValueError("Each parameter must have the same type as in your first case.")
        return
    for value, sample in zip(args, exemplar):
        if type(value) is not type(sample):
            raise ValueError("Each parameter must match the example's type.")
        flat = isinstance(sample, list) and all(type(x) is int for x in sample)
        if isinstance(value, list) and not flat:  # Trees, grids, graphs, word lists and design operations: plain, bounded data.
            sheets.plain(value)
            if size_of(value) > MAX_ITEMS:
                raise ValueError("Use at most 200 values in all.")
        elif isinstance(value, list) and (len(value) > MAX_ITEMS or any(not isinstance(x, int) or isinstance(x, bool) or abs(x) > 1000000 for x in value)):
            raise ValueError("Use at most 200 integers between -1,000,000 and 1,000,000.")
        if isinstance(value, str) and len(value) > MAX_ITEMS:
            raise ValueError("Use at most 200 characters.")
        if isinstance(value, int) and abs(value) > 1000000:
            raise ValueError("Use integers between -1,000,000 and 1,000,000.")
    base = problem.get("parent", problem["id"])  # A changed requirement keeps its problem's input rules.
    if base in {"two-sum-sorted", "binary-search", "search-insert", "first-occurrence", "last-occurrence", "sorted-squares", "remove-duplicates", "merge-sorted"} and args[0] != sorted(args[0]):
        raise ValueError("This problem requires a sorted input array.")
    if base == "merge-sorted" and args[1] != sorted(args[1]):
        raise ValueError("Both input arrays must be sorted.")
    if base in {"max-window-sum", "average-window", "window-max"} and not 1 <= args[1] <= len(args[0]):
        raise ValueError("Window size must be between 1 and the array length.")
    rule = INPUT_RULES.get(base)
    if rule:
        rule(*args)


def size_of(value):
    return sum(size_of(v) for v in value) + 1 if isinstance(value, list) else len(value) if isinstance(value, str) else 1


def need(condition, message):
    if not condition:
        raise ValueError(message)


def ints(values, low=-1000000, high=1000000, what="Values"):
    if not all(type(x) is int and low <= x <= high for x in values):
        raise ValueError(f"{what} must be integers between {low:,} and {high:,}.")


def tree_rule(values):
    if not all(x is None or (type(x) is int and abs(x) <= 1000000) for x in values):
        raise ValueError("Write the tree level by level with integers and None for a missing child.")


def grid_rule(grid):
    if not grid or not all(isinstance(row, list) and row and len(row) == len(grid[0]) for row in grid) or len(grid) > 12 or len(grid[0]) > 12:
        raise ValueError("The grid must be a non-empty rectangle of at most 12 × 12 cells.")
    if not all(cell in (0, 1) and type(cell) is int for row in grid for cell in row):
        raise ValueError("Every cell must be 0 or 1.")


def graph_rule(graph, *nodes):
    n = len(graph)
    if n > 30 or not all(isinstance(row, list) and all(type(v) is int and 0 <= v < n and v != i for v in row) and len(set(row)) == len(row) for i, row in enumerate(graph)):
        raise ValueError("graph[i] must list distinct neighbours of node i, numbered from 0 to len(graph) − 1, with no self-loops (at most 30 nodes).")
    if any(i not in graph[j] for i, row in enumerate(graph) for j in row):
        raise ValueError("The graph is undirected: every edge must appear in both nodes' lists.")
    if any(type(v) is not int or not 0 <= v < n for v in nodes):
        raise ValueError("start and goal must be node numbers of the graph.")


def design_rule(entry, methods, argument_ok):
    def check(operations, arguments):
        if not operations or operations[0] != entry or len(operations) != len(arguments) or len(operations) > 40:
            raise ValueError(f"Start with \"{entry}\", give every operation its arguments, and use at most 40 operations.")
        if arguments[0] != [] or not all(op in methods for op in operations[1:]):
            raise ValueError(f"After {entry} (with no arguments), the operations are {', '.join(methods)}.")
        for op, given in zip(operations[1:], arguments[1:]):
            if not isinstance(given, list) or len(given) != 1 or not argument_ok(op, given[0]):
                raise ValueError(f"Give {op} exactly one valid argument, in a list such as [1] or [\"word\"].")
    return check


def recent_pings(operations, arguments):
    design_rule("RecentCounter", ["ping"], lambda op, t: type(t) is int and 1 <= t <= 1000000000)(operations, arguments)
    times = [a[0] for a in arguments[1:]]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Ping times must strictly increase.")


def word(text):
    return isinstance(text, str) and 1 <= len(text) <= 20 and text.isalpha() and text.islower()


def single_rule(nums):
    counts = collections.Counter(nums)
    if list(counts.values()).count(1) != 1 or any(c not in (1, 2) for c in counts.values()):
        raise ValueError("Exactly one value must appear once, and every other value exactly twice.")


def distinct_rule(limit):
    def check(nums):
        if len(set(nums)) != len(nums) or len(nums) > limit:
            raise ValueError(f"Use at most {limit} distinct values.")
    return check


# Input rules for the data-structure labs, beyond matching the example's types (a changed requirement keeps them).
INPUT_RULES = {
    "merge-two-lists": lambda a, b: need(a == sorted(a) and b == sorted(b), "Both lists must be sorted in nondecreasing order."),
    "valid-parentheses": lambda text: need(set(text) <= set("()[]{}"), "Use only the characters ( ) [ ] { }."),
    "recent-calls": recent_pings,
    "kth-largest": lambda nums, k: need(nums and 1 <= k <= len(nums), "k must be between 1 and the list's length."),
    "last-stone": lambda stones: ints(stones, 1, 1000, "Stone weights"),
    "subsets": distinct_rule(8),
    "permutations": distinct_rule(6),
    "max-depth": tree_rule, "level-order": tree_rule,
    "implement-trie": design_rule("Trie", ["insert", "search", "startsWith"], lambda op, text: word(text)),
    "prefix-counts": lambda words, queries: need(all(word(w) for w in words) and all(word(q) for q in queries), "Words and queries must be lowercase letters (1 to 20 of them)."),
    "count-components": graph_rule, "shortest-path": graph_rule,
    "count-islands": grid_rule, "shortest-grid-path": grid_rule,
    "climb-ways": lambda n: need(0 <= n <= 40, "n must be between 0 and 40."),
    "house-robber": lambda nums: ints(nums, 0, 10000, "Amounts"),
    "single-number": single_rule,
    "count-bits": lambda n: need(0 <= n <= 150, "n must be between 0 and 150."),
}


def correct(problem, result, args, expected):
    if result is None and expected == [] and problem.get("kinds"):
        return True  # An empty linked list or tree is the None head the judges write as [].
    if problem.get("order") == "any" and isinstance(result, list) and isinstance(expected, list):
        key = lambda v: json.dumps(v, sort_keys=True)
        return collections.Counter(map(key, result)) == collections.Counter(map(key, expected))
    if problem.get("custom") and type(expected) is float and type(result) in (int, float):
        return abs(result - expected) <= 1e-6 * max(1.0, abs(expected))
    if problem["id"] == "binary-search":
        nums, target = args
        return type(result) is int and (result == -1 if target not in nums else 0 <= result < len(nums) and nums[result] == target)
    if problem["id"] in {"two-sum", "two-sum-sorted"}:
        nums, target = args
        exists = any(nums[i] + nums[j] == target for i in range(len(nums)) for j in range(i + 1, len(nums)))
        if not exists:
            return result == []
        return isinstance(result, list) and len(result) == 2 and all(type(i) is int and 0 <= i < len(nums) for i in result) and result[0] != result[1] and nums[result[0]] + nums[result[1]] == target
    if problem.get("answer") == "lines" and isinstance(result, list) and isinstance(expected, list) and all(isinstance(x, str) for x in result + expected):
        return [x.rstrip() for x in result] == [x.rstrip() for x in expected]  # Printed lines: trailing spaces don't show.
    if problem["id"] in {"intersection", "unique-values"}:
        return isinstance(result, list) and all(type(v) is int for v in result) and len(result) == len(set(expected)) and set(result) == set(expected)
    return type(result) is type(expected) and same_value(result, expected)


def same_value(a, b):
    """Equal as the contract means it: True is not 1 at any depth (Python's == says it is)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same_value(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_value(a[k], b[k]) for k in a)
    return a == b


# The reference is deterministic, so its result for an input never changes while a learner
# types: cache it and keep each live preview to a single run of the learner's code.
REFERENCE_RESULTS = collections.OrderedDict()
REFERENCE_LOCK = threading.Lock()


def reference_result(p, args):
    """(True, result) for the authored solution on these arguments, or (False, None) if it exceeded limits
    or there is no authored solution (a learner's own lab knows only the cases they wrote)."""
    code = p.get("solution") or p.get("reference")
    if not code:
        return False, None
    key = (p["id"], hash(code), json.dumps(args, sort_keys=True))
    with REFERENCE_LOCK:
        if key in REFERENCE_RESULTS:
            REFERENCE_RESULTS.move_to_end(key)
            return REFERENCE_RESULTS[key]
    # Linked lists and trees reach the reference as nodes, and a design problem builds its class, as for the learner.
    # A built-in solution is traced; the platform's own page references run untraced; a reference from elsewhere
    # (LeetCode's accepted solution) runs as learner code does, guarded, recording nothing.
    runner = run_cases if p.get("solution") else run_quiet if p.get("sandboxed") else run_reference
    run = runner(code, [copy.deepcopy(args)], [p.get("kinds", {}).get(name) for name in p["params"]], p.get("entry", "solve"), p.get("answer"))[0]
    outcome = (run["error"] is None, run["result"])
    with REFERENCE_LOCK:
        REFERENCE_RESULTS[key] = outcome
        while len(REFERENCE_RESULTS) > 512:
            REFERENCE_RESULTS.popitem(last=False)
    return outcome


def explanation(event, error=None):
    kind, meta = event["type"], event.get("meta", {})
    if kind == "ERROR" and error and error.get("explanation"):
        told = error["explanation"]  # What stopped the program, in the learner's names (errors.explain).
        return {"what": told["title"], "why": " ".join(part for part in (told["detail"], told["hint"]) if part)}
    why = {
        "LOOP_START": "Your loop has selected its next iteration. Watch which index and values changed.",
        "LOOP_END": "The loop has ended; execution continues with the following statement.",
        "STATE_CHANGE": "This assignment or operation changes the state that subsequent lines will use.",
        "POINTER_MOVE": "This index now refers to a different position. Its new value comes from the expression in your code.",
        "HASHMAP_INSERT": "The collection now remembers this entry for later operations.",
        "ARRAY_WRITE": "Your code replaced an element. Future reads observe the updated value.",
        "ARRAY_ACCESS": "Your expression needs the value at this position, so Python reads that element.",
        "HASHMAP_LOOKUP": "Your code queries the collection. The recorded lookup result determines the next branch or value.",
        "COMPARE": "Python evaluated this condition using the current values. This result determines which branch executes.",
        "RETURN": "Return ends this function immediately and sends this value back to its caller.",
        "ERROR": "Execution stopped at this line. Review the current state and the error before changing your code.",
        "RECURSION_CALL": "A function call creates a new frame with its own local state.",
        "RECURSION_RETURN": "This function frame has finished and control returns to its caller.",
        "STACK_PUSH": "The appended value is stored at the end of the collection.",
        "STACK_POP": "The selected entry is removed and returned to your code.",
    }.get(kind, "This event records the state produced by your program.")
    if meta.get("targets"):
        why = f"This one statement assigned {len(meta['targets'])} targets. Python evaluated the entire right side first, so each target received a value computed before any of them changed. That is how a[i], a[j] = a[j], a[i] swaps without a temporary variable."
    if "expression" in meta:
        why += f" Here, {meta['left']} compared with {meta['right']} gives {meta['result']}."
    return {"what": event["detail"], "why": why}


def value_origin(events, ret):
    """The recorded step that last changed the returned name: provenance, never blame."""
    match = re.fullmatch(r"return\s+([A-Za-z]\w*)", ret["source"])
    if not match:
        return None
    name, frame = match.group(1), ret["state"]["callstack"]

    def lookup(event):
        state = event["state"]
        found = [v["value"] for v in state["variables"] if v["id"] == name] + [s.get("entries", s.get("values")) for s in state["structures"] if s["id"] == name]
        return json.dumps(found[0]) if found else None

    origin, previous = None, None
    for event in events[:ret["id"] + 1]:
        if event["state"]["callstack"] != frame:
            continue  # Other frames hold different variables with possibly equal names.
        current = lookup(event)
        if current is not None and current != previous:
            origin = event
        previous = current
    if not origin:
        return None
    return dict(step=origin["id"], line=origin["line"], name=name, unchanged=origin["type"] == "RECURSION_CALL")


def kind_of(value):
    return {bool: "a boolean", int: "an integer", float: "a float", str: "a string", list: "a list", dict: "a dictionary"}.get(type(value), "None")


def observable_divergence(p, trace, expected=None, passed=None):
    """The first point where the trace proves something is wrong, or an honest 'not established'."""
    events = trace["events"]
    error = next((e for e in events if e["type"] == "ERROR"), None)
    told = (trace.get("error") or {}).get("explanation") or {}
    plain = " ".join(part for part in (told.get("detail"), told.get("hint")) if part)
    if error:
        cycle = error["meta"].get("cycle")
        if cycle:
            return dict(step=cycle["repeat"] if cycle["repeat"] is not None else error["id"], line=cycle["line"], kind="Proven infinite loop", message=plain or error["detail"], cycle=cycle)
        return dict(step=error["id"], line=error["line"], kind="First recorded runtime failure", title=told.get("title"), message=plain or error["detail"], access=error["meta"].get("access"))
    if trace.get("error"):  # Stopped before a step recorded the failure (a limit, or the event record was full).
        return dict(step=None, line=trace["error"].get("line"), kind="Execution stopped", title=told.get("title"), message=plain or trace["error"]["message"])
    entry = next((e["state"]["callstack"][:1] for e in events if e["state"]["callstack"]), ["solve"])  # solve, or Solution.twoSum
    returns = [e for e in events if e["type"] == "RETURN" and e["state"]["callstack"] == entry]
    if p["id"] in {"two-sum", "two-sum-sorted"}:
        invalid = next((e for e in returns if isinstance(e["meta"].get("value"), list) and len(e["meta"]["value"]) == 2 and e["meta"]["value"][0] == e["meta"]["value"][1]), None)
        if invalid:
            return dict(step=invalid["id"], line=invalid["line"], kind="First observable contract violation", message=f"Returned {invalid['meta']['value']}, reusing one position. The contract requires two different positions. This return proves the violation; an earlier cause is not established.")
    if passed is not False:
        return None
    ret = returns[-1] if returns else None
    location = dict(step=ret["id"], line=ret["line"], origin=value_origin(events, ret)) if ret else dict(step=None, line=None, origin=None)
    result = trace["result"]
    if result is None and expected is not None:
        return dict(**location, kind="Nothing returned yet", message="Your function returned None, so it has not produced an answer yet. Predict what it should return for this input, then make it return that.")
    if expected is not None and type(result) is not type(expected):
        return dict(**location, kind="Output contract mismatch", message=f"Returned {result!r}, {kind_of(result)}; the contract asks for {kind_of(expected)} like {expected!r}. {p['decoder']['returns']}")
    limit = " The trace reached its event limit, so the return was not recorded." if trace.get("truncated") and not ret else ""
    return dict(**location, kind="Observed result mismatch", elements=wrong_elements(p, events, ret, result, expected),
                message=f"Returned {result!r}; {'your case expects' if p.get('custom') else 'a valid result is'} {expected!r}. This is where the wrong value first becomes observable; the trace does not establish the first incorrect intermediate step.{limit}")


def wrong_elements(p, events, ret, result, expected):
    """For a wrong returned list, the recorded step that put each wrong element into the final answer.
    Provenance only: that write's value survived to the end; an earlier cause is not excluded."""
    if not ret or not isinstance(result, list) or not isinstance(expected, list) or p["id"] in {"two-sum", "two-sum-sorted"}:
        return None  # Index-pair answers have several valid forms; the contract checks cover them.
    match = re.fullmatch(r"return\s+([A-Za-z]\w*)(\[\s*0?\s*:[^\]]*\])?", ret["source"])
    if not match:
        return None
    name, frame = match.group(1), ret["state"]["callstack"]
    history = []
    for event in events[:ret["id"] + 1]:
        structure = next((s for s in event["state"]["structures"] if s["id"] == name and s["type"] == "array"), None) if event["state"]["callstack"] == frame else None
        if structure and structure.get("length", len(structure["values"])) <= MAX_ITEMS:
            history.append((event, structure["values"]))
    if not history or history[-1][1][:len(result)] != result:
        return None  # The returned value is not this list (or its prefix): do not guess.

    def origin(position):
        last, previous = None, object()
        for event, values in history:
            current = values[position] if position < len(values) else None
            if position < len(values) and current != previous:
                last = event
            previous = current
        return last

    ordered = p["id"] not in {"intersection", "unique-values"} and p.get("order") != "any"  # Their variants are ordered contracts.
    if ordered:
        positions = [i for i in range(len(result)) if i >= len(expected) or result[i] != expected[i]]
        missing = max(0, len(expected) - len(result))
    else:
        # Surplus copies are the later occurrences: the earlier copy of a value was a valid member.
        surplus = collections.Counter(map(json.dumps, result)) - collections.Counter(map(json.dumps, expected))
        positions = []
        for i in reversed(range(len(result))):
            if surplus[json.dumps(result[i])] > 0:
                surplus[json.dumps(result[i])] -= 1
                positions.insert(0, i)
        missing = sum((collections.Counter(map(json.dumps, expected)) - collections.Counter(map(json.dumps, result))).values())
    found = []
    for position in positions[:5]:
        event = origin(position)
        if event:
            goal = expected[position] if ordered and position < len(expected) else None
            found.append(dict(position=position, value=result[position], goal=goal, step=event["id"], line=event["line"], unchanged=event["type"] == "RECURSION_CALL"))
    return dict(name=name, wrong=found, missing=missing, ordered=ordered)


def error_json(message, status, details=None, **extra):
    """The API's error shape: {"ok": false, "error": "...", "details": "..."} with a matching status code."""
    return jsonify(ok=False, error=message, **({"details": details} if details else {}), **extra), status


@app.errorhandler(ValueError)
@app.errorhandler(SyntaxError)
def bad_request(exc):
    """A refused request. Code the runner can't run (a syntax error, an unsupported construct) also gets its plain
    explanation, and `code: true` so the page can say the code, not the request, needs a change."""
    explained = errors.refused(exc)
    return error_json(errors.clean(str(exc)), 400, line=getattr(exc, "lineno", None), **({"explanation": explained, "code": True} if explained else {}))


def json_body():
    """The request's JSON object. A list, string or number is a client error, not a server failure."""
    data = request.get_json() or {}
    if not isinstance(data, dict):
        raise ValueError("Send a JSON object.")
    return data


@app.errorhandler(RecursionError)
def too_deep(exc):
    return error_json("That input is nested too deeply to read.", 400)


@app.errorhandler(PermissionError)
def unauthorized(exc):
    return error_json(str(exc), 401)


HTTP_MESSAGES = {404: "That API route doesn't exist.", 405: "That API route doesn't accept this kind of request.",
                 413: "That request is too large. Files can be at most 3 MB; pasted text at most 300,000 characters."}


@app.errorhandler(HTTPException)
def http_error(exc):
    if not request.path.startswith("/api/"):
        return exc
    return error_json(HTTP_MESSAGES.get(exc.code, exc.description or exc.name), exc.code or 500, details=exc.name)


@app.errorhandler(Exception)
def server_error(exc):
    """An unexpected failure still answers in JSON, naming what failed, so the page never meets an empty body."""
    app.logger.exception("Unhandled error on %s", request.path)
    if not request.path.startswith("/api/"):
        return "Visual DSA hit an unexpected error.", 500
    return error_json("The server hit an unexpected problem while handling this request.", 500, details=f"{type(exc).__name__}: {exc}"[:300])


@app.get("/api/health")
def health():
    return jsonify(ok=True, runner=os.environ.get("EXECUTION_MODE", "local"), auth=bool(firebase), ai=bool(os.environ.get("LLM_API_KEY")))


@app.get("/api/problems")
def problems():
    # Solutions and private test expectations are fetched only on deliberate reveal. What names the intended
    # technique is sent only once the learner's own recorded work has opened it (see client_problem).
    try:
        uid = identity()
    except PermissionError:
        uid = None  # Before sign-in the library is browsable, with nothing opened.
    with connect() as db:
        committed = {r[0] for r in db.execute("SELECT problem_id FROM learning_evidence WHERE user_id=? AND kind='approach'", (uid,))}
        solved = {r[0] for r in db.execute("SELECT DISTINCT problem_id FROM attempts WHERE user_id=? AND passed=1", (uid,))}
        support = {r["problem_id"]: r for r in db.execute("SELECT problem_id,hint_level,clues FROM learning_support WHERE user_id=?", (uid,))}
    return jsonify([client_problem(p, p["id"] in committed, p["id"] in solved, support.get(p["id"]), support.get(p["modification"]["id"])) for p in PROBLEMS])


def client_problem(p, committed, solved, support, variant_support):
    """A built-in lab as the learner's browser receives it. The topic (category) names the technique, so it is sent
    after a commitment; recall questions and the changed requirement name it too, so they are sent after a commitment
    or a passing run; the reasoning prompts that point at the approach (3 and 4) once revealed through the server or
    after a commitment; hints only up to the level the learner asked for. Everything else is client-safe."""
    hints, clues = (support["hint_level"], support["clues"]) if support else (0, 0)
    opened = committed or solved
    item = {k: v for k, v in p.items() if k not in {"solution", "brute", "tests", "approach", "modification", "category", "hints", "recall", "discovery"}}
    item.update(hints=p["hints"][:hints], hintCount=len(p["hints"]), recall=p["recall"] if opened else [], recallCount=len(p["recall"]),
                discovery=[text if i < 2 or committed or i <= clues else None for i, text in enumerate(p["discovery"])], unlocked=opened, hasModification=True)
    if committed:
        item["category"] = p["category"]
    if opened:
        variant = VARIANTS[p["modification"]["id"]]
        item["modification"] = {**{k: v for k, v in p["modification"].items() if k in {"id", "title", "statement", "returns", "question", "example"}},
                                "hints": variant["hints"][:variant_support["hint_level"] if variant_support else 0], "hintCount": len(variant["hints"])}
    return item


@app.post("/api/topics")
def topic_problems():
    """The labs of one library topic. Listing them tells the learner each one's technique topic, so the server
    records that it did: a later commitment on any of them is not unaided."""
    try:
        uid = identity()
    except PermissionError:
        uid = None  # Browsing before sign-in: nothing to record, and nothing can be committed.
    topic = json_body().get("topic")
    ids = [p["id"] for p in PROBLEMS if p["category"] == topic]
    if not ids:
        raise ValueError("Choose one of the library's topics.")
    if uid:
        with connect() as db:
            for id_ in ids:
                note_support(db, uid, id_, "topic")
    return jsonify(topic=topic, ids=ids)


@app.post("/api/discovery")
def discovery_prompt():
    """A Discover reasoning prompt. Prompts 3 and 4 point toward the approach: revealed before a commitment,
    the server records it, so that commitment is not counted as unaided."""
    uid = identity()
    data = json_body()
    p, step = problem_by_id(data.get("problemId"), uid), data.get("step")
    if not p or p.get("custom") or "parent" in p or type(step) is not int or not 0 <= step < len(p["discovery"]):
        raise ValueError("Choose a reasoning prompt of a built-in lab.")
    with connect() as db:
        committed = db.execute("SELECT 1 FROM learning_evidence WHERE user_id=? AND problem_id=? AND kind='approach'", (uid, p["id"])).fetchone()
        if step >= 2 and not committed:
            note_support(db, uid, p["id"], "clues", step)
    return jsonify(step=step, text=p["discovery"][step])


@app.get("/api/problems/<id_>/solution")
def solution(id_):
    uid = identity()
    p = problem_by_id(id_)
    if not p:
        return jsonify(error="Your own lab has no reference solution: your cases are its specification." if str(id_).startswith("custom-") else "Problem not found."), 404
    require_opened(uid, p)
    with connect() as db:
        db.execute("INSERT INTO learning_support(user_id,problem_id,revealed) VALUES(?,?,1) ON CONFLICT(user_id,problem_id) DO UPDATE SET revealed=1", (uid, id_))
    return jsonify(code=p["brute"] if request.args.get("mode") == "brute" and p["brute"] else p["solution"])


@app.post("/api/hint")
def hint():
    uid = identity()
    data = json_body()
    p = problem_by_id(data.get("problemId"), uid)
    level = data.get("level", 1)
    if not p or type(level) is not int or not 1 <= level <= len(p["hints"]):
        raise ValueError("Choose a valid hint level.")
    require_opened(uid, p)
    context = ""
    with connect() as db:
        support = db.execute("SELECT hint_level FROM learning_support WHERE user_id=? AND problem_id=?", (uid, p["id"])).fetchone()
        previous = support[0] if support else 0
        level = min(len(p["hints"]), previous + 1)
        db.execute("INSERT INTO learning_support(user_id,problem_id,hint_level) VALUES(?,?,?) ON CONFLICT(user_id,problem_id) DO UPDATE SET hint_level=MAX(hint_level,excluded.hint_level)", (uid, p["id"], level))
        row = db.execute("SELECT s.trace FROM execution_sessions s JOIN attempts a ON a.id=s.attempt_id WHERE a.id=? AND a.user_id=? AND a.problem_id=?", (data.get("attemptId"), uid, p["id"])).fetchone()
    if row:
        trace = json.loads(row["trace"])
        if trace["error"]:
            told = trace["error"].get("explanation") or {}
            where = f" at line {trace['error']['line']}" if trace["error"].get("line") else ""
            context = f"Your attempt stopped{where}: {told.get('title') or errors.clean(trace['error']['message'])}. {told.get('hint') or ''}".strip()
        elif p["id"] in {"two-sum", "two-sum-sorted"} and isinstance(trace["result"], list) and len(trace["result"]) == 2 and trace["result"][0] == trace["result"][1]:
            context = "Your attempt returned the same position twice. The problem requires two different positions. Which step allowed that reuse?"
        elif p["id"] == "two-sum" and any(e["type"] == "HASHMAP_LOOKUP" for e in trace["events"]) and not any(e["type"] == "HASHMAP_INSERT" for e in trace["events"]):
            context = "Your trace includes lookups but no dictionary inserts. What information can a later lookup find?"
    return jsonify(level=level, text=p["hints"][level - 1], context=context)


def limited(run):
    """A trace that stopped at the trace's own limits (steps or time), not because the program failed or was
    proven to loop forever: whether it finishes is a question for a full run."""
    failure = (run.get("error") or {}).get("failure") or {}
    return (run.get("error") or {}).get("type") == "ExecutionLimit" and failure.get("limit") in ("steps", "time", "stopped") and not failure.get("cycle")


def with_full_runs(p, code, cases, runs):
    """Judge every case its trace couldn't finish with a full run of the same program (run_quiet). A case that
    finishes is judged on its real answer, its trace kept as its first recorded steps; one that doesn't is still
    stopped, and says that even unrecorded it didn't finish."""
    pending = [i for i, run in enumerate(runs) if limited(run)]
    if not pending:
        return runs
    quiet = run_quiet(code, [cases[i]["args"] for i in pending], [p.get("kinds", {}).get(name) for name in p["params"]], p.get("entry", "solve"), p.get("answer"))
    for i, full in zip(pending, quiet):
        run = runs[i]
        if full["error"] is None:
            run.update(events=[e for e in run["events"] if e["type"] != "ERROR"], truncated=True, error=None, result=full["result"], fullRun=True)
        elif full["error"]["type"] == "ExecutionLimit":
            run["error"].setdefault("failure", {})["unfinished"] = QUIET_SECONDS
        else:  # Unrecorded, it went further and failed: that failure is the answer for this case.
            run.update(error=full["error"], fullRun=True)
    return runs


def practice_cases(p, args):
    """The authored cases (example and edge cases) plus the learner's own input when it differs."""
    cases = [dict(id=f"case-{i}", name=case["name"], args=case["args"], expected=case["expected"], custom=False, computed=bool(case.get("computed")), source=case.get("source")) for i, case in enumerate(p["tests"])]
    if not any(case["args"] == args for case in cases):
        cases.append(dict(id="custom", name="Your input", args=args, expected=None, custom=True, computed=bool(p.get("custom")), source=None))
    return cases


def evaluate_cases(uid, p, code, cases, runs, preview):
    """Goal, verdict and divergence for every case's own trace. A verdict is never a test pass."""
    traces = []
    for case, trace in zip(cases, runs):
        solved, expected = reference_result(p, case["args"]) if case["custom"] else (True, case["expected"])
        if trace["error"]:
            trace["error"]["explanation"] = errors.explain(trace["error"], trace["error"].get("failure"), code, p["params"], p.get("entry", "solve"))
        trace["goal"] = {"expected": expected, "matches": not trace["error"] and correct(p, trace["result"], case["args"], expected), **({"computed": True} if case["computed"] else {})} if solved else None
        for event in trace["events"]:
            event["explanation"] = explanation(event, trace["error"])
        trace.update(divergence=observable_divergence(p, trace, *((expected, trace["goal"]["matches"]) if solved else (None, None))),
                     counts=dict(collections.Counter(e["type"] for e in trace["events"])), input=case["args"])
        trace["traceId"] = retain_preview(uid, p["id"], code, case["args"], trace, preview)
        traces.append(trace)
    return traces


def public_cases(cases, traces):
    keep = ("events", "result", "error", "truncated", "lines", "goal", "divergence", "counts", "traceId", "input", "stdout", "durationMs", "fullRun")
    return [dict(id=case["id"], name=case["name"], custom=case["custom"], computed=case["computed"], source=case.get("source"), **{k: trace.get(k) for k in keep}) for case, trace in zip(cases, traces)]


@app.post("/api/preview")
def preview():
    """Ephemeral typing feedback over every case: no tests, attempts or mastery evidence."""
    uid = identity()
    data = json_body()
    p = problem_by_id(data.get("problemId"), uid)
    if not p:
        raise ValueError("Select a problem before previewing code.")
    require_opened(uid, p)
    code, args = data.get("code", ""), data.get("args", p["example"]["args"])
    valid_args(p, args)
    validate_source(code, p.get("entry", "solve"), len(p["params"]))
    if not RUNNERS.acquire(blocking=False):
        return jsonify(error="The runner is busy. Keep editing, then try again."), 429
    try:
        cases = practice_cases(p, args)
        runs = run_cases(code, [case["args"] for case in cases], [p.get("kinds", {}).get(name) for name in p["params"]], p.get("entry", "solve"), p.get("answer"))
        for run in runs:
            if limited(run):
                run["error"].setdefault("failure", {})["preview"] = True  # Run judges it with a full run.
        traces = evaluate_cases(uid, p, code, cases, runs, preview=True)
        authored = [trace for case, trace in zip(cases, traces) if not case["custom"]]
        if not p.get("custom") and "parent" not in p and authored and all(not t["error"] and t["goal"] and t["goal"]["matches"] for t in authored):
            # No attempt and no stage: only the fact that the code already met every goal before a commitment.
            with connect() as db:
                note_support(db, uid, p["id"], "preview_solved")
        main = next(i for i, case in enumerate(cases) if case["args"] == args)
        return jsonify(**traces[main], preview=True, expected=None, passed=False, tests=[], attemptId="",
                       cases=public_cases(cases, traces), caseId=cases[main]["id"])
    finally:
        RUNNERS.release()


@app.post("/api/execute")
def execute():
    uid = identity()
    data = json_body()
    p = problem_by_id(data.get("problemId"), uid)
    if not p:
        raise ValueError("Select a problem before running code.")
    require_opened(uid, p)
    code, args = data.get("code", ""), data.get("args", p["example"]["args"])
    valid_args(p, args)
    validate_source(code, p.get("entry", "solve"), len(p["params"]))
    if not RUNNERS.acquire(blocking=False):
        return jsonify(error="Both execution workers are busy. Try again shortly."), 429
    try:
        cases = practice_cases(p, args)
        runs = run_cases(code, [case["args"] for case in cases], [p.get("kinds", {}).get(name) for name in p["params"]], p.get("entry", "solve"), p.get("answer"))
        traces = evaluate_cases(uid, p, code, cases, with_full_runs(p, code, cases, runs), preview=False)
        main = next(i for i, case in enumerate(cases) if case["args"] == args)
        trace = traces[main]
        if not trace["goal"] and not p.get("custom"):
            raise ValueError("This input exceeded the reference runner's limits. Use a smaller input.")
        # An input outside a learner's own cases has no known answer: only their cases judge it.
        expected, passed = (trace["goal"]["expected"], trace["goal"]["matches"]) if trace["goal"] else (None, not trace["error"])
        # Every authored case is traced on every run, so whether this attempt passes the whole suite is the
        # server's own result. A request can leave the test list out of its reply, never out of the evidence.
        suite = [{"name": case["name"], "args": case["args"], "expected": case["expected"], "actual": run["result"], "passed": run["goal"]["matches"], "error": run["error"], "computed": case["computed"], "source": case.get("source")}
                 for case, run in zip(cases, traces) if not case["custom"]]
        tests = suite if data.get("test", True) else []
        trace["evaluation"] = {"expected": expected, "passed": passed, "tests": tests}
        for other in traces:  # Each case trace the guide may read comes from this test run, not from a preview.
            other.setdefault("evaluation", {"expected": other["goal"]["expected"] if other["goal"] else None, "passed": other["goal"]["matches"] if other["goal"] else not other["error"], "tests": tests})
        attempt_id = uuid.uuid4().hex
        with connect() as db:
            db.execute("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))
            db.execute("INSERT INTO attempts(id,user_id,problem_id,code,input,result,passed) VALUES(?,?,?,?,?,?,?)", (attempt_id, uid, p["id"], code, json.dumps(args), json.dumps(trace["result"]), int(passed and all(t["passed"] for t in suite))))
            db.execute("INSERT INTO execution_sessions(id,attempt_id,trace) VALUES(?,?,?)", (uuid.uuid4().hex, attempt_id, json.dumps(trace)))
            # Bound retained traces independently of saved attempts.
            db.execute("DELETE FROM execution_sessions WHERE rowid NOT IN (SELECT rowid FROM execution_sessions ORDER BY rowid DESC LIMIT 100)")
        stored = {k: v for k, v in trace.items() if k != "evaluation"}
        return jsonify(**stored, expected=expected, passed=passed, tests=tests, attemptId=attempt_id,
                       cases=public_cases(cases, traces), caseId=cases[main]["id"])
    finally:
        RUNNERS.release()


@app.get("/api/progress")
def get_progress():
    uid = identity()
    with connect() as db:
        progress = [dict(r) for r in db.execute("SELECT * FROM learning_progress WHERE user_id=?", (uid,))]
        saved = [dict(r) for r in db.execute("SELECT problem_id,code FROM saved_code WHERE user_id=?", (uid,))]
        bookmarks_ = [r[0] for r in db.execute("SELECT problem_id FROM bookmarks WHERE user_id=?", (uid,))]
        support = [dict(r) for r in db.execute("SELECT problem_id,hint_level,revealed FROM learning_support WHERE user_id=?", (uid,))]
        evidence = [dict(r, detail=json.loads(r["detail"])) for r in db.execute("SELECT problem_id,kind,detail,created_at FROM learning_evidence WHERE user_id=?", (uid,))]
    for item in evidence:
        if item["kind"] == "modified" and problem_by_id(item["problem_id"]):
            item["detail"]["insight"] = problem_by_id(item["problem_id"])["modification"]["insight"]  # Earned by the adaptation.
    return jsonify(progress=progress, saved=saved, bookmarks=bookmarks_, support=support, evidence=evidence)


@app.post("/api/progress")
def save_progress():
    uid = identity()
    data = json_body()
    p = problem_by_id(data.get("problemId"), uid)
    if not p:
        raise ValueError("Unknown problem.")
    with connect() as db:
        if "code" in data:
            code = data["code"]
            if not isinstance(code, str) or len(code) > 12000:
                raise ValueError("Code is too long.")
            db.execute("INSERT OR REPLACE INTO saved_code VALUES(?,?,?)", (uid, p["id"], code))
        if "bookmark" in data:
            if data["bookmark"]:
                db.execute("INSERT OR IGNORE INTO bookmarks VALUES(?,?)", (uid, p["id"]))
            else:
                db.execute("DELETE FROM bookmarks WHERE user_id=? AND problem_id=?", (uid, p["id"]))
        transferred, insight, reflected = [], None, False
        if "stage" in data:
            stage = data["stage"]
            if stage not in STAGES:
                raise ValueError("Unknown learning stage.")
            if stage == "Transferred":
                raise ValueError("Transfer is recorded from evidence on a related problem; it cannot be requested directly.")
            if "parent" in p:
                raise ValueError("Record learning stages on the original problem.")
            if stage == "Modified" and "modification" not in p:
                raise ValueError("This lab has no changed requirement.")
            # Result-based stages require persisted passing execution evidence. A
            # modification is evidenced by the changed requirement's own tests.
            target = p["modification"]["id"] if stage == "Modified" else p["id"]
            if stage in {"Reproduced", "Modified", "Independent"}:
                evidence = db.execute("SELECT passed FROM attempts WHERE id=? AND user_id=? AND problem_id=?", (data.get("attemptId"), uid, target)).fetchone()
                if not evidence or not evidence[0]:
                    raise ValueError("Pass the changed requirement's tests to record this adaptation." if stage == "Modified" else "Run passing code first to record this learning stage.")
            support = support_row(db, uid, target)
            if stage == "Modified":
                reasoning = data.get("evidence")
                if not isinstance(reasoning, str) or len(reasoning.strip()) < 20:
                    raise ValueError("Describe what the changed requirement changes in your reasoning (at least 20 characters).")
                if support and support["revealed"]:
                    raise ValueError("A revealed reference cannot count as adapting your own solution.")
                base = support_row(db, uid, p["id"])  # The solution being adapted may have come from the original's reference.
                db.execute("INSERT OR IGNORE INTO learning_evidence(user_id,problem_id,kind,detail) VALUES(?,?,'modified',?)",
                           (uid, p["id"], json.dumps({"requirement": p["modification"]["title"], "reasoning": reasoning.strip()[:2000], "attemptId": data["attemptId"], "hints": support["hint_level"] if support else 0,
                                                      "originalReferenceSeen": bool(base and base["revealed"])})))
                insight = p["modification"]["insight"]
            if stage == "Independent" and support and (support["hint_level"] or support["revealed"]):
                stage = "Reproduced"
            if stage == "Explained":
                if len(str(data.get("evidence", "")).strip()) < 40:
                    raise ValueError("Explain your reasoning in at least 40 characters.")
                # The written reflection is kept whatever the stage: a higher stage keeps its name, never discards this.
                db.execute("INSERT INTO learning_evidence(user_id,problem_id,kind,detail) VALUES(?,?,'reflection',?) ON CONFLICT(user_id,problem_id,kind) DO UPDATE SET detail=excluded.detail, created_at=CURRENT_TIMESTAMP",
                           (uid, p["id"], json.dumps({"text": str(data["evidence"])[:4000]})))
                reflected = True
            stage = record_stage(db, uid, p["id"], stage, data.get("evidence", ""))
            if data["stage"] in {"Reproduced", "Independent"}:
                transferred = award_transfers(db, uid, p)
    return jsonify(ok=True, stage=stage if "stage" in data else None, insight=insight, transferred=[t for t, _ in transferred],
                   promptedTransfers=[t for t, prompted in transferred if prompted], reflection=reflected)


def support_row(db, uid, problem_id):
    return db.execute("SELECT hint_level,revealed,clues,topic,preview_solved FROM learning_support WHERE user_id=? AND problem_id=?", (uid, problem_id)).fetchone()


SUPPORT_EVENTS = {"clues", "topic", "preview_solved"}


def require_opened(uid, p):
    """A changed requirement is reachable only once the learner's own work has opened it: a commitment on its lab or a
    passing run of it (the rule /api/problems uses to send it). Its tests, hints and reference name the technique."""
    if p and "parent" in p:
        with connect() as db:
            if not db.execute("SELECT 1 FROM learning_evidence WHERE user_id=? AND problem_id=? AND kind='approach' UNION SELECT 1 FROM attempts WHERE user_id=? AND problem_id=? AND passed=1",
                              (uid, p["parent"], uid, p["parent"])).fetchone():
                raise ValueError("The changed requirement opens after you commit to an approach or pass this lab's tests.")


def note_support(db, uid, problem_id, column, value=1):
    """Record something the server itself gave or saw, before a commitment can be judged: it only ever rises."""
    assert column in SUPPORT_EVENTS
    db.execute(f"INSERT INTO learning_support(user_id,problem_id,{column}) VALUES(?,?,?) ON CONFLICT(user_id,problem_id) DO UPDATE SET {column}=MAX({column},excluded.{column})", (uid, problem_id, value))


def topic_words(text):
    return {w[:-1] if w.endswith("s") and len(w) > 3 else w for w in re.findall(r"[a-z]+", text.lower())}


def sheet_topic(db, uid, p):
    """A heading in one of the learner's own sheets that lists this lab under its topic ("Heaps", "Two Pointers"),
    as the library's topic filter would: the sheet showed the technique's topic next to the problem."""
    names = [topic_words(part) for part in p["category"].split("&")]
    for (rows,) in db.execute("SELECT rows FROM sheets WHERE user_id=?", (uid,)):
        for row in json.loads(rows):
            heading = topic_words(row.get("topic") or "")
            if (row.get("lab") or row.get("match")) == p["id"] and any(name and all(any(h.startswith(w) for h in heading) for w in name) for name in names):
                return row["topic"]
    return None


def record_stage(db, uid, problem_id, stage, evidence=""):
    """Stages never regress: a lower stage keeps the higher stage and its evidence."""
    old = db.execute("SELECT stage FROM learning_progress WHERE user_id=? AND problem_id=?", (uid, problem_id)).fetchone()
    if old and STAGES.index(old[0]) > STAGES.index(stage):
        return old[0]
    db.execute("INSERT OR REPLACE INTO learning_progress(user_id,problem_id,stage,evidence) VALUES(?,?,?,?)", (uid, problem_id, stage, json.dumps(evidence)[:4000]))
    return stage


def award_transfers(db, uid, q):
    """Transfer from P to its related problem Q requires: P solved before an unaided first
    commitment on Q that matched Q's approach, then passing Q without a revealed reference."""
    commitment = db.execute("SELECT detail FROM learning_evidence WHERE user_id=? AND problem_id=? AND kind='approach'", (uid, q["id"])).fetchone()
    if not commitment:
        return []
    detail = json.loads(commitment["detail"])
    support = support_row(db, uid, q["id"])
    if detail["verdict"] != "match" or detail["guided"] or (support and support["revealed"]):
        return []
    awarded = []
    for source in PROBLEMS:
        if source["transfer"] != q["id"] or source["id"] not in detail.get("solvedBefore", []):
            continue
        record = {"to": q["id"], "toTitle": q["title"], "technique": detail["technique"], "prompted": detail.get("transferFrom") == source["id"], "hintsAfterCommitment": support["hint_level"] if support else 0}
        if db.execute("INSERT OR IGNORE INTO learning_evidence(user_id,problem_id,kind,detail) VALUES(?,?,'transferred',?)", (uid, source["id"], json.dumps(record))).rowcount:
            record_stage(db, uid, source["id"], "Transferred", record)
            awarded.append((source["id"], record["prompted"]))
    return awarded


def evaluate_approach(p, technique, notes):
    """Compare a committed hypothesis with the authored approach. Checkpoints are lexical,
    so they report what is visible in the learner's notes rather than what they understand."""
    spec = p["approach"]
    intended, operation, why = spec["technique"], spec["operation"], spec["why"]
    text = " ".join(notes.values())
    resolved = [c["label"] for c in spec["checkpoints"] if re.search(c["pattern"], text, re.I)]
    unresolved = [c["question"] for c in spec["checkpoints"] if not re.search(c["pattern"], text, re.I)]
    alternative = spec["alternatives"].get(technique)
    reference = f"This lab's reference uses {intended}. {why}"
    if technique == intended:
        verdict, summary = "match", f"Your hypothesis matches the approach this lab is built around: {intended}."
        gap = "The technique is settled. The open questions above decide whether your algorithm will be correct." if unresolved else "Your notes cover the key decisions. Now test them: the trace will show whether each step does what your plan says."
    elif alternative:
        verdict = alternative["kind"]
        summary = f"{technique} can solve this, with a tradeoff." if verdict == "alternative" else f"{technique} captures part of the approach."
        gap = f"{alternative['note']} {reference}"
    elif technique == TECHNIQUES[0]:
        verdict, summary = "starting-point", "Trying every candidate is correct, and it is the right place to start."
        gap = f"Its cost is repeated work: {p['discovery'][1]} The operation that must become fast: {operation} {reference}"
    else:
        verdict, summary = "different", f"{technique} isn't the technique this lab is built around."
        gap = f"{technique} relies on {TECHNIQUE_NEEDS[technique]}. Here, the repeated work is: {p['discovery'][1]} The operation that must become fast: {operation} {reference} This compares techniques; your tests decide whether your code is correct."
    return dict(verdict=verdict, chosen=technique, summary=summary, gap=gap, resolved=resolved, unresolved=unresolved,
                intended=dict(technique=intended, operation=operation, why=why))


@app.post("/api/approach")
def commit_approach():
    """Record the learner's hypothesis, then reveal and compare the intended approach."""
    uid = identity()
    data = json_body()
    p = problem_by_id(data.get("problemId"), uid)
    if p and p.get("custom"):
        raise ValueError("Your own lab has no authored approach to compare with. Your plan stays in your notes; your cases will test it.")
    if not p or "approach" not in p:
        raise ValueError("Choose a practice problem before committing an approach.")
    technique = data.get("technique")
    if technique not in TECHNIQUES:
        raise ValueError("Choose the technique you want to commit to.")
    notes = {k: data.get(k, "") for k in ("operation", "rationale", "plan")}
    if any(not isinstance(v, str) or len(v) > 6000 for v in notes.values()):
        raise ValueError("Keep each note under 6,000 characters.")
    if len(notes["operation"].strip()) < 12:
        raise ValueError("Describe the operation that must become fast before committing.")
    origin = data.get("transferFrom")  # The transfer prompt the learner followed, if any: it only marks the transfer as prompted.
    if origin is not None and not problem_by_id(origin):
        raise ValueError("Invalid commitment context.")
    feedback = evaluate_approach(p, technique, notes)
    with connect() as db:
        # Whether this hypothesis was aided is decided from what the server gave and saw, never from the request.
        support = support_row(db, uid, p["id"])
        heading = sheet_topic(db, uid, p)
        # The changed requirement's hints and reference describe the same technique.
        variant = support_row(db, uid, p["modification"]["id"]) if "modification" in p else None
        # A hypothesis stated after the problem was already solved is not a prediction.
        passed = db.execute("SELECT 1 FROM attempts WHERE user_id=? AND problem_id IN (?,?) AND passed=1", (uid, p["id"], p["modification"]["id"] if "modification" in p else p["id"])).fetchone()
        reasons = [reason for condition, reason in [
            (support and support["revealed"], "you opened a reference approach"),
            (support and support["hint_level"], "you used hints or the guide on this problem"),
            (variant and (variant["revealed"] or variant["hint_level"]), "you used hints, the guide or the reference on its changed requirement"),
            (support and support["clues"] >= 2, "you revealed reasoning prompts that point toward the approach"),
            (support and support["topic"], "this problem's topic was shown to you (a library topic list or a guide lesson), so the technique was known"),
            (heading, f"your sheet lists this problem under “{heading}”, so the technique was known"),
            (passed, "you committed after your code had already passed this problem's tests"),
            (support and support["preview_solved"], "your live preview already met every case's goal before you committed"),
        ] if condition]
        # Problems whose reasoning could transfer here, already solved at the moment of commitment.
        solved = [s["id"] for s in PROBLEMS if s["transfer"] == p["id"] and db.execute("SELECT 1 FROM attempts WHERE user_id=? AND problem_id=? AND passed=1", (uid, s["id"])).fetchone()]
        record = dict(technique=technique, verdict=feedback["verdict"], operation=notes["operation"].strip()[:1500], guided=bool(reasons), reasons=reasons, transferFrom=origin, solvedBefore=solved)
        db.execute("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))
        first = db.execute("INSERT OR IGNORE INTO learning_evidence(user_id,problem_id,kind,detail) VALUES(?,?,'approach',?)", (uid, p["id"], json.dumps(record))).rowcount == 1
        stored = json.loads(db.execute("SELECT detail FROM learning_evidence WHERE user_id=? AND problem_id=? AND kind='approach'", (uid, p["id"])).fetchone()[0])
    return jsonify(**feedback, guided=bool(reasons), reasons=reasons, first=first, firstCommitment=stored)


# Live previews remain ephemeral and never become attempts or mastery evidence.
# A bounded, owner-scoped cache lets the tutor read the exact server trace.
PREVIEW_TRACES = collections.OrderedDict()
PREVIEW_LOCK = threading.Lock()


def retain_preview(uid, problem_id, code, args, trace, preview=True):
    token = uuid.uuid4().hex
    with PREVIEW_LOCK:
        now = time.monotonic()
        for key in list(PREVIEW_TRACES):
            if now - PREVIEW_TRACES[key]["created"] > 600:
                del PREVIEW_TRACES[key]
        PREVIEW_TRACES[token] = dict(owner=uid, problem_id=problem_id, code=code, preview=preview,
                                     input=copy.deepcopy(args), trace=trace, created=now, size=len(json.dumps(trace)))
        while len(PREVIEW_TRACES) > 160 or (len(PREVIEW_TRACES) > 1 and sum(item["size"] for item in PREVIEW_TRACES.values()) > 16_000_000):
            PREVIEW_TRACES.popitem(last=False)
    return token


def tutor_context(uid, p, supplied):
    """Resolve evidence and assistance from the server, never from client claims."""
    context = {"problemId": p["id"], "problem": p["title"],
               "metadata": {k: p[k] for k in ("statement", "decoder", "params", "category", "complexity", "recall", "transfer")},
               "stage": supplied.get("stage", "code"), "code": supplied.get("code", ""),
               "notes": supplied.get("notes", {})}
    if "args" in supplied:
        valid_args(p, supplied["args"])
        context["input"] = supplied["args"]
    base = p.get("parent", p["id"])
    if "parent" in p:
        original = problem_by_id(base)
        context["modification"] = dict(requirement=p["statement"], returns=p["decoder"]["returns"], originalProblem=original["title"], originalStatement=original["statement"])
    with connect() as db:
        support = db.execute("SELECT hint_level,revealed FROM learning_support WHERE user_id=? AND problem_id=?", (uid, p["id"])).fetchone()
        progress = db.execute("SELECT stage FROM learning_progress WHERE user_id=? AND problem_id=?", (uid, base)).fetchone()
        commitment = db.execute("SELECT detail FROM learning_evidence WHERE user_id=? AND problem_id=? AND kind='approach'", (uid, base)).fetchone()
        row = db.execute("SELECT s.trace,a.code,a.input FROM execution_sessions s JOIN attempts a ON a.id=s.attempt_id WHERE a.id=? AND a.user_id=? AND a.problem_id=?", (supplied.get("attemptId"), uid, p["id"])).fetchone()
    level = support["hint_level"] if support else 0
    context.update(hintLevel=level, hintsUsed=p["hints"][:level], revealed=bool(support and support["revealed"]), learningStage=progress[0] if progress else "Seen",
                   approach=json.loads(commitment["detail"]) if commitment else None)
    if not commitment:
        # Topic labels and recall questions can name the technique; withhold them until the learner commits.
        context["metadata"].pop("category")
        context["metadata"].pop("recall")
    evidence = dict(trace=json.loads(row["trace"]), code=row["code"], input=json.loads(row["input"])) if row else None
    if not evidence and supplied.get("traceId"):
        with PREVIEW_LOCK:
            item = PREVIEW_TRACES.get(supplied["traceId"])
            if item and item["owner"] == uid and item["problem_id"] == p["id"] and time.monotonic() - item["created"] <= 600:
                evidence = dict(item, preview=item["preview"])
    if evidence:
        trace = evidence["trace"]
        step = supplied.get("step", 0)
        if trace["events"] and not 0 <= step < len(trace["events"]):
            raise ValueError("Choose a valid recorded step.")
        events = trace["events"]
        context.update(recordedEvent=events[step] if events else None,
                       previousEvent=events[step - 1] if events and step > 0 else None,
                       nextEvent=events[step + 1] if step + 1 < len(events) else None,
                       recordedCode=evidence["code"], recordedInput=evidence["input"],
                       result=trace["result"], error=trace["error"], preview=evidence.get("preview", False),
                       evaluation=trace.get("evaluation"), truncated=trace.get("truncated", False),
                       stale=("code" in supplied and supplied["code"] != evidence["code"]) or ("args" in supplied and supplied["args"] != evidence["input"]),
                       eventCount=len(events))
        # Only claims with a witnessed boundary are made. Never equate a final
        # mismatch with the first faulty assignment in an arbitrary algorithm.
        evaluation, goal = trace.get("evaluation") or {}, trace.get("goal") or {}
        # The goal for an input is its answer: like the stage, the guide has it only once the code returned for it.
        context["goal"] = None if trace.get("error") else trace.get("goal")
        divergence = observable_divergence(p, trace, evaluation.get("expected", goal.get("expected")), evaluation["passed"] if "passed" in evaluation else goal.get("matches"))
        if divergence:
            context["divergence"] = divergence
    return context


@app.post("/api/explain")
def explain():
    from guide import answer, validate_chat
    uid = identity()
    data = json_body()
    with connect() as db:
        row = db.execute("SELECT problem_id FROM attempts WHERE id=? AND user_id=?", (data.get("attemptId"), uid)).fetchone()
    problem_id = row[0] if row else data.get("problemId")
    _, history, supplied = validate_chat({"message": "Explain this execution step", "history": data.get("history", []), "context": {**data, "problemId": problem_id, "stage": "code"}})
    p = problem_by_id(problem_id, uid)
    if not p:
        raise ValueError("Run your code before requesting an explanation.")
    context = tutor_context(uid, p, supplied)
    result = answer("Explain this execution step", history, PROBLEMS, context, p)
    result["provider"] = "Trace guide"
    result["sources"] = recorded_lessons(result["sources"], [], set())  # An explanation records no guidance.
    return jsonify(result)


def recorded_lessons(sources, used, helped):
    """The Guide shows a lesson's text only where showing it is recorded: platform help, the lessons this reply records,
    and lessons of problems it records as helped. Any other lesson is listed by title only, because its text (another
    problem's prompts or hints, or a concept lesson naming which problems use a technique) would be unrecorded guidance."""
    return [s if s["id"].startswith("help:") or s in used or (s.get("problemId") in helped and not s["id"].startswith("topic:")) else {**s, "text": ""} for s in sources]


@app.post("/api/chat")
def chat():
    from guide import answer, validate_chat
    uid = identity()
    message, history, supplied = validate_chat(request.get_json())
    p = problem_by_id(supplied.get("problemId"), uid)
    if supplied.get("problemId") and not p:
        raise ValueError("Unknown practice problem.")
    require_opened(uid, p)
    if not GUIDE_REQUESTS.acquire(blocking=False):
        return jsonify(error="The guide is busy. Try again in a moment."), 429
    try:
        context = tutor_context(uid, p, supplied) if p else {}
        result = answer(message, history, PROBLEMS, context, p)
        used = result["sources"] if result["provider"] == "AI guide" else result["sources"][:1]
        helped = {s["problemId"] for s in used if s.get("problemId") and not s["id"].startswith("help:")}
        if p and result.get("tutoring"): helped.add(p["id"])
        # A concept lesson shown in full says which problems use its technique: their topic has been shown.
        named = {q["id"] for s in used if s["id"].startswith("topic:") for q in PROBLEMS if q["title"] in s["text"]}
        with connect() as db:
            for problem_id in helped:
                level = max(1, result.get("hintLevel", 0)) if p and problem_id == p["id"] else 1
                db.execute("INSERT INTO learning_support(user_id,problem_id,hint_level) VALUES(?,?,?) ON CONFLICT(user_id,problem_id) DO UPDATE SET hint_level=MAX(hint_level,excluded.hint_level)", (uid, problem_id, level))
            for problem_id in named:
                note_support(db, uid, problem_id, "topic")
        result["sources"] = recorded_lessons(result["sources"], used, helped)
        result["assistedProblemIds"] = sorted(helped)
        return jsonify(result)
    finally:
        GUIDE_REQUESTS.release()


# ----------------------------- your own sheet -----------------------------
MAX_SHEETS = 30


def public_problem(p):
    return {k: v for k, v in p.items() if k not in {"tests", "solution", "brute"}}


def read_text(text):
    """Pasted or recognised text: a copied spreadsheet range (tab-separated), JSON, HTML or a plain list."""
    stripped = text.strip()
    if sum(1 for line in stripped.splitlines() if "\t" in line) >= 2:
        return sheets.rows_from_csv(stripped)
    if stripped[:1] in "[{":
        try:
            return sheets.rows_from_json(json.loads(stripped))
        except (json.JSONDecodeError, ValueError, RecursionError):
            pass
    if re.search(r"<(table|a\s)", stripped, re.I):
        return sheets.rows_from_html(stripped)[0]
    return sheets.rows_from_text(stripped)


@app.post("/api/sheets/read")
def read_sheet():
    """Read a sheet without saving it: the learner reviews every row first."""
    identity()
    if (request.content_type or "").startswith("multipart/"):
        request.max_content_length = 3_000_000
        upload = request.files.get("file")
        if not upload or not upload.filename:
            raise ValueError("Choose a file to upload.")
        rows, name = sheets.read_upload(upload.filename, upload.read(3_000_001))
        source, origin = "file", upload.filename[:200]
    else:
        request.max_content_length = 400_000
        data = json_body()
        url, text = data.get("url"), data.get("text")
        if isinstance(url, str) and url.strip():
            rows, name = sheets.read_link(url[:2000])
            source, origin = "link", url.strip()[:500]
        elif isinstance(text, str) and text.strip():
            image = data.get("source") == "image"
            rows, title = sheets.read_photo_text(text[:300_000]) if image else (read_text(text[:300_000]), "")
            name = title or (data["name"] if isinstance(data.get("name"), str) and data["name"].strip() else "My sheet")
            source, origin = ("image", "") if image else ("paste", "")
        else:
            raise ValueError("Upload a file, paste a link, or add a picture of your sheet.")
    rows = sheets.finish(rows)
    if not rows:
        raise ValueError("No problems were found. A sheet needs one problem per row or line: a title, a link, or both.")
    return jsonify(name=sheets.clean_title(name)[:80] or "My sheet", source=source, origin=origin, rows=rows)


def sheet_payload(db, uid):
    rows = db.execute("SELECT id,name,source,origin,rows,created_at,updated_at FROM sheets WHERE user_id=? ORDER BY created_at DESC, rowid DESC", (uid,)).fetchall()
    result = [dict(r, rows=json.loads(r["rows"])) for r in rows]
    labs = [lab_problem(db, uid, r["id"]) for r in db.execute("SELECT id FROM custom_labs WHERE user_id=? ORDER BY created_at, rowid", (uid,)).fetchall()]
    return dict(sheets=result, labs=[public_problem(lab) for lab in labs if lab])


@app.get("/api/sheets")
def list_sheets():
    uid = identity()
    with connect() as db:
        return jsonify(**sheet_payload(db, uid))


@app.post("/api/sheets")
def save_sheet():
    """Save a reviewed sheet (new, or edits to an existing one). Built-in matches are re-derived
    from each row; a hand-picked lab must exist; links to the learner's own labs are kept."""
    uid = identity()
    request.max_content_length = 600_000
    data = json_body()
    name = sheets.clean_title(data.get("name") if isinstance(data.get("name"), str) else "")[:80] or "My sheet"
    rows = sheets.clean_rows(data.get("rows"), {p["id"] for p in PROBLEMS})
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))
        if data.get("id"):
            old = db.execute("SELECT rows FROM sheets WHERE id=? AND user_id=?", (data["id"], uid)).fetchone()
            if not old:
                raise ValueError("That sheet no longer exists.")
            mine = {r["id"] for r in db.execute("SELECT id FROM custom_labs WHERE user_id=? AND sheet_id=?", (uid, data["id"]))}
            for row in rows:
                row["lab"] = row["lab"] if row["lab"] in mine else None
            db.execute("UPDATE sheets SET name=?,rows=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", (name, json.dumps(rows), data["id"], uid))
            sheet_id = data["id"]
        else:
            if db.execute("SELECT COUNT(*) FROM sheets WHERE user_id=?", (uid,)).fetchone()[0] >= MAX_SHEETS:
                raise ValueError(f"You can keep up to {MAX_SHEETS} sheets. Remove one to import another.")
            for row in rows:
                row["lab"] = None
            sheet_id = uuid.uuid4().hex[:16]
            source = data.get("source") if data.get("source") in {"file", "link", "image", "paste"} else "paste"
            origin = data.get("origin") if isinstance(data.get("origin"), str) else ""
            db.execute("INSERT INTO sheets(id,user_id,name,source,origin,rows) VALUES(?,?,?,?,?,?)", (sheet_id, uid, name, source, origin[:500], json.dumps(rows)))
        return jsonify(id=sheet_id, **sheet_payload(db, uid))


@app.delete("/api/sheets/<id_>")
def delete_sheet(id_):
    """Remove a sheet and the labs defined on it. Attempts and progress stay as history."""
    uid = identity()
    with connect() as db:
        if not db.execute("DELETE FROM sheets WHERE id=? AND user_id=?", (id_, uid)).rowcount:
            raise ValueError("That sheet no longer exists.")
        db.execute("DELETE FROM custom_labs WHERE sheet_id=? AND user_id=?", (id_, uid))
        return jsonify(**sheet_payload(db, uid))


@app.post("/api/labs/examples")
def lab_examples():
    """Read pasted judge-style examples into parameters and cases for the lab builder."""
    identity()
    request.max_content_length = 100_000
    data = json_body()
    return jsonify(sheets.parse_examples(data.get("text")))


@app.post("/api/labs/fetch")
def fetch_problem():
    """Read a sheet row's problem (statement, constraints, examples) from its own page, for the learner to
    check before building the lab. One page, on request; nothing is saved here."""
    uid = identity()
    data = json_body()
    with connect() as db:
        sheet = db.execute("SELECT rows FROM sheets WHERE id=? AND user_id=?", (data.get("sheetId"), uid)).fetchone()
    if not sheet:
        raise ValueError("Save the sheet before reading its problems.")
    rows, index = json.loads(sheet["rows"]), data.get("row")
    if type(index) is not int or not 0 <= index < len(rows):
        raise ValueError("Choose a problem from the sheet.")
    link = data.get("url")
    if link is not None:
        # A link the learner pastes for this problem: read that page instead of the row's own links.
        if not isinstance(link, str) or not re.match(r"https?://\S+$", link.strip()) or len(link) > 2000:
            raise ValueError("Paste the problem's full link, starting with https://")
        return jsonify(sheets.read_problem({"source": link.strip()}))
    return jsonify(sheets.read_problem(rows[index]))


@app.post("/api/labs")
def save_lab():
    """Create or update the learner's own lab for one row of their sheet."""
    uid = identity()
    request.max_content_length = 300_000
    data = json_body()
    lab = sheets.build_lab(data)
    index = data.get("row")
    with connect() as db:
        sheet = db.execute("SELECT rows FROM sheets WHERE id=? AND user_id=?", (data.get("sheetId"), uid)).fetchone()
        if not sheet:
            raise ValueError("Save the sheet before building a lab for it.")
        rows = json.loads(sheet["rows"])
        if type(index) is not int or not 0 <= index < len(rows):
            raise ValueError("Choose a problem from the sheet.")
        lab_id = rows[index].get("lab")
        if lab_id and not db.execute("SELECT 1 FROM custom_labs WHERE id=? AND user_id=?", (lab_id, uid)).fetchone():
            lab_id = None
        if lab_id:
            db.execute("UPDATE custom_labs SET data=? WHERE id=? AND user_id=?", (json.dumps(lab), lab_id, uid))
        else:
            lab_id = "custom-" + uuid.uuid4().hex[:12]
            db.execute("INSERT INTO custom_labs(id,user_id,sheet_id,data) VALUES(?,?,?,?)", (lab_id, uid, data["sheetId"], json.dumps(lab)))
            rows[index]["lab"] = lab_id
        if lab.get("source") and not rows[index].get("url"):
            rows[index]["url"] = rows[index]["source"] = lab["source"]  # The page the problem was read from becomes its link.
        db.execute("UPDATE sheets SET rows=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", (json.dumps(rows), data["sheetId"], uid))
        return jsonify(lab=public_problem(lab_problem(db, uid, lab_id)), **sheet_payload(db, uid))


@app.get("/practice")
@app.get("/sheets")
@app.get("/")
def index():
    if (ROOT / "dist" / "index.html").exists():
        return send_from_directory(ROOT / "dist", "index.html")
    return "Visual DSA API is running. Open http://127.0.0.1:5173 for the workspace."


if (ROOT / "data" / "problems.json").exists():
    initialize()

if __name__ == "__main__":
    # Its own port rather than Flask's usual 5000, which other local projects often take; `npm run dev` proxies to it.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5057")), debug=False)
