"""Visual DSA: API, persistence, AST instrumentation and isolated trace worker.

The local worker accepts a deliberately restricted Python subset. It is a
development runner, not an OS security boundary. Public mode requires Docker.
"""
import ast
import builtins
import collections
import copy
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
MAX_SECONDS = 3
BIG_BITS = 1 << 18  # Library calls refuse results bounded above this size: their C loops cannot be stepped.
LIMIT_MESSAGE = "Execution limit reached. Check loop boundaries or try a smaller input."
# A batch's case budgets add up to at most 6 seconds; the OS CPU limit and the parent's wall-clock limit sit
# above that as backstops for work inside built-in code that the tracer cannot step through.
WORKER_CPU_SECONDS, WORKER_SECONDS, WORKER_INPUT = 7, 9, 80000


class ExecutionLimit(Exception):
    pass


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
              "map", "filter", "chr", "ord", "bin", "divmod", "pow", "isinstance", "iter", "next", "frozenset", "hash", "object", "hex", "oct"}
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
DECORATORS = {"cache", "lru_cache"}
DUNDER_METHODS = {"__init__", "__lt__", "__le__", "__gt__", "__ge__", "__eq__", "__hash__", "__repr__", "__str__", "__len__"}
EVENT_CALLS = {"heappush", "heappop", "heapify", "heappushpop", "heapreplace", "insort", "insort_left", "insort_right"}


def validate_source(source, entry="solve"):
    if not isinstance(source, str) or len(source) > 12000:
        raise ValueError("Keep your program under 12,000 characters.")
    tree = ast.parse(source, filename="<student>")
    defined = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    lambdas = {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign) and isinstance(n.value, ast.Lambda) for t in n.targets if isinstance(t, ast.Name)}
    if entry == "solve":
        if "solve" not in {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}:
            raise ValueError("Define a function named solve with the problem's parameters.")
    elif entry not in {n.name for n in tree.body if isinstance(n, ast.ClassDef)}:
        raise ValueError(f"Define a class named {entry} with the methods the problem calls.")
    for top in tree.body:
        simple = isinstance(top, (ast.Assign, ast.AnnAssign)) and all(isinstance(t, ast.Name) for t in (top.targets if isinstance(top, ast.Assign) else [top.target]))
        if not (isinstance(top, (ast.FunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)) or simple or (isinstance(top, ast.Expr) and isinstance(top.value, ast.Constant) and isinstance(top.value.value, str))):
            raise ValueError("Place your code inside solve, a helper function or a class.")
    denied = (ast.AsyncFunctionDef, ast.Await, ast.With, ast.AsyncWith, ast.Try, getattr(ast, "TryStar", ast.Try), ast.Raise, ast.Yield, ast.YieldFrom)
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, denied):
            raise ValueError(f"{type(n).__name__} is outside the supported learning subset.")
        if isinstance(n, ast.Import):
            for alias in n.names:
                if alias.name not in MODULES:
                    raise ValueError(f"Importing {alias.name} isn't supported. You can import {', '.join(sorted(MODULES))}.")
                imported.add(alias.asname or alias.name)
        if isinstance(n, ast.ImportFrom):
            if n.level or n.module not in MODULES:
                raise ValueError(f"Importing from {n.module} isn't supported. You can import {', '.join(sorted(MODULES))}.")
            for alias in n.names:
                if alias.name not in MODULES[n.module]:
                    raise ValueError(f"{n.module}.{alias.name} isn't available in the learning runner.")
                imported.add(alias.asname or alias.name)
        if isinstance(n, ast.alias) and (n.asname or "").startswith("_"):
            raise ValueError("Names starting with an underscore are reserved for the tracer.")
        if isinstance(n, (ast.Name, ast.arg)) and (n.id if isinstance(n, ast.Name) else n.arg).startswith("_") and (n.id if isinstance(n, ast.Name) else n.arg) != "_":
            raise ValueError("Names starting with an underscore are reserved for the tracer.")
        if isinstance(n, ast.FunctionDef):
            if n.name.startswith("_") and n.name not in DUNDER_METHODS:
                raise ValueError("Names starting with an underscore are reserved for the tracer.")
            for decorator in n.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
                if name not in DECORATORS:
                    raise ValueError("Only the @cache and @lru_cache decorators are supported.")
        if isinstance(n, ast.ClassDef) and (n.name.startswith("_") or n.decorator_list or n.keywords or any(not isinstance(b, ast.Name) for b in n.bases)):
            raise ValueError("Use plain classes: no decorators, metaclasses or computed base classes.")
        if isinstance(n, ast.Attribute) and (n.attr.startswith("__") or n.attr in BLOCKED_ATTRS):
            raise ValueError(f"Attribute '{n.attr}' is not allowed in the learning runner.")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id not in SAFE_CALLS | defined | imported | lambdas | PROVIDED_NAMES:
            raise ValueError(f"Call '{n.func.id}' is not supported. Use the built-in learning operations.")
        if isinstance(n, ast.Call) and not isinstance(n.func, (ast.Name, ast.Attribute)):
            raise ValueError("Indirect function calls are not supported.")
    if sum(1 for _ in ast.walk(tree)) > 3000:
        raise ValueError("This program is too large for a learning trace.")
    return tree


