"""What stopped a learner's program, in plain words.

Every failure the runner reports (a line Python cannot read, a construct the runner does not run, an exception, a
limit, a result that cannot be checked) is explained the same way everywhere it is shown:

- ``title``: what happened, in a few words;
- ``detail``: the same in the learner's own names and values, from what the runner recorded at the failure;
- ``hint``: a question that points at where to look, never the fix;
- ``line``: the line, when one is known.

Explanations come only from facts: the exception, the failing line's text, and what the runner recorded when it
failed (``failure``: the subscript, operation, attribute, method or comparison that raised, with its values). When
the facts don't say more, the explanation says less rather than guess. Python's own message is kept beside it.
"""
import difflib
import re


def py(value):
    """A value as Python writes it."""
    if value is None or isinstance(value, bool):
        return repr(value)
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(py(v) for v in value[:8]) + (", …" if len(value) > 8 else "") + "]"
    if isinstance(value, dict):
        items = list(value.items())[:6]
        return "{" + ", ".join(f"{py(k)}: {py(v)}" for k, v in items) + (", …" if len(value) > 6 else "") + "}"
    return str(value)


def clean(message):
    """Python's message without the runner's internal file name."""
    return re.sub(r"\s*\(<(?:student|reference)>, line \d+\)", "", str(message or "")).strip()


def kind(type_name):
    """A Python type as a learner would say it."""
    return {"NoneType": "None", "int": "a number", "float": "a number", "str": "a string", "list": "a list", "tuple": "a tuple",
            "dict": "a dictionary", "set": "a set", "bool": "a boolean", "deque": "a deque", "function": "a function"}.get(type_name, f"a {type_name}")


def container(type_name):
    return {"str": "string", "tuple": "tuple", "deque": "deque", "list": "list"}.get(type_name, "sequence")


def explained(title, detail, hint="", line=None):
    return {"title": title, "detail": detail, "hint": hint, "line": line}


# --- Lines Python cannot read -------------------------------------------------------------------------------

SYNTAX = [
    (r"expected ':'", "A colon is missing", "Line {line} starts a block (if, for, while, def, class or else) but does not end with a colon.", "What should come right after the condition or header on line {line}?"),
    (r"'(.)' was never closed", "A bracket is never closed", "The {0} opened on line {line} has no matching closing bracket.", "Where should this {0} end?"),
    (r"unmatched '(.)'", "A closing bracket has no partner", "The {0} on line {line} closes a bracket that was never opened.", "Which opening bracket is it meant to close?"),
    (r"closing parenthesis '(.)' does not match opening parenthesis '(.)'", "Brackets don't match", "On line {line}, a {1} is closed with a {0}.", "Which kind of bracket opened this expression?"),
    (r"expected an indented block after (.+?) on line (\d+)", "A block has no body", "After the {0} on line {1}, the next line must be indented one level deeper.", "What should run inside this block?"),
    (r"unindent does not match any outer indentation level", "Indentation doesn't line up", "Line {line} is indented by an amount that matches no enclosing block.", "Does each level use the same number of spaces (4 is usual)?"),
    (r"unexpected indent", "Unexpected indentation", "Line {line} is indented, but nothing above it opens a block.", "Should this line be at the same level as the one above?"),
    (r"inconsistent use of tabs and spaces", "Tabs and spaces are mixed", "Line {line} mixes tabs and spaces for indentation.", "Can you indent every line with spaces only?"),
    (r"unterminated (?:triple-quoted )?string literal", "A string is not closed", "A string on line {line} has no closing quote.", "Where should this text end?"),
    (r"'break' outside loop", "break is outside a loop", "`break` on line {line} is not inside a for or while loop.", "Which loop should this stop?"),
    (r"'continue' not properly in loop", "continue is outside a loop", "`continue` on line {line} is not inside a for or while loop.", "Which loop should this skip ahead?"),
    (r"'return' outside function", "return is outside a function", "`return` on line {line} is not inside a function.", "Is this line indented inside solve?"),
    (r"no binding for nonlocal '(\w+)' found", "nonlocal names nothing", "`nonlocal {0}` on line {line} refers to no variable in an enclosing function.", "Where is `{0}` first assigned?"),
    (r"duplicate argument '(\w+)'", "A parameter is repeated", "The parameter `{0}` appears twice in the function on line {line}.", "Which two values should these parameters hold?"),
    (r"cannot assign to (.+?)(?: here)?(?:\.|$)", "This can't be assigned to", "Line {line} assigns to {0}, which can't hold a value.", "Is `=` meant to be `==` here?"),
    (r"Perhaps you forgot a comma", "A comma may be missing", "Python can't read line {line}: two values sit next to each other with nothing between them.", "Should a comma separate them?"),
]


