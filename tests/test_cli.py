import io
import json
from datetime import date

import pytest

from task_tracker import __version__
from task_tracker.cli import main, render_table, use_color
from task_tracker.models import Priority, Task


@pytest.fixture
def run(tmp_path, capsys):
    path = tmp_path / "tasks.json"

    def _run(*argv):
        code = main([*argv, "--file", str(path)])
        out, err = capsys.readouterr()
        return code, out, err

    _run.path = path
    return _run


def json_out(run, *argv):
    code, out, _ = run(*argv, "--json")
    assert code == 0
    return json.loads(out)


def test_add_and_list(run):
    code, out, _ = run("add", "Buy", "milk", "-p", "high", "-d", "2026-11-01")
    assert code == 0
    assert out == "Added task 1: Buy milk [high] (due 2026-11-01)\n"
    code, out, _ = run("list")
    assert code == 0
    assert "Buy milk" in out
    assert "1 shown; 1 pending, 0 done in total." in out


def test_add_json_returns_created_task(run):
    task = json_out(run, "add", "Write report")
    assert task["id"] == 1
    assert task["priority"] == "medium"
    assert task["due"] is None
    assert task["created_at"]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["add", "x", "-d", "2026-13-01"], "expected YYYY-MM-DD"),
        (["add", "x", "-p", "urgent"], "invalid priority"),
        (["add", "  "], "cannot be empty"),
        (["done", "abc"], "invalid task id"),
    ],
)
def test_invalid_input_exits_with_usage_error(run, argv, message):
    with pytest.raises(SystemExit) as exc:
        run(*argv)
    assert exc.value.code == 2
    assert not run.path.exists()


def test_invalid_input_message_goes_to_stderr(tmp_path, capsys):
    with pytest.raises(SystemExit):
        main(["add", "x", "--due", "soon", "--file", str(tmp_path / "t.json")])
    assert "invalid date 'soon' (expected YYYY-MM-DD)" in capsys.readouterr().err


def test_list_filters(run):
    run("add", "a", "-p", "low", "-d", "2026-10-01")
    run("add", "b", "-p", "high", "-d", "2026-12-01")
    run("add", "c", "-p", "medium")
    run("done", "3")

    def ids(*argv):
        return [t["id"] for t in json_out(run, "list", *argv)]

    assert ids() == [1, 2]
    assert ids("--all") == [1, 2, 3]
    assert ids("--done") == [3]
    assert ids("--all", "-p", "high", "-p", "medium") == [2, 3]
    assert ids("--due-before", "2026-11-01") == [1]


def test_list_sorting(run):
    run("add", "Charlie", "-p", "low", "-d", "2026-12-01")
    run("add", "alpha", "-p", "high")
    run("add", "Bravo", "-p", "medium", "-d", "2026-11-01")

    def ids(*argv):
        return [t["id"] for t in json_out(run, "list", *argv)]

    assert ids("--sort", "priority") == [2, 3, 1]
    assert ids("--sort", "due") == [3, 1, 2]
    assert ids("--sort", "title") == [2, 3, 1]
    assert ids("--sort", "title", "--reverse") == [1, 3, 2]


def test_list_empty(run):
    code, out, _ = run("list")
    assert code == 0
    assert out.startswith("No tasks to show.")


def test_done_and_undo(run):
    run("add", "a")
    run("add", "b")
    code, out, _ = run("done", "1", "2")
    assert code == 0
    assert out == "Completed task 1: a\nCompleted task 2: b\n"
    tasks = json_out(run, "list", "--all")
    assert all(t["done"] and t["completed_at"] for t in tasks)
    code, out, _ = run("undo", "2")
    assert out == "Reopened task 2: b\n"
    assert [t["id"] for t in json_out(run, "list")] == [2]


def test_unknown_id_exits_1_and_changes_nothing(run):
    run("add", "a")
    before = run.path.read_text(encoding="utf-8")
    code, out, err = run("done", "1", "42")
    assert code == 1
    assert out == ""
    assert err == "tasks: error: no task with id 42\n"
    assert run.path.read_text(encoding="utf-8") == before


def test_edit(run):
    run("add", "draft", "-d", "2026-11-01")
    code, out, _ = run("edit", "1", "--title", "final", "-p", "high")
    assert code == 0
    assert out == "Updated task 1: final\n"
    task = json_out(run, "edit", "1", "--no-due")
    assert (task["title"], task["priority"], task["due"]) == ("final", "high", None)
    task = json_out(run, "edit", "1", "--due", "2026-12-24")
    assert task["due"] == "2026-12-24"


def test_edit_without_changes_is_a_usage_error(run):
    run("add", "a")
    code, _, err = run("edit", "1")
    assert code == 2
    assert "nothing to change" in err


def test_delete(run):
    run("add", "a")
    run("add", "b")
    code, out, _ = run("delete", "1")
    assert code == 0
    assert out == "Deleted task 1: a\n"
    assert [t["id"] for t in json_out(run, "list")] == [2]


def test_clear_done(run):
    run("add", "a")
    run("add", "b")
    run("done", "2")
    code, out, _ = run("clear-done")
    assert (code, out) == (0, "Removed 1 done task.\n")
    assert [t["id"] for t in json_out(run, "list", "--all")] == [1]
    assert json_out(run, "clear-done") == []


def test_tasks_file_env_var(tmp_path, monkeypatch, capsys):
    path = tmp_path / "from-env.json"
    monkeypatch.setenv("TASKS_FILE", str(path))
    assert main(["add", "via env"]) == 0
    assert path.exists()


def test_global_options_before_command(tmp_path, capsys):
    path = tmp_path / "t.json"
    assert main(["--file", str(path), "add", "x"]) == 0
    capsys.readouterr()
    assert main(["--file", str(path), "--json", "list"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["title"] == "x"


def test_corrupt_file_exits_1_with_clear_message(run):
    run.path.write_text("{not json", encoding="utf-8")
    code, _, err = run("list")
    assert code == 1
    assert "is not valid JSON" in err


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"tasks {__version__}"


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


@pytest.mark.parametrize(
    ("stream", "env", "expected"),
    [
        (FakeTTY(), {}, True),
        (FakeTTY(), {"NO_COLOR": "1"}, False),
        (FakeTTY(), {"NO_COLOR": ""}, True),
        (FakeTTY(), {"TERM": "dumb"}, False),
        (io.StringIO(), {}, False),
    ],
)
def test_use_color(stream, env, expected):
    assert use_color(stream, env) is expected


def test_render_table_colour_and_plain():
    tasks = [
        Task(id=1, title="late", priority=Priority.HIGH, due=date(2026, 1, 1)),
        Task(id=2, title="finished", done=True),
    ]
    plain = render_table(tasks, color=False, today=date(2026, 6, 1))
    assert "\033[" not in plain
    assert plain.splitlines()[0].split() == ["ID", "DONE", "PRIORITY", "DUE", "TITLE"]
    coloured = render_table(tasks, color=True, today=date(2026, 6, 1))
    assert "\033[31mhigh" in coloured
    assert "\033[31m2026-01-01" in coloured
    assert "\033[2m" in coloured