def helper(name, args, original):
    return ast.copy_location(ast.Call(func=ast.Name(id=name, ctx=ast.Load()), args=args, keywords=[]), original)


ARRAY_POINTERS = {"i", "j", "left", "right", "mid", "start", "end", "slow", "fast", "lo", "hi", "low", "high"}
NODE_LINKS = {"next", "prev", "left", "right", "random", "child", "parent", "back", "bottom", "down", "up"}
POINTER_NAMES = {"i", "j", "k", "left", "right", "mid", "start", "end", "slow", "fast", "lo", "hi", "low", "high", "l", "r", "top", "front", "rear",
                 "curr", "cur", "prev", "temp", "tmp", "node", "head", "tail", "dummy", "nxt", "p", "q"}


class Instrument(ast.NodeTransformer):
    """Instrument evaluated expressions without evaluating operands twice."""
    def emit(self, kind, node, detail="", root="", targets=()):
        return ast.copy_location(ast.Expr(helper("_mark", [ast.Constant(kind), ast.Constant(node.lineno), ast.Constant(detail), ast.Constant(root), ast.Constant(tuple(targets))], node)), node)

    def visit_Assign(self, node):
        # Classify each element of a tuple target: `a[i], a[j] = a[j], a[i]` writes two elements.
        target = node.targets[0]
        parts = target.elts if isinstance(target, (ast.Tuple, ast.List)) else [target]
        names = [ast.unparse(t) for t in parts]
        written = next((t for t in parts if isinstance(t, ast.Subscript)), None)
        kind, root = "STATE_CHANGE", ""
        if written:
            kind = "WRITE"
            while isinstance(written, ast.Subscript):
                written = written.value
            root = ast.unparse(written)
        elif any(isinstance(t, ast.Attribute) and t.attr in NODE_LINKS for t in parts):
            kind = "LINK_WRITE"  # node.next = prev: the structure is re-linked.
        elif all(isinstance(t, ast.Name) and t.id in POINTER_NAMES for t in parts):
            kind = "POINTER_MOVE"
        self.generic_visit(node)
        return [node, self.emit(kind, node, ", ".join(names), root, names if len(names) > 1 else ())]

    def visit_AugAssign(self, node):
        # Route augmented arithmetic through the same allocation guards.
        target = copy.deepcopy(node.target)
        if hasattr(target, "ctx"):
            target.ctx = ast.Load()
        operation = ast.copy_location(ast.BinOp(left=target, op=node.op, right=node.value), node)
        replacement = ast.copy_location(ast.Assign(targets=[node.target], value=operation), node)
        return self.visit_Assign(replacement)

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
        self.generic_visit(node)
        if len(node.ops) == 1:
            return helper("_compare", [node.left, node.comparators[0], ast.Constant(type(node.ops[0]).__name__), ast.Constant(text), ast.Constant(node.lineno)], node)
        return node  # Python's chained comparison short-circuit semantics remain intact.

    def visit_BinOp(self, node):
        self.generic_visit(node)
        return helper("_binary", [node.left, node.right, ast.Constant(type(node.op).__name__), ast.Constant(node.lineno)], node)

    def visit_FunctionDef(self, node):
        # Type hints are documentation: they are never evaluated.
        node.returns = None
        for arg in node.args.args + node.args.kwonlyargs + node.args.posonlyargs + [x for x in (node.args.vararg, node.args.kwarg) if x]:
            arg.annotation = None
        self.generic_visit(node)
        return node

    def visit_AnnAssign(self, node):
        if node.value is None:
            return None
        return self.visit_Assign(ast.copy_location(ast.Assign(targets=[node.target], value=node.value), node))

    def visit_Attribute(self, node):
        self.generic_visit(node)
        if isinstance(node.ctx, ast.Load):
            return helper("_attr", [node.value, ast.Constant(node.attr)], node)
        return node

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            # obj.method(...): one guarded call that also records what it did to a structure.
            args = [self.visit(a) for a in node.args]
            keywords = [ast.keyword(arg=k.arg, value=self.visit(k.value)) for k in node.keywords]
            call = ast.Call(func=ast.Name(id="_method", ctx=ast.Load()), args=[self.visit(node.func.value), ast.Constant(node.func.attr), ast.Constant(node.lineno), *args], keywords=keywords)
            return ast.copy_location(call, node)
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id in EVENT_CALLS:
            call = ast.Call(func=ast.Name(id="_fcall", ctx=ast.Load()), args=[node.func, ast.Constant(node.func.id), ast.Constant(node.lineno), *node.args], keywords=node.keywords)
            return ast.copy_location(call, node)
        return node

    def visit_For(self, node):
        self.generic_visit(node)
        names = node.target.elts if isinstance(node.target, (ast.Tuple, ast.List)) else [node.target]
        node.body.insert(0, self.emit("LOOP_START", node, ", ".join(ast.unparse(t) for t in names)))
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
GRAPH_NAMES = {"adj", "graph", "g", "adjlist", "adjacency", "adjacencylist", "gr", "isconnected", "edges", "edgelist", "connections", "roads", "neighbors"}
BIT_OPS = {"BitAnd": "&", "BitOr": "|", "BitXor": "^", "LShift": "<<", "RShift": ">>"}
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
    loop_states = {}  # (activation, line) -> {state digest: first step}
    entry, kinds = payload.get("entry", "solve"), payload.get("kinds") or []
    node_ids, keepalive, node_names = {}, [], set()  # Stable node numbers for this run.
    heap_ids, row_of, hot_cells = set(), {}, {}
    tracing = [False]

    def node_id(obj):
        if id(obj) not in node_ids:
            node_ids[id(obj)] = len(node_ids) + 1
            keepalive.append(obj)  # Keep ids from being reused while the run lasts.
        return node_ids[id(obj)]

    def node_like(obj):
        attrs = getattr(obj, "__dict__", {})
        return any(k in LABEL_ATTRS or k in NODE_LINKS or k in ("children", "neighbors") for k in attrs)

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
                    queue.append(value)
                elif value is None and key in NODE_LINKS:
                    links[key] = None
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

    def sequence_kind(name, value):
        base = name.split(".")[-1].lower()
        if isinstance(value, collections.deque) or re.fullmatch(r"q|qu|dq|queue|\w*queue|bfs", base):
            return "queue"
        if id(value) in heap_ids or re.fullmatch(r"h|heap|pq|minh|maxh|\w*heap|\w*_pq", base):
            return "heap"
        if re.fullmatch(r"st|stk|stack|\w*stack", base):
            return "stack"
        return None

    def as_matrix(value):
        return (isinstance(value, list) and 0 < len(value) <= 40 and all(isinstance(r, list) for r in value) and 0 < len(value[0]) <= 40
                and all(len(r) == len(value[0]) for r in value) and all(x is None or isinstance(x, (bool, int, float, str)) for r in value for x in r))

    def as_graph(name, value, size):
        """Adjacency lists, adjacency matrices and edge lists, as drawn graphs (nodes and edges)."""
        key = name.split(".")[-1].lower().replace("_", "")
        if key not in GRAPH_NAMES:
            return None
        edges, labels = [], None
        if isinstance(value, dict) and all(isinstance(v, (list, set, tuple)) for v in value.values()):
            labels = list(value.keys())
            for u, vs in value.items():
                for v in list(vs):
                    target = v[0] if isinstance(v, (list, tuple)) and v else v
                    if target not in labels and len(labels) < MAX_NODES:
                        labels.append(target)
                    if target in labels:
                        edges.append([labels.index(u), labels.index(target), v[1] if isinstance(v, (list, tuple)) and len(v) > 1 else None])
        elif isinstance(value, list) and value and all(isinstance(r, (list, tuple)) for r in value):
            n = len(value)
            ints = lambda r: all(isinstance(x, int) and not isinstance(x, bool) for x in r)
            if key in {"edges", "edgelist", "connections", "roads"} and all(len(r) in (2, 3) and ints(r) for r in value):
                count = size or (max(max(r[0], r[1]) for r in value) + 1)
                labels = list(range(min(count, MAX_NODES)))
                edges = [[r[0], r[1], r[2] if len(r) > 2 else None] for r in value if r[0] < len(labels) and r[1] < len(labels)]
            elif as_matrix(value) and len(value[0]) == n and all(x in (0, 1) for r in value for x in r):
                labels = list(range(n))
                edges = [[i, j, None] for i in range(n) for j in range(n) if value[i][j] and i != j]
            elif all(ints(r) and all(0 <= x < n for x in r) for r in value):
                labels = list(range(n))
                edges = [[u, v, None] for u, r in enumerate(value) for v in r]
            elif all(all(isinstance(x, (list, tuple)) and len(x) == 2 and ints(x) and 0 <= x[0] < n for x in r) for r in value):
                labels = list(range(n))
                edges = [[u, x[0], x[1]] for u, r in enumerate(value) for x in r]
        if labels is None or len(labels) > MAX_NODES:
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
            if name == "self" and is_node_object(value) and not node_like(value):
                # A design class (a stack, a trie, a cache): its fields are the structures.
                items += [(f"self.{k}", v) for k, v in list(vars(value).items())[:16] if not k.startswith("_") and not callable(v)]
                continue
            items.append((name, value))
        size = next((v for n, v in items if n.split(".")[-1] in ("V", "n", "N", "v", "vertices") and isinstance(v, int) and not isinstance(v, bool) and 0 < v <= MAX_NODES), None)
        pointers = {k: v for k, v in items if k in ARRAY_POINTERS and isinstance(v, int) and not isinstance(v, bool)}
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
                structures.append({"id": name, "type": "array", "kind": sequence_kind(name, value), "values": [node_text(x) if is_node_object(x) else bounded(x) for x in seq],
                                   "nodeRefs": [node_id(x) if is_node_object(x) else None for x in seq], "length": len(value), "highlights": hot.get(name, []), "pointers": {}})
                continue
            graph = as_graph(name, value, size)
            if graph:
                structures.append({"id": name, **graph})
                continue
            if as_matrix(value):  # A grid, a DP table, a board: rows of equal length.
                structures.append({"id": name, "type": "matrix", "rows": [[bounded(x) for x in row[:24]] for row in value[:24]], "shape": [len(value), len(value[0])], "hot": hot_cells.get(name, [])})
                continue
            if isinstance(value, str) and len(value) <= 1:
                variables.append({"id": name, "value": value})  # One character is a value, not a sequence.
            elif isinstance(value, (list, tuple, str, collections.deque)):
                values = bounded(value) if not isinstance(value, str) else list(value[:MAX_ITEMS])
                entry_ = {"id": name, "type": "string" if isinstance(value, str) else "array", "values": values, "length": len(value), "highlights": hot.get(name, []), "pointers": {k: v for k, v in pointers.items() if 0 <= v < len(values)}}
                kind = None if isinstance(value, str) else sequence_kind(name, value)
                if kind:
                    entry_["kind"] = kind
                structures.append(entry_)
            elif isinstance(value, dict):
                objects = [v for v in list(value.values())[:MAX_ITEMS] if is_node_object(v)]
                roots += objects
                structures.append({"id": name, "type": "hashmap", "entries": [{"key": bounded(k), "value": node_text(v) if is_node_object(v) else bounded(v)} for k, v in list(value.items())[:MAX_ITEMS]]})
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
                    if key == "self" and is_node_object(value) and not node_like(value):
                        held += [v for k, v in vars(value).items() if not k.startswith("_")]  # A design object: its fields.
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

    def check():
        nonlocal ticks
        ticks += 1
        if ticks > MAX_TICKS or time.monotonic() - started > seconds:
            raise ExecutionLimit(LIMIT_MESSAGE)

    def check_time():
        if time.monotonic() - started > seconds:
            raise ExecutionLimit(LIMIT_MESSAGE)

    def emit(kind, line, locals_, detail="", metadata=None):
        nonlocal truncated
        check()
        if not tracing[0]:
            return  # Definitions run before the traced program starts.
        if len(events) >= MAX_EVENTS:
            truncated = True
            return
        events.append({"id": len(events), "type": kind, "line": line, "source": lines[line - 1].strip() if 0 < line <= len(lines) else "", "detail": detail, "meta": metadata or {}, "state": state(locals_)})

    def mark(kind, line, detail, root, targets):
        loc = sys._getframe(1).f_locals
        if kind == "WRITE":
            kind = "HASHMAP_INSERT" if isinstance(loc.get(root), dict) else "ARRAY_WRITE"
        if kind == "WHILE_START":
            emit("LOOP_START", line, loc, "The loop state changed.", {"loop": "while"})
            repeat_check(loc, line)
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
    def compare(a, b, op, text, line):
        result = compares[op](a, b)
        kind = "HASHMAP_LOOKUP" if op in {"In", "NotIn"} and isinstance(b, (dict, set)) else "COMPARE"
        # Membership presence and branch result differ for `not in`.
        emit(kind, line, sys._getframe(1).f_locals, f"{text} is {result}.", {"expression": text, "left": bounded(a), "right": bounded(b), "result": bool(result), "found": a in b if kind == "HASHMAP_LOOKUP" else None})
        return result

    def access(obj, key, name, line, index):
        try:
            value = obj[key]
        except (IndexError, KeyError):
            # Record what was attempted; the exception still stops the program.
            failure.update(access={"structure": name, "key": bounded(key), "index": index, "size": len(obj), "kind": "dict" if isinstance(obj, dict) else "sequence"})
            raise
        if isinstance(key, int) and not isinstance(key, bool):
            hot[name] = [key if key >= 0 else len(obj) + key]
            if isinstance(value, list):
                row_of[id(value)] = (name, key if key >= 0 else len(obj) + key)  # grid[i] → the row of grid
            if id(obj) in row_of:
                grid, row = row_of[id(obj)]
                hot_cells[grid] = [[row, key if key >= 0 else len(obj) + key]]  # grid[i][j]
        emit("HASHMAP_LOOKUP" if isinstance(obj, dict) else "ARRAY_ACCESS", line, sys._getframe(1).f_locals, f"Read {name}[{key}] → {bounded(value)}.", {"structure": name, "key": bounded(key), "value": bounded(value), "found": True, "index": index})
        hot_cells.clear()  # A grid cell is "just read" only at the step that read it.
        return value

    binops = {"Add": operator.add, "Sub": operator.sub, "Mult": operator.mul, "Div": operator.truediv, "FloorDiv": operator.floordiv, "Mod": operator.mod, "Pow": operator.pow, "BitAnd": operator.and_, "BitOr": operator.or_, "BitXor": operator.xor, "LShift": operator.lshift, "RShift": operator.rshift}
    def binary(a, b, op, line):
        check()
        if op == "Pow" and type(a) is int and type(b) is int and b > 0 and (abs(a).bit_length() - 1) * b > 4096:
            raise ExecutionLimit("The integer exceeds the learning limit.")  # Refused before the big power is computed.
        if op == "Mult" and ((isinstance(a, (str, list, tuple)) and isinstance(b, int) and len(a) * max(0, b) > 10000) or (isinstance(b, (str, list, tuple)) and isinstance(a, int) and len(b) * max(0, a) > 10000)):
            raise ExecutionLimit("That allocation is too large for the learning runner.")
        if op in {"Pow", "LShift", "RShift"} and (not isinstance(b, int) or abs(b) > 1024):
            raise ExecutionLimit("That arithmetic operation exceeds the learning limit.")
        if op == "Add" and isinstance(a, (str, list, tuple)) and isinstance(b, type(a)) and len(a) + len(b) > 10000:
            raise ExecutionLimit("The collection is too large for the learning runner.")
        result = binops[op](a, b)
        if isinstance(result, int) and result.bit_length() > 4096:
            raise ExecutionLimit("The integer exceeds the learning limit.")
        if op in BIT_OPS and type(a) is int and type(b) is int and tracing[0]:
            emit("BIT_OP", line, sys._getframe(1).f_locals, f"{a} {BIT_OPS[op]} {b} → {result}.", {"op": BIT_OPS[op], "left": a, "right": b, "result": result})
        return result

    def attr(obj, name):
        """Attribute reads: anything on the learner's own objects; on built-in values only their safe methods."""
        if is_node_object(obj) or (isinstance(obj, type) and obj.__module__ == "student") or isinstance(obj, ModuleView) or name in SAFE_ATTRS:
            return getattr(obj, name)
        raise AttributeError(f"'{name}' is not available on {type(obj).__name__} in the learning runner.")

    def record(kind, name, line, args, result, loc):
        shown = ", ".join(node_text(a) if is_node_object(a) else str(bounded(a)) for a in args)
        emit(kind, line, loc, f"{name}({shown}) → {node_text(result) if is_node_object(result) else bounded(result)}.")

    def method(obj, name, line, *args, **kwargs):
        check()
        if name in {"append", "add", "appendleft", "insert", "extend"} and hasattr(obj, "__len__") and len(obj) >= 10000:
            raise ExecutionLimit("The collection is too large for the learning runner.")
        if name in EVENT_CALLS and args and isinstance(args[0], list):
            heap_ids.add(id(args[0]))
        result = attr(obj, name)(*args, **kwargs)
        if name == "elements" and isinstance(obj, collections.Counter):
            return stepped(result)  # Counter({1: 10**9}).elements() is a C iterator: each item is a step.
        if is_node_object(obj) or isinstance(obj, type) or (isinstance(obj, ModuleView) and name not in EVENT_CALLS):
            return result  # Calls into the learner's own methods are recorded by the call tracer.
        record(METHOD_EVENTS.get(name, "STATE_CHANGE"), name, line, args, result, sys._getframe(1).f_locals)
        return result

    def fcall(fn, name, line, *args, **kwargs):
        check()
        if args and isinstance(args[0], list):
            heap_ids.add(id(args[0]))
        result = fn(*args, **kwargs)
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
            params = code.co_varnames[:code.co_argcount + code.co_kwonlyargcount]
            args = {p: brief(frame.f_locals.get(p)) for p in params if p != "self"}
            emit("RECURSION_CALL", frame.f_lineno, frame.f_locals, f"Enter {name}({', '.join(f'{k}={v}' for k, v in args.items())}).", {"call": {"id": call_ids[-1], "fn": name, "args": args, "depth": len(callstack)}})
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

    def safe_print(*args, **kwargs):
        if output.tell() > 4000:
            raise ExecutionLimit("Console output limit reached.")
        print(*(bounded(a) for a in args), file=output)

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
                 "ListNode": ListNode, "TreeNode": TreeNode, "Node": Node})
    env = {"__builtins__": safe, "__name__": "student", "_mark": mark, "_access": access, "_compare": compare, "_binary": binary, "_method": method,
           "_fcall": fcall, "_attr": attr, "_returned": returned, "_slice": slice}
    error, result = None, None
    try:
        tree = Instrument().visit(validate_source(source, entry))
        ast.fix_missing_locations(tree)
        sys.setrecursionlimit(400)
        sys.settrace(trace)  # Definitions and top-level values run within the budget, but are not shown.
        exec(compile(tree, "<student>", "exec"), env, env)  # Only in the dedicated worker.
        tracing[0] = True
        if entry == "solve":
            args = [build_input(kind, value) for kind, value in itertools.zip_longest(kinds, payload["args"])][:len(payload["args"])]
            args = link_cycles(args, kinds)
            returned = env["solve"](*args)
            result = node_label(returned) if payload.get("answer") == "node-value" and is_node_object(returned) else result_value(returned)
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
        error = {"type": type(exc).__name__, "message": str(exc)[:700], "line": line}
        if len(events) < MAX_EVENTS:
            events.append({"id": len(events), "type": "ERROR", "line": line or 1, "source": lines[line - 1].strip() if line and 0 < line <= len(lines) else "", "detail": error["message"], "meta": dict(failure), "state": state(loc)})
    finally:
        sys.settrace(None)
    return {"events": events, "truncated": truncated, "result": result, "error": error, "stdout": output.getvalue()[:4000], "durationMs": round((time.monotonic() - started) * 1000, 2),
            "lines": {str(k): v for k, v in sorted(line_counts.items())}}


