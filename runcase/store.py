import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
_VALID_MODES = {"stdio", "function"}
_VALID_STATUSES = {"pass", "fail", "error", "tle", "sle"}
_VALID_CATEGORIES = {"general", "edge", "stress"}


def _db_path() -> str:
    path = os.environ.get("RUNCASE_DB_PATH")
    if path:
        return path
    base = os.path.expanduser("~/.runcase")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "db.sqlite")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_name(name: str) -> None:
    if not _NAME_RE.match(name):
        raise ValueError(
            f"Invalid problem name {name!r}. "
            "Must match ^[a-z0-9][a-z0-9-]*[a-z0-9]$"
        )


@dataclass
class Problem:
    id: int
    name: str
    mode: str
    func_name: Optional[str]
    created_at: str
    params: Optional[List[str]] = None
    arg_types: Optional[List[str]] = None
    return_type: Optional[str] = None


@dataclass
class TestCase:
    id: int
    problem_id: int
    label: Optional[str]
    input: str
    expected: str
    created_at: str
    category: str = "general"
    hidden: bool = False


@dataclass
class RunResult:
    id: int
    run_id: int
    test_case_id: int
    status: str
    actual: Optional[str]
    stderr: Optional[str]
    elapsed_ms: Optional[int]
    memory_kb: Optional[int]


@dataclass
class Run:
    id: int
    problem_id: int
    file_path: str
    language: str
    total: int
    passed: int
    failed: int
    errored: int
    run_at: str


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns that may be missing in pre-existing databases."""
    migrations = [
        "ALTER TABLE test_cases ADD COLUMN category TEXT NOT NULL DEFAULT 'general'",
        "ALTER TABLE test_cases ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE problems ADD COLUMN arg_types TEXT",
        "ALTER TABLE problems ADD COLUMN return_type TEXT",
        "ALTER TABLE problems ADD COLUMN params TEXT",
    ]
    for stmt in migrations:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # column already exists


def init_db() -> None:
    """Idempotent schema creation."""
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS problems (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL UNIQUE,
                mode       TEXT    NOT NULL CHECK(mode IN ('stdio', 'function')),
                func_name  TEXT,
                created_at TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS test_cases (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
                label      TEXT,
                input      TEXT    NOT NULL,
                expected   TEXT    NOT NULL,
                created_at TEXT    NOT NULL,
                category   TEXT    NOT NULL DEFAULT 'general',
                hidden     INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS runs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
                file_path  TEXT    NOT NULL,
                language   TEXT    NOT NULL,
                total      INTEGER NOT NULL,
                passed     INTEGER NOT NULL,
                failed     INTEGER NOT NULL,
                errored    INTEGER NOT NULL,
                run_at     TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS run_results (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id       INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
                status       TEXT    NOT NULL CHECK(status IN ('pass', 'fail', 'error', 'tle', 'sle')),
                actual       TEXT,
                stderr       TEXT,
                elapsed_ms   INTEGER,
                memory_kb    INTEGER
            );
        """)
        _migrate(conn)


def create_problem(
    name: str,
    mode: str,
    func_name: Optional[str] = None,
    arg_types: Optional[List[str]] = None,
    return_type: Optional[str] = None,
    params: Optional[List[str]] = None,
) -> Problem:
    """Insert a new problem. Raises ValueError on invalid name or mode."""
    _validate_name(name)
    if mode not in _VALID_MODES:
        raise ValueError(f"Invalid mode {mode!r}. Must be one of {_VALID_MODES}")
    if mode == "function" and not func_name:
        raise ValueError("func_name is required when mode is 'function'")
    now = _now()
    params_json = json.dumps(params) if params is not None else None
    arg_types_json = json.dumps(arg_types) if arg_types is not None else None
    with _connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO problems (name, mode, func_name, params, arg_types, return_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, mode, func_name, params_json, arg_types_json, return_type, now),
            )
            return Problem(
                id=cur.lastrowid, name=name, mode=mode, func_name=func_name,
                created_at=now, params=params, arg_types=arg_types, return_type=return_type,
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"Problem {name!r} already exists")


def _row_to_problem(row: sqlite3.Row) -> Problem:
    params = json.loads(row["params"]) if row["params"] else None
    arg_types = json.loads(row["arg_types"]) if row["arg_types"] else None
    return Problem(
        id=row["id"], name=row["name"], mode=row["mode"], func_name=row["func_name"],
        created_at=row["created_at"], params=params, arg_types=arg_types, return_type=row["return_type"],
    )


def get_problem(name: str) -> Optional[Problem]:
    """Fetch a problem by name. Returns None if not found."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM problems WHERE name = ?", (name,)).fetchone()
    if row is None:
        return None
    return _row_to_problem(row)


def list_problems() -> List[Problem]:
    """Return all problems ordered by creation time."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM problems ORDER BY created_at").fetchall()
    return [_row_to_problem(r) for r in rows]


