import re
import sqlite3
from typing import Callable

from src.services.backup_policy_service import BackupPolicyService
from src.services.forget_policy_service import ForgetPolicyService
from src.services.repository_service import RepositoryService
from src.services.restic_service import ResticError
from src.services.snapshot_service import SnapshotService
from src.services.log_service import LogService
from src.services.configuration_service import ConfigurationService
from src.services.script_service import ScriptService


class AppApi:
    def __init__(self, repository_service: RepositoryService,
                 policy_service: BackupPolicyService,
                 directory_picker: Callable[[], str | None],
                 forget_service: ForgetPolicyService | None = None,
                 snapshot_service: SnapshotService | None = None,
                 backup_path_picker: Callable[[], str | None] | None = None,
                 backup_file_picker: Callable[[], str | None] | None = None,
                 save_file_picker: Callable[[str], str | None] | None = None,
                 log_service: LogService | None = None,
                 configuration_service: ConfigurationService | None = None,
                 script_service: ScriptService | None = None) -> None:
        self.repository_service = repository_service
        self.policy_service = policy_service
        self.directory_picker = directory_picker
        self.forget_service = forget_service
        self.snapshot_service = snapshot_service
        self.backup_path_picker = backup_path_picker or directory_picker
        self.backup_file_picker = backup_file_picker or self.backup_path_picker
        self.save_file_picker = save_file_picker or (lambda _name: None)
        self.log_service = log_service
        self.configuration_service = configuration_service
        self.script_service = script_service

    def list_repositories(self) -> dict[str, object]:
        return self._value(lambda: {"repositories": [item.to_dict() for item in self.repository_service.list_repositories()]})

    def select_directory(self) -> dict[str, object]:
        return self._value(lambda: {"directory": self.directory_picker()})

    def select_backup_path(self) -> dict[str, object]:
        return self._value(lambda: {"path": self.backup_path_picker()})

    def select_backup_file(self) -> dict[str, object]:
        return self._value(lambda: {"path": self.backup_file_picker()})

    def create_repository(self, name: str, directory: str, password: str) -> dict[str, object]:
        try:
            if not re.fullmatch(r"[A-Za-z0-9]+", name.strip()):
                raise ValueError("저장소 이름은 영문과 숫자만 사용할 수 있습니다.")
            repository = self.repository_service.create_repository(name, directory, password)
            return self._ok({"repository": repository.to_dict()})
        except (ValueError, ResticError) as error:
            return self._error(str(error))
        except sqlite3.IntegrityError:
            return self._error("이미 사용 중인 저장소 이름입니다.")
        except Exception:
            return self._error("저장소를 등록하지 못했습니다.")

    def delete_repository(self, repository_id: int, confirmation: str) -> dict[str, object]:
        return self._action(lambda: self.repository_service.delete_repository(int(repository_id), confirmation))

    def list_backup_policies(self, repository_id: int) -> dict[str, object]:
        return self._value(lambda: {"policies": [item.to_dict() for item in self.policy_service.list_policies(int(repository_id))]})

    def get_policy_files(self, policy_id: int) -> dict[str, object]:
        return self._value(lambda: {"files": self.policy_service.read_policy_files(int(policy_id))})

    def save_backup_policy(self, repository_id: int, name: str, backup_path: str,
                           files: dict[str, object], forget_policy_id: object = None,
                           policy_id: int | None = None) -> dict[str, object]:
        return self._value(lambda: {"policy": self.policy_service.save_policy(
            int(repository_id), name, backup_path, files, forget_policy_id,
            int(policy_id) if policy_id is not None else None).to_dict()})

    def delete_backup_policy(self, policy_id: int, confirmation: str) -> dict[str, object]:
        return self._action(lambda: self.policy_service.delete_policy(int(policy_id), confirmation))

    def regenerate_backup_script(self, policy_id: int) -> dict[str, object]:
        return self._action(lambda: self.policy_service.regenerate_script(int(policy_id)))

    def list_forget_policies(self) -> dict[str, object]:
        return self._value(lambda: {"policies": [item.to_dict() for item in self._forget().list_policies()]})

    def save_forget_policy(self, name: str, values: dict[str, object],
                           policy_id: int | None = None) -> dict[str, object]:
        return self._value(lambda: {"policy": self._forget().save_policy(
            name, values, int(policy_id) if policy_id is not None else None).to_dict(),
            "warning": "이미 생성된 백업 스크립트는 자동 갱신되지 않습니다. 수동으로 갱신해 주세요."})

    def delete_forget_policy(self, policy_id: int, confirmation: str) -> dict[str, object]:
        return self._action(lambda: self._forget().delete_policy(int(policy_id), confirmation))

    def list_snapshots(self, repository_id: int) -> dict[str, object]:
        return self._value(lambda: {"snapshots": self._snapshots().list_snapshots(int(repository_id))})

    def save_snapshot_contents(self, repository_id: int, snapshot_id: str) -> dict[str, object]:
        def save() -> dict[str, object]:
            destination = self.save_file_picker(f"snapshot-{snapshot_id}.txt")
            if not destination:
                return {"cancelled": True}
            self._snapshots().save_contents(int(repository_id), snapshot_id, destination)
            return {"cancelled": False, "path": destination}
        return self._value(save)

    def list_logs(self) -> dict[str, object]:
        return self._value(lambda: {"logs": self._logs().list_logs()})

    def read_log(self, name: str) -> dict[str, object]:
        return self._value(lambda: {"name": name, "content": self._logs().read_log(name)})

    def delete_log(self, name: str) -> dict[str, object]:
        return self._action(lambda: self._logs().delete_log(name))

    def delete_all_logs(self) -> dict[str, object]:
        return self._action(self._logs().delete_all)

    def get_configuration(self) -> dict[str, object]:
        return self._value(lambda: {"configuration": self._configuration().load()})

    def save_configuration(self, values: dict[str, object]) -> dict[str, object]:
        return self._value(lambda: {"configuration": self._configuration().save(values)})

    def run_manual_backup(self) -> dict[str, object]:
        return self._action(self._scripts().run_manual_backup)

    def start_manual_backup(self) -> dict[str, object]:
        return self._value(lambda: {"backup": self._scripts().start_manual_backup()})

    def get_manual_backup_status(self) -> dict[str, object]:
        return self._value(lambda: {"backup": self._scripts().manual_backup_status()})

    def _forget(self) -> ForgetPolicyService:
        if not self.forget_service:
            raise RuntimeError("Forget 정책 서비스를 사용할 수 없습니다.")
        return self.forget_service

    def _snapshots(self) -> SnapshotService:
        if not self.snapshot_service:
            raise RuntimeError("스냅샷 서비스를 사용할 수 없습니다.")
        return self.snapshot_service

    def _logs(self) -> LogService:
        if not self.log_service:
            raise RuntimeError("로그 서비스를 사용할 수 없습니다.")
        return self.log_service

    def _configuration(self) -> ConfigurationService:
        if not self.configuration_service:
            raise RuntimeError("설정 서비스를 사용할 수 없습니다.")
        return self.configuration_service

    def _scripts(self) -> ScriptService:
        if not self.script_service:
            raise RuntimeError("백업 실행 서비스를 사용할 수 없습니다.")
        return self.script_service

    def _value(self, action: Callable[[], dict[str, object]]) -> dict[str, object]:
        try:
            return self._ok(action())
        except (ValueError, TypeError, RuntimeError, sqlite3.IntegrityError, ResticError) as error:
            message = "이미 사용 중인 이름입니다." if isinstance(error, sqlite3.IntegrityError) else str(error)
            return self._error(message)
        except Exception:
            return self._error("요청을 처리하지 못했습니다.")

    def _action(self, action: Callable[[], None]) -> dict[str, object]:
        return self._value(lambda: (action(), {})[1])

    @staticmethod
    def _ok(data: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "data": data}

    @staticmethod
    def _error(message: str) -> dict[str, object]:
        return {"ok": False, "error": {"message": message}}
