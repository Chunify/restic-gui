import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.services.subprocess_options import hidden_window_options
from src.services.windows_identity import WindowsIdentity, current_windows_identity


SCHEDULER_PERMISSION_MESSAGE = (
    "Windows 작업 스케줄러 등록 권한이 없습니다. "
    "프로그램을 관리자 권한으로 실행한 뒤 다시 시도해 주세요."
)


class ConfigurationService:
    TASK_NAME = "ResticGUIAutoTask"
    DEFAULTS = {"enabled": False, "run_at_startup": False, "interval_days": 1,
                "run_when_idle": False, "log_retention_days": 30}

    def __init__(self, data_directory: Path, master_script: Path,
                 runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
                 scheduler_applier: Callable[[dict[str, object]], None] | None = None,
                 identity_provider: Callable[[], WindowsIdentity] | None = None) -> None:
        self.data_directory = data_directory
        self.path = data_directory / "configuration.json"
        self.master_script = master_script
        self.runner = runner
        self.scheduler_applier = scheduler_applier
        self.identity_provider = identity_provider or current_windows_identity

    @staticmethod
    def _task_name_for_sid(sid: str) -> str:
        safe_sid = "".join(character for character in sid if character.isalnum() or character == "-")
        if not safe_sid:
            raise RuntimeError("Windows 사용자 SID가 올바르지 않습니다.")
        return f"{ConfigurationService.TASK_NAME}-{safe_sid}"

    def _identity(self, values: dict[str, object] | None = None) -> WindowsIdentity:
        if values is not None:
            user_id = values.get("_scheduler_user_id")
            sid = values.get("_scheduler_user_sid")
            if isinstance(user_id, str) and user_id.strip() and isinstance(sid, str) and sid.strip():
                return WindowsIdentity(user_id=user_id.strip(), sid=sid.strip())
        return self.identity_provider()

    def load(self) -> dict[str, object]:
        if not self.path.exists():
            return dict(self.DEFAULTS)
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return dict(self.DEFAULTS)
        return {**self.DEFAULTS, **{key: values[key] for key in self.DEFAULTS if key in values}}

    def save(self, values: dict[str, object]) -> dict[str, object]:
        enabled = bool(values.get("enabled"))
        try:
            interval = int(values.get("interval_days", 1))
        except (TypeError, ValueError):
            raise ValueError("자동 실행 주기는 숫자여야 합니다.") from None
        if interval < 1:
            raise ValueError("자동 실행 주기는 1일 이상이어야 합니다.")
        try:
            log_retention_days = int(values.get("log_retention_days", 30))
        except (TypeError, ValueError):
            raise ValueError("로그 보관 기간은 숫자여야 합니다.") from None
        if log_retention_days < 1:
            raise ValueError("로그 보관 기간은 1일 이상이어야 합니다.")
        clean = {"enabled": enabled, "run_at_startup": bool(values.get("run_at_startup")),
                 "interval_days": interval, "run_when_idle": bool(values.get("run_when_idle")),
                 "log_retention_days": log_retention_days}
        try:
            if self.scheduler_applier is not None:
                self.scheduler_applier(clean)
            else:
                self.apply_scheduler(clean)
        except Exception as error:
            self._write_scheduler_log(f"설정 변경 실패: {error}")
            raise
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        action = "등록" if enabled else "삭제"
        self._write_scheduler_log(f"작업 {action} 완료")
        return clean

    def details(self) -> dict[str, object]:
        try:
            identity = self._identity()
            task_name = self._task_name_for_sid(identity.sid)
        except Exception as error:
            return {
                "task_name": self.TASK_NAME,
                "task_path": f"\\{self.TASK_NAME}",
                "script_path": str(self.master_script.resolve()),
                "registered": False,
                "state": "계정 확인 실패",
                "last_result": None,
                "last_run": None,
                "next_run": None,
                "query_error": str(error),
            }
        details: dict[str, object] = {
            "task_name": task_name,
            "task_path": f"\\{task_name}",
            "script_path": str(self.master_script.resolve()),
            "registered": False,
            "state": "등록되지 않음",
            "last_result": None,
            "last_run": None,
            "next_run": None,
        }
        try:
            _scheduler, folder = self._task_folder()
            task = folder.GetTask(f"\\{task_name}")
        except Exception as error:
            # 작업이 없는 경우와 조회 권한/환경 문제를 구분할 COM 오류 코드가
            # 환경마다 달라지므로 화면에 조회 결과를 함께 제공한다.
            details["query_error"] = str(error)
            return details
        # 새 작업을 등록한 직후에는 작업 자체는 조회되더라도 개별 상태
        # 속성의 COM 조회가 일시적으로 실패할 수 있다. 부가 상태 정보 때문에
        # configuration 응답 전체가 실패하지 않게 한다.
        try:
            state_code = int(task.State)
            state_names = {0: "알 수 없음", 1: "사용 안 함", 2: "대기 중", 3: "준비됨", 4: "실행 중"}
            details.update(
                registered=True,
                state=state_names.get(state_code, f"상태 코드 {state_code}"),
                last_result=int(task.LastTaskResult),
                last_run=self._format_scheduler_time(task.LastRunTime),
                next_run=self._format_scheduler_time(task.NextRunTime),
            )
            details.pop("query_error", None)
        except Exception as error:
            details.update(registered=True, state="상태 조회 실패", query_error=str(error))
            self._write_scheduler_log(f"작업 상태 조회 실패: {error}")
        return details

    @staticmethod
    def _format_scheduler_time(value: object) -> str | None:
        if value is None:
            return None
        try:
            if getattr(value, "year", 0) < 1900:
                return None
            return value.isoformat(sep=" ", timespec="seconds")
        except (AttributeError, TypeError, ValueError):
            text = str(value).strip()
            return text or None

    def _write_scheduler_log(self, message: str) -> None:
        try:
            logs = self.data_directory / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().isoformat(sep=" ", timespec="seconds")
            with (logs / "scheduler.log").open("a", encoding="utf-8") as log:
                log.write(f"[{timestamp}] {message}\n")
        except OSError:
            pass

    def apply_scheduler(self, values: dict[str, object]) -> None:
        identity = self._identity(values)
        if bool(values.get("enabled")):
            self._register(values, identity)
        else:
            self._delete(identity=identity)

    def _register(self, values: dict[str, object], identity: WindowsIdentity) -> None:
        if self.runner is None:
            self._register_with_pywin32(values, identity)
            return
        task_name = self._task_name_for_sid(identity.sid)
        command = f'cmd.exe /c "{self.master_script.resolve()}"'
        self._run(["schtasks", "/Create", "/TN", task_name, "/TR", command,
                   "/SC", "DAILY", "/MO", str(values["interval_days"]),
                   "/RU", identity.user_id, "/IT", "/F"])
        if values["run_at_startup"]:
            self._run(["schtasks", "/Create", "/TN", f"{task_name}AtStartup", "/TR", command,
                       "/SC", "ONLOGON", "/RU", identity.user_id, "/IT", "/F"])
        else:
            self._delete(f"{task_name}AtStartup", identity)
        # 유휴 실행은 schtasks CLI로 기존 트리거에 안정적으로 병합할 수 없어,
        # 일일 작업의 유휴 대기 시간을 설정하는 PowerShell ScheduledTasks를 사용한다.
        if values["run_when_idle"]:
            script = (f"$s=New-ScheduledTaskSettingsSet -RunOnlyIfIdle; "
                      f"Set-ScheduledTask -TaskName '{task_name}' -Settings $s | Out-Null")
            self._run(["powershell", "-NoProfile", "-Command", script])

    def _delete(self, name: str | None = None,
                identity: WindowsIdentity | None = None) -> None:
        identity = identity or self._identity()
        task_name = self._task_name_for_sid(identity.sid)
        if self.runner is None:
            self._delete_with_pywin32(name, identity)
            return
        for target_name in ([name] if name else [task_name, f"{task_name}AtStartup"]):
            self.runner(["schtasks", "/Delete", "/TN", target_name, "/F"],
                        check=False, capture_output=True, text=True,
                        **hidden_window_options())

    def _run(self, command: list[str]) -> None:
        try:
            self.runner(command, check=True, capture_output=True, text=True,
                        **hidden_window_options())
        except FileNotFoundError as error:
            raise RuntimeError("Windows 작업 스케줄러를 사용할 수 없습니다.") from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or "").strip()
            if self._is_permission_error(error, detail):
                raise RuntimeError(SCHEDULER_PERMISSION_MESSAGE) from error
            raise RuntimeError(f"자동 실행 작업을 저장하지 못했습니다.{f' {detail}' if detail else ''}") from error

    @staticmethod
    def _is_permission_error(error: BaseException, detail: str = "") -> bool:
        permission_codes = {5, -2147024891, 0x80070005}
        for attribute in ("winerror", "errno", "hresult"):
            if getattr(error, attribute, None) in permission_codes:
                return True
        text = f"{detail} {error}".casefold()
        return any(marker in text for marker in (
            "access is denied", "access denied", "permission denied",
            "액세스가 거부", "액세스 거부", "권한이 없습니다", "0x80070005",
        ))

    @staticmethod
    def _task_folder():
        try:
            import win32com.client
            scheduler = win32com.client.Dispatch("Schedule.Service")
            scheduler.Connect()
            return scheduler, scheduler.GetFolder("\\")
        except (ImportError, OSError) as error:
            if ConfigurationService._is_permission_error(error):
                raise RuntimeError(SCHEDULER_PERMISSION_MESSAGE) from error
            raise RuntimeError("Windows 작업 스케줄러를 사용할 수 없습니다. pywin32 설치를 확인해 주세요.") from error

    def _register_with_pywin32(self, values: dict[str, object],
                               identity: WindowsIdentity) -> None:
        try:
            scheduler, folder = self._task_folder()
            task = scheduler.NewTask(0)
            task.RegistrationInfo.Description = "restic-gui automatic backup"
            task.Principal.UserId = identity.user_id
            task.Principal.LogonType = 3  # TASK_LOGON_INTERACTIVE_TOKEN
            task.Settings.Enabled = True
            task.Settings.StartWhenAvailable = True
            task.Settings.RunOnlyIfIdle = bool(values["run_when_idle"])
            daily = task.Triggers.Create(2)  # TASK_TRIGGER_DAILY
            daily.DaysInterval = int(values["interval_days"])
            daily.StartBoundary = datetime.now().replace(microsecond=0).isoformat()
            if values["run_at_startup"]:
                logon = task.Triggers.Create(9)  # TASK_TRIGGER_LOGON
                logon.UserId = identity.user_id
            action = task.Actions.Create(0)  # TASK_ACTION_EXEC
            action.Path = "cmd.exe"
            action.Arguments = f'/c "{self.master_script.resolve()}"'
            task_name = self._task_name_for_sid(identity.sid)
            # TASK_LOGON_INTERACTIVE_TOKEN does not use a password.  Passing an
            # empty BSTR is not the same as an empty COM VARIANT: Windows treats
            # it as a supplied (but invalid) password and returns 0x8007052E.
            folder.RegisterTaskDefinition(task_name, task, 6, identity.user_id, None, 3)
        except RuntimeError:
            raise
        except Exception as error:
            if self._is_permission_error(error):
                raise RuntimeError(SCHEDULER_PERMISSION_MESSAGE) from error
            raise RuntimeError(f"자동 실행 작업을 저장하지 못했습니다. {error}") from error

    def _delete_with_pywin32(self, name: str | None = None,
                             identity: WindowsIdentity | None = None) -> None:
        identity = identity or self._identity()
        task_name = self._task_name_for_sid(identity.sid)
        _scheduler, folder = self._task_folder()
        for target_name in ([name] if name else [task_name, f"{task_name}AtStartup"]):
            try:
                folder.DeleteTask(target_name, 0)
            except Exception:
                pass
