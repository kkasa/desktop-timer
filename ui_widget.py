"""
Desktop Timer - Tkinter Grafikus Felület.
Minimalista lebegő widget és lenyitható feladat-áttekintő panel.
"""
from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from logger_setup import setup_logger
from models import TaskRecord, TaskStatus, format_seconds
from storage import CsvTaskRepository
from timer_engine import EngineState, TimerSessionController
from virtual_desktop import VirtualDesktopDetector

logger = setup_logger("desktop_timer.ui")

# Modern sötét színpaletta – Nagy kontraszt és fokozott olvashatóság
COLOR_BG = "#121417"               # Mély sötét háttér
COLOR_SURFACE = "#22262e"          # Kártyák, panelek és gombok
COLOR_SURFACE_HOVER = "#2f3540"    # Hover állapot
COLOR_ENTRY_BG = "#191c22"         # Beviteli mező háttere
COLOR_PRIMARY = "#2563eb"          # Élénk kék
COLOR_PRIMARY_HOVER = "#1d4ed8"    # Kék hover
COLOR_SUCCESS = "#16a34a"          # Élénk zöld jelvény és pipák
COLOR_WARNING = "#ea580c"          # Élénk narancs/borostyán jelvény
COLOR_DANGER = "#dc2626"           # Élénk piros befejezés gomb
COLOR_TEXT = "#ffffff"             # Tiszta fehér elsődleges szöveg
COLOR_TEXT_SECONDARY = "#cbd5e1"   # Világos szürke másodlagos szöveg
COLOR_MUTED = "#94a3b8"            # Slate tompított feliratok
COLOR_BORDER = "#3b4252"           # Finom, de jól látható keretek
COLOR_BANNER_BG = "#1e293b"        # Folytatás banner háttere
COLOR_BANNER_TEXT = "#f8fafc"      # Folytatás banner szövege


