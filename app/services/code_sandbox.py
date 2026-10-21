"""Executes student-submitted Python code server-side to auto-grade code_fix
questions against hidden test cases.

This is BEST-EFFORT sandboxing appropriate for a trusted-ish school tool — an
AST import/call allowlist plus process isolation with a timeout, not
container- or gVisor-level isolation. It exists to stop a careless or
malicious student submission from doing something destructive or hanging
forever, not to withstand a deliberately adversarial attacker with unlimited
time to find an escape.
"""

import ast
import io
import multiprocessing
import re
import sys
import tokenize

ALLOWED_IMPORTS = {"math", "random", "string", "itertools", "collections", "functools", "re", "json", "datetime"}
_DANGEROUS_TOKENS = re.compile(
    r"\b(os|sys|subprocess|socket|shutil|pathlib|importlib|ctypes|multiprocessing|threading|"
    r"open|eval|exec|compile|__import__|globals|locals|vars|breakpoint)\b"
)

_SAFE_BUILTINS = [
    "abs", "all", "any", "bool", "chr", "dict", "divmod", "enumerate", "filter",
    "float", "int", "isinstance", "len", "list", "map", "max", "min", "ord",
    "pow", "print", "range", "repr", "reversed", "round", "set", "sorted",
    "str", "sum", "tuple", "type", "zip", "input", "Exception", "ValueError",
    "TypeError", "IndexError", "KeyError", "StopIteration", "ZeroDivisionError",
    "AttributeError", "RuntimeError", "NotImplementedError", "object",
    "staticmethod", "classmethod", "property", "super", "__build_class__",
    "__name__",
]


# Attribute names used to climb from an ordinary object to the interpreter's
# internals (`().__class__.__base__.__subclasses__()` -> a class whose module
# globals hold the real builtins). Blocking these attributes closes the classic
# Python sandbox escape. Everyday dunders students use in classes
# (__init__, __str__, super().__init__(), type(x).__name__, ...) stay allowed.
_BLOCKED_ATTRIBUTES = {
    "__class__", "__base__", "__bases__", "__mro__", "__subclasses__", "__globals__", "__builtins__",
    "__dict__", "__code__", "__closure__", "__func__", "__self__", "__getattribute__", "__reduce__",
    "__reduce_ex__", "__loader__", "__spec__", "__import__", "__traceback__", "__init_subclass__",
    "__subclasshook__", "__getattr__", "__delattr__", "__setattr__", "__weakref__", "__objclass__",
    "f_globals", "f_locals", "f_builtins", "f_back", "f_code", "tb_frame", "tb_next",
    "gi_frame", "gi_code", "cr_frame", "cr_code", "ag_frame", "co_code",
}


class UnsafeCodeError(Exception):
    pass


def _code_outside_strings(source: str) -> str:
    """The source with string literals and comments removed, so the banned-name
    check below looks only at code. A program that prints "The shop is open"
    must not be rejected for the word "open"; calls and imports are checked
    on the AST anyway."""
    skip = {tokenize.STRING, tokenize.COMMENT}
    if hasattr(tokenize, "FSTRING_MIDDLE"):  # literal text inside f-strings (3.12+)
        skip.add(tokenize.FSTRING_MIDDLE)
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        return " ".join(tok.string for tok in tokens if tok.type not in skip)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return source  # be conservative: check everything


class CodeTimeoutError(Exception):
    pass


