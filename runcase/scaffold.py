import os
from pathlib import Path
from typing import List, Optional

from runcase import store

_EXTENSIONS = {
    "python": "py",
    "cpp": "cpp",
    "java": "java",
}

_VALID_LANGUAGES = set(_EXTENSIONS.keys())

# Type mapping: canonical type name (as entered by user) -> language-specific type string.
# Users enter Python/LeetCode-style names: int, str, bool, float, List[int], ListNode, etc.

_PY_TYPE_ALIASES = {"string": "str", "double": "float", "boolean": "bool"}

def _py_type(t: str) -> str:
    return _PY_TYPE_ALIASES.get(t, t)

_CPP_TYPE_MAP = {
    "int": "int", "float": "double", "double": "double",
    "str": "string", "string": "string", "bool": "bool", "boolean": "bool",
    "List[int]": "vector<int>", "List[str]": "vector<string>",
    "List[string]": "vector<string>", "List[bool]": "vector<bool>",
    "List[float]": "vector<double>", "List[double]": "vector<double>",
    "List[List[int]]": "vector<vector<int>>",
    "List[List[str]]": "vector<vector<string>>",
    "ListNode": "ListNode*",
}
_CPP_BY_REF = {"string", "vector<int>", "vector<string>", "vector<bool>",
               "vector<double>", "vector<vector<int>>", "vector<vector<string>>"}

def _cpp_type(t: str, is_param: bool = False) -> str:
    mapped = _CPP_TYPE_MAP.get(t, t)
    if is_param and mapped in _CPP_BY_REF:
        return f"const {mapped}&"
    return mapped

_JAVA_TYPE_MAP = {
    "int": "int", "float": "double", "double": "double",
    "str": "String", "string": "String", "bool": "boolean", "boolean": "boolean",
    "List[int]": "int[]", "List[str]": "String[]", "List[string]": "String[]",
    "List[bool]": "boolean[]", "List[float]": "double[]", "List[double]": "double[]",
    "List[List[int]]": "int[][]", "List[List[str]]": "String[][]",
    "ListNode": "ListNode",
}
_JAVA_DEFAULT_RETURN = {
    "int": "return 0;", "double": "return 0.0;", "boolean": "return false;",
    "String": 'return "";',
    "int[]": "return new int[]{};", "int[][]": "return new int[][]{};",
    "String[]": "return new String[]{};", "boolean[]": "return new boolean[]{};",
    "ListNode": "return null;",
}

def _java_type(t: str) -> str:
    return _JAVA_TYPE_MAP.get(t, t)


def _to_class_name(problem_name: str) -> str:
    return "".join(part.capitalize() for part in problem_name.split("-"))


def _python_stdio() -> str:
    return """\
import sys


def solve():
    data = sys.stdin.read().split()
    # TODO: implement solution
    print()


if __name__ == "__main__":
    solve()
"""


_PYTHON_LISTNODE_STUB = """\
class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next


"""


def _python_function(
    func_name: str,
    params: Optional[List[str]] = None,
    arg_types: Optional[List[str]] = None,
    return_type: Optional[str] = None,
) -> str:
    needs_listnode = (arg_types and "ListNode" in arg_types) or return_type == "ListNode"
    listnode_block = _PYTHON_LISTNODE_STUB if needs_listnode else ""

    if params and arg_types and len(params) == len(arg_types):
        sig = ", ".join(f"{p}: {_py_type(t)}" for p, t in zip(params, arg_types))
    elif params:
        sig = ", ".join(params)
    else:
        sig = "*args"

    ret_annotation = f" -> {_py_type(return_type)}" if return_type else ""

    all_types = list(arg_types or []) + ([return_type] if return_type else [])
    needs_list_import = any("List[" in t for t in all_types)
    typing_import = "from typing import List\n\n\n" if needs_list_import else ""

    return f"""\
{typing_import}{listnode_block}def {func_name}({sig}){ret_annotation}:
    # TODO: implement solution
    pass
"""


def _cpp_stdio() -> str:
    return """\
#include <bits/stdc++.h>
using namespace std;

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);

    // TODO: implement solution

    return 0;
}
"""


