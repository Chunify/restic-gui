import subprocess
import json
import tempfile
import threading
import unittest
from pathlib import Path

from src.services.restic_service import ResticError, ResticService


class ResticServiceTest(unittest.TestCase):
    def test_reports_running_while_a_restic_command_is_active(self) -> None:
        started = threading.Event()
        release = threading.Event()

        def runner(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
            started.set()
            release.wait(timeout=2)
            return subprocess.CompletedProcess(command, 0, "[]", "")

        service = ResticService(runner=runner)
        worker = threading.Thread(target=lambda: service.snapshots("C:/Repo", "C:/key"))
        worker.start()
        self.assertTrue(started.wait(timeout=1))
        self.assertTrue(service.operation_status()["running"])
        self.assertEqual(service.operation_status()["command"][1], "snapshots")
        release.set()
        worker.join(timeout=2)
        self.assertFalse(service.operation_status()["running"])

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

    def test_adds_key_to_existing_repository_without_init(self) -> None:
        calls: list[list[str]] = []

        def runner(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
            calls.append(list(command))
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as temporary_directory:
            key_path = Path(temporary_directory) / "repository.key"
            key_path.write_text("random-key", encoding="utf-8")
            ResticService(runner=runner).add_key("C:/Backup", "password", key_path)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0:5], ["restic", "key", "add", "--repo", "C:/Backup"])
        self.assertNotIn("init", calls[0])

    def test_lists_snapshots_from_json(self) -> None:
        def runner(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
            output = json.dumps([{"id": "abcdef123456", "short_id": "abcdef12",
                                  "time": "2026-08-30T10:00:00Z", "tags": ["daily"],
                                  "paths": ["C:/Source"]}])
            return subprocess.CompletedProcess(command, 0, output, "")

        snapshots = ResticService(runner=runner).snapshots("C:/Repo", "C:/key")
        self.assertEqual(snapshots[0]["id"], "abcdef12")
        self.assertEqual(snapshots[0]["paths"], ["C:/Source"])

    def test_lists_snapshots_filtered_by_tag(self) -> None:
        calls: list[list[str]] = []

        def runner(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
            calls.append(list(command))
            return subprocess.CompletedProcess(command, 0, "[]", "")

        ResticService(runner=runner).snapshots("C:/Repo", "C:/key", "daily")

        self.assertEqual(calls, [[
            "restic", "snapshots", "--json", "--repo", "C:/Repo",
            "--password-file", "C:/key", "--tag", "daily",
        ]])

    def test_large_snapshot_output_is_not_copied_to_log(self) -> None:
        output = json.dumps([{"id": "a" * 64, "payload": "x" * 20_000}])

        def runner(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 0, output, "")

        with tempfile.TemporaryDirectory() as temporary_directory:
            logs = Path(temporary_directory) / "logs"
            ResticService(runner=runner, logs_directory=logs).snapshots("C:/Repo", "C:/key")
            content = next(logs.glob("*.log")).read_text(encoding="utf-8")

        self.assertIn("출력", content)
        self.assertIn("생략", content)
        self.assertNotIn("x" * 100, content)

    def test_restores_snapshot_to_selected_target(self) -> None:
        calls: list[list[str]] = []

        def runner(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
            calls.append(list(command))
            return subprocess.CompletedProcess(command, 0, "", "")

        ResticService(runner=runner).restore_snapshot(
            "C:/Repo", "C:/key", "abcdef12", "D:/Restore"
        )

        self.assertEqual(calls, [[
            "restic", "restore", "abcdef12", "--json", "--target", "D:/Restore",
            "--repo", "C:/Repo", "--password-file", "C:/key",
        ]])

    def test_prunes_repository(self) -> None:
        calls: list[list[str]] = []

        def runner(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
            calls.append(list(command))
            return subprocess.CompletedProcess(command, 0, "", "")

        ResticService(runner=runner).prune("C:/Repo", "C:/key")

        self.assertEqual(calls, [[
            "restic", "prune", "--repo", "C:/Repo", "--password-file", "C:/key",
        ]])


if __name__ == "__main__":
    unittest.main()
