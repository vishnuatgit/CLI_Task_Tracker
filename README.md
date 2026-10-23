# CLI Task Tracker

A small, dependable to-do list for your terminal, written in plain Python.

[![CI](https://github.com/vishnuatgit/CLI_Task_Tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/vishnuatgit/CLI_Task_Tracker/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## What and why

`tasks` keeps a list of tasks in one JSON file. You add, list, finish, edit and delete
tasks with short commands, and you can get the same data as JSON for scripts.

It began as a beginner's interactive script and has been rebuilt as a proper package:
it installs a real command, has no runtime dependencies, validates its input, never
half-writes its data file, and is tested on Linux and Windows.

## Features

- Subcommands: `add`, `list`, `done`, `undo`, `edit`, `delete`, `clear-done`
- Priorities (`low`, `medium`, `high`) and optional due dates (`YYYY-MM-DD`, validated)
- `list` filters (`--all`, `--done`, `--priority`, `--due-before`) and sorting (`--sort`, `--reverse`)
- A readable table; colour only on a terminal, and none when `NO_COLOR` is set
- `--json` output on every command for scripting
- Clear error messages and consistent exit codes
- Atomic saves, a versioned file format, and automatic upgrade from the original format
- Standard library only at runtime

## Install

With [pipx](https://pipx.pypa.io/) (recommended for command-line tools):

```bash
pipx install git+https://github.com/vishnuatgit/CLI_Task_Tracker
```

Or from a clone, into any Python 3.10+ environment:

```bash
git clone https://github.com/vishnuatgit/CLI_Task_Tracker
cd CLI_Task_Tracker
pip install .
```

Both give you a `tasks` command. `python -m task_tracker` also works.

## Usage

A real session (with `TASKS_FILE` pointing at a scratch file, on 23 October 2026):

```text
$ tasks add Write the quarterly report --priority high --due 2026-10-30
Added task 1: Write the quarterly report [high] (due 2026-10-30)
$ tasks add Renew passport -p medium -d 2026-10-20
Added task 2: Renew passport [medium] (due 2026-10-20)
$ tasks add Water the plants -p low
Added task 3: Water the plants [low]
$ tasks list
ID  DONE  PRIORITY  DUE         TITLE
 1  [ ]   high      2026-10-30  Write the quarterly report
 2  [ ]   medium    2026-10-20  Renew passport
 3  [ ]   low       -           Water the plants
3 shown; 3 pending, 0 done in total.
$ tasks done 3
Completed task 3: Water the plants
$ tasks edit 2 --due 2026-11-15
Updated task 2: Renew passport
$ tasks list --all --sort priority
ID  DONE  PRIORITY  DUE         TITLE
 1  [ ]   high      2026-10-30  Write the quarterly report
 2  [ ]   medium    2026-11-15  Renew passport
 3  [x]   low       -           Water the plants
3 shown; 2 pending, 1 done in total.
$ tasks list --due-before 2026-11-01 --json
[
  {
    "id": 1,
    "title": "Write the quarterly report",
    "priority": "high",
    "due": "2026-10-30",
    "done": false,
    "created_at": "2026-10-23T06:08:55+00:00",
    "completed_at": null
  }
]
$ tasks add Pay rent --due 2026-02-30
usage: tasks add [-h] [--file PATH] [--json] [-p PRIORITY] [-d DUE]
                 title [title ...]
tasks add: error: argument -d/--due: invalid date '2026-02-30' (no such day)
$ tasks done 9
tasks: error: no task with id 9
$ tasks clear-done
Removed 1 done task.
```

On a colour terminal, priorities are coloured, overdue dates are red and done tasks
are dimmed. Piped output and `NO_COLOR` output are plain text, as above.

## Commands

| Command | What it does |
| --- | --- |
| `tasks add TITLE... [-p PRIORITY] [-d DATE]` | Add a task. Quotes around the title are optional. Priority defaults to `medium`. |
| `tasks list [-a \| --done] [-p PRIORITY]... [--due-before DATE] [-s KEY] [-r]` | Show pending tasks. `-a/--all` adds done tasks, `--done` shows only done tasks. `-p` can be repeated. `--due-before` keeps tasks due strictly before the date. `-s/--sort` is `id` (default), `priority`, `due` (undated last) or `title`; `-r` reverses. |
| `tasks done ID...` | Mark tasks as done. |
| `tasks undo ID...` | Mark tasks as not done. |
| `tasks edit ID [-t TITLE] [-p PRIORITY] [-d DATE \| --no-due]` | Change a task. At least one option is required. |
| `tasks delete ID...` | Delete tasks. |
| `tasks clear-done` | Delete all done tasks. |

Every command accepts `--file PATH` and `--json`, before or after the command name.
`tasks --version` prints the version and `tasks COMMAND --help` explains each command.

Commands that take several IDs check them all first: if any ID does not exist,
nothing is changed.

**Exit codes**

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | The command could not be carried out (unknown task ID, unreadable or invalid tasks file) |
| 2 | Invalid usage (unknown option, bad date or priority, empty title, `edit` with nothing to change) |

Errors go to standard error, so `--json` output on standard output stays clean.

## Configuration

| Setting | Effect |
| --- | --- |
| `--file PATH` | Use this tasks file for one command. |
| `TASKS_FILE` | Environment variable with the tasks file path. Used when `--file` is not given. |
| default | `~/.task_tracker/tasks.json` (the folder is created on first save). |
| `NO_COLOR` | Any non-empty value turns colour off (see [no-color.org](https://no-color.org/)). |

## Data format

Tasks are stored as UTF-8 JSON:

```json
{
  "version": 1,
  "next_id": 4,
  "tasks": [
    {
      "id": 1,
      "title": "Write the quarterly report",
      "priority": "high",
      "due": "2026-10-30",
      "done": false,
      "created_at": "2026-10-23T06:08:55+00:00",
      "completed_at": null
    }
  ]
}
```

- `next_id` makes sure an ID is never reused after a task is deleted, so a script
  holding an old ID cannot act on a different task by mistake.
- Timestamps are UTC, ISO 8601. `due` is a date or `null`.
- `tasks list --json` prints the same task objects as a list.

**Upgrading from the original script.** The first version saved `tasks.json` in the
current folder as `{"1": "Buy milk", "2": "Read a book"}`. Point the new command at
that file and it is read as-is; it is rewritten in the new format the next time a
command changes it. Nothing is lost: IDs and titles carry over, and each task becomes
a pending `medium` task with no due date.

```bash
tasks --file ./tasks.json list
```

## Running tests

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e . -r requirements-dev.txt
pytest                           # runs the tests with a coverage report
ruff check . && ruff format --check .
```

The suite covers validation, storage (atomic writes, migration, corrupt and malformed
files) and every command end to end through `main(argv)`. CI runs lint, the tests on
Ubuntu and Windows with Python 3.10, 3.11 and 3.12, and a job that builds the wheel,
installs it in a clean virtual environment and runs `tasks`.

## Project structure

```text
.
├── src/task_tracker/
│   ├── __init__.py      # package version
│   ├── __main__.py      # python -m task_tracker
│   ├── cli.py           # argparse subcommands, table and JSON output, exit codes
│   ├── models.py        # Task, TaskList, Priority and input validation
│   └── storage.py       # file location, loading, migration, atomic saves
├── tests/               # pytest suite
├── .github/workflows/ci.yml
├── pyproject.toml       # metadata, console script, pytest and ruff settings
├── requirements-dev.txt # pinned development tools
└── LICENSE
```

## Design notes

- **Atomic writes.** A save writes the whole file to a temporary file in the same
  folder, flushes it to disk, then swaps it into place with `os.replace`. A crash or
  a full disk leaves either the old file or the new one, never a half-written mix,
  and the temporary file is removed on failure.
- **Bad files are never overwritten.** A missing or empty file means "no tasks yet".
  A file that is not valid JSON, has an unknown structure, or comes from a newer
  schema version stops the command with exit code 1 and a message naming the file.
  The file is left untouched so you can fix or move it.
- **Versioned schema and migration.** Every file carries `version`. On load, older
  formats are upgraded in memory (`storage.migrate`); the upgraded form is written on
  the next save. Adding a version 2 means adding one step there.
- **Validation at the edge.** Dates, priorities, titles and IDs are checked while the
  arguments are parsed, so bad input is reported before any file is touched.

## Roadmap

- `tasks list --overdue` and relative due dates such as `today` and `tomorrow`
- Tags and free-text search
- Shell completion

## License

[MIT](LICENSE) © 2026 Chandana Vishnu Jayanth
