"""Tests for runcase/runner.py — Phase 3."""
import json
import os
import tempfile
from pathlib import Path

import pytest

from runcase import store
from runcase.runner import (
    CompilationError,
    _detect_language,
    _normalize_output,
    run_problem,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets its own SQLite database."""
    db_file = tmp_path / "test.sqlite"
    monkeypatch.setenv("RUNCASE_DB_PATH", str(db_file))
    store.init_db()
    yield


@pytest.fixture
def py_solution_dir(tmp_path):
    return tmp_path


def _write_solution(directory: Path, filename: str, content: str) -> str:
    p = directory / filename
    p.write_text(content)
    return str(p)


def _make_stdio_problem(name: str = "test-prob") -> None:
    store.create_problem(name, "stdio")


def _make_function_problem(name: str = "test-func", func_name: str = "solve") -> None:
    store.create_problem(name, "function", func_name=func_name)


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

class TestDetectLanguage:
    def test_python(self, tmp_path):
        assert _detect_language(str(tmp_path / "foo.py")) == "python"

    def test_cpp(self, tmp_path):
        assert _detect_language(str(tmp_path / "foo.cpp")) == "cpp"

    def test_java(self, tmp_path):
        assert _detect_language(str(tmp_path / "foo.java")) == "java"

    def test_uppercase_extension(self, tmp_path):
        assert _detect_language(str(tmp_path / "foo.PY")) == "python"

    def test_unsupported_extension(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported file extension"):
            _detect_language(str(tmp_path / "foo.rb"))

    def test_no_extension(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported file extension"):
            _detect_language(str(tmp_path / "foo"))


# ---------------------------------------------------------------------------
# Output normalization
# ---------------------------------------------------------------------------

class TestNormalizeOutput:
    def test_strips_trailing_spaces_per_line(self):
        assert _normalize_output("hello   \nworld  ") == "hello\nworld"

    def test_strips_trailing_newlines(self):
        assert _normalize_output("hello\n\n") == "hello"

    def test_empty_string(self):
        assert _normalize_output("") == ""

    def test_preserves_leading_spaces(self):
        assert _normalize_output("  hello") == "  hello"

    def test_multiline(self):
        result = _normalize_output("a  \nb  \nc  \n")
        assert result == "a\nb\nc"


# ---------------------------------------------------------------------------
# run_problem — error conditions
# ---------------------------------------------------------------------------

class TestRunProblemErrors:
    def test_file_not_found(self, tmp_path):
        _make_stdio_problem()
        with pytest.raises(FileNotFoundError, match="Solution file not found"):
            run_problem("test-prob", str(tmp_path / "missing.py"))

    def test_problem_not_found(self, tmp_path):
        sol = _write_solution(tmp_path, "foo.py", "")
        with pytest.raises(ValueError, match="does not exist"):
            run_problem("nonexistent", sol)

    def test_no_test_cases(self, tmp_path):
        _make_stdio_problem()
        sol = _write_solution(tmp_path, "foo.py", "print('hi')")
        with pytest.raises(ValueError, match="No test cases"):
            run_problem("test-prob", sol)

    def test_unsupported_extension(self, tmp_path):
        _make_stdio_problem()
        sol = _write_solution(tmp_path, "foo.rb", "puts 'hi'")
        with pytest.raises(ValueError, match="Unsupported file extension"):
            run_problem("test-prob", sol)


# ---------------------------------------------------------------------------
# Python stdio mode
# ---------------------------------------------------------------------------

class TestPythonStdio:
    def _setup(self, tmp_path, solution_code: str, inputs_outputs: list) -> tuple:
        _make_stdio_problem()
        for i, (inp, exp) in enumerate(inputs_outputs):
            store.add_test_case("test-prob", inp, exp, label=f"case-{i}")
        sol = _write_solution(tmp_path, "solution.py", solution_code)
        return sol

    def test_all_pass(self, tmp_path):
        sol = self._setup(
            tmp_path,
            "import sys\nprint(sys.stdin.read().strip())",
            [("hello", "hello"), ("world", "world")],
        )
        run = run_problem("test-prob", sol)
        assert run.total == 2
        assert run.passed == 2
        assert run.failed == 0
        assert run.errored == 0
        assert run.language == "python"

    def test_one_fail(self, tmp_path):
        sol = self._setup(
            tmp_path,
            "print('wrong')",
            [("1 2", "3"), ("4 5", "9")],
        )
        run = run_problem("test-prob", sol)
        assert run.passed == 0
        assert run.failed == 2

    def test_pass_and_fail(self, tmp_path):
        sol = self._setup(
            tmp_path,
            "import sys\ndata = sys.stdin.read().split()\nprint(int(data[0]) + int(data[1]))",
            [("1 2", "3"), ("4 5", "wrong")],
        )
        run = run_problem("test-prob", sol)
        assert run.passed == 1
        assert run.failed == 1

    def test_trailing_whitespace_ignored(self, tmp_path):
        sol = self._setup(
            tmp_path,
            "print('hello   ')",
            [("", "hello")],
        )
        run = run_problem("test-prob", sol)
        assert run.passed == 1

    def test_trailing_newline_ignored(self, tmp_path):
        sol = self._setup(
            tmp_path,
            "import sys; sys.stdout.write('hello\\n\\n')",
            [("", "hello")],
        )
        run = run_problem("test-prob", sol)
        assert run.passed == 1

    def test_tle(self, tmp_path):
        sol = self._setup(
            tmp_path,
            "import time; time.sleep(100)",
            [("", "anything")],
        )
        run = run_problem("test-prob", sol, timeout_sec=0.2)
        assert run.errored == 1
        results = store.get_run_results(run.id)
        assert results[0].status == "tle"

    def test_runtime_error(self, tmp_path):
        sol = self._setup(
            tmp_path,
            "raise RuntimeError('boom')",
            [("", "anything")],
        )
        run = run_problem("test-prob", sol)
        # Non-zero exit still produces output; status is fail (empty output vs expected)
        # or error depending on implementation — we accept either fail or error
        results = store.get_run_results(run.id)
        assert results[0].status in ("fail", "error")

    def test_run_persisted_to_store(self, tmp_path):
        sol = self._setup(
            tmp_path,
            "print('42')",
            [("", "42")],
        )
        run = run_problem("test-prob", sol)
        runs = store.get_runs("test-prob")
        assert len(runs) == 1
        assert runs[0].id == run.id

    def test_run_results_persisted(self, tmp_path):
        sol = self._setup(
            tmp_path,
            "import sys\nprint(sys.stdin.read().strip())",
            [("abc", "abc")],
        )
        run = run_problem("test-prob", sol)
        results = store.get_run_results(run.id)
        assert len(results) == 1
        assert results[0].status == "pass"
        assert results[0].elapsed_ms is not None

    def test_empty_input(self, tmp_path):
        sol = self._setup(
            tmp_path,
            "print('done')",
            [("", "done")],
        )
        run = run_problem("test-prob", sol)
        assert run.passed == 1

    def test_multiline_output(self, tmp_path):
        sol = self._setup(
            tmp_path,
            "print('a'); print('b'); print('c')",
            [("", "a\nb\nc")],
        )
        run = run_problem("test-prob", sol)
        assert run.passed == 1


# ---------------------------------------------------------------------------
# Python function mode
# ---------------------------------------------------------------------------

class TestPythonFunction:
    def _setup(self, tmp_path, solution_code: str, cases: list, func: str = "solve") -> str:
        _make_function_problem(func_name=func)
        for i, (args_json, expected) in enumerate(cases):
            store.add_test_case("test-func", args_json, expected, label=f"case-{i}")
        return _write_solution(tmp_path, "solution.py", solution_code)

    def test_simple_add(self, tmp_path):
        sol = self._setup(
            tmp_path,
            "def solve(a, b): return a + b",
            [("[1, 2]", "3"), ("[10, 20]", "30")],
        )
        run = run_problem("test-func", sol)
        assert run.passed == 2

    def test_string_return(self, tmp_path):
        store.create_problem("test-str", "function", func_name="rev")
        store.add_test_case("test-str", '["hello"]', '"olleh"')
        sol = _write_solution(tmp_path, "rev.py", 'def rev(s): return s[::-1]')
        run = run_problem("test-str", sol)
        assert run.passed == 1

    def test_list_return(self, tmp_path):
        store.create_problem("test-list", "function", func_name="double_list")
        store.add_test_case("test-list", "[[1, 2, 3]]", "[2, 4, 6]")
        sol = _write_solution(tmp_path, "dl.py", "def double_list(lst): return [x * 2 for x in lst]")
        run = run_problem("test-list", sol)
        assert run.passed == 1

    def test_wrong_return(self, tmp_path):
        sol = self._setup(
            tmp_path,
            "def solve(a, b): return a - b",
            [("[1, 2]", "3")],
        )
        run = run_problem("test-func", sol)
        assert run.failed == 1

    def test_tle_function(self, tmp_path):
        sol = self._setup(
            tmp_path,
            "import time\ndef solve(a, b):\n    time.sleep(100)\n    return a + b",
            [("[1, 2]", "3")],
        )
        run = run_problem("test-func", sol, timeout_sec=0.2)
        assert run.errored == 1
        results = store.get_run_results(run.id)
        assert results[0].status == "tle"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _which(name: str) -> bool:
    import shutil
    return shutil.which(name) is not None


# ---------------------------------------------------------------------------
# C++ compilation error
# ---------------------------------------------------------------------------

class TestCppCompilation:
    def test_compilation_error_raised(self, tmp_path):
        store.create_problem("cpp-prob", "stdio")
        store.add_test_case("cpp-prob", "1", "1")
        sol = _write_solution(tmp_path, "bad.cpp", "this is not valid c++ code !!!!")
        with pytest.raises(CompilationError):
            run_problem("cpp-prob", sol)

    @pytest.mark.skipif(
        not _which("g++"), reason="g++ not available"
    )
    def test_cpp_stdio_pass(self, tmp_path):
        store.create_problem("cpp-sum", "stdio")
        store.add_test_case("cpp-sum", "3 4", "7")
        code = """\
#include <iostream>
using namespace std;
int main() {
    int a, b;
    cin >> a >> b;
    cout << a + b << endl;
    return 0;
}
"""
        sol = _write_solution(tmp_path, "sum.cpp", code)
        run = run_problem("cpp-sum", sol)
        assert run.passed == 1


# ---------------------------------------------------------------------------
# Python linked list (ListNode) function mode
# ---------------------------------------------------------------------------

class TestPythonLinkedList:
    def _make_problem(self, arg_types=None, return_type=None):
        store.create_problem(
            "list-prob", "function", func_name="solve",
            arg_types=arg_types, return_type=return_type,
        )

    def test_listnode_arg_pass(self, tmp_path):
        """ListNode arg: reverse a linked list, compare as JSON array."""
        self._make_problem(arg_types=["ListNode"], return_type="ListNode")
        store.add_test_case("list-prob", "[[1,2,3]]", "[3, 2, 1]", label="reverse")
        code = """\
def solve(head):
    prev = None
    while head:
        nxt = head.next
        head.next = prev
        prev = head
        head = nxt
    return prev
"""
        sol = _write_solution(tmp_path, "solution.py", code)
        run = run_problem("list-prob", sol)
        assert run.passed == 1
        assert run.failed == 0

    def test_listnode_arg_fail(self, tmp_path):
        """Wrong output for ListNode problem is detected as fail."""
        self._make_problem(arg_types=["ListNode"], return_type="ListNode")
        store.add_test_case("list-prob", "[[1,2,3]]", "[3, 2, 1]")
        code = "def solve(head): return head"  # no-op, returns original order
        sol = _write_solution(tmp_path, "solution.py", code)
        run = run_problem("list-prob", sol)
        assert run.failed == 1

    def test_listnode_arg_with_scalar(self, tmp_path):
        """ListNode arg alongside a scalar arg (e.g. remove-nth-from-end)."""
        self._make_problem(arg_types=["ListNode", "int"], return_type="ListNode")
        store.add_test_case("list-prob", "[[1,2,3,4,5], 2]", "[1, 2, 3, 5]")
        code = """\
def solve(head, n):
    dummy = ListNode(0, head)
    fast = slow = dummy
    for _ in range(n + 1):
        fast = fast.next
    while fast:
        fast = fast.next
        slow = slow.next
    slow.next = slow.next.next
    return dummy.next
"""
        sol = _write_solution(tmp_path, "solution.py", code)
        run = run_problem("list-prob", sol)
        assert run.passed == 1

    def test_listnode_return_scalar(self, tmp_path):
        """Function takes a ListNode but returns a scalar (e.g. length)."""
        self._make_problem(arg_types=["ListNode"], return_type=None)
        store.add_test_case("list-prob", "[[1,2,3]]", "3")  # input: [args], where args[0] = linked list
        code = """\
def solve(head):
    count = 0
    while head:
        count += 1
        head = head.next
    return count
"""
        sol = _write_solution(tmp_path, "solution.py", code)
        run = run_problem("list-prob", sol)
        assert run.passed == 1

    def test_empty_listnode(self, tmp_path):
        """Empty list input (null head) represented as []."""
        self._make_problem(arg_types=["ListNode"], return_type="ListNode")
        store.add_test_case("list-prob", "[[]]", "[]")
        code = "def solve(head): return head"
        sol = _write_solution(tmp_path, "solution.py", code)
        run = run_problem("list-prob", sol)
        assert run.passed == 1

    def test_store_roundtrip_arg_types(self, tmp_path):
        """arg_types and return_type survive a store round-trip."""
        store.create_problem(
            "rt-prob", "function", func_name="f",
            arg_types=["ListNode", "int"], return_type="ListNode",
        )
        p = store.get_problem("rt-prob")
        assert p.arg_types == ["ListNode", "int"]
        assert p.return_type == "ListNode"


# ---------------------------------------------------------------------------
# Multiple runs tracked independently
# ---------------------------------------------------------------------------

class TestMultipleRuns:
    def test_multiple_runs_stored(self, tmp_path):
        _make_stdio_problem()
        store.add_test_case("test-prob", "hello", "hello")
        sol = _write_solution(tmp_path, "echo.py", "import sys\nprint(sys.stdin.read().strip())")
        run1 = run_problem("test-prob", sol)
        run2 = run_problem("test-prob", sol)
        assert run1.id != run2.id
        runs = store.get_runs("test-prob")
        assert len(runs) == 2
