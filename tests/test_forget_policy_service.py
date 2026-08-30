import tempfile
import unittest
from pathlib import Path

from src.services.forget_policy_service import ForgetPolicyService
from src.storage.repository_store import RepositoryStore


class ForgetPolicyServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = RepositoryStore(Path(self.temporary.name) / "app.db")
        self.store.initialize()
        self.service = ForgetPolicyService(self.store)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_create_update_and_delete_policy(self) -> None:
        policy = self.service.save_policy("retention7", {"keep_daily": "7", "auto_prune": True})
        self.assertEqual(policy.keep_daily, 7)
        self.assertTrue(policy.auto_prune)
        updated = self.service.save_policy("retention30", {"keep_last": "30"}, policy.id)
        self.assertEqual(updated.keep_last, 30)
        with self.assertRaises(ValueError):
            self.service.delete_policy(policy.id, "wrong")
        self.service.delete_policy(policy.id, "retention30")
        self.assertEqual(self.service.list_policies(), [])

    def test_name_uses_letters_and_numbers_only(self) -> None:
        with self.assertRaisesRegex(ValueError, "영문과 숫자"):
            self.service.save_policy("daily-policy", {})


if __name__ == "__main__":
    unittest.main()
