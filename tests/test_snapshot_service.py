import tempfile
import unittest
import time
from pathlib import Path
from unittest.mock import Mock

from src.services.snapshot_service import SnapshotService
from src.storage.repository_store import RepositoryStore


class SnapshotServiceTest(unittest.TestCase):
    def test_list_snapshots_passes_trimmed_tag_to_restic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = RepositoryStore(root / "app.db")
            store.initialize()
            repository = store.add("Repo", "C:/Repo", "C:/key")
            restic = Mock()
            restic.snapshots.return_value = []

            SnapshotService(store, restic).list_snapshots(repository.id, " daily ")

            restic.snapshots.assert_called_once_with("C:/Repo", "C:/key", "daily")

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

    def test_async_restore_reports_progress_and_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            target = root / "restore"
            target.mkdir()
            store = RepositoryStore(root / "app.db")
            store.initialize()
            repository = store.add("Repo", "C:/Repo", "C:/key")
            restic = Mock()
            restic.restore_snapshot.side_effect = lambda *_args: _args[-1]({
                "message_type": "status", "percent_done": 0.5,
                "files_restored": 5, "total_files": 10,
                "bytes_restored": 100, "total_bytes": 200,
            })
            service = SnapshotService(store, restic)

            service.start_restore(repository.id, "abcdef12", str(target))
            for _ in range(100):
                status = service.restore_status()
                if not status["running"]:
                    break
                time.sleep(0.01)

            self.assertEqual(status["status"], "completed")
            self.assertEqual(status["percent"], 1.0)
            self.assertEqual(status["files_done"], 5)


if __name__ == "__main__":
    unittest.main()
