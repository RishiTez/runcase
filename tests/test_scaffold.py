import os
import pytest
from pathlib import Path

from runcase import scaffold, store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("RUNCASE_DB_PATH", str(db_file))
    store.init_db()


# ---------------------------------------------------------------------------
# Language validation
# ---------------------------------------------------------------------------

class TestLanguageValidation:
    def test_invalid_language_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported language"):
            scaffold.scaffold_problem("two-sum", "stdio", language="ruby", directory=str(tmp_path))

    def test_valid_languages_accepted(self, tmp_path):
        for i, lang in enumerate(["python", "cpp", "java"]):
            name = f"prob-{i}a"
            scaffold.scaffold_problem(name, "stdio", language=lang, directory=str(tmp_path))


# ---------------------------------------------------------------------------
# File creation
# ---------------------------------------------------------------------------

class TestFileCreation:
    def test_python_stdio_creates_py_file(self, tmp_path):
        path = scaffold.scaffold_problem("two-sum", "stdio", language="python", directory=str(tmp_path))
        assert path == tmp_path / "two-sum.py"
        assert path.exists()

    def test_cpp_stdio_creates_cpp_file(self, tmp_path):
        path = scaffold.scaffold_problem("two-sum", "stdio", language="cpp", directory=str(tmp_path))
        assert path == tmp_path / "two-sum.cpp"
        assert path.exists()

    def test_java_stdio_creates_java_file(self, tmp_path):
        path = scaffold.scaffold_problem("two-sum", "stdio", language="java", directory=str(tmp_path))
        assert path == tmp_path / "two-sum.java"
        assert path.exists()

    def test_default_language_is_python(self, tmp_path):
        path = scaffold.scaffold_problem("two-sum", "stdio", directory=str(tmp_path))
        assert path.suffix == ".py"

    def test_default_directory_is_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        path = scaffold.scaffold_problem("two-sum", "stdio")
        assert path.parent == tmp_path

    def test_file_exists_raises(self, tmp_path):
        (tmp_path / "two-sum.py").touch()
        with pytest.raises(FileExistsError, match="two-sum.py"):
            scaffold.scaffold_problem("two-sum", "stdio", language="python", directory=str(tmp_path))

    def test_file_exists_does_not_create_db_record(self, tmp_path):
        (tmp_path / "two-sum.py").touch()
        with pytest.raises(FileExistsError):
            scaffold.scaffold_problem("two-sum", "stdio", language="python", directory=str(tmp_path))
        # Problem must NOT be in the store
        assert store.get_problem("two-sum") is None


# ---------------------------------------------------------------------------
# Store integration
# ---------------------------------------------------------------------------

class TestStoreIntegration:
    def test_creates_problem_in_store(self, tmp_path):
        scaffold.scaffold_problem("two-sum", "stdio", directory=str(tmp_path))
        problem = store.get_problem("two-sum")
        assert problem is not None
        assert problem.name == "two-sum"
        assert problem.mode == "stdio"

    def test_function_mode_stores_func_name(self, tmp_path):
        scaffold.scaffold_problem("two-sum", "function", func_name="twoSum", directory=str(tmp_path))
        problem = store.get_problem("two-sum")
        assert problem.func_name == "twoSum"

    def test_duplicate_name_raises(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        scaffold.scaffold_problem("two-sum", "stdio", directory=str(dir_a))
        # Different directory so file check passes; store duplicate check fires.
        with pytest.raises(ValueError, match="already exists"):
            scaffold.scaffold_problem("two-sum", "stdio", directory=str(dir_b))

    def test_invalid_name_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid problem name"):
            scaffold.scaffold_problem("Two_Sum!", "stdio", directory=str(tmp_path))

    def test_function_mode_without_func_name_raises(self, tmp_path):
        with pytest.raises(ValueError, match="func_name"):
            scaffold.scaffold_problem("two-sum", "function", directory=str(tmp_path))


# ---------------------------------------------------------------------------
# Template content — stdio
# ---------------------------------------------------------------------------

class TestStdioTemplates:
    def test_python_stdio_reads_stdin(self, tmp_path):
        path = scaffold.scaffold_problem("two-sum", "stdio", language="python", directory=str(tmp_path))
        content = path.read_text()
        assert "stdin" in content
        assert "print" in content

    def test_cpp_stdio_has_main(self, tmp_path):
        path = scaffold.scaffold_problem("two-sum", "stdio", language="cpp", directory=str(tmp_path))
        content = path.read_text()
        assert "int main()" in content
        assert "#include" in content

    def test_java_stdio_has_main(self, tmp_path):
        path = scaffold.scaffold_problem("two-sum", "stdio", language="java", directory=str(tmp_path))
        content = path.read_text()
        assert "public static void main" in content
        assert "TwoSum" in content  # PascalCase class name


# ---------------------------------------------------------------------------
# Template content — function
# ---------------------------------------------------------------------------

class TestFunctionTemplates:
    def test_python_function_has_func_name(self, tmp_path):
        path = scaffold.scaffold_problem("two-sum", "function", func_name="twoSum", language="python", directory=str(tmp_path))
        content = path.read_text()
        assert "def twoSum" in content

    def test_python_function_no_params_uses_args(self, tmp_path):
        path = scaffold.scaffold_problem("two-sum", "function", func_name="twoSum", language="python", directory=str(tmp_path))
        assert "def twoSum(*args)" in path.read_text()

    def test_python_function_named_params(self, tmp_path):
        path = scaffold.scaffold_problem(
            "two-sum", "function", func_name="twoSum", language="python",
            directory=str(tmp_path), params=["nums", "target"],
        )
        assert "def twoSum(nums, target)" in path.read_text()

    def test_cpp_function_has_func_name(self, tmp_path):
        path = scaffold.scaffold_problem("two-sum", "function", func_name="twoSum", language="cpp", directory=str(tmp_path))
        content = path.read_text()
        assert "twoSum" in content

    def test_cpp_function_named_params(self, tmp_path):
        path = scaffold.scaffold_problem(
            "two-sum", "function", func_name="twoSum", language="cpp",
            directory=str(tmp_path), params=["nums", "target"],
        )
        content = path.read_text()
        # Without arg_types, params appear as 'auto <name>' in the signature
        assert "auto nums" in content
        assert "auto target" in content

    def test_java_function_has_func_name_and_class(self, tmp_path):
        path = scaffold.scaffold_problem("two-sum", "function", func_name="twoSum", language="java", directory=str(tmp_path))
        content = path.read_text()
        assert "twoSum" in content
        assert "TwoSum" in content  # class name

    def test_java_function_named_params(self, tmp_path):
        path = scaffold.scaffold_problem(
            "two-sum", "function", func_name="twoSum", language="java",
            directory=str(tmp_path), params=["nums", "target"],
        )
        content = path.read_text()
        # Without arg_types, params appear as 'Object <name>' in the signature
        assert "Object nums" in content
        assert "Object target" in content


# ---------------------------------------------------------------------------
# Class name derivation for Java
# ---------------------------------------------------------------------------

class TestClassNameDerivation:
    def test_single_segment(self, tmp_path):
        path = scaffold.scaffold_problem("ab", "stdio", language="java", directory=str(tmp_path))
        assert "Ab" in path.read_text()

    def test_multi_segment(self, tmp_path):
        path = scaffold.scaffold_problem("longest-common-subsequence", "stdio", language="java", directory=str(tmp_path))
        assert "LongestCommonSubsequence" in path.read_text()
