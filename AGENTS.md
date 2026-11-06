# AGENTS.md — Desktop Timer Projekt Specifikáció és Konvenciók

Ez a dokumentum az AI ágensek számára foglalja össze a projekt architektúráját, konvencióit és karbantartási szabályait.

---

## 1. Technológiai Stack és Szabályok

- **Nyelv:** Python 3.10+ (Standard Library: `tkinter`, `ctypes`, `winreg`, `csv`, `dataclasses`, `pathlib`, `uuid`).
- **Tesztelés:** `pytest>=8.0`.
- **Szabványok:** A `python_dev_rules` készlet Tier 3 (Desktop App) irányelveit követi.
  - Windows UTF-8 konzolhigiénia (`reconfigure(encoding="utf-8")`).
  - Rotáló hibaplózás (`logger_setup.py` -> `error.log`, `delay=True`, `WARNING+`).
  - Fájlok és elérési utak kezelése kizárólag `pathlib.Path` segítségével.

---

## 2. Modulok és Felelősségek

| Fájl | Felelősség | Főbb osztályok / metódusok |
| :--- | :--- | :--- |
| `app.py` | Belépési pont és CLI vezérlés | `main()`, `parse_args()` |
| `virtual_desktop.py` | Win11 COM és Registry olvasó | `VirtualDesktopDetector`, `IVirtualDesktopManager` wrapper, `bring_window_to_front` |
| `models.py` | Adatmodell és formázás | `TaskRecord`, `TaskStatus`, `format_seconds()`, `generate_task_id()` |
| `storage.py` | CSV perzisztencia (külön asztalonként) | `CsvTaskRepository`, `save_tasks()`, `load_tasks()`, `sanitize_filename()` |
| `timer_engine.py` | Tiszta állapotgép & üzleti logika | `TimerSessionController`, `EngineState`, `tick()`, `handle_desktop_visibility_change()` |
| `ui_widget.py` | Tkinter lebegő widget és lenyíló panel | `DesktopTimerApp`, `_poll_tick()`, `_render_task_list()`, `_adjust_window_size()`, `_on_task_entry_key()`, `_on_task_name_changed()` |
| `logger_setup.py` | Naplózás és kivételek | `setup_logger()`, `ConfigError`, `StorageLockError` |

---

## 3. CSV Adatséma (`data/<Asztal_Neve>.csv`)

- **Kódolás:** `utf-8-sig`
- **Elválasztó:** `;` (pontosvessző, magyar Excel alapértelmezett)
- **Oszlopok:**
  1. `task_id` (string): pl. `20261106-193000-a1b2`
  2. `desktop_name` (string): pl. `Kontrolling`
  3. `task_name` (string): pl. `Havi zárás ellenőrzése`
  4. `status` (string): `IN_PROGRESS` | `PAUSED` | `COMPLETED`
  5. `recorded` (string): `TRUE` | `FALSE` (pipálás)
  6. `elapsed_seconds` (int): Eltelt másodpercek
  7. `formatted_duration` (string): `HH:MM:SS`
  8. `started_at` (string): `YYYY-MM-DD HH:MM:SS`
  9. `updated_at` (string): `YYYY-MM-DD HH:MM:SS`

---

## 4. Tesztelés

A tesztek futtatása:
```powershell
pytest tests -v
```
Minden új üzleti logika módosítást a `tests/test_timer_and_storage.py` fájlban le kell fedni egységtesztekkel.

