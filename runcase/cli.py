"""CLI entry points for runcase."""

import sys
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text

from runcase import scaffold, store


def _is_interactive() -> bool:
    return sys.stdin.isatty()
from runcase.runner import run_problem, run_custom, CompilationError

def _format_signature(problem) -> Optional[str]:
    """Return a LeetCode-style signature string, or None if not applicable."""
    if problem.mode != "function" or not problem.func_name:
        return None
    params = problem.params or []
    arg_types = problem.arg_types or []
    if params and arg_types and len(params) == len(arg_types):
        param_str = ", ".join(f"{p}: {t}" for p, t in zip(params, arg_types))
    elif params:
        param_str = ", ".join(params)
    else:
        param_str = "..."
    ret = f" -> {problem.return_type}" if problem.return_type else ""
    return f"{problem.func_name}({param_str}){ret}"


_STATUS_STYLE = {
    "pass": "green",
    "fail": "red",
    "error": "magenta",
    "tle": "yellow",
    "sle": "yellow",
}


@click.group(context_settings={"max_content_width": 120})
def main() -> None:
    """\b
    Runcase - local CLI tool for DSA (Data Structures & Algorithms) practice.

    \b
    QUICK START (first time)

    \b
    Step 1 - Scaffold a new problem:
      runcase new two-sum

    \b
    You will be prompted for:
      Mode        - 'stdio' (stdin/stdout) or 'function' (return-value comparison)
      Language    - python | cpp | java
      Func name   - only when mode=function; the exact function name in your file
      Params      - only when mode=function; comma-separated parameter names (e.g. nums,target)
      Arg types   - only when mode=function; comma-separated Python/LeetCode-style types.
                    Examples: int, str, bool, float, List[int], List[str], List[List[int]], ListNode.
                    e.g. for twoSum: 'List[int],int'  for reverseList: 'ListNode'
      Return type - only when mode=function; Python/LeetCode-style return type.
                    e.g. for twoSum: 'List[int]'  for isSameTree: 'bool'
    Types are used to generate a typed solution template and display the function signature.
    This creates a solution template in your current directory (e.g. two-sum.py).

    \b
    Step 2 - Add test cases:
      runcase add two-sum

    \b
    You will be prompted for input and expected output, one line at a time.
    Press Enter on a blank line to finish each block.
    To skip prompts, pass flags directly:
      runcase add two-sum --input "1 2 3" --expected "6"
    For function mode, --input must be a JSON array of positional arguments:
      runcase add two-sum --input "[[2,7,11,15], 9]" --expected "[0, 1]"
    For linked list parameters, represent each list as a JSON array (e.g. [1,2,3] = 1->2->3).
    An empty list [] represents a null head. The expected output for a ListNode return is also
    a JSON array. Examples:
      runcase add reverse-list --input "[[1,2,3,4,5]]" --expected "[5,4,3,2,1]"
      runcase add remove-nth --input "[[1,2,3,4,5], 2]" --expected "[1,2,3,5]"
      runcase add reverse-list --input "[[]]" --expected "[]"

    \b
    Step 3 - Write your solution, then run it:
      runcase run two-sum two-sum.py

    \b
    SUBSEQUENT RUNS

    \b
    Add more test cases at any time:
      runcase add two-sum --input "..." --expected "..."
    Re-run after editing your solution:
      runcase run two-sum two-sum.py
    View full run history:
      runcase history two-sum

    \b
    NOTES

    \b
    Problem names: lowercase letters, digits, and hyphens only (e.g. two-sum, lru-cache).
    All data is stored locally at ~/.runcase/db.sqlite - nothing leaves your machine.
    Per-test timeout defaults to 10 s; override per run:
      runcase run two-sum two-sum.py --timeout 2
    """


