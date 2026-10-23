"""Command-line interface: argparse subcommands, table and JSON output."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Any, TextIO

from task_tracker import __version__, storage
from task_tracker.models import (
    Task,
    TaskList,
    TaskNotFoundError,
    ValidationError,
    now_utc,
    parse_due,
    parse_priority,
    parse_title,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

RESET = "\033[0m"
COLORS = {"high": "\033[31m", "medium": "\033[33m", "low": "\033[36m", "dim": "\033[2m"}


class UsageError(Exception):
    """Raised for invalid command usage that argparse cannot catch."""


def use_color(stream: TextIO, env: Mapping[str, str] | None = None) -> bool:
    """Colour only on a terminal, and never when NO_COLOR is set (no-color.org)."""
    env = os.environ if env is None else env
    if env.get("NO_COLOR") or env.get("TERM") == "dumb":
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def _arg(parser: Callable[[str], Any]) -> Callable[[str], Any]:
    """Turn a model parser into an argparse type, so bad input exits with code 2."""

    def convert(value: str) -> Any:
        try:
            return parser(value)
        except ValidationError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from None

    return convert


def _task_id(value: str) -> int:
    if not value.isdigit() or int(value) < 1:
        raise argparse.ArgumentTypeError(f"invalid task id {value!r} (expected a number)")
    return int(value)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--file", default=argparse.SUPPRESS, metavar="PATH", help="tasks file to use"
    )
    common.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="print JSON output"
    )

    parser = argparse.ArgumentParser(prog="tasks", description="Track tasks from the command line.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--file",
        metavar="PATH",
        help=f"tasks file to use (default: ${storage.ENV_VAR} or ~/.task_tracker/tasks.json)",
    )
    parser.add_argument("--json", action="store_true", help="print JSON output")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    p = sub.add_parser("add", parents=[common], help="add a task")
    p.add_argument("title", nargs="+", type=_arg(parse_title), help="task title (quotes optional)")
    p.add_argument(
        "-p", "--priority", type=_arg(parse_priority), default="medium",
        help="low, medium or high (default: medium)",
    )  # fmt: skip
    p.add_argument("-d", "--due", type=_arg(parse_due), help="due date, YYYY-MM-DD")
    p.set_defaults(handler=cmd_add)

    p = sub.add_parser("list", parents=[common], help="list tasks (pending by default)")
    show = p.add_mutually_exclusive_group()
    show.add_argument("-a", "--all", action="store_true", help="include done tasks")
    show.add_argument("--done", action="store_true", help="show only done tasks")
    p.add_argument(
        "-p", "--priority", type=_arg(parse_priority), action="append",
        help="only this priority (repeatable)",
    )  # fmt: skip
    p.add_argument(
        "--due-before", type=_arg(parse_due), metavar="DATE",
        help="only tasks due before DATE (YYYY-MM-DD)",
    )  # fmt: skip
    p.add_argument(
        "-s", "--sort", choices=["id", "priority", "due", "title"], default="id",
        help="sort order (default: id)",
    )  # fmt: skip
    p.add_argument("-r", "--reverse", action="store_true", help="reverse the sort order")
    p.set_defaults(handler=cmd_list)

    for name, help_text, handler in (
        ("done", "mark tasks as done", cmd_done),
        ("undo", "mark tasks as not done", cmd_undo),
        ("delete", "delete tasks", cmd_delete),
    ):
        p = sub.add_parser(name, parents=[common], help=help_text)
        p.add_argument("ids", nargs="+", type=_task_id, metavar="ID")
        p.set_defaults(handler=handler)

    p = sub.add_parser("edit", parents=[common], help="change a task's title, priority or due date")
    p.add_argument("id", type=_task_id, metavar="ID")
    p.add_argument("-t", "--title", type=_arg(parse_title), help="new title")
    p.add_argument("-p", "--priority", type=_arg(parse_priority), help="new priority")
    due = p.add_mutually_exclusive_group()
    due.add_argument("-d", "--due", type=_arg(parse_due), help="new due date, YYYY-MM-DD")
    due.add_argument("--no-due", action="store_true", help="remove the due date")
    p.set_defaults(handler=cmd_edit)

    p = sub.add_parser("clear-done", parents=[common], help="delete all done tasks")
    p.set_defaults(handler=cmd_clear_done)
    return parser


# --- output ------------------------------------------------------------------


def _emit_json(data: Any, out: TextIO) -> None:
    out.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def render_table(tasks: Sequence[Task], color: bool, today: date | None = None) -> str:
    today = today or date.today()
    headers = ["ID", "DONE", "PRIORITY", "DUE", "TITLE"]
    rows = [
        [
            str(t.id),
            "[x]" if t.done else "[ ]",
            t.priority.value,
            t.due.isoformat() if t.due else "-",
            t.title,
        ]
        for t in tasks
    ]
    widths = [max(len(r[i]) for r in [headers, *rows]) for i in range(len(headers) - 1)]

    def line(cells: list[str]) -> str:
        parts = [cells[0].rjust(widths[0])]
        parts += [c.ljust(w) for c, w in zip(cells[1:-1], widths[1:], strict=True)]
        return "  ".join([*parts, cells[-1]]).rstrip()

    out = [line(headers)]
    for task, row in zip(tasks, rows, strict=True):
        text = line(row)
        if color:
            if task.done:
                text = f"{COLORS['dim']}{text}{RESET}"
            else:
                pri = row[2].ljust(widths[2])
                text = text.replace(pri, f"{COLORS[task.priority.value]}{pri}{RESET}", 1)
                if task.due and task.due < today:
                    due_cell = row[3]
                    text = text.replace(due_cell, f"{COLORS['high']}{due_cell}{RESET}", 1)
        out.append(text)
    return "\n".join(out)


def _describe(task: Task) -> str:
    return f"{task.id}: {task.title}"


# --- commands ----------------------------------------------------------------


def cmd_add(args: argparse.Namespace, tl: TaskList, out: TextIO) -> bool:
    task = tl.add(" ".join(args.title), priority=args.priority, due=args.due)
    if args.json:
        _emit_json(task.to_dict(), out)
    else:
        extra = f" (due {task.due.isoformat()})" if task.due else ""
        out.write(f"Added task {_describe(task)} [{task.priority.value}]{extra}\n")
    return True


def cmd_list(args: argparse.Namespace, tl: TaskList, out: TextIO) -> bool:
    tasks = tl.tasks
    if args.done:
        tasks = [t for t in tasks if t.done]
    elif not args.all:
        tasks = [t for t in tasks if not t.done]
    if args.priority:
        tasks = [t for t in tasks if t.priority in args.priority]
    if args.due_before:
        tasks = [t for t in tasks if t.due and t.due < args.due_before]

    keys: dict[str, Callable[[Task], Any]] = {
        "id": lambda t: t.id,
        "priority": lambda t: (t.priority.rank, t.id),
        "due": lambda t: (t.due is None, t.due or date.max, t.id),
        "title": lambda t: (t.title.casefold(), t.id),
    }
    tasks = sorted(tasks, key=keys[args.sort], reverse=args.reverse)

    if args.json:
        _emit_json([t.to_dict() for t in tasks], out)
        return False
    if not tasks:
        out.write("No tasks to show.\n")
    else:
        out.write(render_table(tasks, color=use_color(out)) + "\n")
    pending = sum(not t.done for t in tl.tasks)
    out.write(f"{len(tasks)} shown; {pending} pending, {len(tl.tasks) - pending} done in total.\n")
    return False


def _set_done(args: argparse.Namespace, tl: TaskList, out: TextIO, done: bool) -> bool:
    tasks = tl.get_many(args.ids)
    for task in tasks:
        if task.done != done:
            task.done = done
            task.completed_at = now_utc() if done else None
    if args.json:
        _emit_json([t.to_dict() for t in tasks], out)
    else:
        verb = "Completed" if done else "Reopened"
        for task in tasks:
            out.write(f"{verb} task {_describe(task)}\n")
    return True


def cmd_done(args: argparse.Namespace, tl: TaskList, out: TextIO) -> bool:
    return _set_done(args, tl, out, done=True)


def cmd_undo(args: argparse.Namespace, tl: TaskList, out: TextIO) -> bool:
    return _set_done(args, tl, out, done=False)


def cmd_edit(args: argparse.Namespace, tl: TaskList, out: TextIO) -> bool:
    if args.title is None and args.priority is None and args.due is None and not args.no_due:
        raise UsageError("nothing to change; give --title, --priority, --due or --no-due")
    task = tl.get(args.id)
    if args.title is not None:
        task.title = args.title
    if args.priority is not None:
        task.priority = args.priority
    if args.due is not None:
        task.due = args.due
    if args.no_due:
        task.due = None
    if args.json:
        _emit_json(task.to_dict(), out)
    else:
        out.write(f"Updated task {_describe(task)}\n")
    return True


def cmd_delete(args: argparse.Namespace, tl: TaskList, out: TextIO) -> bool:
    removed = tl.remove(args.ids)
    if args.json:
        _emit_json([t.to_dict() for t in removed], out)
    else:
        for task in removed:
            out.write(f"Deleted task {_describe(task)}\n")
    return True


def cmd_clear_done(args: argparse.Namespace, tl: TaskList, out: TextIO) -> bool:
    removed = tl.clear_done()
    if args.json:
        _emit_json([t.to_dict() for t in removed], out)
    else:
        noun = "task" if len(removed) == 1 else "tasks"
        out.write(f"Removed {len(removed)} done {noun}.\n")
    return bool(removed)


# --- entry point -------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    out, err = sys.stdout, sys.stderr
    try:
        path = storage.resolve_path(args.file)
        task_list = storage.load(path)
        changed = args.handler(args, task_list, out)
        if changed:
            storage.save(path, task_list)
    except UsageError as exc:
        err.write(f"tasks {args.command}: error: {exc}\n")
        return EXIT_USAGE
    except (TaskNotFoundError, storage.StorageError) as exc:
        message = exc.args[0] if exc.args else str(exc)
        err.write(f"tasks: error: {message}\n")
        return EXIT_ERROR
    return EXIT_OK
