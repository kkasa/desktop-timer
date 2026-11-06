"""
Desktop Timer - Unit tests for data models, CSV persistence,
and timer state machine.
"""
from __future__ import annotations

import csv
from pathlib import Path
import time
from unittest.mock import patch
import pytest

from models import TaskRecord, TaskStatus, format_seconds, generate_task_id
from storage import CsvTaskRepository, sanitize_filename
from timer_engine import EngineState, TimerSessionController


def test_format_seconds():
    assert format_seconds(0) == "00:00:00"
    assert format_seconds(59) == "00:00:59"
    assert format_seconds(60) == "00:01:00"
    assert format_seconds(3665) == "01:01:05"
    assert format_seconds(-10) == "00:00:00"


def test_sanitize_filename():
    assert sanitize_filename("Project: Alpha / Test * ?") == "Project__Alpha___Test____"
    assert sanitize_filename("Desktop 1") == "Desktop_1"
    assert sanitize_filename("   ") == "default_desktop"


def test_task_record_lifecycle():
    task = TaskRecord.create_new(
        desktop_name="Controlling",
        task_name="Monthly report preparation",
    )
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.recorded is False
    assert task.elapsed_seconds == 0
    assert task.formatted_duration == "00:00:00"
    assert task.task_name == "Monthly report preparation"

    task.update_duration(125)
    assert task.elapsed_seconds == 125
    assert task.formatted_duration == "00:02:05"

    toggled = task.toggle_recorded()
    assert toggled is True
    assert task.recorded is True

    task.mark_completed(final_name="Monthly report preparation - Final")
    assert task.status == TaskStatus.COMPLETED
    assert task.task_name == "Monthly report preparation - Final"


def test_csv_storage_roundtrip_accented_characters(temp_data_dir: Path):
    """Verifies that international and accented characters are preserved correctly with UTF-8."""
    repo = CsvTaskRepository(
        data_dir=temp_data_dir,
        desktop_name="Pénzügy és Könyvelés",
        delimiter=";",
    )
    assert repo.csv_path.name == "Pénzügy_és_Könyvelés.csv"

    task1 = TaskRecord.create_new("Pénzügy és Könyvelés", "Áfa-bevallás ellenőrzése űrlap")
    task1.update_duration(3600)
    task2 = TaskRecord.create_new("Pénzügy és Könyvelés", "Számlák párosítása & rögzítés")
    task2.mark_completed()
    task2.toggle_recorded()

    saved = repo.save_tasks([task1, task2])
    assert saved is True
    assert repo.is_locked is False

    # Load from a new repository instance pointing to the same file
    loaded_repo = CsvTaskRepository(
        data_dir=temp_data_dir,
        desktop_name="Pénzügy és Könyvelés",
        delimiter=";",
    )
    tasks = loaded_repo.load_tasks()
    assert len(tasks) == 2

    assert tasks[0].task_name == "Áfa-bevallás ellenőrzése űrlap"
    assert tasks[0].elapsed_seconds == 3600
    assert tasks[0].recorded is False
    assert tasks[0].status == TaskStatus.IN_PROGRESS

    assert tasks[1].task_name == "Számlák párosítása & rögzítés"
    assert tasks[1].status == TaskStatus.COMPLETED
    assert tasks[1].recorded is True


def test_csv_storage_locked_excel_simulation(temp_data_dir: Path):
    repo = CsvTaskRepository(
        data_dir=temp_data_dir,
        desktop_name="LockTest",
    )
    task = TaskRecord.create_new("LockTest", "Test task")
    repo.save_tasks([task])

    # Simulate os.replace raising PermissionError (e.g. file locked by Excel)
    with patch("os.replace", side_effect=PermissionError("File locked")):
        success = repo.save_tasks([task])
        assert success is False
        assert repo.is_locked is True

        # In-memory cached tasks remain accessible
        cached = repo.load_tasks()
        assert len(cached) == 1
        assert cached[0].task_name == "Test task"


