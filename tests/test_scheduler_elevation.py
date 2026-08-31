import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from src.services.scheduler_elevation import SchedulerElevator


class SchedulerElevationTest(unittest.TestCase):
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