def stopped_trace(seconds):
    """The case a worker was running when it was stopped from outside (its CPU, memory or wall-clock limit):
    the work ran in built-in code the line tracer cannot step through, so only the limit itself is known."""
    return {"events": [], "result": None, "error": {"type": "ExecutionLimit", "message": "Execution limit reached: the runner stopped this case at its time or memory limit, inside a built-in operation the tracer cannot step through. Check loop boundaries or try a smaller input.", "line": None}, "stdout": "", "durationMs": round(seconds * 1000, 2), "lines": {}}


def not_run_trace(number):
    return {"events": [], "result": None, "error": {"type": "NotRun", "message": f"Not traced: the runner stopped on case {number} before reaching this one.", "line": None}, "stdout": "", "durationMs": 0, "lines": {}}


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
    for args in request_["cases"]:  # One line per finished case, so a stopped worker still reports the cases it finished.
        print(json.dumps(execute_worker({"code": request_["code"], "args": args, "budget": request_["budget"], "kinds": request_.get("kinds"), "entry": request_.get("entry", "solve"), "answer": request_.get("answer")})), flush=True)
    sys.exit(0)


# ----------------------------- HTTP + SQLite -----------------------------
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException
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
        return lab_problem(db, uid, id_)


def lab_problem(db, uid, id_):
    row = db.execute("SELECT l.data,l.sheet_id,s.name,s.rows FROM custom_labs l LEFT JOIN sheets s ON s.id=l.sheet_id AND s.user_id=l.user_id WHERE l.id=? AND l.user_id=?", (id_, uid)).fetchone()
    if not row:
        return None
    rows = json.loads(row["rows"]) if row["rows"] else []
    number = next((i + 1 for i, r in enumerate(rows) if r.get("lab") == id_), 1)
    return sheets.as_problem(id_, json.loads(row["data"]), row["sheet_id"], row["name"] or "Your sheet", number)


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
    if not p.get("solution"):
        return False, None
    key = (p["id"], json.dumps(args, sort_keys=True))
    with REFERENCE_LOCK:
        if key in REFERENCE_RESULTS:
            REFERENCE_RESULTS.move_to_end(key)
            return REFERENCE_RESULTS[key]
    # Linked lists and trees reach the reference as nodes, and a design problem builds its class, as for the learner.
    run = run_cases(p["solution"], [copy.deepcopy(args)], [p.get("kinds", {}).get(name) for name in p["params"]], p.get("entry", "solve"), p.get("answer"))[0]
    outcome = (run["error"] is None, run["result"])
    with REFERENCE_LOCK:
        REFERENCE_RESULTS[key] = outcome
        while len(REFERENCE_RESULTS) > 512:
            REFERENCE_RESULTS.popitem(last=False)
    return outcome


