# Desktop Timer ⏱️

Windows 11 Virtual Desktop-aware minimalist floating work timer application.

Designed specifically for workflows where different Windows 11 Virtual Desktops are dedicated to separate projects. The application runs in separate instances across desktops, accurately measuring only the **actual active work time** spent on that specific desktop.

---

## Key Features

1. **Automatic Windows 11 Virtual Desktop Detection:**
   - On startup, automatically reads the virtual desktop name (e.g., `Controlling`, `BA Workshop`, `Project Alpha`) and GUID from the Windows 11 Explorer registry (`HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops`).
   - If no custom name was assigned in Windows, it falls back to sequential naming (`Desktop 1`, `Desktop 2`, etc.).
2. **Responsive to Desktop Switching:**
   - **When leaving:** Switching away to another desktop (while background processes or AI agents work here) **automatically pauses** the active timer and saves progress to CSV.
   - **When returning:** Returning to the desktop **automatically brings the widget to the foreground** and displays a prompt offering to resume (*"Resume: '...'?"*). The timer resumes **strictly upon user click**.
3. **Per-Desktop CSV Persistence:**
   - Stores records in isolated files at `data/<Desktop_Name>.csv`.
   - **Excel Compatible:** Formatted in `utf-8-sig` encoding with semicolon (`;`) delimiter for direct double-click opening in Excel without character encoding issues or corrupted columns.
   - **File Lock Protection:** If the CSV is locked open in Excel, the app does not crash; it preserves updates in memory and displays a lock warning badge on the widget.
4. **Minimalist Floating Widget + Expandable History:**
   - Compact widget (~440 × 215 px): prominent high-contrast digital clock (`Consolas 28 bold`), real-time editable task name input, Start / Pause / Complete / New buttons, and `[📌 On Top / 📍 Normal]` toggle.
   - **Dynamic State Indication:** The widget automatically switches its background to medium gray (`#545c6e`) while paused (when the Resume button is active), providing instant visual differentiation from the deep dark running background while maintaining crisp legibility for white text.
   - Expandable history panel (~440 × 520 px) via `[📋 Tasks]`: task history with `[☐ / ☑]` recorded checkmarks, unrecorded and total elapsed time summary, and quick `[📂 Open CSV]` access.

---

## Getting Started

### Double-Click Launch:
Run `run.bat`. This starts the widget in the background via `pythonw.exe` without a terminal window.

### Command-Line Options:
```powershell
# Default launch on current desktop
python app.py

# Launch in Always-on-Top mode
python app.py --always-on-top

# Override desktop name
python app.py --desktop-name "Project Alpha"

# Custom data directory
python app.py --data-dir "C:\MyData\TimerRecords"
```

---

## Architecture and Files

- `app.py`: Application entry point, CLI arguments (`argparse`), error handling.
- `virtual_desktop.py`: Native Windows 11 Registry reader and COM `IVirtualDesktopManager` integration (`ctypes`).
- `models.py`: `TaskRecord` data model, duration formatting (`format_seconds`), task statuses.
- `storage.py`: `CsvTaskRepository`, atomic file writes (`.tmp` -> `.csv`), Excel lock handling.
- `timer_engine.py`: State machine (`TimerSessionController`) with drift-free `time.monotonic()` timekeeping and auto-pause/prompt logic.
- `ui_widget.py`: Minimalist floating Tkinter UI and expandable history panel.
- `logger_setup.py`: Rotating error logger (`error.log`, max 1 MB, 3 backups, `delay=True`).
- `tests/`: Pytest unit tests.

---

## Running Tests

```powershell
pytest tests -v
```
