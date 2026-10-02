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


class ExecutionLimit(Exception):
    pass


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
    if isinstance(value, (list, tuple, range, set)):
        return [bounded(v, depth + 1) for v in list(value)[:MAX_ITEMS]]
    if isinstance(value, dict):
        return {str(k)[:100]: bounded(v, depth + 1) for k, v in list(value.items())[:MAX_ITEMS]}
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
        if isinstance(value, (list, dict, set)):
            if id(value) in ids:
                return ("ref", ids[id(value)])
            ids[id(value)] = len(ids)
            if isinstance(value, dict):
                return ("dict", ids[id(value)], tuple((walk(k, depth + 1), walk(v, depth + 1)) for k, v in value.items()))
            return (type(value).__name__, ids[id(value)], tuple(walk(v, depth + 1) for v in value))  # Iteration order is state.
        raise ValueError  # Iterators and other objects carry hidden state.

    try:
        items = sorted(((k, v) for k, v in locals_.items() if not k.startswith("_") and not callable(v)), key=lambda kv: kv[0])
        return hashlib.sha256(repr(tuple((k, walk(v, 0)) for k, v in items)).encode()).hexdigest()
    except (ValueError, RecursionError):
        return None


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
    if isinstance(value, (list, tuple, set, range, dict)):
        if len(value) > 10000:
            raise ExecutionLimit("The returned collection exceeds 10,000 items.")
        if isinstance(value, dict):
            return {str(k): result_value(v, depth + 1) for k, v in value.items()}
        return [result_value(v, depth + 1) for v in value]
    raise ValueError("Return a number, boolean, string, or collection of values.")


SAFE_CALLS = {"len", "range", "enumerate", "zip", "min", "max", "sum", "abs", "sorted", "reversed", "list", "dict", "set", "tuple", "int", "str", "bool", "float", "print", "all", "any", "round"}
SAFE_METHODS = {"append", "pop", "get", "keys", "values", "items", "add", "remove", "discard", "clear", "copy", "sort", "reverse", "count", "index", "lower", "upper", "strip", "split", "join", "isalnum", "isalpha", "isdigit", "startswith", "endswith"}


def validate_source(source):
    if not isinstance(source, str) or len(source) > 12000:
        raise ValueError("Keep your program under 12,000 characters.")
    tree = ast.parse(source, filename="<student>")
    functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    if "solve" not in functions:
        raise ValueError("Define a function named solve with the problem's parameters.")
    for top in tree.body:
        if not isinstance(top, ast.FunctionDef) and not (isinstance(top, ast.Expr) and isinstance(top.value, ast.Constant) and isinstance(top.value.value, str)):
            raise ValueError("Place your code inside solve or a helper function.")
    denied = (ast.Import, ast.ImportFrom, ast.ClassDef, ast.AsyncFunctionDef, ast.Await, ast.With, ast.AsyncWith, ast.Global, ast.Nonlocal, ast.Lambda, ast.Try, ast.Raise, ast.Yield, ast.YieldFrom)
    for n in ast.walk(tree):
        if isinstance(n, denied):
            raise ValueError(f"{type(n).__name__} is outside the supported learning subset.")
        if isinstance(n, (ast.Name, ast.arg)) and (n.id if isinstance(n, ast.Name) else n.arg).startswith("_"):
            raise ValueError("Names starting with an underscore are reserved for the tracer.")
        if isinstance(n, ast.FunctionDef):
            if n.name.startswith("_") or n.decorator_list or n.args.defaults or n.args.kw_defaults and any(n.args.kw_defaults):
                raise ValueError("Use plain functions without decorators or default parameters.")
            if n.returns or any(a.annotation for a in n.args.args + n.args.kwonlyargs + n.args.posonlyargs):
                raise ValueError("Remove type annotations for this learning runner.")
        if isinstance(n, ast.Attribute) and n.attr not in SAFE_METHODS:
            raise ValueError(f"Attribute '{n.attr}' is not allowed in the learning runner.")
        if isinstance(n, ast.Call) and n.keywords:
            raise ValueError("Use positional arguments for calls in this learning runner.")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id not in SAFE_CALLS | functions:
            raise ValueError(f"Call '{n.func.id}' is not supported. Use the built-in learning operations.")
        if isinstance(n, ast.Call) and not isinstance(n.func, (ast.Name, ast.Attribute)):
            raise ValueError("Indirect function calls are not supported.")
    if sum(1 for _ in ast.walk(tree)) > 3000:
        raise ValueError("This program is too large for a learning trace.")
    return tree