@main.command("new")
@click.argument("problem")
@click.option(
    "--mode",
    type=click.Choice(["stdio", "function"]),
    default=None,
    help="Test case mode. Prompted if not provided.",
)
@click.option(
    "--func-name",
    "func_name",
    default=None,
    help="Function name (required when mode=function). Prompted if not provided.",
)
@click.option(
    "--params",
    "params",
    default=None,
    help="Comma-separated parameter names for function mode (e.g. 'nums,target'). Prompted interactively if not provided.",
)
@click.option(
    "--arg-types",
    "arg_types",
    default=None,
    help="Comma-separated Python/LeetCode-style types (e.g. 'List[int],int' or 'ListNode,int'). Prompted interactively if not provided.",
)
@click.option(
    "--return-type",
    "return_type",
    default=None,
    help="Python/LeetCode-style return type (e.g. 'int', 'List[int]', 'bool', 'ListNode'). Prompted interactively if not provided.",
)
@click.option(
    "--language",
    type=click.Choice(["python", "cpp", "java"]),
    default=None,
    help="Programming language. Prompted if not provided.",
)
def cmd_new(
    problem: str,
    mode: Optional[str],
    func_name: Optional[str],
    params: Optional[str],
    arg_types: Optional[str],
    return_type: Optional[str],
    language: Optional[str],
) -> None:
    """Create a problem and generate a typed solution template.

    \b
    For function mode, provide parameter names, argument types, and return type
    using Python/LeetCode-style names (int, str, bool, List[int], ListNode, ...).
    These are used to generate a typed stub and display the function signature
    when running tests.

    \b
    Examples:
      runcase new two-sum --mode function --func-name twoSum \\
        --params nums,target --arg-types List[int],int --return-type List[int]
      runcase new reverse-list --mode function --func-name reverseList \\
        --params head --arg-types ListNode --return-type ListNode
    """
    if mode is None:
        mode = click.prompt(
            "Mode",
            type=click.Choice(["stdio", "function"]),
            default="function",
        )
    if mode == "function" and func_name is None:
        func_name = click.prompt("Function name")
    if mode == "function" and params is None:
        if _is_interactive():
            raw = click.prompt("Parameter names (comma-separated, e.g. nums,target)", default="")
            params = raw if raw else None
    if mode == "function" and arg_types is None:
        if _is_interactive():
            raw = click.prompt(
                "Argument types (comma-separated, e.g. List[int],int — leave blank if not needed)",
                default="",
            )
            arg_types = raw if raw else None
    if mode == "function" and return_type is None:
        if _is_interactive():
            raw = click.prompt(
                "Return type (e.g. int, List[int], bool — leave blank if unknown)",
                default="",
            )
            return_type = raw if raw else None

    params_list = [p.strip() for p in params.split(",") if p.strip()] if params else None
    arg_types_list = [t.strip() for t in arg_types.split(",") if t.strip()] if arg_types else None

    if language is None:
        language = click.prompt(
            "Language",
            type=click.Choice(["python", "cpp", "java"]),
            default="python",
        )

    try:
        file_path = scaffold.scaffold_problem(
            problem, mode, func_name, language,
            params=params_list,
            arg_types=arg_types_list,
            return_type=return_type,
        )
    except (ValueError, FileExistsError) as exc:
        raise click.ClickException(str(exc))

    click.echo(f"Created problem '{problem}'. Template: {file_path}")
    if mode == "function":
        from runcase.store import get_problem as _get_problem
        p = _get_problem(problem)
        sig = _format_signature(p) if p else None
        if sig:
            click.echo(f"Signature: {sig}")


@main.command("list")
def cmd_list() -> None:
    """List all problems with their mode and function name."""
    problems = store.list_problems()
    if not problems:
        click.echo("No problems found. Run 'runcase new <problem>' to create one.")
        return

    console = Console()
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("Name", width=24)
    table.add_column("Mode", width=10)
    table.add_column("Func", width=16)
    table.add_column("Created", width=26)

    for p in problems:
        table.add_row(p.name, p.mode, p.func_name or "", p.created_at)

    console.print(table)


@main.command("delete")
@click.argument("problem")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt.")
def cmd_delete(problem: str, yes: bool) -> None:
    """Delete a problem and all its test cases and run history."""
    if not yes:
        click.confirm(
            f"Delete problem '{problem}' and all its data? This cannot be undone.",
            abort=True,
        )
    try:
        store.delete_problem(problem)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"Deleted problem '{problem}'.")


