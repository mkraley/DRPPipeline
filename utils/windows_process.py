"""
Windows process helpers for the dashboard run-status writer.

Uses Toolhelp32 / OpenProcess so we do not rely on ``os.kill(pid, 0)``,
which returns WinError 87 for other processes on Windows.
"""

from __future__ import annotations

import sys
from typing import Optional


def pid_alive(pid: int) -> bool:
    """Return True if ``pid`` is a live process on this OS."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _pid_alive_windows(pid)
    import os

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def terminal_pid(pid: int) -> Optional[int]:
    """
    Walk parents to find a PowerShell/cmd shell PID (Cursor terminal).

    Args:
        pid: Usually the Python process writing a run-status file.
    """
    if sys.platform != "win32":
        import os

        try:
            return os.getppid()
        except OSError:
            return None
    shells = {
        "powershell.exe",
        "pwsh.exe",
        "cmd.exe",
        "windows terminal.exe",
        "windowsterminal.exe",
    }
    current = int(pid)
    seen: set[int] = set()
    for _ in range(12):
        if current in seen or current <= 0:
            break
        seen.add(current)
        info = _process_info_windows(current)
        if info is None:
            break
        parent, _name = info
        if parent is None or parent <= 0:
            break
        parent_info = _process_info_windows(parent)
        parent_name = (parent_info[1] if parent_info else "") or ""
        if parent_name.lower() in shells:
            return parent
        current = parent
    return None


def _pid_alive_windows(pid: int) -> bool:
    """Windows liveness check via OpenProcess."""
    import ctypes

    process_query_limited_information = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        process_query_limited_information, False, int(pid)
    )
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    return False


def _process_info_windows(pid: int) -> Optional[tuple[int, str]]:
    """
    Return ``(parent_pid, exe_name)`` for ``pid``, or None if not found.
    """
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    th32cs_snapprocess = 0x00000002
    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
    if snapshot == -1:
        return None
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if not kernel32.Process32First(snapshot, ctypes.byref(entry)):
            return None
        while True:
            if int(entry.th32ProcessID) == int(pid):
                raw = entry.szExeFile
                if isinstance(raw, bytes):
                    name = raw.split(b"\0", 1)[0].decode("utf-8", errors="ignore")
                else:
                    name = str(raw)
                return int(entry.th32ParentProcessID), name
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    return None
