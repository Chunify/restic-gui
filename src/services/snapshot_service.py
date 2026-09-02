from pathlib import Path
import threading

from src.services.restic_service import ResticService
from src.storage.repository_store import RepositoryStore


class SnapshotService:
    def __init__(self, store: RepositoryStore, restic: ResticService) -> None:
        self.store = store
        self.restic = restic
        self._restore_lock = threading.Lock()
        self._restore_state: dict[str, object] = {"running": False, "status": "idle"}

    def list_snapshots(self, repository_id: int,
                       tag: str | None = None) -> list[dict[str, object]]:
        repository = self._repository(repository_id)
        clean_tag = str(tag).strip() if tag is not None else None
        return self.restic.snapshots(repository.directory, repository.key, clean_tag or None)

    def save_contents(self, repository_id: int, snapshot_id: str, destination: str) -> None:
        repository = self._repository(repository_id)
        clean_id = str(snapshot_id).strip()
        if not clean_id:
            raise ValueError("스냅샷 ID가 필요합니다.")
        clean_destination = str(destination).strip()
        if not clean_destination:
            raise ValueError("저장할 파일을 선택해 주세요.")
        contents = self.restic.snapshot_contents(repository.directory, repository.key, clean_id)
        Path(clean_destination).write_text(contents, encoding="utf-8")

    def restore(self, repository_id: int, snapshot_id: str, target: str) -> None:
        repository, clean_id, target_path = self._restore_values(repository_id, snapshot_id, target)
        self.restic.restore_snapshot(
            repository.directory, repository.key, clean_id, str(target_path)
        )

    def start_restore(self, repository_id: int, snapshot_id: str, target: str) -> dict[str, object]:
        repository, clean_id, target_path = self._restore_values(repository_id, snapshot_id, target)
        with self._restore_lock:
            if self._restore_state.get("running"):
                raise RuntimeError("스냅샷 복원이 이미 실행 중입니다.")
            self._restore_state = {
                "running": True, "status": "running", "percent": 0.0,
                "files_done": 0, "total_files": 0, "bytes_done": 0,
                "total_bytes": 0, "snapshot_id": clean_id,
                "target": str(target_path),
            }
        threading.Thread(
            target=self._run_restore,
            args=(repository.directory, repository.key, clean_id, str(target_path)),
            daemon=True,
        ).start()
        return dict(self._restore_state)

    def restore_status(self) -> dict[str, object]:
        with self._restore_lock:
            return dict(self._restore_state)

    def _run_restore(self, directory: str, key: str, snapshot_id: str, target: str) -> None:
        try:
            self.restic.restore_snapshot(directory, key, snapshot_id, target, self._restore_progress)
        except Exception as error:
            with self._restore_lock:
                self._restore_state.update(running=False, status="failed", error=str(error))
        else:
            with self._restore_lock:
                self._restore_state.update(running=False, status="completed", percent=1.0)

    def _restore_progress(self, event: dict[str, object]) -> None:
        if event.get("message_type") != "status":
            return
        with self._restore_lock:
            self._restore_state.update(
                percent=float(event.get("percent_done") or 0),
                files_done=int(event.get("files_restored") or event.get("files_done") or 0),
                total_files=int(event.get("total_files") or 0),
                bytes_done=int(event.get("bytes_restored") or event.get("bytes_done") or 0),
                total_bytes=int(event.get("total_bytes") or 0),
            )

    def _restore_values(self, repository_id: int, snapshot_id: str, target: str):
        repository = self._repository(repository_id)
        clean_id = str(snapshot_id).strip()
        if not clean_id:
            raise ValueError("스냅샷 ID가 필요합니다.")
        clean_target = str(target).strip()
        if not clean_target:
            raise ValueError("복원할 폴더를 선택해 주세요.")
        target_path = Path(clean_target)
        if not target_path.is_dir():
            raise ValueError("복원할 폴더를 찾을 수 없습니다.")
        return repository, clean_id, target_path

    def _repository(self, repository_id: int):
        repository = self.store.get(repository_id)
        if not repository:
            raise ValueError("저장소를 찾을 수 없습니다.")
        return repository