def explanation(event):
    kind, meta = event["type"], event.get("meta", {})
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
    if error:
        cycle = error["meta"].get("cycle")
        if cycle:
            return dict(step=cycle["repeat"] if cycle["repeat"] is not None else error["id"], line=cycle["line"], kind="Proven infinite loop", message=error["detail"], cycle=cycle)
        return dict(step=error["id"], line=error["line"], kind="First recorded runtime failure", message=error["detail"], access=error["meta"].get("access"))
    if trace.get("error"):  # Stopped from outside before any step recorded the failure: only the stop itself is known.
        return dict(step=None, line=None, kind="Execution stopped", message=trace["error"]["message"])
    returns = [e for e in events if e["type"] == "RETURN" and e["state"]["callstack"] == ["solve"]]
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
        return dict(**location, kind="Nothing returned yet", message=f"Your function returned None, so it has not produced an answer yet. {'Your case expects' if p.get('custom') else 'A valid result for this input is'} {expected!r}.")
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
    return error_json(str(exc), 400, line=getattr(exc, "lineno", None))


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
            context = f"Your attempt stopped at line {trace['error']['line']}: {trace['error']['message']}"
        elif p["id"] in {"two-sum", "two-sum-sorted"} and isinstance(trace["result"], list) and len(trace["result"]) == 2 and trace["result"][0] == trace["result"][1]:
            context = "Your attempt returned the same position twice. The problem requires two different positions. Which step allowed that reuse?"
        elif p["id"] == "two-sum" and any(e["type"] == "HASHMAP_LOOKUP" for e in trace["events"]) and not any(e["type"] == "HASHMAP_INSERT" for e in trace["events"]):
            context = "Your trace includes lookups but no dictionary inserts. What information can a later lookup find?"
    return jsonify(level=level, text=p["hints"][level - 1], context=context)