def test_timer_session_controller_workflow(temp_data_dir: Path):
    repo = CsvTaskRepository(data_dir=temp_data_dir, desktop_name="Dev")
    controller = TimerSessionController(repository=repo)

    assert controller.state == EngineState.IDLE
    assert controller.active_task is None

    # Start new task
    task = controller.start_new_task("Backend refactoring")
    assert controller.state == EngineState.RUNNING
    assert controller.active_task is not None
    assert controller.active_task.task_name == "Backend refactoring"

    # Simulate time passing
    with patch("time.monotonic") as mock_mono:
        mock_mono.return_value = controller._last_tick_monotonic + 5.0
        elapsed = controller.tick()
        assert elapsed == 5
        assert controller.active_task.elapsed_seconds == 5
        assert controller.active_task.formatted_duration == "00:00:05"

    # Pause
    controller.pause_active_task()
    assert controller.state == EngineState.PAUSED
    assert controller.active_task.status == TaskStatus.PAUSED

    # Resume
    controller.resume_task()
    assert controller.state == EngineState.RUNNING
    assert controller.active_task.status == TaskStatus.IN_PROGRESS

    # Complete
    completed = controller.complete_active_task(final_name="Backend refactoring DONE")
    assert controller.state == EngineState.IDLE
    assert controller.active_task is None
    assert completed.status == TaskStatus.COMPLETED
    assert completed.task_name == "Backend refactoring DONE"

    # Verify persistence
    tasks_in_repo = repo.load_tasks()
    assert len(tasks_in_repo) == 1
    assert tasks_in_repo[0].status == TaskStatus.COMPLETED


def test_desktop_switch_auto_pause_and_resume_prompt(temp_data_dir: Path):
    repo = CsvTaskRepository(data_dir=temp_data_dir, desktop_name="Project A")
    controller = TimerSessionController(repository=repo)

    # 1. Start task on desktop
    controller.start_new_task("Analysis and planning")
    assert controller.state == EngineState.RUNNING

    # 2. Switch to another desktop (is_on_desktop=False) -> auto-paused
    prompt_needed, _ = controller.handle_desktop_visibility_change(is_on_desktop=False)
    assert prompt_needed is False
    assert controller.state == EngineState.PAUSED
    assert controller.active_task.status == TaskStatus.PAUSED

    # 3. Return to desktop (is_on_desktop=True) -> prompt offered
    prompt_needed, target = controller.handle_desktop_visibility_change(is_on_desktop=True)
    assert prompt_needed is True
    assert target is not None
    assert target.task_name == "Analysis and planning"
    assert controller.state == EngineState.PROMPT_RESUME

    # 4. User clicks Resume
    resumed = controller.resume_task()
    assert controller.state == EngineState.RUNNING
    assert resumed.status == TaskStatus.IN_PROGRESS


def test_toggle_recorded_and_totals(temp_data_dir: Path):
    repo = CsvTaskRepository(data_dir=temp_data_dir, desktop_name="Metrics")
    controller = TimerSessionController(repository=repo)

    t1 = controller.start_new_task("Task 1")
    t1.update_duration(100)
    controller.complete_active_task()

    t2 = controller.start_new_task("Task 2")
    t2.update_duration(200)
    controller.complete_active_task()

    unrecorded, total = controller.get_totals()
    assert unrecorded == 300
    assert total == 300

    # Toggle recorded on Task 1
    controller.toggle_recorded(t1.task_id)

    unrecorded_after, total_after = controller.get_totals()
    assert unrecorded_after == 200
    assert total_after == 300


def test_ui_task_entry_editing_and_dynamic_background(temp_data_dir: Path):
    import tkinter as tk
    from unittest.mock import MagicMock
    from ui_widget import COLOR_BG, COLOR_BG_PAUSED, DesktopTimerApp

    root = tk.Tk()
    root.withdraw()
    try:
        repo = CsvTaskRepository(data_dir=temp_data_dir, desktop_name="UITest")
        controller = TimerSessionController(repository=repo)
        controller.start_new_task("Original task")

        detector = MagicMock()
        detector.assigned_desktop_name = "UITest"
        detector.is_on_current_desktop.return_value = True

        app = DesktopTimerApp(root=root, detector=detector, controller=controller)

        # Initially active task name should appear and background is dark (RUNNING)
        assert app.task_var.get() == "Original task"
        assert app._current_bg == COLOR_BG
        assert app.main_container.cget("bg") == COLOR_BG

        # User types in entry field
        app.task_var.set("Modified task name")
        app._on_task_entry_key()

        # Pause task -> background switches to medium gray (Resume active)
        controller.pause_active_task()
        app._refresh_ui_state()

        # Must not overwrite user input in progress while paused
        assert app.task_var.get() == "Modified task name"
        assert controller.active_task.task_name == "Modified task name"
        assert app._current_bg == COLOR_BG_PAUSED
        assert app.main_container.cget("bg") == COLOR_BG_PAUSED

        # Resume task -> background returns to dark
        controller.resume_task()
        app._refresh_ui_state()
        assert app._current_bg == COLOR_BG
        assert app.main_container.cget("bg") == COLOR_BG

        # Simulate Enter or FocusOut -> save to storage
        app._on_task_name_changed()
        loaded = repo.load_tasks()
        assert loaded[0].task_name == "Modified task name"
    finally:
        root.destroy()


