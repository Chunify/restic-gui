import tempfile
import unittest
from pathlib import Path

from src.services.repository_service import RepositoryService
from src.storage.repository_store import RepositoryStore


class FakeResticService:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, str, Path]] = []
        self.add_key_calls: list[tuple[str, str, Path]] = []
        self.error = error
        self.prune_calls: list[tuple[str, str]] = []

    def initialize_repository(self, directory: str, password: str, key_path: Path) -> None:
        self.calls.append((directory, password, key_path))
        if self.error:
            raise self.error

    def add_key(self, directory: str, password: str, key_path: Path) -> None:
        self.add_key_calls.append((directory, password, key_path))
        if self.error:
            raise self.error

    def prune(self, directory: str, key: str) -> None:
        self.prune_calls.append((directory, key))
        if self.error:
            raise self.error


class RepositoryServiceTest(unittest.TestCase):
    def test_create_and_list_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = RepositoryStore(root / "app.db")
            store.initialize()
            restic = FakeResticService()
            service = RepositoryService(store, root / "keys", restic)

            created = service.create_repository("문서", "C:/Backup", "secret")

            self.assertEqual(created.name, "문서")
            self.assertEqual(service.list_repositories(), [created])
            key_value = Path(created.key).read_text(encoding="utf-8")
            self.assertNotEqual(key_value, "secret")
            self.assertGreaterEqual(len(key_value), 48)
            self.assertEqual(restic.calls, [("C:/Backup", "secret", Path(created.key))])

    def test_rejects_empty_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = RepositoryStore(root / "app.db")
            store.initialize()
            service = RepositoryService(store, root / "keys", FakeResticService())
            with self.assertRaises(ValueError):
                service.create_repository("", "C:/Backup", "secret")

    def test_removes_key_and_does_not_save_when_restic_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = RepositoryStore(root / "app.db")
            store.initialize()
            service = RepositoryService(
                store, root / "keys", FakeResticService(RuntimeError("failed"))
            )

            with self.assertRaises(RuntimeError):
                service.create_repository("문서", "C:/Backup", "secret")

            self.assertEqual(store.list_all(), [])
            self.assertEqual(list((root / "keys").iterdir()), [])

    def test_rejects_duplicate_name_before_running_restic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = RepositoryStore(root / "app.db")
            store.initialize()
            first_restic = FakeResticService()
            RepositoryService(store, root / "keys", first_restic).create_repository(
                "문서", "C:/Backup", "secret"
            )
            second_restic = FakeResticService()

            with self.assertRaisesRegex(ValueError, "이미 사용 중"):
                RepositoryService(store, root / "keys", second_restic).create_repository(
                    "문서", "D:/Backup", "another-secret"
                )

            self.assertEqual(second_restic.calls, [])

    def test_existing_repository_requires_confirmation_then_adds_only_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository_directory = root / "existing"
            repository_directory.mkdir()
            (repository_directory / "config").write_text("restic config", encoding="utf-8")
            store = RepositoryStore(root / "app.db")
            store.initialize()
            restic = FakeResticService()
            service = RepositoryService(store, root / "keys", restic)

            with self.assertRaisesRegex(ValueError, "등록하시겠습니까"):
                service.create_repository("기존", str(repository_directory), "secret")

            created = service.create_repository(
                "기존", str(repository_directory), "secret", register_existing=True
            )

            self.assertEqual(restic.calls, [])
            self.assertEqual(restic.add_key_calls, [
                (str(repository_directory), "secret", Path(created.key))
            ])
            self.assertEqual(store.list_all(), [created])

    def test_repository_list_includes_directory_size(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository_directory = root / "repository"
            nested = repository_directory / "data"
            nested.mkdir(parents=True)
            (repository_directory / "config").write_bytes(b"1234")
            (nested / "pack").write_bytes(b"123456")
            store = RepositoryStore(root / "app.db")
            store.initialize()
            stored = store.add("저장소", str(repository_directory), str(root / "key"))

            listed = RepositoryService(store, root / "keys", FakeResticService()).list_repositories()

            self.assertEqual(listed[0].id, stored.id)
            self.assertEqual(listed[0].size_bytes, 10)

    def test_prunes_repository_with_its_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = RepositoryStore(root / "app.db")
            store.initialize()
            repository = store.add("저장소", str(root / "repository"), str(root / "key"))
            restic = FakeResticService()
            service = RepositoryService(store, root / "keys", restic)

            service.prune_repository(repository.id)

            self.assertEqual(restic.prune_calls, [(repository.directory, repository.key)])

    def test_opens_repository_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository_directory = root / "repository"
            repository_directory.mkdir()
            store = RepositoryStore(root / "app.db")
            store.initialize()
            repository = store.add("저장소", str(repository_directory), str(root / "key"))
            opened: list[str] = []
            service = RepositoryService(
                store, root / "keys", FakeResticService(), opened.append
            )

            service.open_repository_directory(repository.id)

            self.assertEqual(opened, [str(repository_directory.resolve())])


if __name__ == "__main__":
    unittest.main()
