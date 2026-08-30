import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

from src.services.subprocess_options import hidden_window_options


class ResticError(RuntimeError):
    """Raised when a restic command fails."""


class ResticService:
    def __init__(self, executable: str = "restic",
                 runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
                 logs_directory: Path | None = None) -> None:
        self.executable = executable
        self.runner = runner
        self.logs_directory = logs_directory

    def initialize_repository(self, directory: str, password: str, key_path: Path) -> None:
        with tempfile.TemporaryDirectory(prefix="restic-gui-") as temporary_directory:
            password_path = Path(temporary_directory) / "password"
            password_path.write_text(password, encoding="utf-8")
            self._run("init", "--repo", directory, "--password-file", str(password_path))
            self._run("key", "add", "--repo", directory, "--password-file", str(password_path),
                      "--new-password-file", str(key_path))

    def snapshots(self, directory: str, key: str) -> list[dict[str, object]]:
        result = self._run("snapshots", "--json", "--repo", directory, "--password-file", key)
        try:
            values = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as error:
            raise ResticError("스냅샷 목록을 해석할 수 없습니다.") from error
        return [{"id": item.get("short_id") or str(item.get("id", ""))[:8],
                 "snapshot_id": item.get("id", ""), "time": item.get("time", ""),
                 "tags": item.get("tags", []), "paths": item.get("paths", [])} for item in values]

    def snapshot_contents(self, directory: str, key: str, snapshot_id: str) -> str:
        return self._run("ls", snapshot_id, "--long", "--repo", directory,
                         "--password-file", key).stdout or ""

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        command: Sequence[str] = (self.executable, *arguments)
        try:
            result = self.runner(command, check=True, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace",
                                 **hidden_window_options())
        except FileNotFoundError as error:
            self._log(command, "restic 실행 파일을 찾을 수 없습니다.\n")
            raise ResticError("restic 실행 파일을 찾을 수 없습니다. restic을 설치하고 PATH를 확인해 주세요.") from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or "").strip()
            self._log(command, f"{error.stdout or ''}{error.stderr or ''}\n")
            raise ResticError(f"restic 명령 실행에 실패했습니다.{f' {detail}' if detail else ''}") from error
        self._log(command, f"{result.stdout or ''}{result.stderr or ''}\n")
        return result

    def _log(self, command: Sequence[str], output: str) -> None:
        if not self.logs_directory:
            return
        self.logs_directory.mkdir(parents=True, exist_ok=True)
        path = self.logs_directory / f"{datetime.now():%y-%m-%d}.log"
        with path.open("a", encoding="utf-8") as log:
            log.write(f"[{datetime.now():%H:%M:%S}] > {' '.join(command)}\n{output}")
