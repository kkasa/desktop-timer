"""
Desktop Timer - Részletes egységtesztek az adatmodellhez, CSV perzisztenciához
és az időmérő állapotgéphez.
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
    assert sanitize_filename("Projekt: Alpha / Teszt * ?") == "Projekt__Alpha___Teszt____"
    assert sanitize_filename("Asztal 1") == "Asztal_1"
    assert sanitize_filename("   ") == "default_desktop"


def test_task_record_lifecycle():
    task = TaskRecord.create_new(
        desktop_name="Kontrolling",
        task_name="Havi riport készítés",
    )
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.recorded is False
    assert task.elapsed_seconds == 0
    assert task.formatted_duration == "00:00:00"
    assert task.task_name == "Havi riport készítés"

    task.update_duration(125)
    assert task.elapsed_seconds == 125
    assert task.formatted_duration == "00:02:05"

    toggled = task.toggle_recorded()
    assert toggled is True
    assert task.recorded is True

    task.mark_completed(final_name="Havi riport készítés - Végleges")
    assert task.status == TaskStatus.COMPLETED
    assert task.task_name == "Havi riport készítés - Végleges"


def test_csv_storage_roundtrip_hungarian_characters(temp_data_dir: Path):
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

    # Új repo példány beolvasása ugyanabból a fájlból
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
    task = TaskRecord.create_new("LockTest", "Teszt task")
    repo.save_tasks([task])

    # Szimuláljuk, hogy os.replace PermissionError-t dob (pl. Excel zárolta)
    with patch("os.replace", side_effect=PermissionError("Fájl zárolva")):
        success = repo.save_tasks([task])
        assert success is False
        assert repo.is_locked is True

        # Memóriából betöltve továbbra is elérhető a cache
        cached = repo.load_tasks()
        assert len(cached) == 1
        assert cached[0].task_name == "Teszt task"


def test_timer_session_controller_workflow(temp_data_dir: Path):
    repo = CsvTaskRepository(data_dir=temp_data_dir, desktop_name="Dev")
    controller = TimerSessionController(repository=repo)

    assert controller.state == EngineState.IDLE
    assert controller.active_task is None

    # Új task indítása
    task = controller.start_new_task("Backend refaktorálás")
    assert controller.state == EngineState.RUNNING
    assert controller.active_task is not None
    assert controller.active_task.task_name == "Backend refaktorálás"

    # Idő telésének szimulációja
    with patch("time.monotonic") as mock_mono:
        mock_mono.return_value = controller._last_tick_monotonic + 5.0
        elapsed = controller.tick()
        assert elapsed == 5
        assert controller.active_task.elapsed_seconds == 5
        assert controller.active_task.formatted_duration == "00:00:05"

    # Szüneteltetés
    controller.pause_active_task()
    assert controller.state == EngineState.PAUSED
    assert controller.active_task.status == TaskStatus.PAUSED

    # Folytatás
    controller.resume_task()
    assert controller.state == EngineState.RUNNING
    assert controller.active_task.status == TaskStatus.IN_PROGRESS

    # Befejezés
    completed = controller.complete_active_task(final_name="Backend refaktorálás KÉSZ")
    assert controller.state == EngineState.IDLE
    assert controller.active_task is None
    assert completed.status == TaskStatus.COMPLETED
    assert completed.task_name == "Backend refaktorálás KÉSZ"

    # Perzisztencia ellenőrzése
    tasks_in_repo = repo.load_tasks()
    assert len(tasks_in_repo) == 1
    assert tasks_in_repo[0].status == TaskStatus.COMPLETED


def test_desktop_switch_auto_pause_and_resume_prompt(temp_data_dir: Path):
    repo = CsvTaskRepository(data_dir=temp_data_dir, desktop_name="Projekt A")
    controller = TimerSessionController(repository=repo)

    # 1. Elindítunk egy feladatot az Asztalon
    controller.start_new_task("Elemzés és tervezés")
    assert controller.state == EngineState.RUNNING

    # 2. Átváltunk egy másik Asztalra (is_on_desktop=False)
    prompt_needed, _ = controller.handle_desktop_visibility_change(is_on_desktop=False)
    assert prompt_needed is False
    # Automatikusan Pause állapotba váltott!
    assert controller.state == EngineState.PAUSED
    assert controller.active_task.status == TaskStatus.PAUSED

    # 3. Visszatérünk az Asztalra (is_on_desktop=True)
    prompt_needed, target = controller.handle_desktop_visibility_change(is_on_desktop=True)
    assert prompt_needed is True
    assert target is not None
    assert target.task_name == "Elemzés és tervezés"
    assert controller.state == EngineState.PROMPT_RESUME

    # 4. Felhasználó rányom a Folytatásra
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

    # Pipáljuk a Task 1-et
    controller.toggle_recorded(t1.task_id)

    unrecorded_after, total_after = controller.get_totals()
    assert unrecorded_after == 200
    assert total_after == 300


def test_ui_task_entry_editing_not_overwritten(temp_data_dir: Path):
    import tkinter as tk
    from unittest.mock import MagicMock
    from ui_widget import DesktopTimerApp

    root = tk.Tk()
    root.withdraw()
    try:
        repo = CsvTaskRepository(data_dir=temp_data_dir, desktop_name="UITest")
        controller = TimerSessionController(repository=repo)
        controller.start_new_task("Eredeti feladat")

        detector = MagicMock()
        detector.assigned_desktop_name = "UITest"
        detector.is_on_current_desktop.return_value = True

        app = DesktopTimerApp(root=root, detector=detector, controller=controller)

        # Kezdetben meg kell jelennie az aktív task nevének
        assert app.task_var.get() == "Eredeti feladat"

        # Felhasználó gépel a mezőben
        app.task_var.set("Módosított feladat név")
        app._on_task_entry_key()

        # Szimulálunk egy időzítő tick / UI refresh ciklust (akár fut, akár szünetel)
        app._refresh_ui_state()

        # Nem írhatja vissza a régi nevet!
        assert app.task_var.get() == "Módosított feladat név"
        assert controller.active_task.task_name == "Módosított feladat név"

        # Enter vagy FocusOut szimulálása -> mentés a tárolóba
        app._on_task_name_changed()
        loaded = repo.load_tasks()
        assert loaded[0].task_name == "Módosított feladat név"
    finally:
        root.destroy()

