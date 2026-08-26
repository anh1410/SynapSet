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


def test_run_code_allows_class_definitions():
    # Regression: `class` compiles to a __build_class__ call, which was
    # missing from the restricted builtins - every class-based submission
    # (linked lists, trees, stacks...) silently crashed with
    # "__build_class__ not found" until this was added.
    source = """class Node:
    def __init__(self, data):
        self.data = data
        self.next = None

head = Node(10)
head.next = Node(20)
curr = head
while curr is not None:
    print(curr.data)
    curr = curr.next
"""
    out = run_code(source)
    assert out.strip() == "10\n20"


def test_run_code_allows_inheritance_and_super():
    source = """class Animal:
    def speak(self):
        return "..."

class Dog(Animal):
    def speak(self):
        return super().speak() + " Woof"

print(Dog().speak())
"""
    out = run_code(source)
    assert out.strip() == "... Woof"


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