def delete_problem(name: str) -> None:
    """Delete a problem and all its associated data. Raises ValueError if not found."""
    with _connect() as conn:
        cur = conn.execute("DELETE FROM problems WHERE name = ?", (name,))
        if cur.rowcount == 0:
            raise ValueError(f"Problem {name!r} does not exist")


def add_test_case(
    problem_name: str,
    input: str,
    expected: str,
    label: Optional[str] = None,
    category: str = "general",
    hidden: bool = False,
) -> TestCase:
    """Programmatic insertion of a test case. Agent-friendly — no interactive prompts."""
    if category not in _VALID_CATEGORIES:
        raise ValueError(f"Invalid category {category!r}. Must be one of {_VALID_CATEGORIES}")
    problem = get_problem(problem_name)
    if problem is None:
        raise ValueError(f"Problem {problem_name!r} does not exist")
    now = _now()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO test_cases (problem_id, label, input, expected, created_at, category, hidden) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (problem.id, label, input, expected, now, category, int(hidden)),
        )
        return TestCase(
            id=cur.lastrowid,
            problem_id=problem.id,
            label=label,
            input=input,
            expected=expected,
            created_at=now,
            category=category,
            hidden=hidden,
        )


def get_test_cases(problem_name: str) -> List[TestCase]:
    """Return all test cases for a problem."""
    problem = get_problem(problem_name)
    if problem is None:
        raise ValueError(f"Problem {problem_name!r} does not exist")
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM test_cases WHERE problem_id = ? ORDER BY created_at",
            (problem.id,),
        ).fetchall()
    return [
        TestCase(
            id=r["id"], problem_id=r["problem_id"], label=r["label"],
            input=r["input"], expected=r["expected"], created_at=r["created_at"],
            category=r["category"], hidden=bool(r["hidden"]),
        )
        for r in rows
    ]


def delete_test_case(id: int) -> None:
    """Remove a test case by id. Raises ValueError if not found."""
    with _connect() as conn:
        cur = conn.execute("DELETE FROM test_cases WHERE id = ?", (id,))
        if cur.rowcount == 0:
            raise ValueError(f"Test case {id} does not exist")


@dataclass
class CaseResult:
    """Input to create_run; represents per-case execution output."""
    test_case_id: int
    status: str
    actual: Optional[str] = None
    stderr: Optional[str] = None
    elapsed_ms: Optional[int] = None
    memory_kb: Optional[int] = None


def create_run(
    problem_name: str,
    file_path: str,
    language: str,
    results: List[CaseResult],
) -> Run:
    """Record a run and all its per-case results in a single transaction."""
    for r in results:
        if r.status not in _VALID_STATUSES:
            raise ValueError(f"Invalid status {r.status!r}")
    problem = get_problem(problem_name)
    if problem is None:
        raise ValueError(f"Problem {problem_name!r} does not exist")

    total = len(results)
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    errored = sum(1 for r in results if r.status in {"error", "tle", "sle"})
    now = _now()

    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO runs (problem_id, file_path, language, total, passed, failed, errored, run_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (problem.id, file_path, language, total, passed, failed, errored, now),
        )
        run_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO run_results (run_id, test_case_id, status, actual, stderr, elapsed_ms, memory_kb) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (run_id, r.test_case_id, r.status, r.actual, r.stderr, r.elapsed_ms, r.memory_kb)
                for r in results
            ],
        )
        return Run(
            id=run_id,
            problem_id=problem.id,
            file_path=file_path,
            language=language,
            total=total,
            passed=passed,
            failed=failed,
            errored=errored,
            run_at=now,
        )


def get_runs(problem_name: str) -> List[Run]:
    """Return run history for a problem, most recent first."""
    problem = get_problem(problem_name)
    if problem is None:
        raise ValueError(f"Problem {problem_name!r} does not exist")
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM runs WHERE problem_id = ? ORDER BY run_at DESC",
            (problem.id,),
        ).fetchall()
    return [
        Run(id=r["id"], problem_id=r["problem_id"], file_path=r["file_path"], language=r["language"],
            total=r["total"], passed=r["passed"], failed=r["failed"], errored=r["errored"], run_at=r["run_at"])
        for r in rows
    ]


def get_run_results(run_id: int) -> List[RunResult]:
    """Return per-case results for a run."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM run_results WHERE run_id = ?", (run_id,)
        ).fetchall()
    return [
        RunResult(
            id=r["id"], run_id=r["run_id"], test_case_id=r["test_case_id"],
            status=r["status"], actual=r["actual"], stderr=r["stderr"],
            elapsed_ms=r["elapsed_ms"], memory_kb=r["memory_kb"],
        )
        for r in rows
    ]
