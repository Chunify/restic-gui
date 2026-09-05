import json
import subprocess
import tempfile
import threading
from contextlib import contextmanager
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
        self._command_lock = threading.RLock()
        self._state_lock = threading.Lock()
        self._active_commands = 0
        self._current_command: list[str] = []

    def operation_status(self) -> dict[str, object]:
        with self._state_lock:
            return {"running": self._active_commands > 0,
                    "command": list(self._current_command)}

    @contextmanager
    def _tracked_command(self, command: Sequence[str]):
        with self._state_lock:
            self._active_commands += 1
        try:
            with self._command_lock:
                with self._state_lock:
                    self._current_command = list(command)
                yield
        finally:
            with self._state_lock:
                self._active_commands -= 1
                if self._active_commands == 0:
                    self._current_command = []

    def initialize_repository(self, directory: str, password: str, key_path: Path) -> None:
        with tempfile.TemporaryDirectory(prefix="restic-gui-") as temporary_directory:
            password_path = Path(temporary_directory) / "password"
            password_path.write_text(password, encoding="utf-8")
            self._run("init", "--repo", directory, "--password-file", str(password_path))
            self._add_key(directory, password_path, key_path)

    def add_key(self, directory: str, password: str, key_path: Path) -> None:
        with tempfile.TemporaryDirectory(prefix="restic-gui-") as temporary_directory:
            password_path = Path(temporary_directory) / "password"
            password_path.write_text(password, encoding="utf-8")
            self._add_key(directory, password_path, key_path)

    def _add_key(self, directory: str, password_path: Path, key_path: Path) -> None:
        self._run("key", "add", "--repo", directory, "--password-file", str(password_path),
                  "--new-password-file", str(key_path))

    def snapshots(self, directory: str, key: str,
                  tag: str | None = None) -> list[dict[str, object]]:
        arguments = ["snapshots", "--json", "--repo", directory, "--password-file", key]
        if tag:
            arguments.extend(("--tag", tag))
        result = self._run(*arguments)
        try:
            values = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as error:
            raise ResticError("스냅샷 목록을 해석할 수 없습니다.") from error
        snapshots = [{"id": item.get("short_id") or str(item.get("id", ""))[:8],
                      "snapshot_id": item.get("id", ""), "time": item.get("time", ""),
                      "tags": item.get("tags", []), "paths": item.get("paths", []),
                      "size_bytes": self._snapshot_size(item)}
                     for item in values]
        return sorted(snapshots, key=lambda snapshot: str(snapshot["time"]), reverse=True)

    @staticmethod
    def _snapshot_size(snapshot: dict[str, object]) -> int | None:
        """Return the logical source size recorded when the snapshot was created."""
        summary = snapshot.get("summary")
        if not isinstance(summary, dict):
            return None
        size = summary.get("total_bytes_processed")
        if isinstance(size, bool) or not isinstance(size, (int, float)) or size < 0:
            return None
        return int(size)

    def snapshot_contents(self, directory: str, key: str, snapshot_id: str) -> str:
        return self._run("ls", snapshot_id, "--long", "--repo", directory,
                         "--password-file", key).stdout or ""

    def restore_snapshot(self, directory: str, key: str, snapshot_id: str,
                         target: str,
                         progress_callback: Callable[[dict[str, object]], None] | None = None) -> None:
        arguments = ("restore", snapshot_id, "--json", "--target", target,
                     "--repo", directory, "--password-file", key)
        if progress_callback is None:
            self._run(*arguments)
            return
        with self._tracked_command((self.executable, *arguments)):
            self._run_json_stream(arguments, progress_callback)

    def prune(self, directory: str, key: str) -> None:
        self._run("prune", "--repo", directory, "--password-file", key)

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        command: Sequence[str] = (self.executable, *arguments)
        try:
            with self._tracked_command(command):
                result = self.runner(command, check=True, capture_output=True, text=True,
                                     encoding="utf-8", errors="replace",
                                     **hidden_window_options())
        except FileNotFoundError as error:
            self._log(command, "restic 실행 파일을 찾을 수 없습니다.\n")
            raise ResticError("restic 실행 파일을 찾을 수 없습니다. restic을 설치하고 PATH를 확인해 주세요.") from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or "").strip()
            self._log(command, self._compact_output(f"{error.stdout or ''}{error.stderr or ''}\n"))
            raise ResticError(f"restic 명령 실행에 실패했습니다.{f' {detail}' if detail else ''}") from error
        output = f"{result.stdout or ''}{result.stderr or ''}\n"
        if arguments and arguments[0] in ("snapshots", "ls") and result.stdout:
            output = f"[출력 {self._human_size(len(result.stdout.encode('utf-8')))} 생략]\n{result.stderr or ''}"
        self._log(command, self._compact_output(output))
        return result

    def _run_json_stream(self, arguments: Sequence[str],
                         callback: Callable[[dict[str, object]], None]) -> None:
        command = (self.executable, *arguments)
        output: list[str] = []
        try:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                **hidden_window_options(),
            )
        except FileNotFoundError as error:
            self._log(command, "restic 실행 파일을 찾을 수 없습니다.\n")
            raise ResticError("restic 실행 파일을 찾을 수 없습니다. restic을 설치하고 PATH를 확인해 주세요.") from error
        assert process.stdout is not None
        for line in process.stdout:
            output.append(line)
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(event, dict):
                callback(event)
        return_code = process.wait()
        combined = self._compact_output("".join(output))
        self._log(command, combined)
        if return_code:
            detail = combined.strip()
            raise ResticError(f"restic 복원에 실패했습니다.{f' {detail}' if detail else ''}")

    @staticmethod
    def _compact_output(output: str, limit: int = 16_384) -> str:
        if len(output) <= limit:
            return output
        half = limit // 2
        omitted = len(output) - limit
        return f"{output[:half]}\n... [{omitted}자 생략] ...\n{output[-half:]}"

    @staticmethod
    def _human_size(size_bytes: int) -> str:
        size = max(0, size_bytes) / 1024
        units = ("KB", "MB", "GB", "TB")
        unit = 0
        while size >= 1024 and unit < len(units) - 1:
            size /= 1024
            unit += 1
        return f"{size:.2f} {units[unit]}"

    def _log(self, command: Sequence[str], output: str) -> None:
        if not self.logs_directory:
            return
        self.logs_directory.mkdir(parents=True, exist_ok=True)
        path = self.logs_directory / f"{datetime.now():%y-%m-%d}.log"
        with path.open("a", encoding="utf-8") as log:
            log.write(f"[{datetime.now():%H:%M:%S}] > {' '.join(command)}\n{output}")