_CPP_LISTNODE_STUB = """\
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

"""


def _cpp_function(
    func_name: str,
    params: Optional[List[str]] = None,
    arg_types: Optional[List[str]] = None,
    return_type: Optional[str] = None,
) -> str:
    needs_listnode = (arg_types and "ListNode" in arg_types) or return_type == "ListNode"
    listnode_block = _CPP_LISTNODE_STUB if needs_listnode else ""

    if params and arg_types and len(params) == len(arg_types):
        param_str = ", ".join(f"{_cpp_type(t, True)} {p}" for p, t in zip(params, arg_types))
    elif params:
        param_str = ", ".join(f"auto {p}" for p in params)
    else:
        param_str = "/* args */"

    ret_type = _cpp_type(return_type) if return_type else "auto"

    return f"""\
#include <bits/stdc++.h>
using namespace std;

{listnode_block}{ret_type} {func_name}({param_str}) {{
    // TODO: implement solution
}}

int main() {{
    // TODO: call {func_name} with args
    return 0;
}}
"""


def _java_stdio(class_name: str) -> str:
    return f"""\
import java.util.Scanner;

public class {class_name} {{
    public static void main(String[] args) {{
        Scanner sc = new Scanner(System.in);
        // TODO: implement solution
    }}
}}
"""


_JAVA_LISTNODE_STUB = """\
    // ListNode is provided by runcase's test runner.
    // class ListNode { int val; ListNode next; ... }

"""


def _java_function(
    class_name: str,
    func_name: str,
    params: Optional[List[str]] = None,
    arg_types: Optional[List[str]] = None,
    return_type: Optional[str] = None,
) -> str:
    needs_listnode = (arg_types and "ListNode" in arg_types) or return_type == "ListNode"
    listnode_block = _JAVA_LISTNODE_STUB if needs_listnode else ""

    if params and arg_types and len(params) == len(arg_types):
        param_str = ", ".join(f"{_java_type(t)} {p}" for p, t in zip(params, arg_types))
    elif params:
        param_str = ", ".join(f"Object {p}" for p in params)
    else:
        param_str = "/* args */"

    java_ret = _java_type(return_type) if return_type else "Object"
    default_return = _JAVA_DEFAULT_RETURN.get(java_ret, "return null;")

    return f"""\
public class {class_name} {{
{listnode_block}    public static {java_ret} {func_name}({param_str}) {{
        // TODO: implement solution
        {default_return}
    }}
}}
"""


def scaffold_problem(
    name: str,
    mode: str,
    func_name: Optional[str] = None,
    language: str = "python",
    directory: Optional[str] = None,
    params: Optional[List[str]] = None,
    arg_types: Optional[List[str]] = None,
    return_type: Optional[str] = None,
) -> Path:
    """
    Create a problem in the store and write a solution template file.

    Returns the path to the created file.

    Raises:
        ValueError: invalid language, invalid problem name/mode, or duplicate problem.
        FileExistsError: solution file already exists at the target path.
    """
    if language not in _VALID_LANGUAGES:
        raise ValueError(
            f"Unsupported language {language!r}. Must be one of {sorted(_VALID_LANGUAGES)}"
        )

    if directory is None:
        directory = os.getcwd()

    ext = _EXTENSIONS[language]
    file_path = Path(directory) / f"{name}.{ext}"

    if file_path.exists():
        raise FileExistsError(f"Solution file already exists: {file_path}")

    # Persist first — raises ValueError on invalid name, mode, or duplicate.
    store.init_db()
    store.create_problem(name, mode, func_name, arg_types=arg_types, return_type=return_type, params=params)

    class_name = _to_class_name(name)

    if language == "python":
        content = _python_stdio() if mode == "stdio" else _python_function(func_name, params, arg_types, return_type)
    elif language == "cpp":
        content = _cpp_stdio() if mode == "stdio" else _cpp_function(func_name, params, arg_types, return_type)
    else:  # java
        content = _java_stdio(class_name) if mode == "stdio" else _java_function(class_name, func_name, params, arg_types, return_type)

    file_path.write_text(content)
    return file_path
