import os
import tempfile
import pytest
from runcase.store import (
    init_db,
    create_problem,
    get_problem,
    list_problems,
    add_test_case,
    get_test_cases,
    delete_test_case,
    create_run,
    get_runs,
    get_run_results,
    CaseResult,
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test.sqlite")
    monkeypatch.setenv("RUNCASE_DB_PATH", db_file)
    init_db()
    yield db_file


# ── Problems ────────────────────────────────────────────────────────────────

class TestCreateProblem:
    def test_creates_stdio_problem(self):
        p = create_problem("two-sum", "stdio")
        assert p.id is not None
        assert p.name == "two-sum"
        assert p.mode == "stdio"
        assert p.func_name is None
        assert p.created_at

    def test_creates_function_problem(self):
        p = create_problem("two-sum", "function", func_name="twoSum")
        assert p.func_name == "twoSum"

    def test_duplicate_name_raises(self):
        create_problem("two-sum", "stdio")
        with pytest.raises(ValueError, match="already exists"):
            create_problem("two-sum", "stdio")

    def test_invalid_name_raises(self):
        for bad in ["TwoSum", "two_sum", "-two-sum", "two-sum-", "t"]:
            with pytest.raises(ValueError, match="Invalid problem name"):
                create_problem(bad, "stdio")

    def test_valid_single_char_boundary(self):
        # Single char is invalid per regex (needs at least two chars: [a-z0-9][a-z0-9-]*[a-z0-9])
        with pytest.raises(ValueError):
            create_problem("a", "stdio")

    def test_valid_two_char_name(self):
        p = create_problem("ab", "stdio")
        assert p.name == "ab"

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid mode"):
            create_problem("two-sum", "invalid")

    def test_function_mode_without_func_name_raises(self):
        with pytest.raises(ValueError, match="func_name is required"):
            create_problem("two-sum", "function")


class TestGetProblem:
    def test_returns_none_for_missing(self):
        assert get_problem("nonexistent") is None

    def test_returns_problem(self):
        create_problem("two-sum", "stdio")
        p = get_problem("two-sum")
        assert p is not None
        assert p.name == "two-sum"


class TestListProblems:
    def test_empty(self):
        assert list_problems() == []

    def test_returns_all(self):
        create_problem("ab", "stdio")
        create_problem("cd", "stdio")
        names = [p.name for p in list_problems()]
        assert "ab" in names
        assert "cd" in names


# ── Test Cases ───────────────────────────────────────────────────────────────

class TestAddTestCase:
    def test_adds_test_case(self):
        create_problem("two-sum", "stdio")
        tc = add_test_case("two-sum", "1 2\n", "3\n")
        assert tc.id is not None
        assert tc.input == "1 2\n"
        assert tc.expected == "3\n"
        assert tc.label is None

    def test_adds_with_label(self):
        create_problem("two-sum", "stdio")
        tc = add_test_case("two-sum", "1 2\n", "3\n", label="basic")
        assert tc.label == "basic"

    def test_missing_problem_raises(self):
        with pytest.raises(ValueError, match="does not exist"):
            add_test_case("nonexistent", "in", "out")

    def test_default_category_and_hidden(self):
        create_problem("two-sum", "stdio")
        tc = add_test_case("two-sum", "in", "out")
        assert tc.category == "general"
        assert tc.hidden is False

    def test_category_edge(self):
        create_problem("two-sum", "stdio")
        tc = add_test_case("two-sum", "in", "out", category="edge")
        assert tc.category == "edge"

    def test_category_stress(self):
        create_problem("two-sum", "stdio")
        tc = add_test_case("two-sum", "in", "out", category="stress")
        assert tc.category == "stress"

    def test_hidden_true(self):
        create_problem("two-sum", "stdio")
        tc = add_test_case("two-sum", "in", "out", hidden=True)
        assert tc.hidden is True

    def test_invalid_category_raises(self):
        create_problem("two-sum", "stdio")
        with pytest.raises(ValueError, match="Invalid category"):
            add_test_case("two-sum", "in", "out", category="invalid")


class TestGetTestCases:
    def test_empty(self):
        create_problem("two-sum", "stdio")
        assert get_test_cases("two-sum") == []

    def test_returns_cases(self):
        create_problem("two-sum", "stdio")
        add_test_case("two-sum", "1 2\n", "3\n", label="a")
        add_test_case("two-sum", "3 4\n", "7\n", label="b")
        cases = get_test_cases("two-sum")
        assert len(cases) == 2
        labels = [c.label for c in cases]
        assert "a" in labels
        assert "b" in labels

    def test_returns_category_and_hidden(self):
        create_problem("two-sum", "stdio")
        add_test_case("two-sum", "in", "out", category="stress", hidden=True)
        cases = get_test_cases("two-sum")
        assert cases[0].category == "stress"
        assert cases[0].hidden is True

    def test_missing_problem_raises(self):
        with pytest.raises(ValueError):
            get_test_cases("nonexistent")


class TestDeleteTestCase:
    def test_deletes(self):
        create_problem("two-sum", "stdio")
        tc = add_test_case("two-sum", "in", "out")
        delete_test_case(tc.id)
        assert get_test_cases("two-sum") == []

    def test_missing_raises(self):
        with pytest.raises(ValueError, match="does not exist"):
            delete_test_case(9999)


# ── Runs ─────────────────────────────────────────────────────────────────────

class TestCreateRun:
    def _setup(self):
        create_problem("two-sum", "stdio")
        tc1 = add_test_case("two-sum", "1 2\n", "3\n", label="a")
        tc2 = add_test_case("two-sum", "3 4\n", "7\n", label="b")
        return tc1, tc2

    def test_creates_run_and_results(self):
        tc1, tc2 = self._setup()
        results = [
            CaseResult(test_case_id=tc1.id, status="pass", actual="3\n", elapsed_ms=10),
            CaseResult(test_case_id=tc2.id, status="fail", actual="8\n", elapsed_ms=12),
        ]
        run = create_run("two-sum", "two-sum.py", "python", results)
        assert run.id is not None
        assert run.total == 2
        assert run.passed == 1
        assert run.failed == 1
        assert run.errored == 0

    def test_run_results_stored(self):
        tc1, tc2 = self._setup()
        results = [
            CaseResult(test_case_id=tc1.id, status="pass", actual="3\n"),
            CaseResult(test_case_id=tc2.id, status="tle"),
        ]
        run = create_run("two-sum", "two-sum.py", "python", results)
        rr = get_run_results(run.id)
        assert len(rr) == 2
        statuses = {r.status for r in rr}
        assert statuses == {"pass", "tle"}

    def test_errored_count_includes_tle_sle_error(self):
        tc1, tc2 = self._setup()
        results = [
            CaseResult(test_case_id=tc1.id, status="tle"),
            CaseResult(test_case_id=tc2.id, status="sle"),
        ]
        run = create_run("two-sum", "two-sum.py", "python", results)
        assert run.errored == 2

    def test_invalid_status_raises(self):
        tc1, _ = self._setup()
        with pytest.raises(ValueError, match="Invalid status"):
            create_run("two-sum", "two-sum.py", "python", [
                CaseResult(test_case_id=tc1.id, status="unknown")
            ])

    def test_missing_problem_raises(self):
        with pytest.raises(ValueError, match="does not exist"):
            create_run("nonexistent", "f.py", "python", [])


class TestGetRuns:
    def test_empty(self):
        create_problem("two-sum", "stdio")
        assert get_runs("two-sum") == []

    def test_most_recent_first(self):
        create_problem("two-sum", "stdio")
        tc = add_test_case("two-sum", "in", "out")
        r1 = create_run("two-sum", "f.py", "python", [CaseResult(tc.id, "pass")])
        r2 = create_run("two-sum", "f.py", "python", [CaseResult(tc.id, "fail")])
        runs = get_runs("two-sum")
        assert runs[0].id == r2.id
        assert runs[1].id == r1.id

    def test_missing_problem_raises(self):
        with pytest.raises(ValueError):
            get_runs("nonexistent")


class TestGetRunResults:
    def test_returns_empty_for_unknown_run(self):
        assert get_run_results(9999) == []

    def test_returns_results(self):
        create_problem("two-sum", "stdio")
        tc = add_test_case("two-sum", "in", "out")
        run = create_run("two-sum", "f.py", "python", [
            CaseResult(tc.id, "pass", actual="out", elapsed_ms=5, memory_kb=100)
        ])
        rr = get_run_results(run.id)
        assert len(rr) == 1
        assert rr[0].status == "pass"
        assert rr[0].actual == "out"
        assert rr[0].elapsed_ms == 5
        assert rr[0].memory_kb == 100


# ── init_db idempotency ───────────────────────────────────────────────────────

def test_init_db_is_idempotent():
    init_db()
    init_db()
    create_problem("two-sum", "stdio")
    assert get_problem("two-sum") is not None
