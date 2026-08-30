import tempfile
import unittest
from pathlib import Path

from src.services.backup_policy_service import BackupPolicyService
from src.services.forget_policy_service import ForgetPolicyService
from src.storage.repository_store import RepositoryStore


class BackupPolicyServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = RepositoryStore(self.root / "app.db")
        self.store.initialize()
        self.repository = self.store.add("Repo", str(self.root / "repo"), str(self.root / "key"))
        self.service = BackupPolicyService(self.store, self.root / "data")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_saves_policy_files_forget_values_and_script(self) -> None:
        forget = ForgetPolicyService(self.store).save_policy(
            "retention7", {"keep_daily": "7", "auto_prune": True}
        )
        policy = self.service.save_policy(
            self.repository.id, "daily", "C:/Source",
            {"exclude": "*.tmp", "file_from": "C:/Source", "exclude_larger_than": "10M"},
            forget.id,
        )
        self.assertEqual(policy.forget_policy_id, forget.id)
        self.assertEqual(Path(policy.exclude).read_text(encoding="utf-8"), "*.tmp")
        self.assertEqual(Path(policy.exclude), (self.root / "data" / "exclude" / "daily.dat").resolve())
        self.assertEqual(Path(policy.file_from), (self.root / "data" / "file_from" / "daily.dat").resolve())
        self.assertEqual(Path(policy.exclude_larger_than), (self.root / "data" / "exclude_larger_than" / "daily.dat").resolve())
        script = (self.root / "data" / "backup-scripts" / "daily.cmd").read_text(encoding="utf-8")
        self.assertIn('"--json"', script)
        self.assertIn("--exclude-file", script)
        self.assertIn("--exclude-larger-than", script)
        self.assertIn("--keep-daily", script)
        self.assertIn("--prune", script)

    def test_delete_requires_exact_policy_name(self) -> None:
        policy = self.service.save_policy(self.repository.id, "daily", "C:/Source", {}, None)
        with self.assertRaises(ValueError):
            self.service.delete_policy(policy.id, "Daily")
        self.service.delete_policy(policy.id, "daily")
        self.assertEqual(self.store.list_policies(self.repository.id), [])

    def test_requires_a_backup_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "백업 경로"):
            self.service.save_policy(self.repository.id, "daily", "", {}, None)

    def test_script_uses_configured_restic_executable(self) -> None:
        executable = str(self.root / "data" / "bin" / "restic.exe")
        service = BackupPolicyService(self.store, self.root / "data", executable)
        service.save_policy(self.repository.id, "portable", "C:/Source", {}, None)
        script = (self.root / "data" / "backup-scripts" / "portable.cmd").read_text(encoding="utf-8")
        self.assertIn(f'"{executable}"', script)


if __name__ == "__main__":
    unittest.main()