def syntax(message, line):
    """A SyntaxError or IndentationError, from Python's own message (which is precise about what it expected)."""
    text = clean(message)
    for pattern, title, detail, hint in SYNTAX:
        match = re.search(pattern, text)
        if match:
            parts = match.groups()
            return explained(title, detail.format(*parts, line=line), hint.format(*parts, line=line), line)
    return explained("Python can't read this line", f"Line {line}: {text}." if line else f"{text}.", "Compare the line with the one above it: is something missing or extra?", line)


# --- Exceptions, from what the runner recorded at the failure ---------------------------------------------------

def access_failure(error, access, line):
    """A subscript that failed: a position outside a sequence, a missing key, or nothing to subscript."""
    name, index, key, size = access.get("structure", "?"), access.get("index", "?"), access.get("key"), access.get("size")
    of = access.get("of")
    if access.get("kind") == "dict":
        return explained(f"Key {py(key)} is not in {name}", f"`{name}[{index}]` looks up {py(key)}, but {name} has no such key at this point" + (f" (it has {size} keys)." if size is not None else "."),
                         f"Which line was meant to add {py(key)} to {name} before this read?", line)
    if access.get("kind") == "none":
        return explained(f"{name} is None", f"`{name}[{index}]` reads from {name}, but {name} is None here, so there is nothing to read.", f"Where does {name} get its value, and can that be None?", line)
    if access.get("kind") == "type":
        return explained(f"{name} can't be indexed", f"`{name}[{index}]` uses [ ] on {kind(of)}, which has no positions or keys.", f"What should {name} hold at this point?", line)
    if access.get("kind") == "badkey":
        if of == "dict":
            return explained(f"{kind(access.get('keytype')).capitalize()} can't be a dictionary key", f"`{name}[{index}]` uses {kind(access.get('keytype'))} as a key, but dictionary keys must be fixed values (a list or set can change).",
                             "Could the key be a tuple instead?", line)
        return explained(f"Positions in {name} are whole numbers", f"`{name}[{index}]` uses {kind(access.get('keytype'))} ({py(key)}) as a position, but positions in {kind(of)} are whole numbers.", f"Should `{index}` be a number here, or is {name} meant to be a dictionary?", line)
    what = container(of)
    items = "characters" if of == "str" else "items"
    if size == 0:
        return explained(f"{name} is empty", f"`{name}[{index}]` reads position {py(key)}, but {name} is an empty {what}: it has no positions at all.", f"Should something check that {name} is not empty first?", line)
    shown = f"{index} = {py(key)}" if str(index) != str(key) else f"Position {py(key)} is asked for"
    return explained(f"{name}[{index}] is outside the {what}", f"{shown}, but {name} has {size} {items}: positions 0 to {size - 1}" + (f" (or -{size} to -1)." if isinstance(key, int) and key < 0 else "."),
                     f"Which step made {index} reach {py(key)}? Check the loop bounds or the update just before." if str(index) != str(key) else f"How many {items} does {name} have here?", line)


def operation_failure(error, op, line):
    """An arithmetic operation that failed: dividing by zero, or a value of the wrong type (often None)."""
    text, symbol = op.get("text", ""), op.get("op", "")
    left, right = op.get("ltext", "the left side"), op.get("rtext", "the right side")
    if error["type"] == "ZeroDivisionError":
        return explained("Division by zero", f"`{text}` divides by `{right}`, which is 0 here.", f"Can `{right}` be 0 for this input? What should happen then?", line)
    ltype, rtype = op.get("ltype"), op.get("rtype")
    for side, typ in ((left, ltype), (right, rtype)):
        if typ == "NoneType":
            return explained(f"`{side}` is None", f"`{text}` needs a value on both sides of {symbol}, but `{side}` is None here.", f"Which line was meant to give `{side}` a value? Did a function return nothing?", line)
    return explained(f"Can't use {symbol} on these values", f"`{text}`: `{left}` is {kind(ltype)} and `{right}` is {kind(rtype)}, and {symbol} doesn't combine those.", "What type should each side have here?", line)


