"""
Desktop Timer - Windows 11 Virtual Desktop Detector module.
Registry and Win32 COM (IVirtualDesktopManager) integration.
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

# Windows API constants
SW_RESTORE = 9
SW_SHOW = 5
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040
GA_ROOT = 2

# COM CLSID and IID definitions
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
    Windows 11 Virtual Desktop detector and state tracker.
    Reads desktop names from Registry and verifies window
    visibility via COM.
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

        # Discover initial state
        desktops = self.get_all_desktops()
        current_desktop = next((d for d in desktops if d.is_current), None)

        if target_desktop_id:
            matched = next((d for d in desktops if d.guid == target_desktop_id.upper()), None)
            if matched:
                self.assigned_desktop_id = matched.guid
                self.assigned_desktop_name = matched.name
            else:
                self.assigned_desktop_id = target_desktop_id.upper()
                self.assigned_desktop_name = target_desktop_name or f"Desktop ({self.assigned_desktop_id[:8]})"
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
                self.assigned_desktop_name = "Default Desktop"

    def _init_com(self) -> None:
        """Initializes IVirtualDesktopManager COM interface."""
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
                # IsWindowOnCurrentVirtualDesktop is the 4th method (index 3) in vtable
                self._is_on_current_fn = ctypes.WINFUNCTYPE(
                    ctypes.c_long,
                    ctypes.c_void_p,
                    wintypes.HWND,
                    ctypes.POINTER(wintypes.BOOL),
                )(vtable[3])
        except Exception as e:
            logger.warning(f"Failed to initialize COM VirtualDesktopManager: {e}")
            self._com_ptr = None
            self._is_on_current_fn = None

    def get_current_desktop_id_from_reg(self) -> Optional[str]:
        """Returns the GUID of the desktop currently active in Windows Explorer."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REG_PATH) as k:
                val, _ = winreg.QueryValueEx(k, "CurrentVirtualDesktop")
                if val and len(val) >= 16:
                    return str(uuid.UUID(bytes_le=bytes(val[:16]))).upper()
        except Exception:
            pass
        return None

    def get_all_desktops(self) -> list[VirtualDesktopInfo]:
        """Lists all registered virtual desktops with names and index."""
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
                    name = f"Desktop {idx}"
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
            logger.warning(f"Error reading virtual desktop registry data: {e}")

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
        """Refreshes desktop name if renamed by user in Windows."""
        desktops = self.get_all_desktops()
        for d in desktops:
            if d.guid == self.assigned_desktop_id:
                self.assigned_desktop_name = d.name
                return d.name
        return self.assigned_desktop_name

    def is_on_current_desktop(self, hwnd: Optional[int] = None) -> bool:
        """
        Determines whether the user is currently on this virtual desktop.
        Dual verification: COM IsWindowOnCurrentVirtualDesktop + Registry check.
        """
        # 1. COM check if valid top-level HWND exists
        if hwnd and self._com_ptr and self._is_on_current_fn:
            try:
                top_hwnd = ctypes.windll.user32.GetAncestor(hwnd, GA_ROOT) or hwnd
                is_curr = wintypes.BOOL()
                hr = self._is_on_current_fn(self._com_ptr, top_hwnd, ctypes.byref(is_curr))
                if hr == 0:
                    return bool(is_curr.value)
            except Exception:
                pass

        # 2. Registry-based comparison
        curr_reg_id = self.get_current_desktop_id_from_reg()
        if curr_reg_id and self.assigned_desktop_id:
            return curr_reg_id == self.assigned_desktop_id

        # Fallback to active if determination fails
        return True

    @staticmethod
    def bring_window_to_front(hwnd: int, keep_topmost: bool = False) -> None:
        """
        Brings the specified window to the foreground, restoring it if minimized.
        """
        try:
            user32 = ctypes.windll.user32
            top_hwnd = user32.GetAncestor(hwnd, GA_ROOT) or hwnd

            # Restore from minimized state if needed
            user32.ShowWindow(top_hwnd, SW_RESTORE)

            # Brief topmost pulse to bring window above others
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
                # Reset to normal z-order if keep_topmost is False
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
            logger.warning(f"Failed to bring window to front: {e}")
