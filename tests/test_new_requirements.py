import subprocess
import json
import tempfile
import unittest
from pathlib import Path

from src.services.configuration_service import ConfigurationService
from src.services.log_service import LogService
from src.services.script_service import ScriptService


class NewRequirementsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_log_list_read_delete_and_delete_all(self) -> None:
        logs = self.root / "logs"
        logs.mkdir()
        (logs / "26-08-30.log").write_text("first", encoding="utf-8")
        (logs / "26-08-31.log").write_text("second", encoding="utf-8")
        service = LogService(logs)
        self.assertEqual([item["name"] for item in service.list_logs()],
                         ["26-08-31.log", "26-08-30.log"])
        self.assertEqual(service.read_log("26-08-30.log"), "first")
        with self.assertRaises(ValueError):
            service.read_log("../secret.log")
        service.delete_log("26-08-30.log")
        service.delete_all()
        self.assertEqual(service.list_logs(), [])

    def test_master_script_discovers_policy_scripts_and_manual_backup_runs_it(self) -> None:
        scripts = self.root / "backup-scripts"
        scripts.mkdir()
        (scripts / "zeta.cmd").write_text("", encoding="utf-8")
        (scripts / "Alpha.cmd").write_text("", encoding="utf-8")
        calls = []

        def runner(command: list[str], **options: object):
            calls.append((command, options))
            return subprocess.CompletedProcess(command, 0)

        service = ScriptService(self.root, runner)
        service.run_manual_backup()
        text = service.master_script.read_text(encoding="utf-8")
        self.assertIn('dir /b /a-d /on "%SCRIPTS_DIR%\\*.cmd"', text)
        self.assertIn('call "%SCRIPTS_DIR%\\%%F"', text)
        self.assertIn("message_type.*status", text)
        self.assertIn("backup-progress.jsonl", text)
        self.assertNotIn(str((scripts / "Alpha.cmd").resolve()), text)
        self.assertNotIn(str((scripts / "zeta.cmd").resolve()), text)
        self.assertEqual(calls[0][0][:2], ["cmd.exe", "/c"])
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            self.assertEqual(calls[0][1]["creationflags"], subprocess.CREATE_NO_WINDOW)

    def test_manual_backup_reads_restic_json_progress(self) -> None:
        service = ScriptService(self.root)
        log = service.progress_file
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(json.dumps({
            "message_type": "status", "percent_done": 0.42,
            "files_done": 4, "total_files": 10,
            "bytes_done": 1024, "total_bytes": 4096,
            "current_files": ["C:/Source/file.txt"],
        }) + "\n", encoding="utf-8")

        status = service.manual_backup_status()

        self.assertEqual(status["percent"], 0.42)
        self.assertEqual(status["files_done"], 4)
        self.assertEqual(status["current_files"], ["C:/Source/file.txt"])

    def test_configuration_validates_persists_and_registers_tasks(self) -> None:
        calls = []

        def runner(command: list[str], **options: object):
            calls.append((command, options))
            return subprocess.CompletedProcess(command, 0, "", "")

        service = ConfigurationService(self.root, self.root / "master.cmd", runner)
        saved = service.save({"enabled": True, "run_at_startup": True,
                              "interval_days": "3", "run_when_idle": True})
        self.assertEqual(saved["interval_days"], 3)
        self.assertEqual(service.load(), saved)
        self.assertTrue(any(call[0][0] == "schtasks" and "/Create" in call[0] for call in calls))
        self.assertTrue(any(call[0][0] == "powershell" for call in calls))
        self.assertTrue(all(call[1].get("creationflags") == subprocess.CREATE_NO_WINDOW
                            for call in calls))
        with self.assertRaises(ValueError):
            service.save({"enabled": True, "interval_days": 0})

    def test_configuration_reports_scheduler_permission_error(self) -> None:
        def runner(command: list[str], **options: object):
            raise subprocess.CalledProcessError(
                1, command, stderr="ERROR: Access is denied."
            )

        service = ConfigurationService(self.root, self.root / "master.cmd", runner)

        with self.assertRaisesRegex(RuntimeError, "권한.*관리자 권한"):
            service.save({"enabled": True, "interval_days": 1})


    def test_configuration_can_delegate_scheduler_changes(self) -> None:
        applied = []
        service = ConfigurationService(
            self.root, self.root / "master.cmd", scheduler_applier=applied.append
        )

        saved = service.save({"enabled": True, "interval_days": "2"})

        self.assertEqual(applied, [saved])
        self.assertEqual(service.load(), saved)

    def test_configuration_is_not_saved_when_elevation_fails(self) -> None:
        def fail(_values: dict[str, object]) -> None:
            raise RuntimeError("관리자 권한 요청이 취소되었습니다.")

        service = ConfigurationService(
            self.root, self.root / "master.cmd", scheduler_applier=fail
        )

        with self.assertRaisesRegex(RuntimeError, "취소"):
            service.save({"enabled": True, "interval_days": 1})
        self.assertFalse(service.path.exists())


if __name__ == "__main__":
    unittest.main()
