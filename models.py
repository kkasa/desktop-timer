"""
Desktop Timer - Data models and helper functions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import uuid


class TaskStatus:
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


def format_seconds(total_seconds: int) -> str:
    """Formats seconds into a HH:MM:SS string."""
    if total_seconds < 0:
        total_seconds = 0
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def now_timestamp() -> str:
    """Formats current local timestamp (YYYY-MM-DD HH:MM:SS)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def generate_task_id() -> str:
    """Generates a unique, readable identifier with timestamp and short random hash."""
    time_prefix = datetime.now().strftime("%Y%m%d-%H%M%S")
    rand_suffix = uuid.uuid4().hex[:4]
    return f"{time_prefix}-{rand_suffix}"


@dataclass
class TaskRecord:
    task_id: str
    desktop_name: str
    task_name: str
    status: str
    recorded: bool
    elapsed_seconds: int
    formatted_duration: str
    started_at: str
    updated_at: str

    @classmethod
    def create_new(cls, desktop_name: str, task_name: str = "") -> TaskRecord:
        """Instantiates a new task with default values."""
        now = now_timestamp()
        clean_name = task_name.strip() or "Untitled task"
        return cls(
            task_id=generate_task_id(),
            desktop_name=desktop_name.strip() or "Default Desktop",
            task_name=clean_name,
            status=TaskStatus.IN_PROGRESS,
            recorded=False,
            elapsed_seconds=0,
            formatted_duration="00:00:00",
            started_at=now,
            updated_at=now,
        )

    def update_duration(self, additional_seconds: int) -> None:
        """Increments elapsed time and updates formatted duration."""
        self.elapsed_seconds += additional_seconds
        self.formatted_duration = format_seconds(self.elapsed_seconds)
        self.updated_at = now_timestamp()

    def mark_completed(self, final_name: str | None = None) -> None:
        """Marks the task as completed."""
        if final_name and final_name.strip():
            self.task_name = final_name.strip()
        self.status = TaskStatus.COMPLETED
        self.formatted_duration = format_seconds(self.elapsed_seconds)
        self.updated_at = now_timestamp()

    def toggle_recorded(self) -> bool:
        """Toggles the recorded status (checked / unchecked)."""
        self.recorded = not self.recorded
        self.updated_at = now_timestamp()
        return self.recorded

    def to_csv_dict(self) -> dict[str, str]:
        """Converts task record to dictionary for writing CSV rows."""
        return {
            "task_id": self.task_id,
            "desktop_name": self.desktop_name,
            "task_name": self.task_name,
            "status": self.status,
            "recorded": "TRUE" if self.recorded else "FALSE",
            "elapsed_seconds": str(self.elapsed_seconds),
            "formatted_duration": self.formatted_duration,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_csv_dict(cls, row: dict[str, str]) -> TaskRecord:
        """Reconstructs TaskRecord from a CSV dictionary with error tolerance."""
        elapsed = 0
        try:
            elapsed = int(row.get("elapsed_seconds", 0))
        except (ValueError, TypeError):
            elapsed = 0

        recorded_val = str(row.get("recorded", "")).strip().upper()
        recorded = recorded_val in ("TRUE", "1", "YES", "IGEN")

        duration = row.get("formatted_duration") or format_seconds(elapsed)

        return cls(
            task_id=row.get("task_id", generate_task_id()),
            desktop_name=row.get("desktop_name", "Unknown Desktop"),
            task_name=row.get("task_name", "Untitled task"),
            status=row.get("status", TaskStatus.IN_PROGRESS),
            recorded=recorded,
            elapsed_seconds=elapsed,
            formatted_duration=duration,
            started_at=row.get("started_at", now_timestamp()),
            updated_at=row.get("updated_at", now_timestamp()),
        )
