import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from src.runtime_paths import data_root, resource_root, restic_executable


class RuntimePathsTest(unittest.TestCase):
    def test_source_paths_use_project_root(self) -> None:
        expected = Path(__file__).resolve().parent.parent
        self.assertEqual(resource_root(), expected)
        self.assertEqual(data_root(), expected / "data")

    def test_frozen_data_is_stored_next_to_executable(self) -> None:
        executable = Path("C:/Apps/restic-gui/restic-gui.exe")
        with patch.object(sys, "frozen", True, create=True), patch.object(
            sys, "executable", str(executable)
        ):
            self.assertEqual(data_root(), executable.parent / "data")

    def test_bundled_resources_use_meipass(self) -> None:
        bundle = Path("C:/Temp/restic-gui-bundle")
        with patch.object(sys, "_MEIPASS", str(bundle), create=True):
            self.assertEqual(resource_root(), bundle)

    def test_source_mode_falls_back_to_path_restic(self) -> None:
        self.assertEqual(restic_executable(Path("unused")), "restic")


if __name__ == "__main__":
    unittest.main()
