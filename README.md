# Runcase

A local CLI tool for DSA practice. Define your test cases once, run them every time.

---

## Installation

```bash
git clone https://github.com/RishiTez/runcase.git
cd runcase
pip install -e .
```

Requires Python 3. Language runners (`python3`, `g++`, `javac`/`java`) must be on PATH.

---

## Commands

```bash
runcase new <problem>                                  # Scaffold a problem entry and solution file
runcase add <problem> --input "..." --expected "..."   # Add a test case non-interactively
runcase run <problem> <file>                           # Run solution against all saved test cases
runcase history <problem>                              # View past run history
```

Problem names must match `^[a-z0-9][a-z0-9-]*[a-z0-9]$` (lowercase, hyphens, minimum 2 characters).

---

## Agent Usage (Claude Code)

Claude Code can add test cases and run solutions programmatically. No interactive prompts are needed.

### Step 1 — Scaffold the problem (first time only)

```bash
runcase new <problem>
```

When prompted:
- Mode: `stdio` (for stdin/stdout problems) or `function` (for function-call problems)
- Language: `python`, `cpp`, or `java`

If the problem already exists in the database, skip this step.

### Step 2 — Add test cases

Use the `--input` and `--expected` flags. This bypasses all interactive prompts and is safe to call from scripts or agents.

**stdio mode** — input is what goes to stdin, expected is what should appear on stdout:

```bash
runcase add two-sum --input "4\n[2,7,11,15]\n9" --expected "[0,1]"
runcase add two-sum --input "3\n[3,2,4]\n6" --expected "[1,2]"
```

**function mode** — input is a JSON array of arguments, expected is the JSON-encoded return value:

```bash
runcase add two-sum --input '[2, 7, 11, 15]' --expected '[0, 1]'
runcase add two-sum --input '[3, 2, 4]' --expected '[1, 2]'
```

An optional `--label` flag names the test case for display:

```bash
runcase add two-sum --input "..." --expected "..." --label "basic case"
```

### Step 3 — Run the solution

```bash
runcase run <problem> <file>
```

Examples:

```bash
runcase run two-sum two-sum.py
runcase run two-sum two-sum.cpp
runcase run two-sum TwoSum.java
```

Runcase detects the language from the file extension. Output shows per-case pass/fail with diffs on failure.

---

## Test Case Formats

### stdio mode

`--input` is the exact string fed to stdin. Use `\n` for newlines. `--expected` is the exact stdout the solution must produce.

Example for a problem that reads `n` then an array then a target:

```
Input:
4
2 7 11 15
9

Expected output:
0 1
```

As a CLI call:

```bash
runcase add two-sum --input $'4\n2 7 11 15\n9' --expected "0 1"
```

### function mode

`--input` is a JSON array of positional arguments passed to the function. `--expected` is the JSON-encoded return value.

For `def twoSum(nums: List[int], target: int) -> List[int]`:

```bash
runcase add two-sum --input '[[2,7,11,15], 9]' --expected '[0,1]'
```

Supported argument types: `int`, `double`, `string`, `List[int]`, `List[List[int]]`.

---

## Supported Languages

| Language | Extension | Execution         |
|----------|-----------|-------------------|
| Python   | `.py`     | `python3`         |
| C++      | `.cpp`    | `g++ -std=c++17 -O2` then binary |
| Java     | `.java`   | `javac` + `java`  |

---

## Storage

All data is stored locally at `~/.runcase/db.sqlite`. Nothing leaves your machine.

---

## Project Structure

```
runcase/
├── runcase/
│   ├── cli.py        # Click commands; entry points
│   ├── runner.py     # Code execution and output diff
│   ├── store.py      # SQLite interface
│   └── scaffold.py   # Problem and file scaffolding
├── tests/
├── pyproject.toml
└── README.md
```

---

## License

MIT
