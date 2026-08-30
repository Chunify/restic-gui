from pathlib import Path

import webview

from src.api.app_api import AppApi
from src.services.repository_service import RepositoryService
from src.services.backup_policy_service import BackupPolicyService
from src.services.forget_policy_service import ForgetPolicyService
from src.services.restic_service import ResticService
from src.services.snapshot_service import SnapshotService
from src.services.log_service import LogService
from src.services.configuration_service import ConfigurationService
from src.services.script_service import ScriptService
from src.storage.repository_store import RepositoryStore
from src.runtime_paths import data_root, resource_root, restic_executable


def main() -> None:
    resources = resource_root()
    data_directory = data_root()
    restic_path = restic_executable(data_directory)
    store = RepositoryStore(data_directory / "restic-gui.db")
    store.initialize()
    window_holder: dict[str, webview.Window] = {}

    def select_directory() -> str | None:
        result = window_holder["window"].create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        return result[0] if isinstance(result, tuple) else result

    def select_backup_path() -> str | None:
        result = window_holder["window"].create_file_dialog(webview.FOLDER_DIALOG)
        return (result[0] if isinstance(result, tuple) else result) if result else None

    def select_backup_file() -> str | None:
        result = window_holder["window"].create_file_dialog(webview.OPEN_DIALOG)
        return (result[0] if isinstance(result, tuple) else result) if result else None

    def save_file(default_name: str) -> str | None:
        result = window_holder["window"].create_file_dialog(
            webview.SAVE_DIALOG, save_filename=default_name
        )
        return result[0] if isinstance(result, tuple) else result

    restic = ResticService(executable=restic_path, logs_directory=data_directory / "logs")
    service = RepositoryService(store, data_directory / "keys", restic)
    policy_service = BackupPolicyService(store, data_directory, restic_path)
    policy_service.regenerate_all_scripts()
    script_service = ScriptService(data_directory)
    script_service.regenerate_master()
    api = AppApi(service, policy_service, select_directory, ForgetPolicyService(store),
                 SnapshotService(store, restic), select_backup_path, select_backup_file,
                 save_file, LogService(data_directory / "logs"),
                 ConfigurationService(data_directory, script_service.master_script),
                 script_service)
    window = webview.create_window(
        "restic-gui", str(resources / "frontend" / "index.html"), js_api=api,
        width=1120, height=720, min_size=(760, 540),
    )
    window_holder["window"] = window
    webview.start()


if __name__ == "__main__":
    main()
