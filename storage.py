"""
Desktop Timer - CSV Persistence layer.
Handles per-desktop CSV file storage with utf-8-sig encoding and Excel lock protection.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
import re
from typing import Optional

from logger_setup import StorageLockError, setup_logger
from models import TaskRecord, TaskStatus

logger = setup_logger("desktop_timer.storage")

CSV_FIELDNAMES = [
    "task_id",
    "desktop_name",
    "task_name",
    "status",
    "recorded",
    "elapsed_seconds",
    "formatted_duration",
    "started_at",
    "updated_at",
]


def sanitize_filename(name: str) -> str:
    """Cleans filename from invalid Windows characters."""
    clean = re.sub(r'[\\/*?:"<>|]', "_", name.strip())
    clean = re.sub(r"\s+", "_", clean)
    return clean or "default_desktop"


class CsvTaskRepository:
    def __init__(self, data_dir: Path, desktop_name: str, delimiter: str = ";") -> None:
        self.data_dir = Path(data_dir).resolve()
        self.desktop_name = desktop_name.strip() or "Default Desktop"
        self.delimiter = delimiter
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._filename = f"{sanitize_filename(self.desktop_name)}.csv"
        self.csv_path = self.data_dir / self._filename
        self.is_locked: bool = False
        self._cached_tasks: list[TaskRecord] = []
        self._init_storage()

    def _init_storage(self) -> None:
        """Initializes the CSV header if the file does not exist yet."""
        if not self.csv_path.exists():
            try:
                with open(
                    self.csv_path,
                    mode="w",
                    encoding="utf-8-sig",
                    newline="",
                ) as f:
                    writer = csv.DictWriter(
                        f,
                        fieldnames=CSV_FIELDNAMES,
                        delimiter=self.delimiter,
                        quoting=csv.QUOTE_MINIMAL,
                    )
                    writer.writeheader()
                self.is_locked = False
            except Exception as e:
                logger.warning(f"Failed to initialize CSV file ({self.csv_path}): {e}")

    def load_tasks(self) -> list[TaskRecord]:
        """Loads tasks from the CSV file."""
        if not self.csv_path.exists():
            self._cached_tasks = []
            return []

        tasks: list[TaskRecord] = []
        try:
            with open(
                self.csv_path,
                mode="r",
                encoding="utf-8-sig",
                newline="",
            ) as f:
                reader = csv.DictReader(f, delimiter=self.delimiter)
                # Fallback if header delimiter differs (e.g. comma vs semicolon)
                if reader.fieldnames and len(reader.fieldnames) == 1 and "," in reader.fieldnames[0]:
                    f.seek(0)
                    reader = csv.DictReader(f, delimiter=",")

                for row in reader:
                    if row.get("task_id"):
                        tasks.append(TaskRecord.from_csv_dict(row))

            self._cached_tasks = tasks
            self.is_locked = False
            return tasks
        except PermissionError:
            self.is_locked = True
            logger.warning(f"CSV file is locked by another application: {self.csv_path}")
            return list(self._cached_tasks)
        except Exception as e:
            logger.exception(f"Error reading tasks ({self.csv_path}): {e}")
            return list(self._cached_tasks)

    def save_tasks(self, tasks: list[TaskRecord]) -> bool:
        """
        Saves tasks to CSV file using atomic replacement (.tmp).
        If the file is locked (e.g. open in Excel), keeps tasks in cache and returns False.
        """
        self._cached_tasks = list(tasks)
        tmp_path = self.csv_path.with_suffix(".tmp")

        try:
            with open(
                tmp_path,
                mode="w",
                encoding="utf-8-sig",
                newline="",
            ) as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=CSV_FIELDNAMES,
                    delimiter=self.delimiter,
                    quoting=csv.QUOTE_MINIMAL,
                )
                writer.writeheader()
                for task in tasks:
                    writer.writerow(task.to_csv_dict())

            # Atomic swap
            os.replace(tmp_path, self.csv_path)
            self.is_locked = False
            return True
        except PermissionError:
            self.is_locked = True
            logger.warning(
                f"Cannot write CSV file because it is locked (e.g. open in Excel): {self.csv_path}"
            )
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            return False
        except Exception as e:
            logger.exception(f"Unexpected error while saving CSV ({self.csv_path}): {e}")
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            return False

    def upsert_task(self, task: TaskRecord) -> bool:
        """Adds a single task or updates an existing one."""
        tasks = self.load_tasks()
        updated = False
        for idx, t in enumerate(tasks):
            if t.task_id == task.task_id:
                tasks[idx] = task
                updated = True
                break
        if not updated:
            tasks.append(task)
        return self.save_tasks(tasks)

    def get_resumable_task(self) -> Optional[TaskRecord]:
        """Finds the most recent unfinished (IN_PROGRESS or PAUSED) task."""
        tasks = self.load_tasks()
        for task in reversed(tasks):
            if task.status in (TaskStatus.IN_PROGRESS, TaskStatus.PAUSED):
                return task
        return None

    def toggle_recorded(self, task_id: str) -> Optional[TaskRecord]:
        """Toggles the recorded status of a task."""
        tasks = self.load_tasks()
        target_task = None
        for task in tasks:
            if task.task_id == task_id:
                task.toggle_recorded()
                target_task = task
                break
        if target_task:
            self.save_tasks(tasks)
        return target_task
