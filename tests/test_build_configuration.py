import unittest
from pathlib import Path


class BuildConfigurationTest(unittest.TestCase):
    def test_windows_com_timezone_module_is_bundled(self) -> None:
        root = Path(__file__).resolve().parent.parent
        build_script = (root / "scripts" / "build.ps1").read_text(encoding="utf-8")
        spec = (root / "restic-gui.spec").read_text(encoding="utf-8")

        self.assertIn("--hidden-import win32timezone", build_script)
        self.assertIn("hiddenimports=['win32timezone']", spec)


if __name__ == "__main__":
    unittest.main()
