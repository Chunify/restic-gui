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


def restic_executable(_data_directory: Path) -> str:
    """Return the restic executable installed on PATH."""
    installed = shutil.which("restic")
    if installed is None:
        raise FileNotFoundError("restic executable was not found")
    return installed
