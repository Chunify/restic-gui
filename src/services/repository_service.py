import secrets
import shutil
import re
from pathlib import Path

from src.models.repository import Repository
from src.services.restic_service import ResticService
from src.storage.repository_store import RepositoryStore
from src.services.script_service import ScriptService


class RepositoryService:
    def __init__(
        self,
        store: RepositoryStore,
        keys_directory: Path,
        restic_service: ResticService | None = None,
    ) -> None:
        self.store = store
        self.keys_directory = keys_directory
        self.restic_service = restic_service or ResticService()

    def list_repositories(self) -> list[Repository]:
        return self.store.list_all()

    def create_repository(self, name: str, directory: str, password: str) -> Repository:
        clean_name = name.strip()
        clean_directory = directory.strip()
        if not clean_name:
            raise ValueError("저장소 이름을 입력해 주세요.")
        if not clean_directory:
            raise ValueError("저장 경로를 선택해 주세요.")
        if not password:
            raise ValueError("비밀번호를 입력해 주세요.")
        if self.store.name_exists(clean_name):
            raise ValueError("이미 사용 중인 저장소 이름입니다.")

        self.keys_directory.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", clean_name).strip("._") or "repository"
        key_path = self._available_key_path(safe_name)
        key_path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        try:
            self.restic_service.initialize_repository(
                clean_directory, password, key_path.resolve()
            )
            return self.store.add(clean_name, clean_directory, str(key_path.resolve()))
        except Exception:
            key_path.unlink(missing_ok=True)
            raise

    def delete_repository(self, repository_id: int, confirmation: str) -> None:
        repository = self.store.get(repository_id)
        if not repository:
            raise ValueError("저장소를 찾을 수 없습니다.")
        if confirmation != repository.directory:
            raise ValueError("저장소 경로를 정확히 입력해 주세요.")
        policies = self.store.list_policies(repository_id)
        directory = Path(repository.directory).resolve()
        if directory == Path(directory.anchor) or len(directory.parts) < 2:
            raise ValueError("안전하지 않은 저장소 경로는 삭제할 수 없습니다.")
        if directory.exists():
            shutil.rmtree(directory)
        Path(repository.key).unlink(missing_ok=True)
        data_directory = self.keys_directory.parent
        for policy in policies:
            for field in ("exclude", "iexclude", "file_from", "exclude_larger_than"):
                value = getattr(policy, field)
                if value:
                    Path(value).unlink(missing_ok=True)
            (data_directory / "backup-scripts" / f"{policy.name}.cmd").unlink(missing_ok=True)
        self.store.delete(repository_id)
        ScriptService(data_directory).regenerate_master()

    def _available_key_path(self, base_name: str) -> Path:
        candidate = self.keys_directory / f"{base_name}.key"
        index = 2
        while candidate.exists():
            candidate = self.keys_directory / f"{base_name}-{index}.key"
            index += 1
        return candidate