class DesktopTimerApp:
    def __init__(
        self,
        root: tk.Tk,
        detector: VirtualDesktopDetector,
        controller: TimerSessionController,
        always_on_top: bool = False,
    ) -> None:
        self.root = root
        self.detector = detector
        self.controller = controller
        self.always_on_top = always_on_top
        self.is_expanded: bool = False
        self._top_hwnd: Optional[int] = None
        self._current_task_id: Optional[str] = None

        self._setup_window()
        self._build_ui()
        self._refresh_ui_state()

        # Háttér ciklus indítása (300 ms ellenőrzés)
        self.root.after(300, self._poll_tick)

    def _setup_window(self) -> None:
        """Ablak kezdeti méretezése és stílusbeállításai."""
        desktop_name = self.detector.assigned_desktop_name
        self.root.title(f"Timer – {desktop_name}")
        self.root.configure(bg=COLOR_BG)
        self.root.minsize(420, 215)
        self.root.geometry("440x215")
        self.root.attributes("-topmost", self.always_on_top)

        # Alkalmazás ikon vagy fejléc beállítása
        try:
            # DPI skálázás támogatás Windows alatt
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    def _get_hwnd(self) -> Optional[int]:
        """Top-level Win32 ablak HWND lekérése."""
        if not self._top_hwnd:
            try:
                import ctypes
                cid = self.root.winfo_id()
                self._top_hwnd = ctypes.windll.user32.GetAncestor(cid, 2) or cid
            except Exception:
                self._top_hwnd = None
        return self._top_hwnd

    def _build_ui(self) -> None:
        """Komplett felhasználói felület felépítése."""
        self.main_container = tk.Frame(self.root, bg=COLOR_BG, padx=12, pady=10)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # 1. Fejléc sáv (Asztal név + Mindig felül + Taskok lenyitó)
        self.header_frame = tk.Frame(self.main_container, bg=COLOR_BG)
        self.header_frame.pack(fill=tk.X, pady=(0, 6))

        self.lbl_desktop = tk.Label(
            self.header_frame,
            text=f"🖥  {self.detector.assigned_desktop_name}",
            bg=COLOR_BG,
            fg=COLOR_TEXT,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        )
        self.lbl_desktop.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_topmost = tk.Button(
            self.header_frame,
            text="📌 Felül" if self.always_on_top else "📍 Normál",
            bg=COLOR_PRIMARY if self.always_on_top else COLOR_SURFACE,
            fg="#ffffff" if self.always_on_top else COLOR_TEXT,
            activebackground=COLOR_PRIMARY_HOVER,
            relief=tk.FLAT,
            padx=7,
            pady=2,
            font=("Segoe UI", 9, "bold"),
            command=self._toggle_always_on_top,
        )
        self.btn_topmost.pack(side=tk.RIGHT, padx=(6, 0))

        self.btn_tasks_toggle = tk.Button(
            self.header_frame,
            text="📋 Feladatok",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            activebackground=COLOR_SURFACE_HOVER,
            relief=tk.FLAT,
            padx=8,
            pady=2,
            font=("Segoe UI", 9, "bold"),
            command=self._toggle_tasks_panel,
        )
        self.btn_tasks_toggle.pack(side=tk.RIGHT)

        # 2. Előugró folytatás-kérdés sáv (rejtve, amíg nincs esemény)
        self.resume_banner = tk.Frame(
            self.main_container,
            bg=COLOR_BANNER_BG,
            padx=8,
            pady=6,
            highlightbackground=COLOR_WARNING,
            highlightthickness=1,
        )
        self.lbl_banner_prompt = tk.Label(
            self.resume_banner,
            text="Folytatod a megkezdett taskot?",
            bg=COLOR_BANNER_BG,
            fg=COLOR_BANNER_TEXT,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.lbl_banner_prompt.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_banner_resume = tk.Button(
            self.resume_banner,
            text="▶ Folytatás",
            bg=COLOR_SUCCESS,
            fg="#ffffff",
            relief=tk.FLAT,
            padx=8,
            pady=2,
            font=("Segoe UI", 9, "bold"),
            command=self._on_click_resume,
        )
        self.btn_banner_resume.pack(side=tk.RIGHT, padx=(6, 0))

        self.btn_banner_dismiss = tk.Button(
            self.resume_banner,
            text="✕",
            bg=COLOR_BANNER_BG,
            fg=COLOR_BANNER_TEXT,
            relief=tk.FLAT,
            padx=6,
            pady=2,
            font=("Segoe UI", 9, "bold"),
            command=self._dismiss_resume_banner,
        )
        self.btn_banner_dismiss.pack(side=tk.RIGHT)

        # 3. Digitális Óra és Státusz sor
        self.timer_frame = tk.Frame(self.main_container, bg=COLOR_BG)
        self.timer_frame.pack(fill=tk.X, pady=(2, 6))

        self.lbl_clock = tk.Label(
            self.timer_frame,
            text="00:00:00",
            bg=COLOR_BG,
            fg=COLOR_TEXT,
            font=("Consolas", 28, "bold"),
        )
        self.lbl_clock.pack(side=tk.LEFT)

        self.lbl_status = tk.Label(
            self.timer_frame,
            text="○ KÉSZENLÉT",
            bg="#334155",
            fg="#f8fafc",
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=3,
        )
        self.lbl_status.pack(side=tk.LEFT, padx=(12, 0))

        self.lbl_lock_warning = tk.Label(
            self.timer_frame,
            text="⚠️ CSV zárolva (Excel?)",
            bg=COLOR_BG,
            fg=COLOR_WARNING,
            font=("Segoe UI", 9, "bold"),
        )

        # 4. Task név szerkesztő mező
        self.task_entry_frame = tk.Frame(self.main_container, bg=COLOR_BG)
        self.task_entry_frame.pack(fill=tk.X, pady=(2, 8))

        self.task_var = tk.StringVar(value="")
        self.task_entry = tk.Entry(
            self.task_entry_frame,
            textvariable=self.task_var,
            bg=COLOR_ENTRY_BG,
            fg=COLOR_TEXT,
            insertbackground=COLOR_TEXT,
            relief=tk.FLAT,
            font=("Segoe UI", 11, "bold"),
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            highlightcolor=COLOR_PRIMARY,
        )
        self.task_entry.pack(fill=tk.X, ipady=6)
        self.task_entry.bind("<KeyRelease>", self._on_task_entry_key)
        self.task_entry.bind("<FocusOut>", self._on_task_name_changed)
        self.task_entry.bind("<Return>", self._on_task_name_changed)

        # 5. Vezérlőgombok sávja
        self.controls_frame = tk.Frame(self.main_container, bg=COLOR_BG)
        self.controls_frame.pack(fill=tk.X, pady=(0, 2))

        self.btn_start = tk.Button(
            self.controls_frame,
            text="▶ Indítás",
            bg=COLOR_PRIMARY,
            fg="#ffffff",
            activebackground=COLOR_PRIMARY_HOVER,
            relief=tk.FLAT,
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=5,
            command=self._on_click_start,
        )
        self.btn_start.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_pause = tk.Button(
            self.controls_frame,
            text="⏸ Szünet",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            activebackground=COLOR_SURFACE_HOVER,
            relief=tk.FLAT,
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=5,
            command=self._on_click_pause,
        )
        self.btn_pause.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_complete = tk.Button(
            self.controls_frame,
            text="⏹ Befejezés",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            activebackground=COLOR_SURFACE_HOVER,
            relief=tk.FLAT,
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=5,
            command=self._on_click_complete,
        )
        self.btn_complete.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_new_task = tk.Button(
            self.controls_frame,
            text="＋ Új",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            activebackground=COLOR_SURFACE_HOVER,
            relief=tk.FLAT,
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=5,
            command=self._on_click_new_task,
        )
        self.btn_new_task.pack(side=tk.RIGHT)

        # 6. Lenyitható Feladat panel (Task lista, összesítés, CSV nyitás)
        self.history_frame = tk.Frame(self.main_container, bg=COLOR_BG)

        # Elválasztó
        self.sep = tk.Frame(self.history_frame, bg=COLOR_BORDER, height=1)
        self.sep.pack(fill=tk.X, pady=(4, 6))

        # Görgethető lista konténer
        self.list_container = tk.Frame(self.history_frame, bg=COLOR_BG)
        self.list_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.list_container, bg=COLOR_BG, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.list_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.task_list_frame = tk.Frame(self.canvas, bg=COLOR_BG)

        self.task_list_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.task_list_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width),
        )

        # Lábjéc / összesítő sáv
        self.footer_frame = tk.Frame(self.history_frame, bg=COLOR_BG)
        self.footer_frame.pack(fill=tk.X, pady=(6, 0))

        self.lbl_totals = tk.Label(
            self.footer_frame,
            text="Nem rögzített: 00:00:00",
            bg=COLOR_BG,
            fg=COLOR_MUTED,
            font=("Segoe UI", 8),
            anchor="w",
        )
        self.lbl_totals.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_open_csv = tk.Button(
            self.footer_frame,
            text="📂 CSV megnyitása",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            activebackground=COLOR_SURFACE_HOVER,
            relief=tk.FLAT,
            font=("Segoe UI", 8),
            padx=6,
            pady=1,
            command=self._open_csv_file,
        )
        self.btn_open_csv.pack(side=tk.RIGHT)

    def _toggle_always_on_top(self) -> None:
        """Mindig felül (Always on Top) kapcsolása."""
        self.always_on_top = not self.always_on_top
        self.root.attributes("-topmost", self.always_on_top)
        self.btn_topmost.configure(
            text="📌 Felül" if self.always_on_top else "📍 Normál",
            bg=COLOR_PRIMARY if self.always_on_top else COLOR_SURFACE,
            fg="#ffffff" if self.always_on_top else COLOR_TEXT,
        )

    def _adjust_window_size(self) -> None:
        """Ablak magasságának finomhangolása a belső elemekhez (ha nincs lenyitva a lista)."""
        if not self.is_expanded:
            self.root.update_idletasks()
            h = max(215, self.root.winfo_reqheight())
            self.root.minsize(420, 215)
            self.root.geometry(f"440x{h}")

    def _toggle_tasks_panel(self) -> None:
        """Feladat lista lenyitása vagy összecsukása."""
        self.is_expanded = not self.is_expanded
        if self.is_expanded:
            self.history_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
            self.root.minsize(440, 480)
            self.root.geometry("440x520")
            self.btn_tasks_toggle.configure(bg=COLOR_PRIMARY, fg="#ffffff")
            self._render_task_list()
        else:
            self.history_frame.pack_forget()
            self._adjust_window_size()
            self.btn_tasks_toggle.configure(bg=COLOR_SURFACE, fg=COLOR_TEXT)

    def _render_task_list(self) -> None:
        """A korábbi feladatok dinamikus kirajzolása."""
        for widget in self.task_list_frame.winfo_children():
            widget.destroy()

        tasks = self.controller.get_all_tasks()
        if not tasks:
            lbl_empty = tk.Label(
                self.task_list_frame,
                text="Még nincs rögzített feladat ezen az Asztalon.",
                bg=COLOR_BG,
                fg=COLOR_MUTED,
                font=("Segoe UI", 9, "italic"),
                pady=14,
            )
            lbl_empty.pack()
        else:
            # Legfrissebb felül
            for task in reversed(tasks):
                row_frame = tk.Frame(
                    self.task_list_frame,
                    bg=COLOR_SURFACE,
                    padx=8,
                    pady=5,
                    highlightbackground=COLOR_BORDER,
                    highlightthickness=1,
                )
                row_frame.pack(fill=tk.X, pady=3)

                # Pipáló gomb (Kipipálás / Rögzítve)
                check_char = "☑" if task.recorded else "☐"
                check_color = COLOR_SUCCESS if task.recorded else COLOR_MUTED
                btn_check = tk.Button(
                    row_frame,
                    text=check_char,
                    bg=COLOR_SURFACE,
                    fg=check_color,
                    activebackground=COLOR_SURFACE_HOVER,
                    relief=tk.FLAT,
                    font=("Segoe UI", 12, "bold"),
                    padx=3,
                    pady=0,
                    command=lambda tid=task.task_id: self._on_toggle_recorded(tid),
                )
                btn_check.pack(side=tk.LEFT)

                # Task név és státusz
                name_frame = tk.Frame(row_frame, bg=COLOR_SURFACE)
                name_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 4))

                name_fg = COLOR_MUTED if task.recorded else COLOR_TEXT
                lbl_name = tk.Label(
                    name_frame,
                    text=task.task_name,
                    bg=COLOR_SURFACE,
                    fg=name_fg,
                    font=("Segoe UI", 10, "bold" if not task.recorded else "normal"),
                    anchor="w",
                )
                lbl_name.pack(fill=tk.X)

                status_text = "Befejezve" if task.status == TaskStatus.COMPLETED else "Folyamatban"
                lbl_sub = tk.Label(
                    name_frame,
                    text=f"{status_text} • {task.started_at[:16]}",
                    bg=COLOR_SURFACE,
                    fg=COLOR_MUTED,
                    font=("Segoe UI", 8),
                    anchor="w",
                )
                lbl_sub.pack(fill=tk.X)

                # Időtartam felirat
                lbl_duration = tk.Label(
                    row_frame,
                    text=task.formatted_duration,
                    bg=COLOR_SURFACE,
                    fg="#38bdf8" if not task.recorded else COLOR_MUTED,
                    font=("Consolas", 11, "bold"),
                )
                lbl_duration.pack(side=tk.RIGHT, padx=(6, 4))

                # Folytatás gomb, ha még nincs rögzítve és nem fut
                if not task.recorded:
                    btn_resume = tk.Button(
                        row_frame,
                        text="▶",
                        bg=COLOR_SURFACE_HOVER,
                        fg=COLOR_PRIMARY,
                        relief=tk.FLAT,
                        font=("Segoe UI", 9, "bold"),
                        padx=6,
                        pady=1,
                        command=lambda tid=task.task_id: self._on_resume_from_list(tid),
                    )
                    btn_resume.pack(side=tk.RIGHT)

        # Összesítések frissítése
        unrecorded, total = self.controller.get_totals()
        self.lbl_totals.configure(
            text=f"Nem rögzített: {format_seconds(unrecorded)}  |  Összes: {format_seconds(total)}",
            font=("Segoe UI", 9, "bold"),
            fg=COLOR_TEXT_SECONDARY,
        )
        self.btn_open_csv.configure(
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=3,
        )
        self._update_tasks_button_badge(tasks)

    def _update_tasks_button_badge(self, tasks: Optional[list[TaskRecord]] = None) -> None:
        """A fejlécben lévő 'Feladatok' gomb számlálójának frissítése."""
        if tasks is None:
            tasks = self.controller.get_all_tasks()
        unrec_count = sum(1 for t in tasks if not t.recorded)
        if unrec_count > 0:
            self.btn_tasks_toggle.configure(text=f"📋 Feladatok ({unrec_count})")
        else:
            self.btn_tasks_toggle.configure(text="📋 Feladatok")

    def _refresh_ui_state(self) -> None:
        """Gombok, óra és státuszcímke szinkronizálása a kontroller állapotával."""
        state = self.controller.state
        active = self.controller.active_task

        is_entry_focused = False
        try:
            is_entry_focused = (self.root.focus_get() == self.task_entry)
        except Exception:
            is_entry_focused = False

        active_id = active.task_id if active else None
        if active:
            self.lbl_clock.configure(text=active.formatted_duration)
            if active_id != self._current_task_id:
                self._current_task_id = active_id
                self.task_var.set(active.task_name)
            elif not is_entry_focused and not self.task_var.get().strip():
                self.task_var.set(active.task_name)
        else:
            self.lbl_clock.configure(text="00:00:00")
            if active_id != self._current_task_id:
                self._current_task_id = None
                if not is_entry_focused:
                    self.task_var.set("")

        if state == EngineState.RUNNING:
            self.lbl_status.configure(text="● MÉRÉS ALATT", bg=COLOR_SUCCESS, fg="#ffffff")
            self.btn_start.configure(
                text="▶ Fut",
                bg="#1e293b",
                fg="#64748b",
                state=tk.DISABLED,
            )
            self.btn_pause.configure(state=tk.NORMAL, bg=COLOR_SURFACE, fg=COLOR_TEXT)
            self.btn_complete.configure(state=tk.NORMAL, bg=COLOR_DANGER, fg="#ffffff")
            self._hide_resume_banner()
        elif state == EngineState.PAUSED:
            self.lbl_status.configure(text="⏸ SZÜNETEL", bg=COLOR_WARNING, fg="#ffffff")
            self.btn_start.configure(
                text="▶ Folytatás",
                bg=COLOR_PRIMARY,
                fg="#ffffff",
                state=tk.NORMAL,
            )
            self.btn_pause.configure(state=tk.DISABLED, bg="#1e293b", fg="#64748b")
            self.btn_complete.configure(state=tk.NORMAL, bg=COLOR_SURFACE, fg=COLOR_TEXT)
        elif state == EngineState.PROMPT_RESUME:
            self.lbl_status.configure(text="↩ VISSZATÉRTÉL", bg=COLOR_PRIMARY, fg="#ffffff")
            self.btn_start.configure(
                text="▶ Folytatás",
                bg=COLOR_SUCCESS,
                fg="#ffffff",
                state=tk.NORMAL,
            )
            self.btn_pause.configure(state=tk.DISABLED, bg="#1e293b", fg="#64748b")
            self.btn_complete.configure(state=tk.NORMAL, bg=COLOR_SURFACE, fg=COLOR_TEXT)
            self._show_resume_banner()
        else:  # IDLE
            self.lbl_status.configure(text="○ KÉSZENLÉT", bg="#334155", fg="#f8fafc")
            self.btn_start.configure(
                text="▶ Indítás",
                bg=COLOR_PRIMARY,
                fg="#ffffff",
                state=tk.NORMAL,
            )
            self.btn_pause.configure(state=tk.DISABLED, bg="#1e293b", fg="#64748b")
            self.btn_complete.configure(state=tk.DISABLED, bg="#1e293b", fg="#64748b")
            self._hide_resume_banner()

        # CSV zárolás jelzése
        if self.controller.repo.is_locked:
            self.lbl_lock_warning.pack(side=tk.RIGHT)
        else:
            self.lbl_lock_warning.pack_forget()

        self._update_tasks_button_badge()

    def _show_resume_banner(self) -> None:
        """Megjeleníti a 'Folytatod a megkezdett taskot?' sávot."""
        task_name = "feladat"
        if self.controller.active_task:
            task_name = f"'{self.controller.active_task.task_name}'"
        self.lbl_banner_prompt.configure(text=f"Folytatod: {task_name}?")
        self.resume_banner.pack(fill=tk.X, pady=(0, 4), before=self.timer_frame)
        self._adjust_window_size()

    def _hide_resume_banner(self) -> None:
        """Elrejti az előugró folytatás sávot."""
        self.resume_banner.pack_forget()
        self._adjust_window_size()

    def _dismiss_resume_banner(self) -> None:
        """Elveti a felugró folytatás ajánlatot."""
        self._hide_resume_banner()
        if self.controller.state == EngineState.PROMPT_RESUME:
            self.controller.state = EngineState.PAUSED
        self._refresh_ui_state()

    def _on_click_start(self) -> None:
        """Indítás / Folytatás gomb megnyomása."""
        if self.controller.state in (EngineState.PAUSED, EngineState.PROMPT_RESUME) and self.controller.active_task:
            # Meglévő folytatása
            name = self.task_var.get().strip()
            if name:
                self.controller.active_task.task_name = name
            self.controller.resume_task()
        else:
            # Új task indítása
            name = self.task_var.get().strip() or "Új munkafolyamat"
            self.controller.start_new_task(name)

        self._refresh_ui_state()
        if self.is_expanded:
            self._render_task_list()

    def _on_click_resume(self) -> None:
        """Bannerből indított folytatás."""
        self._on_click_start()

    def _on_click_pause(self) -> None:
        """Szüneteltetés gomb megnyomása."""
        name = self.task_var.get().strip()
        if name and self.controller.active_task:
            self.controller.active_task.task_name = name
        self.controller.pause_active_task()
        self._refresh_ui_state()
        if self.is_expanded:
            self._render_task_list()

    def _on_click_complete(self) -> None:
        """Feladat befejezése és lezárása."""
        name = self.task_var.get().strip()
        self.controller.complete_active_task(final_name=name)
        self._current_task_id = None
        self.task_var.set("")
        self._refresh_ui_state()
        if self.is_expanded:
            self._render_task_list()

    def _on_click_new_task(self) -> None:
        """Új task indítása (ha volt korábbi, megkérdezi vagy lezárja)."""
        if self.controller.state == EngineState.RUNNING:
            if messagebox.askyesno("Új feladat indítása", "A futó feladatot befejezed és elindítasz egy újat?"):
                self._on_click_complete()
                self.task_entry.focus_set()
        else:
            if self.controller.active_task:
                self.controller.complete_active_task()
            self._current_task_id = None
            self.task_var.set("")
            self.task_entry.focus_set()
            self._refresh_ui_state()
            if self.is_expanded:
                self._render_task_list()

    def _on_resume_from_list(self, task_id: str) -> None:
        """Feladat folytatása közvetlenül a listából."""
        self.controller.resume_task(task_id)
        self._refresh_ui_state()
        self._render_task_list()

    def _on_toggle_recorded(self, task_id: str) -> None:
        """Task rögzítettségének váltása a listában."""
        self.controller.toggle_recorded(task_id)
        self._render_task_list()

    def _on_task_entry_key(self, event=None) -> None:
        """Gépelés közben valós időben szinkronizáljuk a task nevét a memóriában."""
        new_name = self.task_var.get().strip()
        if new_name and self.controller.active_task:
            self.controller.active_task.task_name = new_name

    def _on_task_name_changed(self, event=None) -> None:
        """Task név mező elhagyása (FocusOut) vagy Enter leütése -> lemezre írás."""
        new_name = self.task_var.get().strip()
        if new_name and self.controller.active_task:
            self.controller.active_task.task_name = new_name
            self.controller.repo.upsert_task(self.controller.active_task)
            if self.is_expanded:
                self._render_task_list()
        elif not new_name and self.controller.active_task:
            # Ha üresen hagyták el a mezőt, visszaállítjuk az aktív task nevét
            self.task_var.set(self.controller.active_task.task_name)

        if event and getattr(event, "keysym", "") == "Return":
            self.root.focus_set()

    def _open_csv_file(self) -> None:
        """CSV fájl vagy mappa megnyitása az Intézőben / Excelben."""
        csv_path = self.controller.repo.csv_path
        try:
            if csv_path.exists():
                os.startfile(str(csv_path))
            else:
                os.startfile(str(self.controller.repo.data_dir))
        except Exception as e:
            messagebox.showerror("Megnyitási hiba", f"Nem sikerült megnyitni a fájlt: {e}")

    def _poll_tick(self) -> None:
        """
        Rendszeres háttérciklus:
        1. Ellenőrzi, hogy a felhasználó még ezen az Asztalon van-e.
        2. Ha elhagyta: auto-pause.
        3. Ha visszatért: előtérbe hozás + folytatás ajánlása.
        4. Időmérő frissítése.
        """
        hwnd = self._get_hwnd()
        is_on_desktop = self.detector.is_on_current_desktop(hwnd)

        prompt_needed, target_task = self.controller.handle_desktop_visibility_change(is_on_desktop)

        if prompt_needed and hwnd:
            # Visszatértünk az Asztalra -> előtérbe ugrik a widget és felajánlja a folytatást
            self.detector.bring_window_to_front(hwnd, keep_topmost=self.always_on_top)
            self._show_resume_banner()

        if self.controller.state == EngineState.RUNNING:
            seconds = self.controller.tick()
            self.lbl_clock.configure(text=format_seconds(seconds))
            if self.is_expanded:
                # 5 másodpercenként frissítjük a kibontott listát is futás közben
                if seconds % 5 == 0:
                    self._render_task_list()

        # Ha közben megváltozott a státusz (pl. auto-pause miatt)
        self._refresh_ui_state()

        self.root.after(300, self._poll_tick)

