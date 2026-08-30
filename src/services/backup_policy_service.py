import re
from pathlib import Path

from src.models.backup_policy import BackupPolicy
from src.services.forget_policy_service import ForgetPolicyService
from src.storage.repository_store import RepositoryStore
from src.services.script_service import ScriptService


class BackupPolicyService:
    FILE_FIELDS = ("exclude", "iexclude", "file_from", "exclude_larger_than")

    def __init__(self, store: RepositoryStore, data_directory: Path,
                 restic_executable: str = "restic") -> None:
        self.store = store
        self.data_directory = data_directory
        self.scripts = ScriptService(data_directory)
        self.restic_executable = restic_executable

    def list_policies(self, repository_id: int) -> list[BackupPolicy]:
        if not self.store.get(repository_id):
            raise ValueError("저장소를 찾을 수 없습니다.")
        return self.store.list_policies(repository_id)

    def save_policy(self, repository_id: int, name: str, backup_path: str,
                    file_contents: dict[str, object] | None,
                    forget_policy_id: object = None, policy_id: int | None = None) -> BackupPolicy:
        clean_name = str(name).strip()
        if not re.fullmatch(r"[A-Za-z0-9]+", clean_name):
            raise ValueError("정책 이름은 영문과 숫자만 사용할 수 있습니다.")
        clean_backup_path = str(backup_path).strip()
        if not clean_backup_path:
            raise ValueError("백업 경로를 선택해 주세요.")
        if not self.store.get(repository_id):
            raise ValueError("저장소를 찾을 수 없습니다.")
        current = self.store.get_policy(policy_id) if policy_id is not None else None
        if policy_id is not None and (not current or current.repository_id != repository_id):
            raise ValueError("백업 정책을 찾을 수 없습니다.")
        forget_id = int(forget_policy_id) if forget_policy_id not in (None, "") else None
        if forget_id is not None and not self.store.get_forget_policy(forget_id):
            raise ValueError("Forget 정책을 찾을 수 없습니다.")
        paths: dict[str, str | None] = {}
        for field in self.FILE_FIELDS:
            content = str((file_contents or {}).get(field, ""))
            path = self.data_directory / field / f"{clean_name}.dat"
            if content:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                paths[field] = str(path.resolve())
            else:
                path.unlink(missing_ok=True)
                paths[field] = None
        policy = self.store.save_policy(repository_id, clean_name, clean_backup_path, paths, forget_id, policy_id)
        if current and current.name != clean_name:
            self._remove_policy_files(current)
        self._write_script(policy)
        self.scripts.regenerate_master()
        return policy

    def read_policy_files(self, policy_id: int) -> dict[str, str]:
        policy = self.store.get_policy(policy_id)
        if not policy:
            raise ValueError("백업 정책을 찾을 수 없습니다.")
        return {field: Path(value).read_text(encoding="utf-8") if (value := getattr(policy, field)) and Path(value).exists() else "" for field in self.FILE_FIELDS}

    def delete_policy(self, policy_id: int, confirmation: str) -> None:
        policy = self.store.get_policy(policy_id)
        if not policy:
            raise ValueError("백업 정책을 찾을 수 없습니다.")
        if confirmation != policy.name:
            raise ValueError("정책 이름을 정확히 입력해 주세요.")
        self.store.delete_policy(policy_id)
        self._remove_policy_files(policy)
        self.scripts.regenerate_master()

    def regenerate_script(self, policy_id: int) -> None:
        policy = self.store.get_policy(policy_id)
        if not policy:
            raise ValueError("백업 정책을 찾을 수 없습니다.")
        self._write_script(policy)
        self.scripts.regenerate_master()

    def regenerate_all_scripts(self) -> None:
        for repository in self.store.list_all():
            for policy in self.store.list_policies(repository.id):
                self._write_script(policy)
        self.scripts.regenerate_master()

    def _remove_policy_files(self, policy: BackupPolicy) -> None:
        for field in self.FILE_FIELDS:
            if value := getattr(policy, field):
                Path(value).unlink(missing_ok=True)
        (self.data_directory / "backup-scripts" / f"{policy.name}.cmd").unlink(missing_ok=True)

    def _write_script(self, policy: BackupPolicy) -> None:
        repository = self.store.get(policy.repository_id)
        if not repository:
            raise ValueError("저장소를 찾을 수 없습니다.")
        args = [self.restic_executable, "backup", "--json", "--repo", repository.directory, "--password-file", repository.key, "--tag", policy.name]
        for field, flag in {"exclude": "--exclude-file", "iexclude": "--iexclude-file", "file_from": "--files-from", "exclude_larger_than": "--exclude-larger-than"}.items():
            if value := getattr(policy, field):
                option = Path(value).read_text(encoding="utf-8").strip() if field == "exclude_larger_than" else value
                if option:
                    args.extend((flag, option))
        args.append(policy.backup_path)
        commands = [args]
        forget = self.store.get_forget_policy(policy.forget_policy_id) if policy.forget_policy_id else None
        if forget:
            forget_args = [self.restic_executable, "forget", "--repo", repository.directory, "--password-file", repository.key, "--tag", policy.name]
            for field in ForgetPolicyService.INTEGER_FIELDS + ForgetPolicyService.WITHIN_FIELDS:
                if (value := getattr(forget, field)) is not None:
                    forget_args.extend((f"--{field.replace('_', '-')}", str(value)))
            if forget.auto_prune:
                forget_args.append("--prune")
            commands.append(forget_args)
        quote = lambda value: f'"{str(value).replace(chr(34), chr(34) * 2)}"'
        log = (self.data_directory / "logs" / "%LOGDATE%.log").resolve()
        script = "@echo off\nfor /f %%i in ('powershell -NoProfile -Command \"Get-Date -Format yy-MM-dd\"') do set LOGDATE=%%i\n"
        script += "".join(f"{' '.join(map(quote, command))} >> {quote(log)} 2>&1\n" for command in commands)
        directory = self.data_directory / "backup-scripts"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{policy.name}.cmd").write_text(script, encoding="utf-8")
