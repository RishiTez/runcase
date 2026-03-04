# Runcase

A local CLI tool for DSA practice. Define your test cases once, run them every time — no more retyping inputs.

---

## The Problem

Every time you tweak a solution, you retype the same inputs. Runcase stores your test cases in a local database per problem, runs your code against all of them at once, and shows you exactly where your output diverges from what you expected.

---

## Features

- Scaffold a new problem with a single command
- Add test cases interactively (stdin/stdout or function args + expected return)
- Run your solution against all saved test cases in one shot
- Diff expected vs actual output per test case
- Track pass/fail history across attempts
- Supports Python, C++, and Java
- TLE and SLE support for sufficiently large testcases
- Agents like Claude Code should be able to add testecases on command
- Beautiful Terminal UI

---

## Installation

```bash
git clone https://github.com/RishiTez/runcase.git
cd runcase
pip install -e .
```

---

## Usage

### Scaffold a new problem

```bash
runcase new two-sum
```

Creates an entry in the local database for the problem `two-sum` and scaffolds a solution file in your working directory.

### Add a test case

```bash
runcase add two-sum
```

Prompts you interactively to enter input and expected output. Both stdin/stdout and function-call styles are supported. Test cases are persisted to the local store.

### Run your solution

```bash
runcase run two-sum solution.py
```

Executes your solution against all saved test cases for `two-sum`. Outputs a per-case pass/fail result with a diff on failure.

### View run history

```bash
runcase history two-sum
```

Lists all past runs for a problem with timestamps and pass/fail counts.

---

## Test Case Modes

**stdin/stdout** — input is fed via stdin, output is compared against expected stdout.

**function call** — you define argument values and an expected return value. Runcase wraps your function and compares the return.

---

## Storage

All problems and test cases are stored in a local SQLite database at `~/.runcase/db.sqlite`. Nothing leaves your machine.

---

## Project Structure

```
runcase/
├── runcase/
│   ├── __init__.py
│   ├── cli.py          # Entry point, Click command definitions
│   ├── runner.py       # Code execution and diff logic
│   ├── store.py        # SQLite database interface
│   └── scaffold.py     # Problem and solution file scaffolding
├── tests/
├── pyproject.toml
└── README.md
```

---

## Supported Languages

| Language | Extension | Execution         |
|----------|-----------|-------------------|
| Python   | `.py`     | `python3`         |
| C++      | `.cpp`    | `g++` then binary |
| Java     | `.java`   | `javac` + `java`  |

---

## Roadmap

- [ ] `runcase edit` — modify or delete existing test cases
- [ ] `runcase export` — export problem + test cases to JSON
- [ ] Time and memory tracking per run
- [ ] Shell completions (bash/zsh/fish)

---

## Contributing

This tool was built for personal DSA practice but is open to contributions. Open an issue or a PR — feedback on the CLI UX especially welcome.

---

## License

MIT
