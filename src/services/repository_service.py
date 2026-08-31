import secrets
import shutil
import re
import os
from dataclasses import replace
from pathlib import Path

from src.models.repository import Repository
from src.services.restic_service import ResticService
from src.storage.repository_store import RepositoryStore
from src.services.script_service import ScriptService


class ExistingRepositoryError(ValueError):
    """Raised when registration of an existing restic repository needs consent."""


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
        return [
            replace(repository, size_bytes=self._directory_size(repository.directory))
            for repository in self.store.list_all()
        ]

    def create_repository(self, name: str, directory: str, password: str,
                          register_existing: bool = False) -> Repository:
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

        existing_repository = (Path(clean_directory) / "config").is_file()
        if existing_repository and not register_existing:
            raise ExistingRepositoryError("이미 리포지터리가 생성된 경로입니다. 등록하시겠습니까?")

        self.keys_directory.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", clean_name).strip("._") or "repository"
        key_path = self._available_key_path(safe_name)
        key_path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        try:
            if existing_repository:
                self.restic_service.add_key(clean_directory, password, key_path.resolve())
            else:
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
            for field in ("exclude", "iexclude", "file_from"):
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

    @staticmethod
    def _directory_size(directory: str) -> int:
        total = 0
        try:
            for root, _directories, files in os.walk(directory, followlinks=False):
                for name in files:
                    try:
                        total += os.stat(Path(root) / name, follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            return 0
        return total
