"""
Desktop Timer - Timer state machine and business logic.
UI-independent, testable engine with drift-free (time.monotonic) timekeeping.
"""
from __future__ import annotations

import time
from typing import Optional

from models import TaskRecord, TaskStatus, format_seconds
from storage import CsvTaskRepository


class EngineState:
    IDLE = "IDLE"                      # No active measurement
    RUNNING = "RUNNING"                # Timer actively running
    PAUSED = "PAUSED"                  # Timer paused
    PROMPT_RESUME = "PROMPT_RESUME"    # Returned to desktop, awaiting confirmation


class TimerSessionController:
    """
    Manages timer state, transitions, and CSV persistence
    for a specific desktop.
    """

    def __init__(self, repository: CsvTaskRepository, auto_save_interval_sec: int = 30) -> None:
        self.repo = repository
        self.auto_save_interval_sec = auto_save_interval_sec
        self.state: str = EngineState.IDLE
        self.active_task: Optional[TaskRecord] = None
        self._last_tick_monotonic: Optional[float] = None
        self._last_save_monotonic: float = time.monotonic()
        self._was_on_desktop: bool = True

        # Check for previously unfinished task on startup
        resumable = self.repo.get_resumable_task()
        if resumable:
            self.active_task = resumable
            self.state = EngineState.PROMPT_RESUME

    def start_new_task(self, task_name: str) -> TaskRecord:
        """Starts a new task. Closes any previously running task first."""
        if self.state == EngineState.RUNNING and self.active_task:
            self._flush_monotonic_delta()
            self.active_task.mark_completed()
            self.repo.upsert_task(self.active_task)

        task = TaskRecord.create_new(
            desktop_name=self.repo.desktop_name,
            task_name=task_name,
        )
        self.active_task = task
        self.state = EngineState.RUNNING
        self._last_tick_monotonic = time.monotonic()
        self._last_save_monotonic = self._last_tick_monotonic
        self.repo.upsert_task(task)
        return task

    def resume_task(self, task_id: Optional[str] = None) -> Optional[TaskRecord]:
        """Resumes an unfinished task."""
        target: Optional[TaskRecord] = None
        if task_id:
            tasks = self.repo.load_tasks()
            target = next((t for t in tasks if t.task_id == task_id), None)
        elif self.active_task:
            target = self.active_task
        else:
            target = self.repo.get_resumable_task()

        if not target:
            return None

        self.active_task = target
        self.active_task.status = TaskStatus.IN_PROGRESS
        self.state = EngineState.RUNNING
        self._last_tick_monotonic = time.monotonic()
        self._last_save_monotonic = self._last_tick_monotonic
        self.repo.upsert_task(self.active_task)
        return self.active_task

    def pause_active_task(self) -> Optional[TaskRecord]:
        """Pauses the running task (e.g. when leaving the desktop or via button click)."""
        if self.state != EngineState.RUNNING or not self.active_task:
            return self.active_task

        self._flush_monotonic_delta()
        self.active_task.status = TaskStatus.PAUSED
        self.state = EngineState.PAUSED
        self.repo.upsert_task(self.active_task)
        return self.active_task

    def complete_active_task(self, final_name: Optional[str] = None) -> Optional[TaskRecord]:
        """Completes and closes the task."""
        if not self.active_task:
            return None

        if self.state == EngineState.RUNNING:
            self._flush_monotonic_delta()

        completed_task = self.active_task
        completed_task.mark_completed(final_name=final_name)
        self.repo.upsert_task(completed_task)

        self.active_task = None
        self.state = EngineState.IDLE
        self._last_tick_monotonic = None
        return completed_task

    def toggle_recorded(self, task_id: str) -> Optional[TaskRecord]:
        """Toggles the recorded status of a task (check / uncheck)."""
        updated = self.repo.toggle_recorded(task_id)
        if self.active_task and self.active_task.task_id == task_id and updated:
            self.active_task.recorded = updated.recorded
        return updated

    def adjust_active_task_duration(self, delta_seconds: int) -> Optional[TaskRecord]:
        """Adjusts active task elapsed seconds by delta_seconds (minimum 0) and persists immediately."""
        if not self.active_task or self.state == EngineState.IDLE:
            return None

        if self.state == EngineState.RUNNING:
            self._flush_monotonic_delta()
            self._last_tick_monotonic = time.monotonic()

        self.active_task.update_duration(delta_seconds)
        self.repo.upsert_task(self.active_task)
        return self.active_task

    def tick(self) -> int:
        """
        Updates the timer. Called regularly (e.g. every 900 ms).
        Returns current task elapsed seconds and performs periodic auto-saving.
        """
        if self.state != EngineState.RUNNING or not self.active_task or self._last_tick_monotonic is None:
            return self.active_task.elapsed_seconds if self.active_task else 0

        now = time.monotonic()
        delta = now - self._last_tick_monotonic
        if delta >= 1.0:
            add_secs = int(delta)
            self.active_task.update_duration(add_secs)
            self._last_tick_monotonic += add_secs

            # Check periodic auto-save
            if (now - self._last_save_monotonic) >= self.auto_save_interval_sec:
                self.repo.upsert_task(self.active_task)
                self._last_save_monotonic = now

        return self.active_task.elapsed_seconds

    def handle_desktop_visibility_change(self, is_on_desktop: bool) -> tuple[bool, Optional[TaskRecord]]:
        """
        Handles desktop switch events.
        Returns: (prompt_needed, target_task)
        """
        prompt_needed = False
        target_task = None

        if self._was_on_desktop and not is_on_desktop:
            # User left the desktop -> auto-pause active timer
            if self.state == EngineState.RUNNING:
                self.pause_active_task()
        elif not self._was_on_desktop and is_on_desktop:
            # User returned to this desktop
            if self.active_task or self.repo.get_resumable_task():
                self.state = EngineState.PROMPT_RESUME
                target_task = self.active_task or self.repo.get_resumable_task()
                prompt_needed = True

        self._was_on_desktop = is_on_desktop
        return prompt_needed, target_task

    def _flush_monotonic_delta(self) -> None:
        """Flushes fractional and remaining elapsed seconds."""
        if self._last_tick_monotonic is not None and self.active_task:
            now = time.monotonic()
            delta = now - self._last_tick_monotonic
            if delta >= 0.5:
                add_secs = int(round(delta))
                if add_secs > 0:
                    self.active_task.update_duration(add_secs)
            self._last_tick_monotonic = None

    def get_all_tasks(self) -> list[TaskRecord]:
        """Retrieves all tasks for the history panel."""
        return self.repo.load_tasks()

    def get_totals(self) -> tuple[int, int]:
        """Calculates (unrecorded_seconds, total_seconds)."""
        tasks = self.repo.load_tasks()
        unrecorded = sum(t.elapsed_seconds for t in tasks if not t.recorded)
        total = sum(t.elapsed_seconds for t in tasks)
        return unrecorded, total
