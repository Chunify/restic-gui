import unittest
from unittest.mock import Mock

from src.api.app_api import AppApi
from src.models.repository import Repository


class AppApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository_service = Mock()
        self.repository_service.create_repository.return_value = Repository(
            1, "Repo2026", "C:/Backup", "C:/keys/Repo2026.key"
        )
        self.api = AppApi(self.repository_service, Mock(), lambda: None)

    def test_repository_name_accepts_english_letters_and_numbers(self) -> None:
        result = self.api.create_repository("Repo2026", "C:/Backup", "secret")

        self.assertTrue(result["ok"])
        self.repository_service.create_repository.assert_called_once_with(
            "Repo2026", "C:/Backup", "secret"
        )

    def test_repository_name_rejects_special_characters(self) -> None:
        result = self.api.create_repository("Repo-2026", "C:/Backup", "secret")

        self.assertFalse(result["ok"])
        self.repository_service.create_repository.assert_not_called()


if __name__ == "__main__":
    unittest.main()
