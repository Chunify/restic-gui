from pathlib import Path

from src.services.restic_service import ResticService
from src.storage.repository_store import RepositoryStore


class SnapshotService:
    def __init__(self, store: RepositoryStore, restic: ResticService) -> None:
        self.store = store
        self.restic = restic

    def list_snapshots(self, repository_id: int) -> list[dict[str, object]]:
        repository = self._repository(repository_id)
        return self.restic.snapshots(repository.directory, repository.key)

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

    def _repository(self, repository_id: int):
        repository = self.store.get(repository_id)
        if not repository:
            raise ValueError("저장소를 찾을 수 없습니다.")
        return repository