def helper(name, args, original):
    return ast.copy_location(ast.Call(func=ast.Name(id=name, ctx=ast.Load()), args=args, keywords=[]), original)


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
        elif all(isinstance(t, ast.Name) and t.id in {"i", "j", "left", "right", "mid", "start", "end", "slow", "fast"} for t in parts):
            kind = "POINTER_MOVE"
        self.generic_visit(node)
        return [node, self.emit(kind, node, ", ".join(names), root, names if len(names) > 1 else ())]

    def visit_AugAssign(self, node):
        # Route augmented arithmetic through the same allocation guards.
        target = copy.deepcopy(node.target)
        if hasattr(target, "ctx"):
            target.ctx = ast.Load()
        replacement = ast.copy_location(ast.Assign(targets=[node.target], value=ast.BinOp(left=target, op=node.op, right=node.value)), node)
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
        return helper("_binary", [node.left, node.right, ast.Constant(type(node.op).__name__)], node)

    def visit_Call(self, node):
        self.generic_visit(node)
        if isinstance(node.func, ast.Attribute):
            return helper("_method", [node.func.value, ast.Constant(node.func.attr), ast.Constant(node.lineno), *node.args], node) if not node.keywords else node
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

    def state(locals_):
        structures, variables = [], []
        pointers = {k: v for k, v in locals_.items() if k in {"i", "j", "left", "right", "mid", "start", "end", "slow", "fast"} and isinstance(v, int) and not isinstance(v, bool)}
        for name, value in locals_.items():
            if name.startswith("_") or callable(value):
                continue
            if isinstance(value, (list, tuple, str)):
                values = bounded(value) if not isinstance(value, str) else list(value[:MAX_ITEMS])
                structures.append({"id": name, "type": "string" if isinstance(value, str) else "array", "values": values, "length": len(value), "highlights": hot.get(name, []), "pointers": {k: v for k, v in pointers.items() if 0 <= v < len(values)}})
            elif isinstance(value, dict):
                structures.append({"id": name, "type": "hashmap", "entries": [{"key": bounded(k), "value": bounded(v)} for k, v in list(value.items())[:MAX_ITEMS]]})
            elif isinstance(value, set):
                structures.append({"id": name, "type": "hashset", "values": bounded(value)})
            else:
                variables.append({"id": name, "value": bounded(value)})
        return {"structures": structures, "variables": variables, "callstack": list(callstack)}

    def check():
        nonlocal ticks
        ticks += 1
        if ticks > MAX_TICKS or time.monotonic() - started > seconds:
            raise ExecutionLimit("Execution limit reached. Check loop boundaries or try a smaller input.")

    def emit(kind, line, locals_, detail="", metadata=None):
        nonlocal truncated
        check()
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
        if isinstance(key, int):
            hot[name] = [key if key >= 0 else len(obj) + key]
        emit("HASHMAP_LOOKUP" if isinstance(obj, dict) else "ARRAY_ACCESS", line, sys._getframe(1).f_locals, f"Read {name}[{key}] → {bounded(value)}.", {"structure": name, "key": bounded(key), "value": bounded(value), "found": True, "index": index})
        return value

    binops = {"Add": operator.add, "Sub": operator.sub, "Mult": operator.mul, "Div": operator.truediv, "FloorDiv": operator.floordiv, "Mod": operator.mod, "Pow": operator.pow, "BitAnd": operator.and_, "BitOr": operator.or_, "BitXor": operator.xor, "LShift": operator.lshift, "RShift": operator.rshift}
    def binary(a, b, op):
        check()
        if op == "Mult" and ((isinstance(a, (str, list, tuple)) and isinstance(b, int) and len(a) * max(0, b) > 10000) or (isinstance(b, (str, list, tuple)) and isinstance(a, int) and len(b) * max(0, a) > 10000)):
            raise ExecutionLimit("That allocation is too large for the learning runner.")
        if op in {"Pow", "LShift", "RShift"} and (not isinstance(b, int) or abs(b) > 1024):
            raise ExecutionLimit("That arithmetic operation exceeds the learning limit.")
        if op == "Add" and isinstance(a, (str, list, tuple)) and isinstance(b, type(a)) and len(a) + len(b) > 10000:
            raise ExecutionLimit("The collection is too large for the learning runner.")
        result = binops[op](a, b)
        if isinstance(result, int) and result.bit_length() > 4096:
            raise ExecutionLimit("The integer exceeds the learning limit.")
        return result

    def method(obj, name, line, *args):
        check()
        if name in {"append", "add"} and len(obj) >= 10000:
            raise ExecutionLimit("The collection is too large for the learning runner.")
        result = getattr(obj, name)(*args)
        kind = {"append": "STACK_PUSH", "pop": "STACK_POP", "add": "HASHMAP_INSERT", "remove": "HASHMAP_DELETE", "discard": "HASHMAP_DELETE", "get": "HASHMAP_LOOKUP"}.get(name, "STATE_CHANGE")
        emit(kind, line, sys._getframe(1).f_locals, f"{name}({', '.join(str(bounded(a)) for a in args)}) → {bounded(result)}.")
        return result

    def returned(value, line):
        emit("RETURN", line, sys._getframe(1).f_locals, f"Returned {bounded(value)}.", {"value": bounded(value)})
        return value

    def trace(frame, event, arg):
        if frame.f_code.co_filename != "<student>":
            return None
        check()
        if event == "call" and frame.f_code.co_name != "<module>":
            callstack.append(frame.f_code.co_name)
            activations[0] += 1
            call_ids.append(activations[0])  # Each call is its own activation for loop-state comparison.
            emit("RECURSION_CALL", frame.f_lineno, frame.f_locals, f"Enter {frame.f_code.co_name}.")
        if event == "return" and frame.f_code.co_name != "<module>":
            emit("RECURSION_RETURN", frame.f_lineno, frame.f_locals, f"Leave {frame.f_code.co_name} → {bounded(arg)}.")
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

    safe = {name: getattr(builtins, name) for name in SAFE_CALLS}
    safe.update({"range": safe_range, "print": safe_print})
    env = {"__builtins__": safe, "_mark": mark, "_access": access, "_compare": compare, "_binary": binary, "_method": method, "_returned": returned, "_slice": slice}
    error, result = None, None
    try:
        tree = Instrument().visit(validate_source(source))
        ast.fix_missing_locations(tree)
        sys.setrecursionlimit(160)
        sys.settrace(trace)
        exec(compile(tree, "<student>", "exec"), env, env)  # Only in the dedicated worker.
        result = result_value(env["solve"](*payload["args"]))
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


