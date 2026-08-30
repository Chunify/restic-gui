import subprocess
import json
import tempfile
import unittest
from pathlib import Path

from src.services.restic_service import ResticError, ResticService


class ResticServiceTest(unittest.TestCase):
    def test_initializes_with_password_then_adds_random_key(self) -> None:
        calls: list[tuple[list[str], dict[str, object]]] = []

        def runner(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
            calls.append((list(command), options))
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as temporary_directory:
            key_path = Path(temporary_directory) / "repository.key"
            key_path.write_text("random-key", encoding="utf-8")
            ResticService(runner=runner).initialize_repository(
                "C:/Backup", "user-password", key_path
            )

            self.assertEqual(calls[0][0][0:4], ["restic", "init", "--repo", "C:/Backup"])
            password_path = Path(calls[0][0][-1])
            self.assertEqual(calls[1][0][0:5], ["restic", "key", "add", "--repo", "C:/Backup"])
            self.assertEqual(calls[1][0][-2:], ["--new-password-file", str(key_path)])
            self.assertFalse(password_path.exists())
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                self.assertTrue(all(options["creationflags"] == subprocess.CREATE_NO_WINDOW
                                    for _command, options in calls))

    def test_reports_missing_restic(self) -> None:
        def runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError

        with tempfile.TemporaryDirectory() as temporary_directory:
            key_path = Path(temporary_directory) / "repository.key"
            key_path.write_text("random-key", encoding="utf-8")
            with self.assertRaisesRegex(ResticError, "restic 실행 파일"):
                ResticService(runner=runner).initialize_repository(
                    "C:/Backup", "password", key_path
                )

    def test_lists_snapshots_from_json(self) -> None:
        def runner(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
            output = json.dumps([{"id": "abcdef123456", "short_id": "abcdef12",
                                  "time": "2026-08-30T10:00:00Z", "tags": ["daily"],
                                  "paths": ["C:/Source"]}])
            return subprocess.CompletedProcess(command, 0, output, "")

        snapshots = ResticService(runner=runner).snapshots("C:/Repo", "C:/key")
        self.assertEqual(snapshots[0]["id"], "abcdef12")
        self.assertEqual(snapshots[0]["paths"], ["C:/Source"])


if __name__ == "__main__":
    unittest.main()
