"""Exclusive slug locks for article pipeline runs."""

from __future__ import annotations

import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import PipelineError
from .store import RunStore


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def process_is_alive(pid: object) -> bool | None:
    if not isinstance(pid, int) or pid <= 0:
        return None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        error_access_denied = 5
        error_invalid_parameter = 87
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if error == error_invalid_parameter:
                return False
            if error == error_access_denied:
                return True
            return None
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return None
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


class SlugLock:
    def __init__(self, store: RunStore, slug: str, run_id: str) -> None:
        self.store = store
        self.slug = slug
        self.run_id = run_id
        self.relative = Path("locks") / f"{slug}.lock"
        self.acquired = False

    def acquire(self) -> None:
        payload = {
            "hostname": platform.node(),
            "pid": os.getpid(),
            "run_id": self.run_id,
            "started_at": utc_now(),
        }
        try:
            self.store.create_exclusive_json(self.relative, payload)
        except FileExistsError as exc:
            holder = self.read_holder(self.store, self.slug)
            raise PipelineError(
                "slug のロックを取得できません: "
                f"slug={self.slug}, holder_run_id={holder.get('run_id')}, "
                f"holder_pid={holder.get('pid')}, holder_started_at={holder.get('started_at')}, "
                f"process_alive={process_is_alive(holder.get('pid'))}"
            ) from exc
        self.acquired = True

    def release(self) -> None:
        if not self.acquired:
            return
        holder = self.read_holder(self.store, self.slug)
        if holder.get("run_id") != self.run_id or holder.get("pid") != os.getpid():
            raise PipelineError(
                "所有者が異なるためロックを解放できません: "
                f"slug={self.slug}, expected_run_id={self.run_id}, "
                f"actual_run_id={holder.get('run_id')}, actual_pid={holder.get('pid')}"
            )
        self.store.remove(self.relative)
        self.acquired = False

    def __enter__(self) -> "SlugLock":
        self.acquire()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.release()

    @staticmethod
    def read_holder(store: RunStore, slug: str) -> dict[str, Any]:
        relative = Path("locks") / f"{slug}.lock"
        data = store.read_json(relative)
        if not isinstance(data, dict):
            raise PipelineError(
                f"ロックファイルの形式が不正です: path={store.path(relative)}, value_type={type(data).__name__}"
            )
        return data
