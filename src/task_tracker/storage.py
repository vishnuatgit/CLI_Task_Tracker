"""JSON storage with atomic writes and schema migration."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from task_tracker.models import Task, TaskList, ValidationError

SCHEMA_VERSION = 1
ENV_VAR = "TASKS_FILE"


class StorageError(Exception):
    """Raised when the tasks file cannot be read or written."""


def default_path() -> Path:
    return Path.home() / ".task_tracker" / "tasks.json"


def resolve_path(cli_path: str | None = None, env: Mapping[str, str] | None = None) -> Path:
    """Pick the tasks file: --file, then $TASKS_FILE, then the default."""
    env = os.environ if env is None else env
    if cli_path:
        return Path(cli_path).expanduser()
    if env.get(ENV_VAR):
        return Path(env[ENV_VAR]).expanduser()
    return default_path()


def migrate(data: Any) -> dict[str, Any]:
    """Upgrade any known file format to the current schema."""
    if isinstance(data, dict) and "version" not in data:
        # Version 0: the original script stored {"1": "Buy milk", ...}.
        tasks = []
        for key, title in data.items():
            if not (isinstance(key, str) and key.isdigit() and isinstance(title, str)):
                raise ValidationError("unrecognised file format")
            tasks.append({"id": int(key), "title": title})
        tasks.sort(key=lambda t: t["id"])
        next_id = max((t["id"] for t in tasks), default=0) + 1
        return {"version": SCHEMA_VERSION, "next_id": next_id, "tasks": tasks}
    if not isinstance(data, dict):
        raise ValidationError("unrecognised file format")
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ValidationError("schema version must be an integer")
    if version > SCHEMA_VERSION:
        raise ValidationError(
            f"file uses schema version {version}, but this program supports up to "
            f"{SCHEMA_VERSION}; upgrade task-tracker"
        )
    return data


def load(path: Path) -> TaskList:
    """Read tasks. A missing or empty file is an empty list; a bad file is an error."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return TaskList()
    except OSError as exc:
        raise StorageError(f"cannot read {path}: {exc.strerror or exc}") from exc
    if not text.strip():
        return TaskList()
    try:
        data = migrate(json.loads(text))
        tasks_raw = data.get("tasks", [])
        if not isinstance(tasks_raw, list):
            raise ValidationError("'tasks' must be a list")
        tasks = [Task.from_dict(item) for item in tasks_raw]
    except json.JSONDecodeError as exc:
        raise StorageError(
            f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno}); "
            "fix or move the file. It has not been changed."
        ) from exc
    except ValidationError as exc:
        raise StorageError(f"{path}: {exc}. The file has not been changed.") from exc
    ids = [t.id for t in tasks]
    if len(ids) != len(set(ids)):
        raise StorageError(f"{path}: duplicate task ids. The file has not been changed.")
    next_id = data.get("next_id")
    floor = max(ids, default=0) + 1
    if not isinstance(next_id, int) or isinstance(next_id, bool) or next_id < floor:
        next_id = floor
    return TaskList(tasks=tasks, next_id=next_id)


def save(path: Path, task_list: TaskList) -> None:
    """Write atomically: write a temp file in the same folder, then replace."""
    payload = {
        "version": SCHEMA_VERSION,
        "next_id": task_list.next_id,
        "tasks": [t.to_dict() for t in task_list.tasks],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    except OSError as exc:
        raise StorageError(f"cannot write {path}: {exc.strerror or exc}") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException as exc:
        Path(tmp_name).unlink(missing_ok=True)
        if isinstance(exc, OSError):
            raise StorageError(f"cannot write {path}: {exc.strerror or exc}") from exc
        raise
