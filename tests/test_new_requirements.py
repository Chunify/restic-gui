import subprocess
import json
import tempfile
import unittest
from pathlib import Path

from src.services.configuration_service import ConfigurationService
from src.services.log_service import LogService
from src.services.script_service import ScriptService
from src.services.windows_identity import WindowsIdentity


TEST_IDENTITY = WindowsIdentity("TEST\\mint", "S-1-5-21-1000")


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
        self.assertIn('"message_type":"script_start"', text)
        self.assertIn('"message_type":"script_complete"', text)
        self.assertIn("message_type.*status", text)
        self.assertIn("backup-progress.jsonl", text)
        self.assertIn("log_retention_days", text)
        self.assertIn("Get-ChildItem", text)
        self.assertIn("Remove-Item -Force", text)
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

    def test_manual_backup_tracks_remaining_scripts(self) -> None:
        scripts = self.root / "backup-scripts"
        scripts.mkdir()
        (scripts / "first.cmd").write_text("", encoding="utf-8")
        (scripts / "second.cmd").write_text("", encoding="utf-8")
        service = ScriptService(self.root)
        service._backup_state = {
            "running": True, "status": "running", "total_scripts": 2,
            "scripts_completed": 0, "scripts_remaining": 2,
            "current_script": None,
        }
        service.progress_file.write_text(
            '{"message_type":"script_start","script_name":"first"}\n'
            '{"message_type":"script_complete","script_name":"first"}\n'
            '{"message_type":"script_start","script_name":"second"}\n',
            encoding="utf-8",
        )

        status = service.manual_backup_status()

        self.assertEqual(status["scripts_completed"], 1)
        self.assertEqual(status["scripts_remaining"], 1)
        self.assertEqual(status["current_script"], "second")

    def test_configuration_validates_persists_and_registers_tasks(self) -> None:
        calls = []

        def runner(command: list[str], **options: object):
            calls.append((command, options))
            return subprocess.CompletedProcess(command, 0, "", "")

        service = ConfigurationService(
            self.root, self.root / "master.cmd", runner,
            identity_provider=lambda: TEST_IDENTITY,
        )
        saved = service.save({"enabled": True, "run_at_startup": True,
                              "interval_days": "3", "run_when_idle": True,
                              "log_retention_days": "14"})
        self.assertEqual(saved["interval_days"], 3)
        self.assertEqual(saved["log_retention_days"], 14)
        self.assertEqual(service.load(), saved)
        self.assertTrue(any(call[0][0] == "schtasks" and "/Create" in call[0] for call in calls))
        create = next(call[0] for call in calls if call[0][0] == "schtasks" and "/Create" in call[0])
        self.assertIn("ResticGUIAutoTask-S-1-5-21-1000", create)
        self.assertEqual(create[create.index("/RU") + 1], "TEST\\mint")
        startup = next(
            call[0] for call in calls
            if call[0][0] == "schtasks" and "/Create" in call[0]
            and "ResticGUIAutoTask-S-1-5-21-1000AtStartup" in call[0]
        )
        self.assertEqual(startup[startup.index("/SC") + 1], "ONLOGON")
        self.assertTrue(any(call[0][0] == "powershell" for call in calls))
        self.assertTrue(all(call[1].get("creationflags") == subprocess.CREATE_NO_WINDOW
                            for call in calls))
        with self.assertRaises(ValueError):
            service.save({"enabled": True, "interval_days": 0})
        with self.assertRaisesRegex(ValueError, "로그 보관 기간"):
            service.save({"enabled": True, "interval_days": 1,
                          "log_retention_days": 0})

    def test_configuration_reports_scheduler_permission_error(self) -> None:
        def runner(command: list[str], **options: object):
            raise subprocess.CalledProcessError(
                1, command, stderr="ERROR: Access is denied."
            )

        service = ConfigurationService(
            self.root, self.root / "master.cmd", runner,
            identity_provider=lambda: TEST_IDENTITY,
        )

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
        scheduler_log = (self.root / "logs" / "scheduler.log").read_text(encoding="utf-8")
        self.assertIn("설정 변경 실패", scheduler_log)

    def test_configuration_exposes_scheduler_name_and_script(self) -> None:
        service = ConfigurationService(
            self.root, self.root / "master.cmd",
            identity_provider=lambda: TEST_IDENTITY,
        )
        service._task_folder = lambda: (_FakeScheduler(), _FakeFolder())

        details = service.details()

        self.assertEqual(details["task_name"], "ResticGUIAutoTask-S-1-5-21-1000")
        self.assertEqual(details["task_path"], "\\ResticGUIAutoTask-S-1-5-21-1000")
        self.assertTrue(details["registered"])
        self.assertEqual(details["state"], "준비됨")
        self.assertEqual(details["last_result"], 0)

    def test_configuration_remains_available_when_task_status_read_fails(self) -> None:
        class UnreadableTask:
            @property
            def State(self):
                raise OSError("status unavailable")

        class Folder:
            def GetTask(self, _name: str):
                return UnreadableTask()

        service = ConfigurationService(
            self.root, self.root / "master.cmd",
            identity_provider=lambda: TEST_IDENTITY,
        )
        service._task_folder = lambda: (_FakeScheduler(), Folder())

        details = service.details()

        self.assertTrue(details["registered"])
        self.assertEqual(details["state"], "상태 조회 실패")
        self.assertIn("status unavailable", details["query_error"])

    def test_pywin32_registration_targets_original_unelevated_user(self) -> None:
        service = ConfigurationService(
            self.root, self.root / "master.cmd",
            identity_provider=lambda: WindowsIdentity("ADMIN\\other", "S-1-5-21-9999"),
        )
        scheduler = _RegisteringScheduler()
        folder = _RegisteringFolder()
        service._task_folder = lambda: (scheduler, folder)

        service.apply_scheduler({
            "enabled": True,
            "interval_days": 1,
            "run_at_startup": False,
            "run_when_idle": False,
            "_scheduler_user_id": "TEST\\mint",
            "_scheduler_user_sid": "S-1-5-21-1000",
        })

        self.assertEqual(folder.registration[0], "ResticGUIAutoTask-S-1-5-21-1000")
        self.assertEqual(folder.registration[3], "TEST\\mint")
        self.assertIsNone(folder.registration[4])
        self.assertEqual(folder.registration[5], 3)
        self.assertEqual(scheduler.task.Principal.UserId, "TEST\\mint")

    def test_pywin32_startup_option_uses_account_logon_trigger(self) -> None:
        service = ConfigurationService(
            self.root, self.root / "master.cmd",
            identity_provider=lambda: TEST_IDENTITY,
        )
        scheduler = _RegisteringScheduler()
        folder = _RegisteringFolder()
        service._task_folder = lambda: (scheduler, folder)

        service.apply_scheduler({
            "enabled": True,
            "interval_days": 1,
            "run_at_startup": True,
            "run_when_idle": False,
        })

        logon = scheduler.task.Triggers.created[1]
        self.assertEqual(scheduler.task.Triggers.kinds, [2, 9])
        self.assertEqual(logon.UserId, "TEST\\mint")


class _FakeScheduler:
    pass


class _FakeTask:
    State = 3
    LastTaskResult = 0
    LastRunTime = None
    NextRunTime = None


class _FakeFolder:
    def GetTask(self, name: str):
        if name != "\\ResticGUIAutoTask-S-1-5-21-1000":
            raise ValueError(name)
        return _FakeTask()


class _PropertyBag:
    pass


class _Collection:
    def __init__(self) -> None:
        self.kinds = []
        self.created = []

    def Create(self, kind: int):
        item = _PropertyBag()
        self.kinds.append(kind)
        self.created.append(item)
        return item


class _Definition:
    def __init__(self) -> None:
        self.RegistrationInfo = _PropertyBag()
        self.Settings = _PropertyBag()
        self.Principal = _PropertyBag()
        self.Triggers = _Collection()
        self.Actions = _Collection()


class _RegisteringScheduler:
    def __init__(self) -> None:
        self.task = _Definition()

    def NewTask(self, _flags: int):
        return self.task


class _RegisteringFolder:
    registration = None

    def RegisterTaskDefinition(self, *arguments):
        self.registration = arguments


if __name__ == "__main__":
    unittest.main()
