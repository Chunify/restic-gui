import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from src.services.snapshot_service import SnapshotService
from src.storage.repository_store import RepositoryStore


class SnapshotServiceTest(unittest.TestCase):
    def test_restore_validates_target_and_calls_restic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            target = root / "restore"
            target.mkdir()
            store = RepositoryStore(root / "app.db")
            store.initialize()
            repository = store.add("Repo", "C:/Repo", "C:/key")
            restic = Mock()
            service = SnapshotService(store, restic)

            service.restore(repository.id, "abcdef12", str(target))

            restic.restore_snapshot.assert_called_once_with(
                "C:/Repo", "C:/key", "abcdef12", str(target)
            )

    def test_restore_rejects_missing_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = RepositoryStore(root / "app.db")
            store.initialize()
            repository = store.add("Repo", "C:/Repo", "C:/key")
            restic = Mock()
            service = SnapshotService(store, restic)

            with self.assertRaisesRegex(ValueError, "폴더를 찾을 수 없습니다"):
                service.restore(repository.id, "abcdef12", str(root / "missing"))

            restic.restore_snapshot.assert_not_called()


if __name__ == "__main__":
    unittest.main()
