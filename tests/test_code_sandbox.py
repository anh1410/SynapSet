import pytest

from app.services.code_sandbox import CodeTimeoutError, UnsafeCodeError, check_code_safety, run_code


def test_run_code_captures_print_output():
    out = run_code("print('hello world')")
    assert out.strip() == "hello world"


def test_run_code_reads_stdin_via_input():
    source = "n = int(input())\nprint(n * 2)"
    out = run_code(source, stdin_text="21\n")
    assert out.strip() == "42"


def test_run_code_allows_safe_stdlib_import():
    out = run_code("import math\nprint(math.sqrt(16))")
    assert out.strip() == "4.0"


def test_check_code_safety_blocks_os_import():
    with pytest.raises(UnsafeCodeError):
        check_code_safety("import os\nprint(os.getcwd())")


def test_check_code_safety_blocks_open_call():
    with pytest.raises(UnsafeCodeError):
        check_code_safety("f = open('secrets.txt')")


def test_check_code_safety_blocks_dunder_import_obfuscation():
    with pytest.raises(UnsafeCodeError):
        check_code_safety("__import__('os').system('echo hi')")


def test_check_code_safety_blocks_syntax_error():
    with pytest.raises(UnsafeCodeError):
        check_code_safety("def broken(:\n  pass")


def test_run_code_raises_unsafe_on_import_before_running():
    with pytest.raises(UnsafeCodeError):
        run_code("import socket")


def test_run_code_raises_timeout_on_infinite_loop():
    with pytest.raises(CodeTimeoutError):
        run_code("while True:\n    pass", timeout_seconds=2)


def test_run_code_reports_runtime_error():
    with pytest.raises(UnsafeCodeError):
        run_code("1 / 0")