def practice_cases(p, args):
    """The authored cases (example and edge cases) plus the learner's own input when it differs."""
    cases = [dict(id=f"case-{i}", name=case["name"], args=case["args"], expected=case["expected"], custom=False) for i, case in enumerate(p["tests"])]
    if not any(case["args"] == args for case in cases):
        cases.append(dict(id="custom", name="Your input", args=args, expected=None, custom=True))
    return cases


def evaluate_cases(uid, p, code, cases, runs, preview):
    """Goal, verdict and divergence for every case's own trace. A verdict is never a test pass."""
    traces = []
    for case, trace in zip(cases, runs):
        solved, expected = reference_result(p, case["args"]) if case["custom"] else (True, case["expected"])
        trace["goal"] = {"expected": expected, "matches": not trace["error"] and correct(p, trace["result"], case["args"], expected)} if solved else None
        for event in trace["events"]:
            event["explanation"] = explanation(event)
        trace.update(divergence=observable_divergence(p, trace, *((expected, trace["goal"]["matches"]) if solved else (None, None))),
                     counts=dict(collections.Counter(e["type"] for e in trace["events"])), input=case["args"])
        trace["traceId"] = retain_preview(uid, p["id"], code, case["args"], trace, preview)
        traces.append(trace)
    return traces


def public_cases(cases, traces):
    keep = ("events", "result", "error", "truncated", "lines", "goal", "divergence", "counts", "traceId", "input", "stdout", "durationMs")
    return [dict(id=case["id"], name=case["name"], custom=case["custom"], **{k: trace.get(k) for k in keep}) for case, trace in zip(cases, traces)]


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
    validate_source(code, p.get("entry", "solve"))
    if not RUNNERS.acquire(blocking=False):
        return jsonify(error="The runner is busy. Keep editing, then try again."), 429
    try:
        cases = practice_cases(p, args)
        traces = evaluate_cases(uid, p, code, cases, run_cases(code, [case["args"] for case in cases], [p.get("kinds", {}).get(name) for name in p["params"]], p.get("entry", "solve"), p.get("answer")), preview=True)
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
    validate_source(code, p.get("entry", "solve"))
    if not RUNNERS.acquire(blocking=False):
        return jsonify(error="Both execution workers are busy. Try again shortly."), 429
    try:
        cases = practice_cases(p, args)
        traces = evaluate_cases(uid, p, code, cases, run_cases(code, [case["args"] for case in cases], [p.get("kinds", {}).get(name) for name in p["params"]], p.get("entry", "solve"), p.get("answer")), preview=False)
        main = next(i for i, case in enumerate(cases) if case["args"] == args)
        trace = traces[main]
        if not trace["goal"] and not p.get("custom"):
            raise ValueError("This input exceeded the reference runner's limits. Use a smaller input.")
        # An input outside a learner's own cases has no known answer: only their cases judge it.
        expected, passed = (trace["goal"]["expected"], trace["goal"]["matches"]) if trace["goal"] else (None, not trace["error"])
        # Every authored case is traced on every run, so whether this attempt passes the whole suite is the
        # server's own result. A request can leave the test list out of its reply, never out of the evidence.
        suite = [{"name": case["name"], "args": case["args"], "expected": case["expected"], "actual": run["result"], "passed": run["goal"]["matches"], "error": run["error"]}
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
        context["goal"] = trace.get("goal")
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
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
