import json
import os
from pathlib import Path

import pytest

from task_tracker import storage
from task_tracker.models import TaskList


def test_missing_and_empty_files_load_as_empty(tmp_path):
    assert storage.load(tmp_path / "nope.json").tasks == []
    empty = tmp_path / "empty.json"
    empty.write_text("  \n", encoding="utf-8")
    assert storage.load(empty).tasks == []


def test_save_then_load_round_trips_and_creates_folders(tmp_path):
    path = tmp_path / "deep" / "dir" / "tasks.json"
    tl = TaskList()
    tl.add("Write tests")
    storage.save(path, tl)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == storage.SCHEMA_VERSION
    assert data["next_id"] == 2
    assert storage.load(path) == tl


def test_failed_write_keeps_old_file_and_leaves_no_temp_file(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    tl = TaskList()
    tl.add("original")
    storage.save(path, tl)
    before = path.read_bytes()

    def broken_replace(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", broken_replace)
    tl.add("new")
    with pytest.raises(storage.StorageError, match="No space left"):
        storage.save(path, tl)
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["tasks.json"]


def test_legacy_format_is_migrated(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps({"1": "Buy milk", "3": "Read a book"}), encoding="utf-8")
    tl = storage.load(path)
    assert [(t.id, t.title, t.done) for t in tl.tasks] == [
        (1, "Buy milk", False),
        (3, "Read a book", False),
    ]
    assert tl.next_id == 4
    storage.save(path, tl)
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


def test_corrupt_json_is_an_error_and_file_is_untouched(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text('{"version": 1, "tasks": [', encoding="utf-8")
    with pytest.raises(storage.StorageError, match="not valid JSON"):
        storage.load(path)
    assert path.read_text(encoding="utf-8") == '{"version": 1, "tasks": ['


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ([1, 2], "unrecognised file format"),
        ({"a": "b"}, "unrecognised file format"),
        ({"version": "1", "tasks": []}, "schema version must be an integer"),
        ({"version": 99, "tasks": []}, "schema version 99"),
        ({"version": 1, "tasks": {}}, "'tasks' must be a list"),
        ({"version": 1, "tasks": [{"id": 1, "title": "a"}, {"id": 1, "title": "b"}]}, "duplicate"),
    ],
)
def test_bad_structure_is_an_error(tmp_path, content, message):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(storage.StorageError, match=message):
        storage.load(path)


def test_next_id_never_falls_below_existing_ids(tmp_path):
    path = tmp_path / "tasks.json"
    payload = {"version": 1, "next_id": 1, "tasks": [{"id": 5, "title": "x"}]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert storage.load(path).next_id == 6


def test_resolve_path_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert storage.resolve_path(None, {}) == tmp_path / ".task_tracker" / "tasks.json"
    assert storage.resolve_path(None, {"TASKS_FILE": "env.json"}) == Path("env.json")
    assert storage.resolve_path("cli.json", {"TASKS_FILE": "env.json"}) == Path("cli.json")
