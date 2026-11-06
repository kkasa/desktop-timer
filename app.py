"""
Desktop Timer - Fő belépési pont (Application Entrypoint).
Több példányban futtatható Windows 11 asztali időmérő.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tkinter as tk

from logger_setup import ConfigError, setup_logger
from storage import CsvTaskRepository
from timer_engine import TimerSessionController
from ui_widget import DesktopTimerApp
from virtual_desktop import VirtualDesktopDetector

# Windows konzol UTF-8 kompatibilitás beállítása
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Desktop Timer – Windows 11 Virtuális Asztal-érzékeny munkaidő mérő."
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="A CSV adatfájlok tárolási könyvtára (alapértelmezett: ./data).",
    )
    parser.add_argument(
        "--desktop-name",
        type=str,
        default=None,
        help="Egyedi Asztal név felülbírálás (pl. 'Projekt Alpha').",
    )
    parser.add_argument(
        "--desktop-id",
        type=str,
        default=None,
        help="Windows Virtuális Asztal GUID azonosító felülbírálás.",
    )
    parser.add_argument(
        "--always-on-top",
        action="store_true",
        help="A widget mindig felül maradjon az ablakok felett.",
    )
    parser.add_argument(
        "--delimiter",
        type=str,
        default=";",
        help="CSV oszlopelválasztó karakter (alapértelmezett: pontosvessző a magyar Excelhez).",
    )
    return parser.parse_args()


def main() -> int:
    logger = setup_logger("desktop_timer")

    try:
        args = parse_args()

        # Adatkönyvtár feloldása
        base_dir = Path(__file__).resolve().parent
        env_data_dir = os.environ.get("DESKTOP_TIMER_DATA_DIR")
        if args.data_dir:
            data_dir = Path(args.data_dir).resolve()
        elif env_data_dir:
            data_dir = Path(env_data_dir).resolve()
        else:
            data_dir = base_dir / "data"

        data_dir.mkdir(parents=True, exist_ok=True)

        # Virtuális Asztal detektor inicializálása
        detector = VirtualDesktopDetector(
            target_desktop_name=args.desktop_name,
            target_desktop_id=args.desktop_id,
        )

        # CSV Adattár és Időmérő motor példányosítása
        repository = CsvTaskRepository(
            data_dir=data_dir,
            desktop_name=detector.assigned_desktop_name,
            delimiter=args.delimiter,
        )

        controller = TimerSessionController(repository=repository)

        # Tkinter UI indítása
        root = tk.Tk()
        app = DesktopTimerApp(
            root=root,
            detector=detector,
            controller=controller,
            always_on_top=args.always_on_top,
        )

        root.mainloop()
        return 0

    except ConfigError as ce:
        print(f"Konfigurációs hiba: {ce}", file=sys.stderr)
        return 2
    except Exception as e:
        logger.exception("Váratlan hiba történt a Desktop Timer futása közben.")
        log_path = Path(__file__).resolve().parent / "error.log"
        print(f"Hiba történt: {e} (Részletek a naplóban: {log_path})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

