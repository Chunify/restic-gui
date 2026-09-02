import unittest
import os
from pathlib import Path
from unittest.mock import Mock, patch

from src import main


class MainWiringTest(unittest.TestCase):
    @patch("src.main.webbrowser.open")
    @patch("src.main.ctypes.windll.user32.MessageBoxW")
    def test_missing_restic_message_opens_installation_page(
        self, message_box: Mock, open_browser: Mock
    ) -> None:
        main.show_missing_restic_message()

        self.assertIn("restic을 설치", message_box.call_args.args[1])
        open_browser.assert_called_once_with(main.RESTIC_INSTALLATION_URL)

    @patch("src.main.show_missing_restic_message")
    @patch("src.main.restic_executable", side_effect=FileNotFoundError)
    @patch("src.main.data_root", return_value=Path("data"))
    @patch("src.main.resource_root", return_value=Path("resources"))
    @patch("src.main.webview.create_window")
    def test_missing_restic_shows_message_and_exits(
        self,
        create_window: Mock,
        _resource_root: Mock,
        _data_root: Mock,
        _restic_executable: Mock,
        show_message: Mock,
    ) -> None:
        main.main()

        show_message.assert_called_once_with()
        create_window.assert_not_called()

    @patch.dict(os.environ, {"LOCALAPPDATA": "data"})
    @patch("src.main.webview.start")
    @patch("src.main.webview.create_window")
    @patch("src.main.SchedulerElevator")
    @patch("src.main.ScriptService")
    @patch("src.main.RepositoryStore")
    @patch("src.main.restic_executable", return_value="restic")
    @patch("src.main.data_root", return_value=Path("data"))
    @patch("src.main.resource_root", return_value=Path("resources"))
    def test_configuration_changes_use_elevated_scheduler_helper(
        self,
        _resource_root: Mock,
        _data_root: Mock,
        _restic_executable: Mock,
        repository_store: Mock,
        script_service: Mock,
        scheduler_elevator: Mock,
        create_window: Mock,
        _start: Mock,
    ) -> None:
        class ClosingEvent:
            def __iadd__(self, _handler: object):
                return self

        window = create_window.return_value
        window.events.closing = ClosingEvent()
        script_service.return_value.master_script = Path("data/master.cmd")

        main.main()

        api = create_window.call_args.kwargs["js_api"]
        self.assertIs(
            api.configuration_service.scheduler_applier,
            scheduler_elevator.return_value.apply,
        )
        repository_store.return_value.initialize.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
