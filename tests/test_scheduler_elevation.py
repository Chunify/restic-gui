import subprocess
import sys
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.services.scheduler_elevation import SchedulerElevator
from src.services.windows_identity import WindowsIdentity


class SchedulerElevationTest(unittest.TestCase):
    def test_apply_captures_identity_before_elevation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            elevator = SchedulerElevator(Path(temporary))

            def fake_run(request_path: Path, result_path: Path) -> int:
                request = json.loads(request_path.read_text(encoding="utf-8"))
                self.assertEqual(request["_scheduler_user_id"], "TEST\\mint")
                self.assertEqual(request["_scheduler_user_sid"], "S-1-5-21-1000")
                result_path.write_text('{"ok": true}', encoding="utf-8")
                return 0

            with patch(
                "src.services.scheduler_elevation.current_windows_identity",
                return_value=WindowsIdentity("TEST\\mint", "S-1-5-21-1000"),
            ), patch.object(elevator, "_run_elevated", side_effect=fake_run):
                elevator.apply({"enabled": True})

    def test_source_mode_relaunches_main_module(self) -> None:
        request = Path("C:/Temp/request file.json")
        result = Path("C:/Temp/result file.json")
        with patch.object(sys, "frozen", False, create=True):
            executable, arguments = SchedulerElevator._command(request, result)
        self.assertEqual(executable, sys.executable)
        self.assertEqual(arguments, subprocess.list2cmdline(
            ["-m", "src.main", "--scheduler-helper", str(request), str(result)]
        ))

    def test_frozen_mode_relaunches_same_executable(self) -> None:
        request = Path("C:/Temp/request.json")
        result = Path("C:/Temp/result.json")
        with patch.object(sys, "frozen", True, create=True), patch.object(
            sys, "executable", "C:/Apps/restic-gui.exe"
        ):
            executable, arguments = SchedulerElevator._command(request, result)
        self.assertEqual(executable, "C:/Apps/restic-gui.exe")
        self.assertEqual(arguments, subprocess.list2cmdline(
            ["--scheduler-helper", str(request), str(result)]
        ))


if __name__ == "__main__":
    unittest.main()