def compare_failure(error, compare, line):
    text = compare.get("text", "")
    types = [compare.get("ltype"), compare.get("rtype")]
    if compare.get("op") in {"in", "not in"}:
        inside = compare.get("rtext", "the right side")
        if types[1] == "NoneType":
            return explained(f"`{inside}` is None", f"`{text}` looks inside `{inside}`, but `{inside}` is None here, so there is nothing to look in.", f"Where does `{inside}` get its value?", line)
        return explained(f"Can't look inside `{inside}`", f"`{text}` looks inside `{inside}`, which is {kind(types[1])}: it has no items to search.", f"Should `{inside}` be a list, set, dict or string?", line)
    if "NoneType" in types:
        side = compare.get("ltext") if types[0] == "NoneType" else compare.get("rtext")
        return explained(f"`{side}` is None in a comparison", f"`{text}` compares with `{side}`, which is None here; None can't be ordered against {kind(types[1] if types[0] == 'NoneType' else types[0])}.", f"Where does `{side}` get its value?", line)
    return explained("These values can't be compared", f"`{text}` compares {kind(types[0])} with {kind(types[1])}, which have no order between them.", "What type should both sides have?", line)


def attribute_failure(error, attr, line):
    """An attribute that failed: a None pointer, a field the object doesn't have, or a method the runner doesn't offer."""
    text, name = attr.get("text", "the value"), attr.get("name", "?")
    if attr.get("none"):
        return explained(f"`{text}` is None", f"`{text}.{name}` reads `.{name}`, but `{text}` is None here, so there is no `.{name}` to read." if not attr.get("store") else f"`{text}.{name} = …` sets `.{name}`, but `{text}` is None here, so there is nothing to set it on.",
                         f"Which step set `{text}` to None? Should a condition stop before it gets there (past the end of a list, or below a leaf)?", line)
    if attr.get("blocked"):
        return explained(f"`.{name}` isn't available on {kind(attr.get('of'))}", f"`{text}.{name}` uses `.{name}`, which the learning runner doesn't offer on {kind(attr.get('of'))}.", "Is there another way to do this with the common methods?", line)
    of = attr.get("of")
    owner = kind(of) if of in {"NoneType", "int", "float", "str", "list", "tuple", "dict", "set", "bool", "deque"} else f"an object of class {of}" if of != "module" else "this module"
    return explained(f"`{text}` has no `.{name}`", f"`{text}` is {owner}, which has no field or method called `{name}`.", f"Is `{name}` spelled the way it is defined?", line)


def method_failure(error, method, line):
    """A method or heap call that failed: popping from an empty collection, an item not found, a call on None."""
    text, name, size = method.get("text", "the value"), method.get("name", "?"), method.get("size")
    args = method.get("args") or []
    if method.get("none"):
        return explained(f"`{text}` is None", f"`{text}.{name}(…)` calls a method on `{text}`, but `{text}` is None here.", f"Where does `{text}` get its value? Did a function return nothing?", line)
    if name in {"pop", "popleft", "heappop", "popitem"} and size == 0:
        return explained(f"`{text}` is empty", f"`{name}` takes an item out of `{text}`, but `{text}` has no items at this point.", f"Should the code check that `{text}` isn't empty first? When did it become empty?", line)
    if name in {"index", "remove"} and args:
        return explained(f"{py(args[0])} is not in `{text}`", f"`{text}.{name}({py(args[0])})` looks for {py(args[0])}, but `{text}` doesn't contain it here.", f"Should the code check `{py(args[0])} in {text}` first?", line)
    if name == "pop" and error["type"] == "KeyError" and args:
        return explained(f"Key {py(args[0])} is not in `{text}`", f"`{text}.pop({py(args[0])})` removes a key that `{text}` doesn't have.", "Was the key added, or already removed?", line)
    if name == "pop" and error["type"] == "IndexError" and args:
        return explained(f"`{text}` has no position {py(args[0])}", f"`{text}.pop({py(args[0])})` removes position {py(args[0])}, but `{text}` has {size} items.", "How many items does it have at this point?", line)
    return explained(f"`{text}.{name}(…)` failed", f"`{text}.{name}(…)`: {clean(error['message'])}.", "What values did this call receive?", line)


LIMITS = {
    "steps": ("The program ran too many steps", "It took more than {steps:,} steps and was stopped. A loop that never ends, or one that does much more work than needed, is the usual cause.", "Which loop's condition never becomes false, or which loop runs far more often than you expect?"),
    "time": ("The program ran too long", "It ran for more than {seconds:g} seconds and was stopped.", "Which loop's condition never becomes false? Try a smaller input to see the pattern."),
    "stopped": ("The runner stopped this case", "It reached the runner's time or memory limit inside a built-in operation, so no steps were recorded.", "Is a very large list, string or number being built? Try a smaller input."),
}