def timeout_trace():
    return {"events": [], "result": None, "error": {"type": "Timeout", "message": "Execution stopped after 8 seconds. Check your loop or reduce input size.", "line": None}, "stdout": "", "durationMs": 8000}


def run_isolated(code, args):
    output = run_worker(code, {"code": code, "args": args})
    return output if output is not None else timeout_trace()


def run_cases(code, inputs):
    """Trace several inputs in one worker process. Each case is executed in a fresh namespace
    with its own share of the time budget, so one runaway case cannot starve the others."""
    budget = max(0.6, min(MAX_SECONDS, 6.0 / max(1, len(inputs))))
    output = run_worker(code, {"code": code, "cases": inputs, "budget": budget})
    return output["runs"] if output is not None else [timeout_trace() for _ in inputs]


def run_worker(code, payload):
    """Run the worker on a payload; None when the parent timeout expires."""
    validate_source(code)
    mode = os.environ.get("EXECUTION_MODE", "local")
    if os.environ.get("APP_ENV") == "production" and mode != "docker":
        raise ValueError("Public execution requires EXECUTION_MODE=docker.")
    if mode == "docker":
        container = "visual-dsa-" + uuid.uuid4().hex
        command = ["docker", "run", "--name", container, "--rm", "-i", "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--memory=192m", "--cpus=0.5", "--pids-limit=16", "--user=65534:65534", os.environ.get("EXECUTION_IMAGE", "visual-dsa-worker"), "python", "-I", "app.py", "--worker"]
    else:
        command = [sys.executable, "-I", str(ROOT / "app.py"), "--worker"]
    try:
        proc = subprocess.run(command, input=json.dumps(payload), capture_output=True, text=True, timeout=8, cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        if proc.returncode != 0:
            raise ValueError("Execution worker stopped. Check the runner configuration or reduce memory use.")
        return json.loads(proc.stdout)
    except subprocess.TimeoutExpired:
        return None
    finally:
        if mode == "docker":
            try:
                subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass


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
    limits.BasicLimitInformation.PerProcessUserTimeLimit = 4 * 10000000
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
        resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
    request_ = json.loads(sys.stdin.read(80000))
    if "cases" in request_:
        print(json.dumps({"runs": [execute_worker({"code": request_["code"], "args": args, "budget": request_["budget"]}) for args in request_["cases"]]}))
    else:
        print(json.dumps(execute_worker(request_)))
    sys.exit(0)


# ----------------------------- HTTP + SQLite -----------------------------
from flask import Flask, request, jsonify, send_from_directory
import sheets

app = Flask(__name__, static_folder="dist", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 32000
DB = os.environ.get("DSA_DATABASE", str(ROOT / "learning.sqlite3"))
RUNNERS = threading.BoundedSemaphore(2)
GUIDE_REQUESTS = threading.BoundedSemaphore(2)
PROBLEMS = []
VARIANTS = {}  # Changed-requirement problems, keyed by id; never listed in the library.
STAGES = ["Seen", "Understood", "Reproduced", "Explained", "Modified", "Independent", "Transferred"]
TECHNIQUES = ["Direct iteration / brute force", "Hash map / set", "Two pointers", "Sliding window", "Binary search", "Running best / running total"]
TECHNIQUE_NEEDS = {
    "Hash map / set": "remembering earlier information so that a later step can look it up by key instead of searching again",
    "Two pointers": "two positions whose movement is decided by order or symmetry: sorted values, mirrored ends, or a read/write split",
    "Sliding window": "a contiguous range whose summary can be updated as elements enter and leave",
    "Binary search": "a sorted (monotonic) order in which one comparison rules out half of the remaining positions",
    "Running best / running total": "one pass in which a small summary of the prefix (a best value, a minimum or a total) is enough for each next step",
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
        CREATE TABLE IF NOT EXISTS learning_support(user_id TEXT, problem_id TEXT, hint_level INTEGER DEFAULT 0, revealed INTEGER DEFAULT 0, PRIMARY KEY(user_id,problem_id));
        -- Distinct kinds of evidence (approach commitment, modification, transfer); the first record of each kind is kept.
        CREATE TABLE IF NOT EXISTS learning_evidence(user_id TEXT, problem_id TEXT, kind TEXT, detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id,problem_id,kind));
        -- A learner's own practice sheets, and the labs they define for rows without a built-in lab.
        CREATE TABLE IF NOT EXISTS sheets(id TEXT PRIMARY KEY, user_id TEXT, name TEXT, source TEXT, origin TEXT, rows TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS custom_labs(id TEXT PRIMARY KEY, user_id TEXT, sheet_id TEXT, data TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
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
        if isinstance(value, list) and (len(value) > MAX_ITEMS or any(not isinstance(x, int) or isinstance(x, bool) or abs(x) > 1000000 for x in value)):
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
    if base in {"max-window-sum", "average-window"} and not 1 <= args[1] <= len(args[0]):
        raise ValueError("Window size must be between 1 and the array length.")


def correct(problem, result, args, expected):
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
    if problem["id"] in {"intersection", "unique-values"}:
        return isinstance(result, list) and all(type(v) is int for v in result) and len(result) == len(set(expected)) and set(result) == set(expected)
    return type(result) is type(expected) and result == expected


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
    run = run_isolated(p["solution"], copy.deepcopy(args))
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


@app.errorhandler(ValueError)
@app.errorhandler(SyntaxError)
def bad_request(exc):
    return jsonify(error=str(exc), line=getattr(exc, "lineno", None)), 400


@app.errorhandler(PermissionError)
def unauthorized(exc):
    return jsonify(error=str(exc)), 401


@app.get("/api/health")
def health():
    return jsonify(ok=True, runner=os.environ.get("EXECUTION_MODE", "local"), auth=bool(firebase), ai=bool(os.environ.get("LLM_API_KEY")))


@app.get("/api/problems")
def problems():
    # Solutions and private test expectations are fetched only on deliberate reveal.
    # The intended approach stays server-side until the learner commits a hypothesis.
    public = {"id", "title", "statement", "returns", "question", "example"}
    return jsonify([{**{k: v for k, v in p.items() if k not in {"solution", "brute", "tests", "approach", "modification"}},
                     "modification": {**{k: v for k, v in p["modification"].items() if k in public}, "hints": VARIANTS[p["modification"]["id"]]["hints"]}}
                    for p in PROBLEMS])


@app.get("/api/problems/<id_>/solution")
def solution(id_):
    uid = identity()
    p = problem_by_id(id_)
    if not p:
        return jsonify(error="Your own lab has no reference solution: your cases are its specification." if str(id_).startswith("custom-") else "Problem not found."), 404
    with connect() as db:
        db.execute("INSERT INTO learning_support(user_id,problem_id,revealed) VALUES(?,?,1) ON CONFLICT(user_id,problem_id) DO UPDATE SET revealed=1", (uid, id_))
    return jsonify(code=p["brute"] if request.args.get("mode") == "brute" and p["brute"] else p["solution"])


@app.post("/api/hint")
def hint():
    uid = identity()
    data = request.get_json() or {}
    p = problem_by_id(data.get("problemId"), uid)
    level = data.get("level", 1)
    if not p or type(level) is not int or not 1 <= level <= len(p["hints"]):
        raise ValueError("Choose a valid hint level.")
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


def evaluate_cases(uid, p, code, cases, runs):
    """Goal, verdict and divergence for every case's own trace. A verdict is never a test pass."""
    traces = []
    for case, trace in zip(cases, runs):
        solved, expected = reference_result(p, case["args"]) if case["custom"] else (True, case["expected"])
        trace["goal"] = {"expected": expected, "matches": not trace["error"] and correct(p, trace["result"], case["args"], expected)} if solved else None
        for event in trace["events"]:
            event["explanation"] = explanation(event)
        trace.update(divergence=observable_divergence(p, trace, *((expected, trace["goal"]["matches"]) if solved else (None, None))),
                     counts=dict(collections.Counter(e["type"] for e in trace["events"])), input=case["args"])
        trace["traceId"] = retain_preview(uid, p["id"], code, case["args"], trace)
        traces.append(trace)
    return traces


def public_cases(cases, traces):
    keep = ("events", "result", "error", "truncated", "lines", "goal", "divergence", "counts", "traceId", "input", "stdout", "durationMs")
    return [dict(id=case["id"], name=case["name"], custom=case["custom"], **{k: trace.get(k) for k in keep}) for case, trace in zip(cases, traces)]


@app.post("/api/preview")
def preview():
    """Ephemeral typing feedback over every case: no tests, attempts or mastery evidence."""
    uid = identity()
    data = request.get_json() or {}
    p = problem_by_id(data.get("problemId"), uid)
    if not p:
        raise ValueError("Select a problem before previewing code.")
    code, args = data.get("code", ""), data.get("args", p["example"]["args"])
    valid_args(p, args)
    validate_source(code)
    if not RUNNERS.acquire(blocking=False):
        return jsonify(error="The runner is busy. Keep editing, then try again."), 429
    try:
        cases = practice_cases(p, args)
        traces = evaluate_cases(uid, p, code, cases, run_cases(code, [case["args"] for case in cases]))
        main = next(i for i, case in enumerate(cases) if case["args"] == args)
        return jsonify(**traces[main], preview=True, expected=None, passed=False, tests=[], attemptId="",
                       cases=public_cases(cases, traces), caseId=cases[main]["id"])
    finally:
        RUNNERS.release()


@app.post("/api/execute")
def execute():
    uid = identity()
    data = request.get_json() or {}
    p = problem_by_id(data.get("problemId"), uid)
    if not p:
        raise ValueError("Select a problem before running code.")
    code, args = data.get("code", ""), data.get("args", p["example"]["args"])
    valid_args(p, args)
    validate_source(code)
    if not RUNNERS.acquire(blocking=False):
        return jsonify(error="Both execution workers are busy. Try again shortly."), 429
    try:
        cases = practice_cases(p, args)
        traces = evaluate_cases(uid, p, code, cases, run_cases(code, [case["args"] for case in cases]))
        main = next(i for i, case in enumerate(cases) if case["args"] == args)
        trace = traces[main]
        if not trace["goal"] and not p.get("custom"):
            raise ValueError("This input exceeded the reference runner's limits. Use a smaller input.")
        # An input outside a learner's own cases has no known answer: only their cases judge it.
        expected, passed = (trace["goal"]["expected"], trace["goal"]["matches"]) if trace["goal"] else (None, not trace["error"])
        tests = [{"name": case["name"], "args": case["args"], "expected": case["expected"], "actual": run["result"], "passed": run["goal"]["matches"], "error": run["error"]}
                 for case, run in zip(cases, traces) if not case["custom"]] if data.get("test", True) else []
        counts = trace["counts"]
        trace["evaluation"] = {"expected": expected, "passed": passed, "tests": tests}
        attempt_id = uuid.uuid4().hex
        with connect() as db:
            db.execute("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))
            db.execute("INSERT INTO attempts(id,user_id,problem_id,code,input,result,passed) VALUES(?,?,?,?,?,?,?)", (attempt_id, uid, p["id"], code, json.dumps(args), json.dumps(trace["result"]), int(passed and all(t["passed"] for t in tests))))
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
    data = request.get_json() or {}
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
        transferred, insight = [], None
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
                db.execute("INSERT OR IGNORE INTO learning_evidence(user_id,problem_id,kind,detail) VALUES(?,?,'modified',?)",
                           (uid, p["id"], json.dumps({"requirement": p["modification"]["title"], "reasoning": reasoning.strip()[:2000], "attemptId": data["attemptId"], "hints": support["hint_level"] if support else 0})))
                insight = p["modification"]["insight"]
            if stage == "Independent" and support and (support["hint_level"] or support["revealed"]):
                stage = "Reproduced"
            if stage == "Explained" and len(str(data.get("evidence", "")).strip()) < 40:
                raise ValueError("Explain your reasoning in at least 40 characters.")
            stage = record_stage(db, uid, p["id"], stage, data.get("evidence", ""))
            if data["stage"] in {"Reproduced", "Independent"}:
                transferred = award_transfers(db, uid, p)
    return jsonify(ok=True, stage=stage if "stage" in data else None, insight=insight, transferred=transferred)


def support_row(db, uid, problem_id):
    return db.execute("SELECT hint_level,revealed FROM learning_support WHERE user_id=? AND problem_id=?", (uid, problem_id)).fetchone()


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
            awarded.append(source["id"])
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
        verdict, summary = "different", f"{technique} is not the approach this problem rewards."
        gap = f"{technique} relies on {TECHNIQUE_NEEDS[technique]}. Here, the repeated work is: {p['discovery'][1]} The operation that must become fast: {operation} {reference}"
    return dict(verdict=verdict, chosen=technique, summary=summary, gap=gap, resolved=resolved, unresolved=unresolved,
                intended=dict(technique=intended, operation=operation, why=why))


@app.post("/api/approach")
def commit_approach():
    """Record the learner's hypothesis, then reveal and compare the intended approach."""
    uid = identity()
    data = request.get_json() or {}
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
    clues, topic, origin = data.get("cluesRevealed", 0), data.get("topicKnown", False), data.get("transferFrom")
    if type(clues) is not int or clues < 0 or type(topic) is not bool or (origin is not None and not problem_by_id(origin)):
        raise ValueError("Invalid commitment context.")
    feedback = evaluate_approach(p, technique, notes)
    with connect() as db:
        support = support_row(db, uid, p["id"])
        reasons = [reason for condition, reason in [
            (support and support["revealed"], "you opened a reference approach"),
            (support and support["hint_level"], "you used hints or the guide on this problem"),
            (clues, "you revealed reasoning prompts that point toward the approach"),
            (topic, "you opened this problem from its topic, so the technique was known"),
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


def retain_preview(uid, problem_id, code, args, trace):
    token = uuid.uuid4().hex
    with PREVIEW_LOCK:
        now = time.monotonic()
        for key in list(PREVIEW_TRACES):
            if now - PREVIEW_TRACES[key]["created"] > 600:
                del PREVIEW_TRACES[key]
        PREVIEW_TRACES[token] = dict(owner=uid, problem_id=problem_id, code=code,
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
        context["metadata"].pop("category")  # Topic labels can name the technique; withhold until the learner commits.
    evidence = dict(trace=json.loads(row["trace"]), code=row["code"], input=json.loads(row["input"])) if row else None
    if not evidence and supplied.get("traceId"):
        with PREVIEW_LOCK:
            item = PREVIEW_TRACES.get(supplied["traceId"])
            if item and item["owner"] == uid and item["problem_id"] == p["id"] and time.monotonic() - item["created"] <= 600:
                evidence = dict(item, preview=True)
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
    data = request.get_json() or {}
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
    return jsonify(result)


@app.post("/api/chat")
def chat():
    from guide import answer, validate_chat
    uid = identity()
    message, history, supplied = validate_chat(request.get_json())
    p = problem_by_id(supplied.get("problemId"), uid)
    if supplied.get("problemId") and not p:
        raise ValueError("Unknown practice problem.")
    if not GUIDE_REQUESTS.acquire(blocking=False):
        return jsonify(error="The guide is busy. Try again in a moment."), 429
    try:
        context = tutor_context(uid, p, supplied) if p else {}
        result = answer(message, history, PROBLEMS, context, p)
        used = result["sources"] if result["provider"] == "AI guide" else result["sources"][:1]
        helped = {s["problemId"] for s in used if s.get("problemId") and not s["id"].startswith("help:")}
        if p and result.get("tutoring"): helped.add(p["id"])
        with connect() as db:
            for problem_id in helped:
                level = max(1, result.get("hintLevel", 0)) if p and problem_id == p["id"] else 1
                db.execute("INSERT INTO learning_support(user_id,problem_id,hint_level) VALUES(?,?,?) ON CONFLICT(user_id,problem_id) DO UPDATE SET hint_level=MAX(hint_level,excluded.hint_level)", (uid, problem_id, level))
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
        except (json.JSONDecodeError, ValueError):
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
        data = request.get_json() or {}
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
    data = request.get_json() or {}
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
    data = request.get_json() or {}
    return jsonify(sheets.parse_examples(data.get("text")))


@app.post("/api/labs/fetch")
def fetch_problem():
    """Read a sheet row's problem (statement, constraints, examples) from its own page, for the learner to
    check before building the lab. One page, on request; nothing is saved here."""
    uid = identity()
    data = request.get_json() or {}
    with connect() as db:
        sheet = db.execute("SELECT rows FROM sheets WHERE id=? AND user_id=?", (data.get("sheetId"), uid)).fetchone()
    if not sheet:
        raise ValueError("Save the sheet before reading its problems.")
    rows, index = json.loads(sheet["rows"]), data.get("row")
    if type(index) is not int or not 0 <= index < len(rows):
        raise ValueError("Choose a problem from the sheet.")
    return jsonify(sheets.read_problem(rows[index]))


@app.post("/api/labs")
def save_lab():
    """Create or update the learner's own lab for one row of their sheet."""
    uid = identity()
    request.max_content_length = 300_000
    data = request.get_json() or {}
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