@main.command("add")
@click.argument("problem")
@click.option("--input", "input_data", default=None, help="Test case input. Skips interactive prompt.")
@click.option("--expected", "expected_data", default=None, help="Expected output. Skips interactive prompt.")
@click.option("--label", default=None, help="Optional label for this test case.")
@click.option(
    "--category",
    type=click.Choice(["general", "edge", "stress"]),
    default="general",
    show_default=True,
    help="Category: general, edge, or stress.",
)
@click.option("--hidden", is_flag=True, default=False, help="Hide the label when displaying run results.")
def cmd_add(
    problem: str,
    input_data: Optional[str],
    expected_data: Optional[str],
    label: Optional[str],
    category: str,
    hidden: bool,
) -> None:
    """Add a test case to a problem.

    \b
    For stdio mode, --input is raw stdin text and --expected is the expected stdout.

    \b
    For function mode, --input must be a JSON array of positional arguments
    and --expected must be the JSON-serialized return value:
      runcase add two-sum --input "[[2,7,11,15], 9]" --expected "[0, 1]"

    \b
    For ListNode parameters, represent each list as a JSON array ([1,2,3] = 1->2->3).
    An empty list [] is a null/None head:
      runcase add reverse-list --input "[[1,2,3]]" --expected "[3,2,1]"
      runcase add reverse-list --input "[[]]" --expected "[]"
    """
    if input_data is None:
        click.echo("Enter input (blank line to finish):")
        lines = []
        while True:
            line = click.prompt("", default="", prompt_suffix="", show_default=False)
            if line == "":
                break
            lines.append(line)
        input_data = "\n".join(lines)

    if expected_data is None:
        click.echo("Enter expected output (blank line to finish):")
        lines = []
        while True:
            line = click.prompt("", default="", prompt_suffix="", show_default=False)
            if line == "":
                break
            lines.append(line)
        expected_data = "\n".join(lines)

    try:
        tc = store.add_test_case(problem, input_data, expected_data, label, category, hidden)
    except ValueError as exc:
        raise click.ClickException(str(exc))

    label_part = f" [{tc.label}]" if tc.label else ""
    hidden_part = " [hidden]" if tc.hidden else ""
    click.echo(f"Added test case {tc.id}{label_part} ({tc.category}){hidden_part}")


