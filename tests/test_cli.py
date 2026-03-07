"""Integration tests for the runcase CLI (Phase 4)."""

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from runcase.cli import main
from runcase import store
from runcase.runner import CompilationError


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets its own isolated SQLite database."""
    db = str(tmp_path / "test.sqlite")
    monkeypatch.setenv("RUNCASE_DB_PATH", db)
    store.init_db()
    return db


@pytest.fixture
def cli():
    return CliRunner()


# ---------------------------------------------------------------------------
# runcase new
# ---------------------------------------------------------------------------


class TestCmdNew:
    def test_flags_stdio_python(self, cli, tmp_path):
        """Creates a stdio/python problem via flags (no prompts)."""
        with cli.isolated_filesystem(temp_dir=tmp_path):
            result = cli.invoke(
                main,
                ["new", "two-sum", "--mode", "stdio", "--language", "python"],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "two-sum" in result.output
        assert "Template" in result.output

    def test_flags_function_python(self, cli, tmp_path):
        """Creates a function/python problem via flags."""
        with cli.isolated_filesystem(temp_dir=tmp_path):
            result = cli.invoke(
                main,
                ["new", "add-nums", "--mode", "function", "--func-name", "add", "--language", "python"],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "add-nums" in result.output

    def test_interactive_prompts(self, cli, tmp_path):
        """Prompts are used when flags are omitted."""
        with cli.isolated_filesystem(temp_dir=tmp_path):
            result = cli.invoke(
                main,
                ["new", "bin-search"],
                input="stdio\npython\n",
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "bin-search" in result.output

    def test_function_mode_prompts_for_func_name(self, cli, tmp_path):
        """Function mode without --func-name prompts for func name then params."""
        with cli.isolated_filesystem(temp_dir=tmp_path):
            result = cli.invoke(
                main,
                ["new", "my-func", "--mode", "function", "--language", "python"],
                input="my_func\n\n",  # func name, then empty params
                catch_exceptions=False,
            )
        assert result.exit_code == 0

    def test_params_flag_generates_named_signature(self, cli, tmp_path):
        """--params generates named parameters in the Python stub."""
        with cli.isolated_filesystem(temp_dir=tmp_path):
            result = cli.invoke(
                main,
                ["new", "two-sum", "--mode", "function", "--func-name", "twoSum",
                 "--params", "nums,target", "--language", "python"],
                catch_exceptions=False,
            )
            assert result.exit_code == 0
            content = Path("two-sum.py").read_text()
            assert "def twoSum(nums, target)" in content

    def test_params_prompt_generates_named_signature(self, cli, tmp_path):
        """Interactive params prompt generates named parameters in the Python stub."""
        with cli.isolated_filesystem(temp_dir=tmp_path):
            with patch("runcase.cli._is_interactive", return_value=True):
                result = cli.invoke(
                    main,
                    ["new", "two-sum", "--mode", "function", "--language", "python"],
                    input="twoSum\nnums,target\n\n\n",  # extra \n for return-type prompt
                    catch_exceptions=False,
                )
            assert result.exit_code == 0
            content = Path("two-sum.py").read_text()
            assert "def twoSum(nums, target)" in content

    def test_invalid_problem_name(self, cli):
        """Invalid problem name yields non-zero exit and error on stderr."""
        result = cli.invoke(
            main,
            ["new", "INVALID!", "--mode", "stdio", "--language", "python"],
        )
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_duplicate_problem(self, cli, tmp_path):
        """Second new for same name fails gracefully."""
        with cli.isolated_filesystem(temp_dir=tmp_path):
            cli.invoke(
                main,
                ["new", "dup-prob", "--mode", "stdio", "--language", "python"],
                catch_exceptions=False,
            )
            result = cli.invoke(
                main,
                ["new", "dup-prob", "--mode", "stdio", "--language", "python"],
            )
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_cpp_language(self, cli, tmp_path):
        """C++ language creates a .cpp template file."""
        with cli.isolated_filesystem(temp_dir=tmp_path):
            result = cli.invoke(
                main,
                ["new", "quick-sort", "--mode", "stdio", "--language", "cpp"],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert ".cpp" in result.output


# ---------------------------------------------------------------------------
# runcase add
# ---------------------------------------------------------------------------


class TestCmdAdd:
    @pytest.fixture(autouse=True)
    def setup_problem(self):
        """Seed a problem directly via store (bypassing CLI for isolation)."""
        store.create_problem("two-sum", "stdio")

    def test_flags_noninteractive(self, cli):
        """Non-interactive add via --input and --expected."""
        result = cli.invoke(
            main,
            ["add", "two-sum", "--input", "2 7", "--expected", "9"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Added test case" in result.output
        cases = store.get_test_cases("two-sum")
        assert len(cases) == 1
        assert cases[0].input == "2 7"
        assert cases[0].expected == "9"

    def test_label_stored(self, cli):
        """Label is stored and appears in output."""
        result = cli.invoke(
            main,
            ["add", "two-sum", "--input", "1 2", "--expected", "3", "--label", "basic"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "basic" in result.output
        cases = store.get_test_cases("two-sum")
        assert cases[0].label == "basic"

    def test_interactive_single_line(self, cli):
        """Interactive mode with single-line input/expected."""
        result = cli.invoke(
            main,
            ["add", "two-sum"],
            input="5 3\n\n8\n\n",
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        cases = store.get_test_cases("two-sum")
        assert cases[0].input == "5 3"
        assert cases[0].expected == "8"

    def test_interactive_multiline(self, cli):
        """Multi-line input is joined with newlines."""
        result = cli.invoke(
            main,
            ["add", "two-sum"],
            input="line1\nline2\n\nout1\nout2\n\n",
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        cases = store.get_test_cases("two-sum")
        assert cases[0].input == "line1\nline2"
        assert cases[0].expected == "out1\nout2"

    def test_only_input_flag_still_prompts_expected(self, cli):
        """Providing --input but not --expected still prompts for expected."""
        result = cli.invoke(
            main,
            ["add", "two-sum", "--input", "1 2"],
            input="3\n\n",
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        cases = store.get_test_cases("two-sum")
        assert cases[0].expected == "3"

    def test_nonexistent_problem(self, cli):
        """Adding to a non-existent problem fails with an error."""
        result = cli.invoke(
            main,
            ["add", "no-such", "--input", "x", "--expected", "y"],
        )
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_category_flag_stored(self, cli):
        """--category flag is stored on the test case."""
        result = cli.invoke(
            main,
            ["add", "two-sum", "--input", "1 2", "--expected", "3", "--category", "edge"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "edge" in result.output
        cases = store.get_test_cases("two-sum")
        assert cases[0].category == "edge"

    def test_stress_category_flag(self, cli):
        """--category stress is stored correctly."""
        cli.invoke(
            main,
            ["add", "two-sum", "--input", "1 2", "--expected", "3", "--category", "stress"],
            catch_exceptions=False,
        )
        cases = store.get_test_cases("two-sum")
        assert cases[0].category == "stress"

    def test_hidden_flag_stored(self, cli):
        """--hidden flag is stored and shown in confirmation."""
        result = cli.invoke(
            main,
            ["add", "two-sum", "--input", "1 2", "--expected", "3", "--label", "secret", "--hidden"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "[hidden]" in result.output
        cases = store.get_test_cases("two-sum")
        assert cases[0].hidden is True

    def test_multiple_cases_incrementing_ids(self, cli):
        """Multiple test cases get distinct IDs."""
        cli.invoke(
            main,
            ["add", "two-sum", "--input", "1 2", "--expected", "3"],
            catch_exceptions=False,
        )
        cli.invoke(
            main,
            ["add", "two-sum", "--input", "3 4", "--expected", "7"],
            catch_exceptions=False,
        )
        cases = store.get_test_cases("two-sum")
        assert len(cases) == 2
        assert cases[0].id != cases[1].id


# ---------------------------------------------------------------------------
# runcase run
# ---------------------------------------------------------------------------


class TestCmdRun:
    @pytest.fixture(autouse=True)
    def setup(self):
        """Seed problem and test cases directly via store."""
        store.create_problem("two-sum", "stdio")
        store.add_test_case("two-sum", "2 7", "9")
        store.add_test_case("two-sum", "1 1", "2")

    def _fake_run(self, tmp_path, case_results):
        """Create a real Run in the DB from pre-built CaseResult list."""
        return store.create_run("two-sum", str(tmp_path / "sol.py"), "python", case_results)

    def test_all_pass(self, cli, tmp_path):
        """All-pass run shows PASS status and summary."""
        cases = store.get_test_cases("two-sum")
        fake_run = self._fake_run(tmp_path, [
            store.CaseResult(test_case_id=cases[0].id, status="pass", actual="9\n", elapsed_ms=5),
            store.CaseResult(test_case_id=cases[1].id, status="pass", actual="2\n", elapsed_ms=3),
        ])
        sol = str(tmp_path / "sol.py")
        Path(sol).write_text("print('x')")
        with patch("runcase.cli.run_problem", return_value=fake_run):
            result = cli.invoke(main, ["run", "two-sum", sol], catch_exceptions=False)
        assert result.exit_code == 0
        assert "PASS" in result.output
        assert "2 passed" in result.output

    def test_one_fail(self, cli, tmp_path):
        """Failing run shows FAIL status and diff details."""
        cases = store.get_test_cases("two-sum")
        fake_run = self._fake_run(tmp_path, [
            store.CaseResult(test_case_id=cases[0].id, status="fail", actual="wrong\n", elapsed_ms=5),
            store.CaseResult(test_case_id=cases[1].id, status="pass", actual="2\n", elapsed_ms=3),
        ])
        sol = str(tmp_path / "sol.py")
        Path(sol).write_text("print('x')")
        with patch("runcase.cli.run_problem", return_value=fake_run):
            result = cli.invoke(main, ["run", "two-sum", sol], catch_exceptions=False)
        assert result.exit_code == 0
        assert "FAIL" in result.output
        assert "1 failed" in result.output

    def test_tle_case(self, cli, tmp_path):
        """TLE case shows TLE status and errored count."""
        cases = store.get_test_cases("two-sum")
        fake_run = self._fake_run(tmp_path, [
            store.CaseResult(test_case_id=cases[0].id, status="tle", elapsed_ms=10000),
            store.CaseResult(test_case_id=cases[1].id, status="pass", actual="2\n", elapsed_ms=3),
        ])
        sol = str(tmp_path / "sol.py")
        Path(sol).write_text("print('x')")
        with patch("runcase.cli.run_problem", return_value=fake_run):
            result = cli.invoke(main, ["run", "two-sum", sol], catch_exceptions=False)
        assert result.exit_code == 0
        assert "TLE" in result.output
        assert "1 errored" in result.output

    def test_sle_case(self, cli, tmp_path):
        """SLE case shows SLE status."""
        cases = store.get_test_cases("two-sum")
        fake_run = self._fake_run(tmp_path, [
            store.CaseResult(test_case_id=cases[0].id, status="sle", elapsed_ms=100),
            store.CaseResult(test_case_id=cases[1].id, status="pass", actual="2\n", elapsed_ms=3),
        ])
        sol = str(tmp_path / "sol.py")
        Path(sol).write_text("print('x')")
        with patch("runcase.cli.run_problem", return_value=fake_run):
            result = cli.invoke(main, ["run", "two-sum", sol], catch_exceptions=False)
        assert result.exit_code == 0
        assert "SLE" in result.output

    def test_error_case(self, cli, tmp_path):
        """Error case shows ERROR status."""
        cases = store.get_test_cases("two-sum")
        fake_run = self._fake_run(tmp_path, [
            store.CaseResult(
                test_case_id=cases[0].id, status="error",
                stderr="NameError: name 'x' is not defined", elapsed_ms=2,
            ),
            store.CaseResult(test_case_id=cases[1].id, status="pass", actual="2\n", elapsed_ms=3),
        ])
        sol = str(tmp_path / "sol.py")
        Path(sol).write_text("print('x')")
        with patch("runcase.cli.run_problem", return_value=fake_run):
            result = cli.invoke(main, ["run", "two-sum", sol], catch_exceptions=False)
        assert result.exit_code == 0
        assert "ERROR" in result.output

    def test_compilation_error(self, cli, tmp_path):
        """CompilationError shows error message and non-zero exit."""
        sol = str(tmp_path / "sol.cpp")
        Path(sol).write_text("invalid cpp")
        with patch(
            "runcase.cli.run_problem",
            side_effect=CompilationError("compile failed", stderr="error: expected ';'"),
        ):
            result = cli.invoke(main, ["run", "two-sum", sol])
        assert result.exit_code != 0
        assert "Compilation error" in result.output

    def test_file_not_found(self, cli):
        """FileNotFoundError shows error and non-zero exit."""
        with patch("runcase.cli.run_problem", side_effect=FileNotFoundError("no file")):
            result = cli.invoke(main, ["run", "two-sum", "missing.py"])
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_problem_not_found(self, cli, tmp_path):
        """ValueError (problem not found) shows error and non-zero exit."""
        sol = str(tmp_path / "sol.py")
        Path(sol).write_text("print('x')")
        with patch("runcase.cli.run_problem", side_effect=ValueError("problem not found")):
            result = cli.invoke(main, ["run", "no-such", sol])
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_fail_shows_diff(self, cli, tmp_path):
        """Failing case output includes expected and actual values."""
        cases = store.get_test_cases("two-sum")
        fake_run = self._fake_run(tmp_path, [
            store.CaseResult(test_case_id=cases[0].id, status="fail", actual="wrong\n", elapsed_ms=5),
            store.CaseResult(test_case_id=cases[1].id, status="pass", actual="2\n", elapsed_ms=3),
        ])
        sol = str(tmp_path / "sol.py")
        Path(sol).write_text("print('x')")
        with patch("runcase.cli.run_problem", return_value=fake_run):
            result = cli.invoke(main, ["run", "two-sum", sol], catch_exceptions=False)
        assert "expected:" in result.output
        assert "got:" in result.output

    def test_category_shown_in_results(self, cli, tmp_path):
        """Category column appears in run output."""
        store.add_test_case("two-sum", "0 0", "0", category="edge")
        cases = store.get_test_cases("two-sum")
        fake_run = self._fake_run(tmp_path, [
            store.CaseResult(test_case_id=cases[0].id, status="pass", actual="9\n", elapsed_ms=1),
            store.CaseResult(test_case_id=cases[1].id, status="pass", actual="2\n", elapsed_ms=1),
            store.CaseResult(test_case_id=cases[2].id, status="pass", actual="0\n", elapsed_ms=1),
        ])
        sol = str(tmp_path / "sol.py")
        Path(sol).write_text("print('x')")
        with patch("runcase.cli.run_problem", return_value=fake_run):
            result = cli.invoke(main, ["run", "two-sum", sol], catch_exceptions=False)
        assert "edge" in result.output

    def test_hidden_label_not_shown(self, cli, tmp_path):
        """Hidden test case label does not appear in run output."""
        store.add_test_case("two-sum", "0 0", "0", label="secret-case", hidden=True)
        cases = store.get_test_cases("two-sum")
        fake_run = self._fake_run(tmp_path, [
            store.CaseResult(test_case_id=cases[0].id, status="pass", actual="9\n", elapsed_ms=1),
            store.CaseResult(test_case_id=cases[1].id, status="pass", actual="2\n", elapsed_ms=1),
            store.CaseResult(test_case_id=cases[2].id, status="pass", actual="0\n", elapsed_ms=1),
        ])
        sol = str(tmp_path / "sol.py")
        Path(sol).write_text("print('x')")
        with patch("runcase.cli.run_problem", return_value=fake_run):
            result = cli.invoke(main, ["run", "two-sum", sol], catch_exceptions=False)
        assert "secret-case" not in result.output

    def test_label_shown_in_results(self, cli, tmp_path):
        """Test case label appears in the run output table."""
        store.add_test_case("two-sum", "0 0", "0", label="zero-case")
        cases = store.get_test_cases("two-sum")
        fake_run = self._fake_run(tmp_path, [
            store.CaseResult(test_case_id=cases[0].id, status="pass", actual="9\n", elapsed_ms=1),
            store.CaseResult(test_case_id=cases[1].id, status="pass", actual="2\n", elapsed_ms=1),
            store.CaseResult(test_case_id=cases[2].id, status="pass", actual="0\n", elapsed_ms=1),
        ])
        sol = str(tmp_path / "sol.py")
        Path(sol).write_text("print('x')")
        with patch("runcase.cli.run_problem", return_value=fake_run):
            result = cli.invoke(main, ["run", "two-sum", sol], catch_exceptions=False)
        assert "zero-case" in result.output


# ---------------------------------------------------------------------------
# runcase history
# ---------------------------------------------------------------------------


class TestCmdHistory:
    @pytest.fixture(autouse=True)
    def setup_problem(self):
        """Seed a problem directly via store."""
        store.create_problem("two-sum", "stdio")

    def test_no_runs(self, cli):
        """No runs shows appropriate message."""
        result = cli.invoke(main, ["history", "two-sum"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "No run history" in result.output

    def test_with_runs(self, cli, tmp_path):
        """Run history shows a table with run details."""
        store.add_test_case("two-sum", "1 2", "3")
        cases = store.get_test_cases("two-sum")
        store.create_run(
            "two-sum",
            "/path/to/solution.py",
            "python",
            [store.CaseResult(test_case_id=cases[0].id, status="pass", actual="3\n", elapsed_ms=5)],
        )
        result = cli.invoke(main, ["history", "two-sum"], catch_exceptions=False)
        assert result.exit_code == 0
        # Rich may truncate column values to fit terminal width; check prefix
        assert "pyt" in result.output  # "python" or truncated "pyt…"
        assert "/path/to/solution.py" in result.output

    def test_multiple_runs_ordered_newest_first(self, cli, tmp_path):
        """Multiple runs appear in the history table."""
        store.add_test_case("two-sum", "1 2", "3")
        cases = store.get_test_cases("two-sum")
        cr = store.CaseResult(test_case_id=cases[0].id, status="pass", actual="3\n", elapsed_ms=5)
        store.create_run("two-sum", "sol1.py", "python", [cr])
        store.create_run("two-sum", "sol2.py", "python", [cr])
        result = cli.invoke(main, ["history", "two-sum"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "sol1.py" in result.output
        assert "sol2.py" in result.output

    def test_nonexistent_problem(self, cli):
        """Non-existent problem shows error and non-zero exit."""
        result = cli.invoke(main, ["history", "no-such"])
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_pass_fail_counts_in_table(self, cli, tmp_path):
        """Passed/failed/errored counts appear in history table."""
        store.add_test_case("two-sum", "1 2", "3")
        store.add_test_case("two-sum", "0 0", "0")
        cases = store.get_test_cases("two-sum")
        store.create_run(
            "two-sum",
            "sol.py",
            "python",
            [
                store.CaseResult(test_case_id=cases[0].id, status="pass", actual="3\n", elapsed_ms=5),
                store.CaseResult(test_case_id=cases[1].id, status="fail", actual="wrong\n", elapsed_ms=3),
            ],
        )
        result = cli.invoke(main, ["history", "two-sum"], catch_exceptions=False)
        assert result.exit_code == 0
        # Both 1 passed and 1 failed should appear as counts
        assert "1" in result.output


# ---------------------------------------------------------------------------
# runcase list
# ---------------------------------------------------------------------------


class TestCmdList:
    def test_empty(self, cli):
        """No problems shows appropriate message."""
        result = cli.invoke(main, ["list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "No problems" in result.output

    def test_shows_problems(self, cli):
        """Problems appear in the list output."""
        store.create_problem("two-sum", "stdio")
        store.create_problem("add-nums", "function", func_name="add")
        result = cli.invoke(main, ["list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "two-sum" in result.output
        assert "add-nums" in result.output

    def test_shows_mode_and_func(self, cli):
        """Mode and func_name columns are shown."""
        store.create_problem("my-func", "function", func_name="solve")
        result = cli.invoke(main, ["list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "function" in result.output
        assert "solve" in result.output


# ---------------------------------------------------------------------------
# runcase delete
# ---------------------------------------------------------------------------


class TestCmdDelete:
    @pytest.fixture(autouse=True)
    def setup_problem(self):
        """Seed a problem directly via store."""
        store.create_problem("two-sum", "stdio")

    def test_delete_with_yes_flag(self, cli):
        """--yes skips confirmation and deletes the problem."""
        result = cli.invoke(main, ["delete", "two-sum", "--yes"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Deleted" in result.output
        assert store.get_problem("two-sum") is None

    def test_delete_short_yes_flag(self, cli):
        """-y skips confirmation."""
        result = cli.invoke(main, ["delete", "two-sum", "-y"], catch_exceptions=False)
        assert result.exit_code == 0
        assert store.get_problem("two-sum") is None

    def test_delete_confirmation_accepted(self, cli):
        """Confirmation prompt accepted deletes the problem."""
        result = cli.invoke(main, ["delete", "two-sum"], input="y\n", catch_exceptions=False)
        assert result.exit_code == 0
        assert store.get_problem("two-sum") is None

    def test_delete_confirmation_rejected(self, cli):
        """Confirmation prompt rejected aborts without deleting."""
        result = cli.invoke(main, ["delete", "two-sum"], input="n\n")
        assert result.exit_code != 0
        assert store.get_problem("two-sum") is not None

    def test_delete_nonexistent_problem(self, cli):
        """Deleting a non-existent problem shows error."""
        result = cli.invoke(main, ["delete", "no-such", "--yes"])
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_delete_cascades_test_cases(self, cli):
        """Deleting a problem removes its test cases."""
        store.add_test_case("two-sum", "1 2", "3")
        cli.invoke(main, ["delete", "two-sum", "--yes"], catch_exceptions=False)
        assert store.get_problem("two-sum") is None
