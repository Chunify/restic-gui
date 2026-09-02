import json
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.services.subprocess_options import hidden_window_options


class ScriptService:
    def __init__(self, data_directory: Path,
                 runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> None:
        self.data_directory = data_directory
        self.runner = runner
        self._state_lock = threading.Lock()
        self._backup_state: dict[str, object] = {"running": False, "status": "idle"}
        self._log_offset = 0

    @property
    def master_script(self) -> Path:
        return self.data_directory / "backup-master-script.cmd"

    @property
    def progress_file(self) -> Path:
        return self.data_directory / "backup-progress.jsonl"

    def regenerate_master(self) -> Path:
        scripts_directory = self.data_directory / "backup-scripts"
        scripts_directory.mkdir(parents=True, exist_ok=True)
        lines = [
            "@echo off",
            "setlocal",
            'set "SCRIPTS_DIR=%~dp0backup-scripts"',
            'set "PROGRESS_FILE=%~dp0backup-progress.jsonl"',
            'for /f %%i in (\'powershell -NoProfile -Command "Get-Date -Format yy-MM-dd"\') do set LOGDATE=%%i',
            'set "LOG_FILE=%~dp0logs\\%LOGDATE%.log"',
            'if not exist "%~dp0logs" mkdir "%~dp0logs"',
            'if exist "%~dp0configuration.json" powershell -NoProfile -Command "$c=Get-Content -Raw -LiteralPath \'%~dp0configuration.json\' | ConvertFrom-Json; $d=[int]$c.log_retention_days; if ($d -gt 0) { Get-ChildItem -LiteralPath \'%~dp0logs\' -Filter \'*.log\' -File | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$d) } | Remove-Item -Force }"',
            'if exist "%PROGRESS_FILE%" del /q "%PROGRESS_FILE%"',
            'for /f "delims=" %%F in (\'dir /b /a-d /on "%SCRIPTS_DIR%\\*.cmd" 2^>nul\') do (',
            '    >>"%PROGRESS_FILE%" echo {"message_type":"script_start","script_name":"%%~nF"}',
            '    call "%SCRIPTS_DIR%\\%%F"',
            '    >>"%PROGRESS_FILE%" echo {"message_type":"script_complete","script_name":"%%~nF"}',
            ")",
            'if exist "%PROGRESS_FILE%" powershell -NoProfile -Command "Get-Content -LiteralPath \'%PROGRESS_FILE%\' | Where-Object { $_ -notmatch \'message_type.*status\' } | Add-Content -LiteralPath \'%LOG_FILE%\' -Encoding utf8"',
            'if exist "%PROGRESS_FILE%" del /q "%PROGRESS_FILE%"',
            "endlocal",
        ]
        self.data_directory.mkdir(parents=True, exist_ok=True)
        self.master_script.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return self.master_script

    def run_manual_backup(self) -> None:
        script = self.regenerate_master()
        try:
            self.runner(["cmd.exe", "/c", str(script.resolve())], check=True,
                        **hidden_window_options())
        except FileNotFoundError as error:
            raise RuntimeError("Windows 명령 실행기를 찾을 수 없습니다.") from error
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"수동 백업 실행에 실패했습니다. (종료 코드 {error.returncode})") from error

    def start_manual_backup(self) -> dict[str, object]:
        with self._state_lock:
            if self._backup_state.get("running"):
                raise RuntimeError("수동 백업이 이미 실행 중입니다.")
            self.progress_file.unlink(missing_ok=True)
            self._log_offset = 0
            total_scripts = len(list((self.data_directory / "backup-scripts").glob("*.cmd")))
            self._backup_state = {
                "running": True, "status": "running", "percent": 0.0,
                "files_done": 0, "total_files": 0, "bytes_done": 0,
                "total_bytes": 0, "current_files": [], "total_scripts": total_scripts,
                "scripts_completed": 0, "scripts_remaining": total_scripts,
                "current_script": None,
            }
        threading.Thread(target=self._run_in_background, daemon=True).start()
        return dict(self._backup_state)

    def manual_backup_status(self) -> dict[str, object]:
        self._read_progress_log()
        with self._state_lock:
            return dict(self._backup_state)

    def _run_in_background(self) -> None:
        try:
            self.run_manual_backup()
        except Exception as error:
            self._read_progress_log()
            with self._state_lock:
                self._backup_state.update(running=False, status="failed", error=str(error))
        else:
            self._read_progress_log()
            with self._state_lock:
                total_scripts = int(self._backup_state.get("total_scripts") or 0)
                self._backup_state.update(
                    running=False, status="completed", percent=1.0,
                    scripts_completed=total_scripts, scripts_remaining=0,
                    current_script=None,
                )

    def _today_log_path(self) -> Path:
        return self.data_directory / "logs" / f"{datetime.now():%y-%m-%d}.log"

    def _read_progress_log(self) -> None:
        path = self.progress_file
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8", errors="replace") as log:
                if path.stat().st_size < self._log_offset:
                    self._log_offset = 0
                log.seek(self._log_offset)
                content = log.read()
                self._log_offset = log.tell()
        except OSError:
            return
        for line in content.splitlines():
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            message_type = event.get("message_type")
            if message_type == "script_start":
                with self._state_lock:
                    self._backup_state["current_script"] = str(event.get("script_name") or "")
                continue
            if message_type == "script_complete":
                with self._state_lock:
                    total = int(self._backup_state.get("total_scripts") or 0)
                    completed = min(total, int(self._backup_state.get("scripts_completed") or 0) + 1)
                    self._backup_state.update(
                        scripts_completed=completed,
                        scripts_remaining=max(0, total - completed),
                        current_script=None,
                    )
                continue
            if message_type != "status":
                continue
            with self._state_lock:
                self._backup_state.update(
                    percent=float(event.get("percent_done") or 0),
                    files_done=int(event.get("files_done") or 0),
                    total_files=int(event.get("total_files") or 0),
                    bytes_done=int(event.get("bytes_done") or 0),
                    total_bytes=int(event.get("total_bytes") or 0),
                    current_files=list(event.get("current_files") or [])[:3],
                )
