"""
Resolve a stable id for the interactive shell that launched this process.

``os.getppid()`` is often a short-lived launcher, not the PowerShell or cmd
window the user types in. Walking parents to the nearest shell keeps the
DataLumos session file keyed to that window across consecutive commands.
"""

from __future__ import annotations

import os
import sys
from typing import Callable

_SHELL_NAMES = frozenset(
    {
        "powershell.exe",
        "pwsh.exe",
        "cmd.exe",
        "bash.exe",
        "zsh.exe",
        "fish.exe",
        "sh.exe",
    }
)


def resolve_terminal_id(
    getenv: Callable[[str], str | None] | None = None,
    getppid: Callable[[], int] | None = None,
    parents: Callable[[], dict[int, tuple[int, str]]] | None = None,
) -> int:
    """
    Return the process id used to name this terminal's session file.

    Args:
        getenv: Environment lookup; defaults to ``os.getenv``.
        getppid: Immediate parent id; defaults to ``os.getppid``.
        parents: Optional ``pid -> (parent_pid, exe_name)`` map for tests.

    Returns:
        ``DRP_TERMINAL_ID`` when set, else the nearest shell ancestor, else
        the immediate parent process id.
    """
    env = getenv or os.getenv
    override = (env("DRP_TERMINAL_ID") or "").strip()
    if override.isdigit():
        return int(override)
    parent = (getppid or os.getppid)()
    tree = parents() if parents is not None else _process_parents()
    shell = _nearest_shell_pid(parent, tree)
    return shell if shell is not None else parent


def _nearest_shell_pid(start: int, tree: dict[int, tuple[int, str]]) -> int | None:
    """Walk parents from ``start`` and return the first recognized shell."""
    seen: set[int] = set()
    current = start
    while current and current not in seen:
        seen.add(current)
        info = tree.get(current)
        if info is None:
            return None
        parent_pid, name = info
        if name.casefold() in _SHELL_NAMES:
            return current
        current = parent_pid
    return None


def _process_parents() -> dict[int, tuple[int, str]]:
    """Return ``pid -> (parent_pid, executable name)`` for this machine."""
    if sys.platform == "win32":
        return _windows_process_parents()
    return _posix_process_parents()


def _posix_process_parents() -> dict[int, tuple[int, str]]:
    """Build a parent map from ``/proc`` when available."""
    result: dict[int, tuple[int, str]] = {}
    proc = os.path.join(os.sep, "proc")
    if not os.path.isdir(proc):
        return result
    for name in os.listdir(proc):
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            with open(os.path.join(proc, name, "stat"), encoding="utf-8") as handle:
                fields = handle.read().split()
            with open(os.path.join(proc, name, "comm"), encoding="utf-8") as handle:
                comm = handle.read().strip()
            result[pid] = (int(fields[3]), comm)
        except (OSError, IndexError, ValueError):
            continue
    return result


def _windows_process_parents() -> dict[int, tuple[int, str]]:
    """Build a parent map with Toolhelp32 (no extra packages)."""
    import ctypes
    from ctypes import wintypes

    th32cs_snapprocess = 0x00000002
    invalid_handle = wintypes.HANDLE(-1).value

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    snapshot = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
    if snapshot == invalid_handle:
        return {}
    entry = ProcessEntry32W()
    entry.dwSize = ctypes.sizeof(ProcessEntry32W)
    result: dict[int, tuple[int, str]] = {}
    try:
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            result[int(entry.th32ProcessID)] = (
                int(entry.th32ParentProcessID),
                str(entry.szExeFile or ""),
            )
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return result
