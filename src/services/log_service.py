from pathlib import Path


class LogService:
    def __init__(self, logs_directory: Path) -> None:
        self.logs_directory = logs_directory

    def list_logs(self) -> list[dict[str, object]]:
        if not self.logs_directory.exists():
            return []
        return [
            {"name": path.name, "size": path.stat().st_size}
            for path in sorted(self.logs_directory.glob("*.log"), reverse=True)
            if path.is_file()
        ]

    def read_log(self, name: str) -> str:
        return self._log_path(name).read_text(encoding="utf-8", errors="replace")

    def delete_log(self, name: str) -> None:
        path = self._log_path(name)
        if not path.exists():
            raise ValueError("로그 파일을 찾을 수 없습니다.")
        path.unlink()

    def delete_all(self) -> None:
        if self.logs_directory.exists():
            for path in self.logs_directory.glob("*.log"):
                if path.is_file():
                    path.unlink()

    def _log_path(self, name: str) -> Path:
        clean = str(name).strip()
        if not clean or Path(clean).name != clean or not clean.endswith(".log"):
            raise ValueError("올바른 로그 파일 이름이 아닙니다.")
        return self.logs_directory / clean
