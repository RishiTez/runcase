import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List, Optional

from runcase import store
from runcase.store import CaseResult

_EXT_TO_LANGUAGE = {
    ".py": "python",
    ".cpp": "cpp",
    ".java": "java",
}

MAX_OUTPUT_BYTES = 10 * 1024 * 1024  # 10 MB


class CompilationError(Exception):
    """Raised when compilation of a solution file fails."""

    def __init__(self, message: str, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


def _detect_language(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    language = _EXT_TO_LANGUAGE.get(ext)
    if language is None:
        raise ValueError(
            f"Unsupported file extension {ext!r}. Supported: {sorted(_EXT_TO_LANGUAGE.keys())}"
        )
    return language


def _normalize_output(text: str) -> str:
    """Strip trailing whitespace per line and trailing newlines for comparison."""
    lines = text.splitlines()
    stripped = [line.rstrip() for line in lines]
    return "\n".join(stripped).rstrip("\n")


def _compile_cpp(file_path: str, out_dir: str) -> str:
    """Compile a C++ file; return path to binary. Raises CompilationError on failure."""
    binary = os.path.join(out_dir, "solution")
    result = subprocess.run(
        ["g++", "-std=c++17", "-O2", "-o", binary, file_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CompilationError(
            f"C++ compilation failed for {file_path!r}",
            stderr=result.stderr,
        )
    return binary


def _compile_java(file_path: str, out_dir: str) -> str:
    """Compile a Java file; return the class name for execution. Raises CompilationError on failure."""
    result = subprocess.run(
        ["javac", "-d", out_dir, file_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CompilationError(
            f"Java compilation failed for {file_path!r}",
            stderr=result.stderr,
        )
    return Path(file_path).stem


def _run_process(
    cmd: List[str],
    stdin_data: str,
    timeout_sec: float,
    cwd: Optional[str] = None,
) -> tuple:
    """
    Run a subprocess and return (stdout, stderr, elapsed_ms, timed_out, size_exceeded).
    Reads up to MAX_OUTPUT_BYTES + 1 bytes to detect SLE.
    """
    start = time.monotonic()
    timed_out = False
    size_exceeded = False
    stdout_data = ""
    stderr_data = ""

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
        )
        try:
            stdout_bytes, stderr_bytes = proc.communicate(
                input=stdin_data.encode(),
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            timed_out = True
            stdout_bytes = b""
            stderr_bytes = b""

        if not timed_out:
            if len(stdout_bytes) > MAX_OUTPUT_BYTES:
                size_exceeded = True
                stdout_data = stdout_bytes[:MAX_OUTPUT_BYTES].decode(errors="replace")
            else:
                stdout_data = stdout_bytes.decode(errors="replace")
            stderr_data = stderr_bytes.decode(errors="replace")

    except FileNotFoundError as exc:
        raise RuntimeError(f"Executable not found: {cmd[0]!r}") from exc

    elapsed_ms = int((time.monotonic() - start) * 1000)
    return stdout_data, stderr_data, elapsed_ms, timed_out, size_exceeded


# ---------------------------------------------------------------------------
# Function-call mode: wrapper generation
# ---------------------------------------------------------------------------

_PYTHON_LISTNODE = """\
class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next

def _list_to_node(arr):
    if not arr:
        return None
    head = ListNode(arr[0])
    cur = head
    for v in arr[1:]:
        cur.next = ListNode(v)
        cur = cur.next
    return head

def _node_to_list(node):
    result = []
    while node:
        result.append(node.val)
        node = node.next
    return result

"""


def _python_wrapper(
    solution_path: str,
    func_name: str,
    args_json: str,
    arg_types: Optional[List[str]] = None,
    return_type: Optional[str] = None,
) -> str:
    """Generate a Python wrapper script for function-call mode."""
    needs_listnode = (arg_types and "ListNode" in arg_types) or return_type == "ListNode"
    listnode_block = _PYTHON_LISTNODE if needs_listnode else ""

    arg_conversions = ""
    if arg_types:
        lines = []
        for i, t in enumerate(arg_types):
            if t == "ListNode":
                lines.append(f"_args[{i}] = _list_to_node(_args[{i}])")
        if lines:
            arg_conversions = "\n".join(lines) + "\n"

    if return_type == "ListNode":
        result_expr = "json.dumps(_node_to_list(_result))"
    else:
        result_expr = "json.dumps(_result)"

    inject_listnode = "_mod.ListNode = ListNode\n" if needs_listnode else ""

    return f"""\
import sys
import json
sys.path.insert(0, {str(Path(solution_path).parent)!r})

{listnode_block}import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("_solution", {str(solution_path)!r})
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
{inject_listnode}
_args = json.loads({args_json!r})
{arg_conversions}_result = _mod.{func_name}(*_args)
print({result_expr})
"""


def _cpp_json_value(val) -> str:
    """Render a Python value as a C++ literal expression."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        return repr(val)
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(val, list):
        if val and isinstance(val[0], list):
            # vector<vector<int>>
            inner = ", ".join(
                "{" + ", ".join(_cpp_json_value(x) for x in sub) + "}" for sub in val
            )
            return f"{{{inner}}}"
        items = ", ".join(_cpp_json_value(x) for x in val)
        return f"{{{items}}}"
    raise ValueError(f"Unsupported C++ argument type: {type(val)}")


def _cpp_type_name(val) -> str:
    """Infer a C++ type name from a Python value."""
    if isinstance(val, bool):
        return "bool"
    if isinstance(val, int):
        return "long long"
    if isinstance(val, float):
        return "double"
    if isinstance(val, str):
        return "string"
    if isinstance(val, list):
        if val and isinstance(val[0], list):
            return "vector<vector<int>>"
        return "vector<int>"
    raise ValueError(f"Unsupported C++ argument type: {type(val)}")


_CPP_LISTNODE = """\
#ifndef RUNCASE_LISTNODE
#define RUNCASE_LISTNODE
struct ListNode {
    int val;
    ListNode *next;
    ListNode() : val(0), next(nullptr) {}
    ListNode(int x) : val(x), next(nullptr) {}
    ListNode(int x, ListNode *next) : val(x), next(next) {}
};
#endif

static ListNode* _buildList(vector<int> arr) {
    if (arr.empty()) return nullptr;
    ListNode* head = new ListNode(arr[0]);
    ListNode* cur = head;
    for (size_t i = 1; i < arr.size(); i++) {
        cur->next = new ListNode((int)arr[i]);
        cur = cur->next;
    }
    return head;
}

static string _serializeList(ListNode* head) {
    string result = "[";
    bool first = true;
    while (head) {
        if (!first) result += ",";
        result += to_string(head->val);
        first = false;
        head = head->next;
    }
    result += "]";
    return result;
}

"""


def _cpp_wrapper(
    solution_path: str,
    func_name: str,
    args_json: str,
    arg_types: Optional[List[str]] = None,
    return_type: Optional[str] = None,
) -> str:
    args = json.loads(args_json)
    needs_listnode = (arg_types and "ListNode" in arg_types) or return_type == "ListNode"
    listnode_block = _CPP_LISTNODE if needs_listnode else ""

    decls = []
    call_args = []
    for i, arg in enumerate(args):
        vname = f"_arg{i}"
        if arg_types and i < len(arg_types) and arg_types[i] == "ListNode":
            inner = ", ".join(_cpp_json_value(x) for x in arg)
            decls.append(f"    ListNode* {vname} = _buildList({{{inner}}});")
        else:
            ctype = _cpp_type_name(arg)
            literal = _cpp_json_value(arg)
            decls.append(f"    {ctype} {vname} = {literal};")
        call_args.append(vname)

    decls_str = "\n".join(decls)
    call_str = ", ".join(call_args)

    if return_type == "ListNode":
        output_stmt = "    cout << _serializeList(_result) << endl;"
    else:
        output_stmt = "    cout << _result << endl;"

    return f"""\
#include <bits/stdc++.h>
{listnode_block}#include "{solution_path}"
using namespace std;

int main() {{
{decls_str}
    auto _result = {func_name}({call_str});
{output_stmt}
    return 0;
}}
"""


def _java_type_name(val) -> str:
    if isinstance(val, bool):
        return "boolean"
    if isinstance(val, int):
        return "long"
    if isinstance(val, float):
        return "double"
    if isinstance(val, str):
        return "String"
    if isinstance(val, list):
        if val and isinstance(val[0], list):
            return "int[][]"
        return "int[]"
    raise ValueError(f"Unsupported Java argument type: {type(val)}")


def _java_literal(val) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val) + "L"
    if isinstance(val, float):
        return repr(val)
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(val, list):
        if val and isinstance(val[0], list):
            inner = ", ".join(
                "{" + ", ".join(_java_literal(x) for x in sub) + "}" for sub in val
            )
            return f"new int[][]{{{inner}}}"
        items = ", ".join(_java_literal(x) for x in val)
        return f"new int[]{{{items}}}"
    raise ValueError(f"Unsupported Java argument type: {type(val)}")


_JAVA_LISTNODE = """\
    static class ListNode {
        int val;
        ListNode next;
        ListNode() {}
        ListNode(int val) { this.val = val; }
        ListNode(int val, ListNode next) { this.val = val; this.next = next; }
    }

    static ListNode _buildList(int[] arr) {
        if (arr.length == 0) return null;
        ListNode head = new ListNode(arr[0]);
        ListNode cur = head;
        for (int i = 1; i < arr.length; i++) {
            cur.next = new ListNode(arr[i]);
            cur = cur.next;
        }
        return head;
    }

    static String _serializeList(ListNode head) {
        StringBuilder sb = new StringBuilder("[");
        boolean first = true;
        while (head != null) {
            if (!first) sb.append(",");
            sb.append(head.val);
            first = false;
            head = head.next;
        }
        sb.append("]");
        return sb.toString();
    }

"""


def _java_wrapper(
    solution_path: str,
    func_name: str,
    args_json: str,
    class_name: str,
    arg_types: Optional[List[str]] = None,
    return_type: Optional[str] = None,
) -> str:
    args = json.loads(args_json)
    needs_listnode = (arg_types and "ListNode" in arg_types) or return_type == "ListNode"
    listnode_block = _JAVA_LISTNODE if needs_listnode else ""

    decls = []
    call_args = []
    for i, arg in enumerate(args):
        vname = f"_arg{i}"
        if arg_types and i < len(arg_types) and arg_types[i] == "ListNode":
            items = ", ".join(_java_literal(x) for x in arg)
            decls.append(f"        ListNode {vname} = _buildList(new int[]{{{items}}});")
        else:
            jtype = _java_type_name(arg)
            literal = _java_literal(arg)
            decls.append(f"        {jtype} {vname} = {literal};")
        call_args.append(vname)

    decls_str = "\n".join(decls)
    call_str = ", ".join(call_args)
    wrapper_class = f"_Wrapper_{class_name}"

    if return_type == "ListNode":
        output_stmt = f"        System.out.println(_serializeList((ListNode)_result));"
    else:
        output_stmt = f"        System.out.println(_result);"

    return f"""\
public class {wrapper_class} {{
{listnode_block}    public static void main(String[] args) throws Exception {{
{decls_str}
        Object _result = {class_name}.{func_name}({call_str});
{output_stmt}
    }}
}}
"""


# ---------------------------------------------------------------------------
# Per-case execution
# ---------------------------------------------------------------------------

def _execute_stdio(
    language: str,
    cmd_or_binary: str,
    class_name: Optional[str],
    test_case: store.TestCase,
    timeout_sec: float,
    cwd: Optional[str] = None,
) -> CaseResult:
    if language == "python":
        cmd = ["python3", cmd_or_binary]
    elif language == "cpp":
        cmd = [cmd_or_binary]
    else:  # java
        cmd = ["java", "-cp", cwd or ".", class_name]

    stdout, stderr, elapsed_ms, timed_out, size_exceeded = _run_process(
        cmd, test_case.input, timeout_sec, cwd=cwd
    )

    if timed_out:
        return CaseResult(
            test_case_id=test_case.id,
            status="tle",
            actual=None,
            stderr=None,
            elapsed_ms=int(timeout_sec * 1000),
        )
    if size_exceeded:
        return CaseResult(
            test_case_id=test_case.id,
            status="sle",
            actual=stdout,
            stderr=stderr,
            elapsed_ms=elapsed_ms,
        )

    actual_norm = _normalize_output(stdout)
    expected_norm = _normalize_output(test_case.expected)
    status = "pass" if actual_norm == expected_norm else "fail"

    return CaseResult(
        test_case_id=test_case.id,
        status=status,
        actual=stdout,
        stderr=stderr or None,
        elapsed_ms=elapsed_ms,
    )


def _execute_function(
    language: str,
    solution_path: str,
    func_name: str,
    class_name: Optional[str],
    test_case: store.TestCase,
    timeout_sec: float,
    tmp_dir: str,
    arg_types: Optional[List[str]] = None,
    return_type: Optional[str] = None,
) -> CaseResult:
    """Execute one function-mode test case via a generated wrapper."""
    args_json = test_case.input  # stored as JSON array

    if language == "python":
        wrapper_code = _python_wrapper(solution_path, func_name, args_json, arg_types, return_type)
        wrapper_path = os.path.join(tmp_dir, f"_wrapper_{test_case.id}.py")
        Path(wrapper_path).write_text(wrapper_code)
        cmd = ["python3", wrapper_path]
        stdout, stderr, elapsed_ms, timed_out, size_exceeded = _run_process(
            cmd, "", timeout_sec
        )

    elif language == "cpp":
        # C++ function mode: generate wrapper, compile, run
        wrapper_code = _cpp_wrapper(solution_path, func_name, args_json, arg_types, return_type)
        wrapper_path = os.path.join(tmp_dir, f"_wrapper_{test_case.id}.cpp")
        Path(wrapper_path).write_text(wrapper_code)
        binary = os.path.join(tmp_dir, f"_wrapper_{test_case.id}")
        compile_result = subprocess.run(
            ["g++", "-std=c++17", "-O2", "-o", binary, wrapper_path],
            capture_output=True,
            text=True,
        )
        if compile_result.returncode != 0:
            return CaseResult(
                test_case_id=test_case.id,
                status="error",
                actual=None,
                stderr=compile_result.stderr,
                elapsed_ms=0,
            )
        stdout, stderr, elapsed_ms, timed_out, size_exceeded = _run_process(
            [binary], "", timeout_sec
        )

    else:  # java
        wrapper_code = _java_wrapper(solution_path, func_name, args_json, class_name, arg_types, return_type)
        wrapper_class = f"_Wrapper_{class_name}"
        wrapper_path = os.path.join(tmp_dir, f"{wrapper_class}.java")
        Path(wrapper_path).write_text(wrapper_code)
        compile_result = subprocess.run(
            ["javac", "-cp", tmp_dir, "-d", tmp_dir, wrapper_path],
            capture_output=True,
            text=True,
        )
        if compile_result.returncode != 0:
            return CaseResult(
                test_case_id=test_case.id,
                status="error",
                actual=None,
                stderr=compile_result.stderr,
                elapsed_ms=0,
            )
        stdout, stderr, elapsed_ms, timed_out, size_exceeded = _run_process(
            ["java", "-cp", tmp_dir, wrapper_class], "", timeout_sec
        )

    if timed_out:
        return CaseResult(
            test_case_id=test_case.id,
            status="tle",
            actual=None,
            stderr=None,
            elapsed_ms=int(timeout_sec * 1000),
        )
    if size_exceeded:
        return CaseResult(
            test_case_id=test_case.id,
            status="sle",
            actual=stdout,
            stderr=stderr,
            elapsed_ms=elapsed_ms,
        )

    # Compare JSON-serialized return value against expected
    actual_norm = _normalize_output(stdout)
    expected_norm = _normalize_output(test_case.expected)
    status = "pass" if actual_norm == expected_norm else "fail"

    return CaseResult(
        test_case_id=test_case.id,
        status=status,
        actual=stdout,
        stderr=stderr or None,
        elapsed_ms=elapsed_ms,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_custom(
    problem_name: str,
    file_path: str,
    input_data: str,
    expected_data: str = "",
    timeout_sec: float = 10.0,
) -> CaseResult:
    """
    Run a single ad-hoc test case without persisting to DB.

    The returned CaseResult has test_case_id=0 (sentinel; not stored).

    Raises:
        ValueError: problem not found or unsupported file extension.
        CompilationError: compilation failed for C++ or Java.
        FileNotFoundError: solution file does not exist.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Solution file not found: {file_path!r}")

    language = _detect_language(file_path)

    problem = store.get_problem(problem_name)
    if problem is None:
        raise ValueError(f"Problem {problem_name!r} does not exist")

    tc = store.TestCase(
        id=0,
        problem_id=problem.id,
        label=None,
        input=input_data,
        expected=expected_data,
        created_at="",
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        binary: Optional[str] = None
        class_name: Optional[str] = None

        if problem.mode == "stdio":
            if language == "cpp":
                binary = _compile_cpp(file_path, tmp_dir)
            elif language == "java":
                class_name = _compile_java(file_path, tmp_dir)
        else:  # function
            if language == "java":
                class_name = _compile_java(file_path, tmp_dir)

        try:
            if problem.mode == "stdio":
                result = _execute_stdio(
                    language=language,
                    cmd_or_binary=binary if binary else file_path,
                    class_name=class_name,
                    test_case=tc,
                    timeout_sec=timeout_sec,
                    cwd=tmp_dir if language == "java" else None,
                )
            else:  # function
                result = _execute_function(
                    language=language,
                    solution_path=file_path,
                    func_name=problem.func_name,
                    class_name=class_name,
                    test_case=tc,
                    timeout_sec=timeout_sec,
                    tmp_dir=tmp_dir,
                    arg_types=problem.arg_types,
                    return_type=problem.return_type,
                )
        except Exception as exc:
            result = CaseResult(
                test_case_id=0,
                status="error",
                actual=None,
                stderr=str(exc),
                elapsed_ms=None,
            )

    return result


def run_problem(
    problem_name: str,
    file_path: str,
    timeout_sec: float = 10.0,
) -> store.Run:
    """
    Run all test cases for a problem against the given solution file.

    Returns a Run record with all results persisted to the store.

    Raises:
        ValueError: problem not found, no test cases, or unsupported file extension.
        CompilationError: compilation failed for C++ or Java.
        FileNotFoundError: solution file does not exist.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Solution file not found: {file_path!r}")

    language = _detect_language(file_path)

    problem = store.get_problem(problem_name)
    if problem is None:
        raise ValueError(f"Problem {problem_name!r} does not exist")

    test_cases = store.get_test_cases(problem_name)
    if not test_cases:
        raise ValueError(f"No test cases found for problem {problem_name!r}")

    results: List[CaseResult] = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Compile once up front for compiled languages (stdio mode).
        # For function mode, compilation happens per test case wrapper.
        binary: Optional[str] = None
        class_name: Optional[str] = None

        if problem.mode == "stdio":
            if language == "cpp":
                binary = _compile_cpp(file_path, tmp_dir)
            elif language == "java":
                class_name = _compile_java(file_path, tmp_dir)

        elif problem.mode == "function":
            if language == "java":
                # Compile the solution class first so wrapper can reference it.
                class_name = _compile_java(file_path, tmp_dir)
            elif language == "cpp":
                # C++ function mode: solution is header-included; no pre-compile.
                pass

        for tc in test_cases:
            try:
                if problem.mode == "stdio":
                    result = _execute_stdio(
                        language=language,
                        cmd_or_binary=binary if binary else file_path,
                        class_name=class_name,
                        test_case=tc,
                        timeout_sec=timeout_sec,
                        cwd=tmp_dir if language == "java" else None,
                    )
                else:  # function
                    result = _execute_function(
                        language=language,
                        solution_path=file_path,
                        func_name=problem.func_name,
                        class_name=class_name,
                        test_case=tc,
                        timeout_sec=timeout_sec,
                        tmp_dir=tmp_dir,
                        arg_types=problem.arg_types,
                        return_type=problem.return_type,
                    )
            except Exception as exc:
                result = CaseResult(
                    test_case_id=tc.id,
                    status="error",
                    actual=None,
                    stderr=str(exc),
                    elapsed_ms=None,
                )
            results.append(result)

    return store.create_run(
        problem_name=problem_name,
        file_path=file_path,
        language=language,
        results=results,
    )
