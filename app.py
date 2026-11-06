"""
Desktop Timer - Main Application Entrypoint.
Windows 11 virtual desktop-aware multi-instance work timer.
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

# Configure Windows console UTF-8 compatibility
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Desktop Timer – Windows 11 Virtual Desktop-aware work timer."
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Directory for storing CSV data files (default: ./data).",
    )
    parser.add_argument(
        "--desktop-name",
        type=str,
        default=None,
        help="Custom desktop name override (e.g. 'Project Alpha').",
    )
    parser.add_argument(
        "--desktop-id",
        type=str,
        default=None,
        help="Windows Virtual Desktop GUID override.",
    )
    parser.add_argument(
        "--always-on-top",
        action="store_true",
        help="Keep widget always on top of other windows.",
    )
    parser.add_argument(
        "--delimiter",
        type=str,
        default=";",
        help="CSV column delimiter character (default: semicolon for Excel compatibility).",
    )
    return parser.parse_args()


def main() -> int:
    logger = setup_logger("desktop_timer")

    try:
        args = parse_args()

        # Resolve data directory
        base_dir = Path(__file__).resolve().parent
        env_data_dir = os.environ.get("DESKTOP_TIMER_DATA_DIR")
        if args.data_dir:
            data_dir = Path(args.data_dir).resolve()
        elif env_data_dir:
            data_dir = Path(env_data_dir).resolve()
        else:
            data_dir = base_dir / "data"

        data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Virtual Desktop detector
        detector = VirtualDesktopDetector(
            target_desktop_name=args.desktop_name,
            target_desktop_id=args.desktop_id,
        )

        # Instantiate CSV repository and Timer controller
        repository = CsvTaskRepository(
            data_dir=data_dir,
            desktop_name=detector.assigned_desktop_name,
            delimiter=args.delimiter,
        )

        controller = TimerSessionController(repository=repository)

        # Start Tkinter UI
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
        print(f"Configuration error: {ce}", file=sys.stderr)
        return 2
    except Exception as e:
        logger.exception("An unexpected error occurred while running Desktop Timer.")
        log_path = Path(__file__).resolve().parent / "error.log"
        print(f"An error occurred: {e} (Details in log: {log_path})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
