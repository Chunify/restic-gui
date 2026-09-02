import unittest
from unittest.mock import Mock

from src.api.app_api import AppApi
from src.models.repository import Repository
from src.services.repository_service import ExistingRepositoryError


class AppApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository_service = Mock()
        self.repository_service.create_repository.return_value = Repository(
            1, "Repo2026", "C:/Backup", "C:/keys/Repo2026.key"
        )
        self.api = AppApi(self.repository_service, Mock(), lambda: None)

    def test_repository_name_accepts_english_letters_and_numbers(self) -> None:
        result = self.api.create_repository(
            "Repo2026", "C:/Backup", "secret", "secret"
        )

        self.assertTrue(result["ok"])
        self.repository_service.create_repository.assert_called_once_with(
            "Repo2026", "C:/Backup", "secret", False
        )

    def test_repository_name_rejects_special_characters(self) -> None:
        result = self.api.create_repository(
            "Repo-2026", "C:/Backup", "secret", "secret"
        )

        self.assertFalse(result["ok"])
        self.repository_service.create_repository.assert_not_called()

    def test_repository_passwords_must_match(self) -> None:
        result = self.api.create_repository(
            "Repo2026", "C:/Backup", "secret", "different"
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["message"], "비밀번호가 일치하지 않습니다.")
        self.repository_service.create_repository.assert_not_called()

    def test_existing_repository_returns_confirmation_code(self) -> None:
        self.repository_service.create_repository.side_effect = ExistingRepositoryError(
            "이미 리포지터리가 생성된 경로입니다. 등록하시겠습니까?"
        )

        result = self.api.create_repository(
            "Repo2026", "C:/Backup", "secret", "secret"
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "existing_repository")

    def test_restore_snapshot_uses_selected_directory(self) -> None:
        snapshot_service = Mock()
        self.api.snapshot_service = snapshot_service
        self.api.directory_picker = lambda: "D:/Restore"

        result = self.api.restore_snapshot(1, "abcdef12")

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"], {"cancelled": False, "path": "D:/Restore"})
        snapshot_service.restore.assert_called_once_with(1, "abcdef12", "D:/Restore")

    def test_list_snapshots_passes_policy_tag(self) -> None:
        snapshot_service = Mock()
        snapshot_service.list_snapshots.return_value = []
        self.api.snapshot_service = snapshot_service

        result = self.api.list_snapshots(1, "daily")

        self.assertTrue(result["ok"])
        snapshot_service.list_snapshots.assert_called_once_with(1, "daily")

    def test_restore_snapshot_cancel_does_not_call_service(self) -> None:
        snapshot_service = Mock()
        self.api.snapshot_service = snapshot_service
        self.api.directory_picker = lambda: None

        result = self.api.restore_snapshot(1, "abcdef12")

        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["cancelled"])
        snapshot_service.restore.assert_not_called()


if __name__ == "__main__":
    unittest.main()