@main.command("run")
@click.argument("problem")
@click.argument("file")
@click.option("--timeout", default=10.0, show_default=True, help="Timeout per test case in seconds.")
@click.option("--input", "input_data", default=None, help="Custom input to run once (not saved). Skips saved test cases.")
@click.option("--expected", "expected_data", default=None, help="Expected output for custom input comparison.")
def cmd_run(problem: str, file: str, timeout: float, input_data: Optional[str], expected_data: Optional[str]) -> None:
    """Run solution against all saved test cases and display results.

    \b
    For function-mode problems with typed parameters, the function signature is
    shown above the results table (e.g. twoSum(nums: List[int], target: int) -> List[int]).

    \b
    To run a one-off input without saving it as a test case, use --input:
      runcase run two-sum two-sum.py --input "[[2,7,11,15], 9]"
      runcase run two-sum two-sum.py --input "[[2,7,11,15], 9]" --expected "[0, 1]"
    """
    if input_data is not None:
        try:
            result = run_custom(problem, file, input_data, expected_data or "", timeout_sec=timeout)
        except CompilationError as exc:
            raise click.ClickException(f"Compilation error:\n{exc.stderr or str(exc)}")
        except (FileNotFoundError, ValueError) as exc:
            raise click.ClickException(str(exc))

        console = Console()
        elapsed = str(result.elapsed_ms) if result.elapsed_ms is not None else "-"

        if expected_data is not None:
            status_text = Text(result.status.upper(), style=_STATUS_STYLE.get(result.status, ""))
            console.print(f"[bold]Status:[/bold] {status_text}  [dim]{elapsed} ms[/dim]")
            if result.status == "fail":
                console.print(f"[bold]Expected:[/bold] {expected_data.strip()}")
                console.print(f"[bold]Got:[/bold]      {(result.actual or '').strip()}")
            elif result.status == "pass":
                console.print(f"[bold]Output:[/bold] {(result.actual or '').strip()}")
            elif result.status == "error":
                console.print(f"[bold red]Error:[/bold red] {(result.stderr or '').strip()}")
            elif result.status == "tle":
                console.print("[bold yellow]Time limit exceeded[/bold yellow]")
            elif result.status == "sle":
                console.print("[bold yellow]Output size limit exceeded[/bold yellow]")
        else:
            console.print(f"[bold]Output:[/bold] {(result.actual or '').strip()}  [dim]{elapsed} ms[/dim]")
            if result.status == "error":
                console.print(f"[bold red]Error:[/bold red] {(result.stderr or '').strip()}")
            elif result.status == "tle":
                console.print("[bold yellow]Time limit exceeded[/bold yellow]")
            elif result.status == "sle":
                console.print("[bold yellow]Output size limit exceeded[/bold yellow]")
        return

    try:
        run = run_problem(problem, file, timeout_sec=timeout)
    except CompilationError as exc:
        raise click.ClickException(f"Compilation error:\n{exc.stderr or str(exc)}")
    except (FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc))

    results = store.get_run_results(run.id)
    test_cases = store.get_test_cases(problem)
    tc_map = {tc.id: tc for tc in test_cases}

    # Console() is created here (not at module level) so it captures the
    # current sys.stdout — important for correct capture in CliRunner tests.
    console = Console()

    prob = store.get_problem(problem)
    sig = _format_signature(prob) if prob else None
    if sig:
        console.print(f"[bold dim]{sig}[/bold dim]")

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("#", width=4, style="dim")
    table.add_column("Category", width=10)
    table.add_column("Title", width=16)
    table.add_column("Status", width=8)
    table.add_column("ms", width=8)
    table.add_column("Details")

    for i, result in enumerate(results, 1):
        tc = tc_map.get(result.test_case_id)
        category = tc.category if tc else "general"
        is_hidden = tc is not None and tc.hidden
        title: Text | str = Text("hidden", style="dim") if is_hidden else (tc.label or "" if tc else "")
        status_text = Text(result.status.upper(), style=_STATUS_STYLE.get(result.status, ""))
        elapsed = str(result.elapsed_ms) if result.elapsed_ms is not None else "-"

        if result.status == "fail":
            if is_hidden:
                details = "Wrong Answer"
            else:
                input_str = ((tc.input if tc else "") or "").strip()
                expected = ((tc.expected if tc else "") or "").strip()
                actual = (result.actual or "").strip()
                input_preview = input_str[:80] + ("…" if len(input_str) > 80 else "")
                details = f"input: {input_preview}  expected: {expected}  got: {actual}"
        elif result.status == "pass":
            details = ""
        elif result.status == "error":
            last_line = (result.stderr or "").strip().split("\n")[-1]
            details = last_line[:120]
        elif result.status == "tle":
            details = "time limit exceeded"
        elif result.status == "sle":
            details = "output size limit exceeded"
        else:
            details = ""

        table.add_row(str(i), category, title, status_text, elapsed, details)

    console.print(table)

    parts = []
    if run.passed:
        parts.append(f"[green]{run.passed} passed[/green]")
    if run.failed:
        parts.append(f"[red]{run.failed} failed[/red]")
    if run.errored:
        parts.append(f"[yellow]{run.errored} errored[/yellow]")
    summary = "  ".join(parts) if parts else "no results"
    console.print(f"[bold]Result:[/bold] {summary}  [dim]({run.total} total)[/dim]")


@main.command("history")
@click.argument("problem")
def cmd_history(problem: str) -> None:
    """Show past run history for a problem (pass/fail/error counts per run)."""
    try:
        runs = store.get_runs(problem)
    except ValueError as exc:
        raise click.ClickException(str(exc))

    if not runs:
        click.echo(f"No run history for '{problem}'.")
        return

    console = Console()
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("ID", width=6, style="dim")
    table.add_column("File", width=32)
    table.add_column("Lang", width=8)
    table.add_column("Pass", width=6, style="green")
    table.add_column("Fail", width=6, style="red")
    table.add_column("Err", width=6, style="yellow")
    table.add_column("Total", width=6)
    table.add_column("Run At", width=22)

    for run in runs:
        table.add_row(
            str(run.id),
            run.file_path,
            run.language,
            str(run.passed),
            str(run.failed),
            str(run.errored),
            str(run.total),
            run.run_at,
        )

    console.print(table)
