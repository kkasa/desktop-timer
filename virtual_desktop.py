"""
Desktop Timer - Windows 11 Virtuális Asztal Detektor modul.
Registry és Win32 COM (IVirtualDesktopManager) integráció.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
from typing import Optional
import uuid
import winreg

from logger_setup import setup_logger

logger = setup_logger("desktop_timer.virtual_desktop")

# Windows API konstansok
SW_RESTORE = 9
SW_SHOW = 5
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040
GA_ROOT = 2

# COM CLSID és IID definíciók
CLSID_VirtualDesktopManager = uuid.UUID("{aa509086-5ca9-4c25-8f95-589d3c07b48a}")
IID_IVirtualDesktopManager = uuid.UUID("{a5cd92ff-29be-454c-8d04-d82879fb3f1b}")


class VirtualDesktopInfo:
    def __init__(self, guid: str, name: str, index: int, is_current: bool = False):
        self.guid = guid.upper()
        self.name = name
        self.index = index
        self.is_current = is_current

    def __repr__(self) -> str:
        return f"<VirtualDesktop #{self.index}: '{self.name}' ({self.guid}) current={self.is_current}>"


class VirtualDesktopDetector:
    """
    Windows 11 Virtuális Asztal felismerő és állapotkövető.
    Kiolvassa az asztalok neveit a Registryből, és COM-on keresztül ellenőrzi
    az ablak aktuális láthatóságát.
    """

    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops"

    def __init__(
        self,
        target_desktop_name: Optional[str] = None,
        target_desktop_id: Optional[str] = None,
    ) -> None:
        self._com_ptr: Optional[ctypes.c_void_p] = None
        self._is_on_current_fn = None
        self._init_com()

        # Kezdeti állapot felderítése
        desktops = self.get_all_desktops()
        current_desktop = next((d for d in desktops if d.is_current), None)

        if target_desktop_id:
            matched = next((d for d in desktops if d.guid == target_desktop_id.upper()), None)
            if matched:
                self.assigned_desktop_id = matched.guid
                self.assigned_desktop_name = matched.name
            else:
                self.assigned_desktop_id = target_desktop_id.upper()
                self.assigned_desktop_name = target_desktop_name or f"Asztal ({self.assigned_desktop_id[:8]})"
        elif target_desktop_name:
            matched = next((d for d in desktops if d.name.lower() == target_desktop_name.lower()), None)
            if matched:
                self.assigned_desktop_id = matched.guid
                self.assigned_desktop_name = matched.name
            else:
                self.assigned_desktop_id = current_desktop.guid if current_desktop else str(uuid.uuid4()).upper()
                self.assigned_desktop_name = target_desktop_name
        else:
            if current_desktop:
                self.assigned_desktop_id = current_desktop.guid
                self.assigned_desktop_name = current_desktop.name
            else:
                self.assigned_desktop_id = str(uuid.uuid4()).upper()
                self.assigned_desktop_name = "Alapértelmezett Asztal"

    def _init_com(self) -> None:
        """IVirtualDesktopManager COM interfész inicializálása."""
        try:
            ole32 = ctypes.windll.ole32
            ole32.CoInitialize(None)
            ptr = ctypes.c_void_p()
            hr = ole32.CoCreateInstance(
                CLSID_VirtualDesktopManager.bytes_le,
                None,
                1,  # CLSCTX_INPROC_SERVER
                IID_IVirtualDesktopManager.bytes_le,
                ctypes.byref(ptr),
            )
            if hr == 0 and ptr.value:
                self._com_ptr = ptr
                vtable = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
                # IsWindowOnCurrentVirtualDesktop a vtable 3. metódusa
                self._is_on_current_fn = ctypes.WINFUNCTYPE(
                    ctypes.c_long,
                    ctypes.c_void_p,
                    wintypes.HWND,
                    ctypes.POINTER(wintypes.BOOL),
                )(vtable[3])
        except Exception as e:
            logger.warning(f"Nem sikerült inicializálni a COM VirtualDesktopManagert: {e}")
            self._com_ptr = None
            self._is_on_current_fn = None

    def get_current_desktop_id_from_reg(self) -> Optional[str]:
        """A Windows Explorer által éppen megjelenített virtuális asztal GUID-ja."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REG_PATH) as k:
                val, _ = winreg.QueryValueEx(k, "CurrentVirtualDesktop")
                if val and len(val) >= 16:
                    return str(uuid.UUID(bytes_le=bytes(val[:16]))).upper()
        except Exception:
            pass
        return None

    def get_all_desktops(self) -> list[VirtualDesktopInfo]:
        """Minden regisztrált virtuális asztal listázása névvel és sorszámmal."""
        result: list[VirtualDesktopInfo] = []
        try:
            curr_id = self.get_current_desktop_id_from_reg()
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REG_PATH) as k:
                try:
                    all_bytes, _ = winreg.QueryValueEx(k, "VirtualDesktopIDs")
                    num_ids = len(all_bytes) // 16
                    all_guids = [
                        str(uuid.UUID(bytes_le=bytes(all_bytes[i * 16 : (i + 1) * 16]))).upper()
                        for i in range(num_ids)
                    ]
                except FileNotFoundError:
                    all_guids = [curr_id] if curr_id else []

                for idx, guid in enumerate(all_guids, 1):
                    name = f"Asztal {idx}"
                    try:
                        with winreg.OpenKey(k, f"Desktops\\{{{guid}}}") as desk_k:
                            try:
                                reg_name, _ = winreg.QueryValueEx(desk_k, "Name")
                                if reg_name and str(reg_name).strip():
                                    name = str(reg_name).strip()
                            except FileNotFoundError:
                                pass
                    except FileNotFoundError:
                        pass

                    result.append(
                        VirtualDesktopInfo(
                            guid=guid,
                            name=name,
                            index=idx,
                            is_current=(guid == curr_id),
                        )
                    )
        except Exception as e:
            logger.warning(f"Hiba az asztalok regisztrációs adatainak olvasásakor: {e}")

        if not result and self.assigned_desktop_name:
            result.append(
                VirtualDesktopInfo(
                    guid=self.assigned_desktop_id or "DEFAULT",
                    name=self.assigned_desktop_name,
                    index=1,
                    is_current=True,
                )
            )
        return result

    def refresh_desktop_name(self) -> str:
        """Ha a felhasználó átnevezte az asztalt a Windowsban, lekéri a frissített nevet."""
        desktops = self.get_all_desktops()
        for d in desktops:
            if d.guid == self.assigned_desktop_id:
                self.assigned_desktop_name = d.name
                return d.name
        return self.assigned_desktop_name

    def is_on_current_desktop(self, hwnd: Optional[int] = None) -> bool:
        """
        Megvizsgálja, hogy a felhasználó éppen ezen az asztalon van-e.
        Kettős ellenőrzés: COM IsWindowOnCurrentVirtualDesktop + Registry ellenőrzés.
        """
        # 1. COM ellenőrzés ha van érvényes top-level HWND
        if hwnd and self._com_ptr and self._is_on_current_fn:
            try:
                # Biztosítjuk, hogy a GA_ROOT szintű HWND-vel kérdezzünk
                top_hwnd = ctypes.windll.user32.GetAncestor(hwnd, GA_ROOT) or hwnd
                is_curr = wintypes.BOOL()
                hr = self._is_on_current_fn(self._com_ptr, top_hwnd, ctypes.byref(is_curr))
                if hr == 0:
                    return bool(is_curr.value)
            except Exception:
                pass

        # 2. Registry alapú összehasonlítás
        curr_reg_id = self.get_current_desktop_id_from_reg()
        if curr_reg_id and self.assigned_desktop_id:
            return curr_reg_id == self.assigned_desktop_id

        # Ha nem sikerült eldönteni, alapértelmezetten aktívnak tekintjük
        return True

    @staticmethod
    def bring_window_to_front(hwnd: int, keep_topmost: bool = False) -> None:
        """
        A megadott ablakot előtérbe hozza, visszaállítja ha minimalizálva volt.
        """
        try:
            user32 = ctypes.windll.user32
            top_hwnd = user32.GetAncestor(hwnd, GA_ROOT) or hwnd

            # Visszaállítás minimalizált állapotból ha szükséges
            user32.ShowWindow(top_hwnd, SW_RESTORE)

            # Rövid TOPMOST impulzus, hogy a többi ablak fölé ugorjon
            user32.SetWindowPos(
                top_hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
            )
            user32.SetForegroundWindow(top_hwnd)

            if not keep_topmost:
                # Ha nem kért 'Mindig felül' módot, visszaállítjuk normál rétegre
                user32.SetWindowPos(
                    top_hwnd,
                    HWND_NOTOPMOST,
                    0,
                    0,
                    0,
                    0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
                )
        except Exception as e:
            logger.warning(f"Nem sikerült előtérbe hozni az ablakot: {e}")

