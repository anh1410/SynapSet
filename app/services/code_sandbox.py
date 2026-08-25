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
]


class UnsafeCodeError(Exception):
    pass


class CodeTimeoutError(Exception):
    pass


def check_code_safety(source: str) -> None:
    """Raises UnsafeCodeError if `source` imports anything outside
    ALLOWED_IMPORTS, calls a code-execution/file/system primitive, or even
    mentions a dangerous module name (belt-and-suspenders against
    `import os as x`-style obfuscation)."""
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

    if _DANGEROUS_TOKENS.search(source):
        raise UnsafeCodeError("Code references a disallowed module or function name")


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
