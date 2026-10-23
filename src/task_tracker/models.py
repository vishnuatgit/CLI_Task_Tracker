"""Task data model and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ValidationError(ValueError):
    """Raised when user input or stored data is invalid."""


class TaskNotFoundError(LookupError):
    """Raised when no task has the requested id."""


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        return {"high": 0, "medium": 1, "low": 2}[self.value]


def parse_priority(value: str) -> Priority:
    try:
        return Priority(value.strip().lower())
    except ValueError:
        raise ValidationError(
            f"invalid priority {value!r} (choose from low, medium, high)"
        ) from None


def parse_due(value: str) -> date:
    """Parse a strict ISO date (YYYY-MM-DD)."""
    text = value.strip()
    if not _DATE_RE.match(text):
        raise ValidationError(f"invalid date {value!r} (expected YYYY-MM-DD)")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValidationError(f"invalid date {value!r} (no such day)") from None


def parse_title(value: str) -> str:
    title = " ".join(value.split())
    if not title:
        raise ValidationError("task title cannot be empty")
    return title


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Task:
    id: int
    title: str
    priority: Priority = Priority.MEDIUM
    due: date | None = None
    done: bool = False
    created_at: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority.value,
            "due": self.due.isoformat() if self.due else None,
            "done": self.done,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Task:
        if not isinstance(data, dict):
            raise ValidationError("task entry must be an object")
        task_id = data.get("id")
        if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id < 1:
            raise ValidationError(f"task id must be a positive integer, got {task_id!r}")
        title = data.get("title")
        if not isinstance(title, str):
            raise ValidationError(f"task {task_id}: title must be a string")
        done = data.get("done", False)
        if not isinstance(done, bool):
            raise ValidationError(f"task {task_id}: done must be true or false")
        due = data.get("due")
        if due is not None and not isinstance(due, str):
            raise ValidationError(f"task {task_id}: due must be a date string or null")
        return cls(
            id=task_id,
            title=parse_title(title),
            priority=parse_priority(str(data.get("priority", "medium"))),
            due=parse_due(due) if due else None,
            done=done,
            created_at=data.get("created_at"),
            completed_at=data.get("completed_at"),
        )


@dataclass
class TaskList:
    tasks: list[Task] = field(default_factory=list)
    next_id: int = 1

    def add(
        self, title: str, priority: Priority = Priority.MEDIUM, due: date | None = None
    ) -> Task:
        task = Task(
            id=self.next_id,
            title=parse_title(title),
            priority=priority,
            due=due,
            created_at=now_utc(),
        )
        self.tasks.append(task)
        self.next_id += 1
        return task

    def get(self, task_id: int) -> Task:
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise TaskNotFoundError(f"no task with id {task_id}")

    def get_many(self, ids: list[int]) -> list[Task]:
        """Look up every id first, so one bad id means nothing changes."""
        return [self.get(task_id) for task_id in ids]

    def remove(self, ids: list[int]) -> list[Task]:
        removed = self.get_many(ids)
        removed_ids = {t.id for t in removed}
        self.tasks = [t for t in self.tasks if t.id not in removed_ids]
        return removed

    def clear_done(self) -> list[Task]:
        removed = [t for t in self.tasks if t.done]
        self.tasks = [t for t in self.tasks if not t.done]
        return removed