def check_code_safety(source: str) -> None:
    """Raises UnsafeCodeError if `source` imports anything outside
    ALLOWED_IMPORTS, calls a code-execution/file/system primitive, touches an
    introspection attribute (_BLOCKED_ATTRIBUTES), or mentions a dangerous
    module/function name in its code (belt-and-suspenders against
    `import os as x`-style obfuscation; string literals and comments are
    ignored for that last check)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise UnsafeCodeError(f"Code has a syntax error: {exc}") from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in ALLOWED_IMPORTS:
                    raise UnsafeCodeError(f"Import not allowed: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module not in ALLOWED_IMPORTS:
                raise UnsafeCodeError(f"Import not allowed: {node.module}")
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name in {"eval", "exec", "compile", "__import__", "open", "globals", "locals", "vars"}:
                raise UnsafeCodeError(f"Call not allowed: {name}")
        elif isinstance(node, ast.Attribute) and node.attr in _BLOCKED_ATTRIBUTES:
            raise UnsafeCodeError(f"Attribute not allowed: {node.attr}")
        elif isinstance(node, ast.Name) and node.id in _BLOCKED_ATTRIBUTES:
            raise UnsafeCodeError(f"Name not allowed: {node.id}")

    if _DANGEROUS_TOKENS.search(_code_outside_strings(source)):
        raise UnsafeCodeError("Code references a disallowed module or function name")


def normalize_output(text: str) -> str:
    """Program output as graders compare it: any line-ending style, no
    trailing spaces on a line, no leading/trailing blank space overall."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()


def outputs_match(actual: str, expected: str) -> bool:
    """Whether a program's printed output matches a test case's expected
    output. Whitespace at line ends and Windows line endings don't count -
    `print(x, end=" ")` style trailing spaces shouldn't cost marks."""
    return normalize_output(actual) == normalize_output(expected)


def _safe_import(name, *args, **kwargs):
    # check_code_safety already restricts `import` statements in the source to
    # ALLOWED_IMPORTS - this just makes those imports actually work, since the
    # restricted builtins namespace below has no working __import__ otherwise.
    if name in ALLOWED_IMPORTS:
        return __import__(name, *args, **kwargs)
    raise ImportError(f"import not allowed: {name}")


def _run_worker(source: str, stdin_text: str, conn) -> None:
    """Runs in a separate process against a restricted builtins namespace,
    with stdin/stdout swapped for in-memory buffers so the harness can feed
    a test case's input and capture the program's printed output."""
    try:
        import builtins as _builtins

        safe_globals = {
            "__builtins__": {
                **{name: getattr(_builtins, name) for name in _SAFE_BUILTINS},
                "__import__": _safe_import,
            }
        }
        stdout_buf = io.StringIO()
        stdin_buf = io.StringIO(stdin_text)
        old_stdout, old_stdin = sys.stdout, sys.stdin
        sys.stdout, sys.stdin = stdout_buf, stdin_buf
        try:
            exec(compile(source, "<submission>", "exec"), safe_globals)  # noqa: S102 - pre-checked by check_code_safety
        finally:
            sys.stdout, sys.stdin = old_stdout, old_stdin
        conn.send(("ok", stdout_buf.getvalue()))
    except Exception as exc:  # noqa: BLE001 - any failure must reach the parent as data, not a crash
        conn.send(("error", str(exc)))
    finally:
        conn.close()


def run_code(source: str, stdin_text: str = "", timeout_seconds: int = 5) -> str:
    """Runs `source` in an isolated process, feeding `stdin_text` to any
    input() calls, and returns everything printed to stdout. Raises
    UnsafeCodeError if the code fails the safety check or raises at runtime,
    or CodeTimeoutError if it runs too long (e.g. an infinite loop)."""
    check_code_safety(source)

    parent_conn, child_conn = multiprocessing.Pipe()
    process = multiprocessing.Process(target=_run_worker, args=(source, stdin_text, child_conn))
    process.start()

    if not parent_conn.poll(timeout_seconds):
        process.terminate()
        process.join()
        raise CodeTimeoutError(f"Code execution exceeded {timeout_seconds}s")

    status, payload = parent_conn.recv()
    process.join(timeout=2)
    if process.is_alive():
        process.terminate()
        process.join()

    if status == "error":
        raise UnsafeCodeError(f"Code raised an error: {payload}")
    return payload
