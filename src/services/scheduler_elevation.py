import ctypes
import json
import subprocess
import sys
import uuid
from ctypes import wintypes
from pathlib import Path

from src.services.windows_identity import current_windows_identity


SEE_MASK_NOCLOSEPROCESS = 0x00000040
SW_HIDE = 0
INFINITE = 0xFFFFFFFF
ERROR_CANCELLED = 1223


class ShellExecuteInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND), ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE), ("lpIDList", wintypes.LPVOID),
        ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


class SchedulerElevator:
    """Run only Task Scheduler mutations in an elevated copy of this program."""

    def __init__(self, data_directory: Path) -> None:
        self.exchange_directory = data_directory / "scheduler"

    def apply(self, values: dict[str, object]) -> None:
        self.exchange_directory.mkdir(parents=True, exist_ok=True)
        identity = current_windows_identity()
        request_values = {
            **values,
            "_scheduler_user_id": identity.user_id,
            "_scheduler_user_sid": identity.sid,
        }
        identifier = uuid.uuid4().hex
        request_path = self.exchange_directory / f"request-{identifier}.json"
        result_path = self.exchange_directory / f"result-{identifier}.json"
        request_path.write_text(json.dumps(request_values, ensure_ascii=False), encoding="utf-8")
        try:
            exit_code = self._run_elevated(request_path, result_path)
            result = self._read_result(result_path)
            if exit_code != 0 or not result.get("ok"):
                message = result.get("error") or "작업 스케줄러 설정을 변경하지 못했습니다."
                raise RuntimeError(str(message))
        finally:
            request_path.unlink(missing_ok=True)
            result_path.unlink(missing_ok=True)

    @staticmethod
    def _command(request_path: Path, result_path: Path) -> tuple[str, str]:
        helper_arguments = ["--scheduler-helper", str(request_path), str(result_path)]
        if getattr(sys, "frozen", False):
            return sys.executable, subprocess.list2cmdline(helper_arguments)
        arguments = ["-m", "src.main", *helper_arguments]
        return sys.executable, subprocess.list2cmdline(arguments)

    def _run_elevated(self, request_path: Path, result_path: Path) -> int:
        if sys.platform != "win32":
            raise RuntimeError("작업 스케줄러 설정은 Windows에서만 사용할 수 있습니다.")
        executable, parameters = self._command(request_path, result_path)
        info = ShellExecuteInfo()
        info.cbSize = ctypes.sizeof(info)
        info.fMask = SEE_MASK_NOCLOSEPROCESS
        info.lpVerb = "runas"
        info.lpFile = executable
        info.lpParameters = parameters
        info.nShow = SW_HIDE
        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
            error_code = ctypes.windll.kernel32.GetLastError()
            if error_code == ERROR_CANCELLED:
                raise RuntimeError("관리자 권한 요청이 취소되었습니다.")
            raise RuntimeError(f"관리자 권한으로 실행하지 못했습니다. (오류 {error_code})")
        try:
            ctypes.windll.kernel32.WaitForSingleObject(info.hProcess, INFINITE)
            exit_code = wintypes.DWORD()
            ctypes.windll.kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code))
            return int(exit_code.value)
        finally:
            ctypes.windll.kernel32.CloseHandle(info.hProcess)

    @staticmethod
    def _read_result(result_path: Path) -> dict[str, object]:
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"ok": False, "error": "관리자 프로세스의 실행 결과를 확인하지 못했습니다."}
        return result if isinstance(result, dict) else {"ok": False}
