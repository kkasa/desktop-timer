# AGENTS.md — Desktop Timer Project Specifications and Conventions

This document summarizes the architecture, technical conventions, and maintenance guidelines for AI agents working on this project.

---

## 1. Project Language & Standards

- **Project Language:** **American English (en-US)**.
  - All documentation (`.md` files), code comments, docstrings, UI labels, button texts, dialogs, log messages, error messages, and unit tests MUST be written in American English.
  - User-provided data (e.g., custom virtual desktop names or task descriptions in Hungarian or other languages) must continue to be handled transparently using `utf-8-sig` encoding.
- **Technology Stack:** Python 3.10+ (Standard Library: `tkinter`, `ctypes`, `winreg`, `csv`, `dataclasses`, `pathlib`, `uuid`).
- **Testing:** `pytest>=8.0`.
- **Python Development Rules:** Follows Tier 3 (Desktop App) guidelines from `python_dev_rules`:
  - Windows console UTF-8 hygiene (`sys.stdout.reconfigure(encoding="utf-8")`).
  - Rotating error logging (`logger_setup.py` -> `error.log`, `delay=True`, `WARNING+`).
  - All file and directory path operations must strictly use `pathlib.Path`.

---

## 2. Modules and Responsibilities

| File | Responsibility | Key Classes / Methods |
| :--- | :--- | :--- |
| `app.py` | Entry point and CLI parsing | `main()`, `parse_args()` |
| `virtual_desktop.py` | Win11 COM and Registry reader | `VirtualDesktopDetector`, `IVirtualDesktopManager` wrapper, `bring_window_to_front()` |
| `models.py` | Data models and formatting | `TaskRecord`, `TaskStatus`, `format_seconds()`, `generate_task_id()` |
| `storage.py` | Per-desktop CSV persistence | `CsvTaskRepository`, `save_tasks()`, `load_tasks()`, `sanitize_filename()` |
| `timer_engine.py` | Pure state machine & business logic | `TimerSessionController`, `EngineState`, `tick()`, `adjust_active_task_duration()`, `handle_desktop_visibility_change()` |
| `ui_widget.py` | Tkinter floating widget & history panel | `DesktopTimerApp`, `_poll_tick()`, `_apply_background_color()`, `_on_click_adjust_time()`, `_toggle_task_filter()`, `_render_task_list()`, `_adjust_window_size()`, `_on_task_entry_key()`, `_on_task_name_changed()` |
| `logger_setup.py` | Logging and structured exceptions | `setup_logger()`, `ConfigError`, `StorageLockError` |

- **UI Visual & Polling Conventions:**
  - Background Polling Frequency: 900 ms (`POLL_INTERVAL_MS = 900`) for virtual desktop switching checks and drift-free monotonic timekeeping.
  - Active / Running / Idle background: Deep dark (`#121417`, `COLOR_BG`).
  - Paused / Resume-active background: Medium gray (`#545c6e`, `COLOR_BG_PAUSED`), maintaining high-contrast visibility for white text while clearly differentiating paused from running state.
  - Time Adjustment Controls: Quick `[-1m]` and `[+1m]` buttons next to the digital clock to adjust active or paused measurements by 1 minute (bounded at 0 seconds minimum).
  - Task List Filtering: Defaults to hiding recorded (checked off) tasks (`show_all_tasks = False`). An inline toolbar toggle button (`[👁 Show All]` / `[👁 Hide Recorded]`) allows revealing the full history.

---

## 3. CSV Data Schema (`data/<Desktop_Name>.csv`)

- **Encoding:** `utf-8-sig`
- **Delimiter:** `;` (semicolon, default for Excel compatibility)
- **Columns:**
  1. `task_id` (string): e.g., `20261106-193000-a1b2`
  2. `desktop_name` (string): e.g., `Controlling`
  3. `task_name` (string): e.g., `Monthly report verification`
  4. `status` (string): `IN_PROGRESS` | `PAUSED` | `COMPLETED`
  5. `recorded` (string): `TRUE` | `FALSE` (checkbox tracking)
  6. `elapsed_seconds` (int): Total elapsed seconds
  7. `formatted_duration` (string): `HH:MM:SS`
  8. `started_at` (string): `YYYY-MM-DD HH:MM:SS`
  9. `updated_at` (string): `YYYY-MM-DD HH:MM:SS`

---

## 4. Testing

To run tests:
```powershell
pytest tests -v
```
All new business logic or storage changes must be covered with unit tests in `tests/test_timer_and_storage.py`.