def runtime(error, failure, lines, params=None, entry="solve"):
    """An exception or limit recorded by the runner, explained from what it recorded."""
    failure = failure or {}
    kind_name, message, line = error.get("type", ""), clean(error.get("message")), error.get("line")
    source = (lines[line - 1].strip() if line and 0 < line <= len(lines) else "")
    if kind_name in {"SyntaxError", "IndentationError", "TabError"}:
        return syntax(message, line)
    if kind_name == "ExecutionLimit":
        if failure.get("cycle"):
            cycle = failure["cycle"]
            return explained("Infinite loop, proven", f"The while loop on line {cycle['line']} came back to exactly the same state as before: nothing it depends on changed between those iterations, so it would repeat forever.",
                             "Which variable in the loop's condition is meant to change each time round?", cycle["line"])
        limit = failure.get("limit")
        if limit in LIMITS:
            title, detail, hint = LIMITS[limit]
            where = f" It was running line {line} when it was stopped." if line else ""
            if failure.get("unfinished"):  # A full run without recording steps didn't finish either.
                where += f" Run again without recording steps, it still hadn't finished after {failure['unfinished']} seconds."
                hint = "Which loop's condition never becomes false, or which loop does far more work than the input needs?"
            elif failure.get("preview"):
                where += " Run your code (Ctrl+Enter) to judge this case with a full run that records no steps."
            return explained(title, detail.format(steps=failure.get("steps", 0), seconds=failure.get("seconds", 0)) + where, hint, line)
        return explained("A value grew too large for the runner", f"{message}", "Is a list, string or number growing on every step without limit?", line)
    if kind_name == "NotRun":
        return explained("Not run", "An earlier case stopped the runner, so this case never started.", "Fix the case that stopped first, then run again.", None)
    if failure.get("raised"):  # The program's own `raise`: not a mistake Python found, a choice the code made.
        raised = failure["raised"]
        return explained(f"Your code raised {raised['type']}", f"Line {raised['line']} raises {raised['type']}" + (f": {message}" if message else "") + ". Nothing caught it, so the program stopped there.",
                         "Is raising what this case should do? If not, which value led the code to this line?", raised["line"])
    for key, explain in (("access", access_failure), ("op", operation_failure), ("compare", compare_failure), ("attr", attribute_failure), ("method", method_failure)):
        if failure.get(key) and (key != "access" or kind_name in {"IndexError", "KeyError", "TypeError"}):
            return explain(error, failure[key], line)
    if kind_name == "TypeError" and line is None and re.search(r"(positional argument|required|takes \d+)", message):
        expected = ", ".join(params or [])
        called = re.match(r"(?:\w+\.)?(\w+)\(\)", message)
        name = called.group(1) if called and called.group(1) != "__init__" else entry
        return explained(f"{name}'s parameters don't match this problem", f"This problem calls {name}({expected}) with {len(params or [])} input{'s' if len(params or []) != 1 else ''}. Python says: {message}.",
                         f"Does your def {name}(…) list exactly these parameters?" if entry == "solve" else "Do the methods take the arguments the problem passes?", line)
    if kind_name == "AttributeError" and re.match(rf"{re.escape(entry)} has no method", message):
        return explained("A method the problem calls is missing", f"{message}", "Which methods does the problem call, in what order?", None)
    if kind_name == "NameError":
        name = re.search(r"name '(\w+)'", message)
        known = sorted(set(re.findall(r"[A-Za-z_]\w*", "\n".join(lines))) - {name.group(1) if name else ""})
        close = difflib.get_close_matches(name.group(1), known, n=1, cutoff=0.75) if name else []
        return explained(f"`{name.group(1) if name else '?'}` doesn't exist here", f"Line {line} uses `{name.group(1) if name else '?'}`, but no variable or function of that name exists at this point.",
                         f"Did you mean `{close[0]}`?" if close else "Is it defined in another function, or later than it is used?", line)
    if kind_name == "UnboundLocalError":
        name = re.search(r"variable '(\w+)'", message)
        n = name.group(1) if name else "?"
        return explained(f"`{n}` is read before it's set", f"Line {line} reads `{n}`, but this function hasn't assigned it yet. Because the function assigns `{n}` somewhere, Python treats it as this function's own variable from the start.",
                         f"Should `{n}` get a starting value before this line, or come from outside (nonlocal)?", line)
    if kind_name == "RecursionError":
        return explained("The calls went too deep", "Each call made another call, more than 400 deep, without reaching a case that returns directly." + (" The runner keeps the depth at 400, so sys.setrecursionlimit has no effect here." if "setrecursionlimit" in "\n".join(lines) else ""),
                         "Does every call move closer to the base case? Is the base case checked before the recursive call?", line)
    if kind_name == "AssertionError":
        return explained("An assert failed", f"The check on line {line} was False: `{source}`" + (f" ({message})" if message else "") + ".", "Which value made this check fail? Step back to where it was set.", line)
    if kind_name == "ZeroDivisionError":
        return explained("Division by zero", f"Line {line} divides by a value that is 0 here: `{source}`.", "Can the divisor be 0 for this input?", line)
    if kind_name == "KeyError":
        return explained(f"Key {message} is missing", f"Line {line} uses the key {message}, which isn't there: `{source}`.", "Was the key added before this line?", line)
    if kind_name == "IndexError":
        return explained("A position is out of range", f"Line {line}: {message}: `{source}`.", "How many items are there at this point?", line)
    if kind_name == "ValueError":
        if "empty" in message and re.search(r"\b(max|min)\(", message):
            fn = re.search(r"\b(max|min)\(", message).group(1)
            return explained(f"{fn}() got nothing to compare", f"`{fn}(…)` on line {line} was given an empty sequence.", "Can this sequence be empty for this input? What should the answer be then?", line)
        unpack = re.search(r"(too many|not enough) values to unpack \(expected (\d+)(?:, got (\d+))?\)", message)
        if unpack:
            return explained("Unpacking doesn't fit", f"Line {line} unpacks into {unpack.group(2)} names, but the value has {'more' if unpack.group(1) == 'too many' else 'fewer'} items" + (f" ({unpack.group(3)})." if unpack.group(3) else "."), "What does the value on the right hold here?", line)
        return explained("A value doesn't fit this operation", f"Line {line}: {message}.", "What value reached this line?", line)
    if kind_name == "TypeError":
        if "not subscriptable" in message:
            return explained("This value can't be indexed", f"Line {line} uses [ ] on a value that has no positions: {message}.", "What should this name hold at this point?", line)
        if "not iterable" in message:
            return explained("This value can't be looped over", f"Line {line} loops over a value that isn't a collection: {message}.", "Should it be a list, or range(n)?", line)
        if "not callable" in message:
            return explained("This value can't be called", f"Line {line} calls something that isn't a function: {message}.", "Is a variable using the same name as a function?", line)
        return explained("A value of the wrong type", f"Line {line}: {message}.", "What type does each value have here?", line)
    if kind_name == "RuntimeError" and "changed size during iteration" in message:
        return explained("A collection changed while looping over it", f"Line {line} added or removed items of a dict or set while a loop was going through it.", "Can the loop go over a copy (list(...)) instead?", line)
    if kind_name == "StopIteration":
        return explained("next() found nothing left", f"Line {line} asked an iterator for another item after its last one.", "Should a default be given to next(), or the loop stop earlier?", line)
    if kind_name == "MemoryError":
        return explained("The program used too much memory", "It needed more memory than the runner allows.", "Is a list or string growing without limit?", line)
    if kind_name == "ValueError" or kind_name == "Contract":
        return explained("The result can't be checked", message, "What should solve return for this problem?", line)
    return explained(f"{kind_name} on line {line}" if line else kind_name, message or kind_name, "What values did this line receive?", line)


def contract(message):
    """A returned value the runner can't compare (an unsupported object, a cyclic list): not an exception in the code."""
    return explained("The returned value can't be checked", clean(message), "What should solve return for this problem: a number, a list, a string, or a node?", None)


CONTRACT_MESSAGES = ("Return a value, a list", "Return a number, boolean", "The returned", "Return a finite number")


def explain(error, failure=None, code="", params=None, entry="solve"):
    """The explanation for a recorded error (from a trace)."""
    if not error:
        return None
    lines = code.split("\n")
    if error.get("type") == "ValueError" and error.get("message", "").startswith(CONTRACT_MESSAGES):
        return contract(error["message"])
    return runtime(error, failure, lines, params, entry)


def refused(exc):
    """The explanation for code refused before it ran: a syntax error, or a construct the runner doesn't run
    (app.Unsupported, which carries its own title and question)."""
    if isinstance(exc, SyntaxError):
        return syntax(exc.msg if hasattr(exc, "msg") else str(exc), exc.lineno)
    if getattr(exc, "title", None):
        return explained(exc.title, str(exc), getattr(exc, "hint", ""), getattr(exc, "lineno", None))
    return None
