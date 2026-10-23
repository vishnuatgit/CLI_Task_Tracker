from datetime import date

import pytest

from task_tracker.models import (
    Priority,
    Task,
    TaskList,
    TaskNotFoundError,
    ValidationError,
    parse_due,
    parse_priority,
    parse_title,
)


def test_parse_due_accepts_iso_date():
    assert parse_due("2026-10-25") == date(2026, 10, 25)


@pytest.mark.parametrize("value", ["25-10-2026", "20261025", "2026-W43-1", "tomorrow", ""])
def test_parse_due_rejects_other_formats(value):
    with pytest.raises(ValidationError, match="expected YYYY-MM-DD"):
        parse_due(value)


def test_parse_due_rejects_impossible_day():
    with pytest.raises(ValidationError, match="no such day"):
        parse_due("2026-02-30")


def test_parse_priority_is_case_insensitive():
    assert parse_priority(" HIGH ") is Priority.HIGH


def test_parse_priority_rejects_unknown():
    with pytest.raises(ValidationError, match="choose from low, medium, high"):
        parse_priority("urgent")


def test_parse_title_collapses_whitespace_and_rejects_blank():
    assert parse_title("  buy   milk ") == "buy milk"
    with pytest.raises(ValidationError, match="cannot be empty"):
        parse_title("   ")


def test_task_round_trips_through_dict():
    task = Task(id=3, title="Pay rent", priority=Priority.HIGH, due=date(2026, 11, 1), done=True)
    assert Task.from_dict(task.to_dict()) == task


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ("nope", "must be an object"),
        ({"id": True, "title": "x"}, "positive integer"),
        ({"id": 0, "title": "x"}, "positive integer"),
        ({"id": 1, "title": 5}, "title must be a string"),
        ({"id": 1, "title": "x", "done": "yes"}, "done must be true or false"),
        ({"id": 1, "title": "x", "due": 20261025}, "due must be a date string"),
        ({"id": 1, "title": "x", "priority": "urgent"}, "invalid priority"),
    ],
)
def test_task_from_dict_rejects_bad_data(data, message):
    with pytest.raises(ValidationError, match=message):
        Task.from_dict(data)


def test_ids_are_never_reused_after_delete():
    tl = TaskList()
    tl.add("one")
    second = tl.add("two")
    tl.remove([second.id])
    assert tl.add("three").id == 3


def test_get_many_fails_before_changing_anything():
    tl = TaskList()
    tl.add("one")
    with pytest.raises(TaskNotFoundError, match="no task with id 9"):
        tl.remove([1, 9])
    assert [t.id for t in tl.tasks] == [1]


def test_clear_done_removes_only_done_tasks():
    tl = TaskList()
    tl.add("keep")
    tl.add("drop").done = True
    removed = tl.clear_done()
    assert [t.title for t in removed] == ["drop"]
    assert [t.title for t in tl.tasks] == ["keep"]
