"""
Desktop Timer - Időmérő állapotgép és üzleti logika.
UI-független, tesztelhető motor pontos (time.monotonic) időszámítással.
"""
from __future__ import annotations

import time
from typing import Optional

from models import TaskRecord, TaskStatus, format_seconds
from storage import CsvTaskRepository


class EngineState:
    IDLE = "IDLE"                      # Nincs aktív mérés
    RUNNING = "RUNNING"                # Időmérő aktívan ketyeg
    PAUSED = "PAUSED"                  # Mérés szüneteltetve
    PROMPT_RESUME = "PROMPT_RESUME"    # Visszatértünk az asztalra, megerősítésre vár


class TimerSessionController:
    """
    Kezeli az adott Asztalhoz tartozó időmérő állapotot, a váltásokat
    és a CSV perzisztenciát.
    """

    def __init__(self, repository: CsvTaskRepository, auto_save_interval_sec: int = 30) -> None:
        self.repo = repository
        self.auto_save_interval_sec = auto_save_interval_sec
        self.state: str = EngineState.IDLE
        self.active_task: Optional[TaskRecord] = None
        self._last_tick_monotonic: Optional[float] = None
        self._last_save_monotonic: float = time.monotonic()
        self._was_on_desktop: bool = True

        # Indításkor megkeressük, van-e korábban félbehagyott task
        resumable = self.repo.get_resumable_task()
        if resumable:
            self.active_task = resumable
            self.state = EngineState.PROMPT_RESUME

    def start_new_task(self, task_name: str) -> TaskRecord:
        """Új feladat indítása. Ha volt korábbi futó feladat, azt előbb lezárja."""
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
        """Félbehagyott feladat folytatása."""
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
        """Futó feladat szüneteltetése (pl. Asztal elhagyásakor vagy gombnyomásra)."""
        if self.state != EngineState.RUNNING or not self.active_task:
            return self.active_task

        self._flush_monotonic_delta()
        self.active_task.status = TaskStatus.PAUSED
        self.state = EngineState.PAUSED
        self.repo.upsert_task(self.active_task)
        return self.active_task

    def complete_active_task(self, final_name: Optional[str] = None) -> Optional[TaskRecord]:
        """Feladat befejezése és lezárása."""
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
        """Feladat rögzítettnek jelölése (pipálás)."""
        updated = self.repo.toggle_recorded(task_id)
        if self.active_task and self.active_task.task_id == task_id and updated:
            self.active_task.recorded = updated.recorded
        return updated

    def tick(self) -> int:
        """
        Időmérő frissítése. Rendszeresen (pl. 500-1000 ms-enként) hívandó.
        Visszaadja az aktuális task másodperceit, és periodikusan ment.
        """
        if self.state != EngineState.RUNNING or not self.active_task or self._last_tick_monotonic is None:
            return self.active_task.elapsed_seconds if self.active_task else 0

        now = time.monotonic()
        delta = now - self._last_tick_monotonic
        if delta >= 1.0:
            add_secs = int(delta)
            self.active_task.update_duration(add_secs)
            self._last_tick_monotonic += add_secs

            # Időszakos mentés ellenőrzése
            if (now - self._last_save_monotonic) >= self.auto_save_interval_sec:
                self.repo.upsert_task(self.active_task)
                self._last_save_monotonic = now

        return self.active_task.elapsed_seconds

    def handle_desktop_visibility_change(self, is_on_desktop: bool) -> tuple[bool, Optional[TaskRecord]]:
        """
        Kezeli az Asztal-váltás eseményt.
        Visszatérés: (kell_e_prompt_felugro, erintett_task)
        """
        prompt_needed = False
        target_task = None

        if self._was_on_desktop and not is_on_desktop:
            # Felhasználó elhagyta az Asztalt -> ha futott mérés, automatikus Pause!
            if self.state == EngineState.RUNNING:
                self.pause_active_task()
        elif not self._was_on_desktop and is_on_desktop:
            # Felhasználó visszatért erre az Asztalra!
            if self.active_task or self.repo.get_resumable_task():
                self.state = EngineState.PROMPT_RESUME
                target_task = self.active_task or self.repo.get_resumable_task()
                prompt_needed = True

        self._was_on_desktop = is_on_desktop
        return prompt_needed, target_task

    def _flush_monotonic_delta(self) -> None:
        """A törtrészek és maradék másodpercek elszámolása."""
        if self._last_tick_monotonic is not None and self.active_task:
            now = time.monotonic()
            delta = now - self._last_tick_monotonic
            if delta >= 0.5:
                add_secs = int(round(delta))
                if add_secs > 0:
                    self.active_task.update_duration(add_secs)
            self._last_tick_monotonic = None

    def get_all_tasks(self) -> list[TaskRecord]:
        """Minden rögzített feladat lekérése a listához."""
        return self.repo.load_tasks()

    def get_totals(self) -> tuple[int, int]:
        """(nem_rögzített_másodpercek, összes_másodpercek) összegzése."""
        tasks = self.repo.load_tasks()
        unrecorded = sum(t.elapsed_seconds for t in tasks if not t.recorded)
        total = sum(t.elapsed_seconds for t in tasks)
        return unrecorded, total

