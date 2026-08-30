import sys
import shutil
from pathlib import Path


def resource_root() -> Path:
    """Return the directory containing bundled, read-only application files."""
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(bundled_root)
    return Path(__file__).resolve().parent.parent


def data_root() -> Path:
    """Return the persistent data directory next to the executable/source tree."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return resource_root() / "data"


def restic_executable(data_directory: Path) -> str:
    """Install and return the bundled restic binary, or fall back to PATH in source mode."""
    bundled = resource_root() / "restic" / "restic.exe"
    if not bundled.is_file():
        return "restic"
    installed = data_directory / "bin" / "restic.exe"
    installed.parent.mkdir(parents=True, exist_ok=True)
    if not installed.is_file() or installed.stat().st_size != bundled.stat().st_size:
        shutil.copy2(bundled, installed)
    return str(installed.resolve())
