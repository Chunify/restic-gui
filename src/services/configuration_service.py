import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.services.subprocess_options import hidden_window_options


SCHEDULER_PERMISSION_MESSAGE = (
    "Windows 작업 스케줄러 등록 권한이 없습니다. "
    "프로그램을 관리자 권한으로 실행한 뒤 다시 시도해 주세요."
)


class ConfigurationService:
    TASK_NAME = "ResticGUIAutoTask"
    DEFAULTS = {"enabled": False, "run_at_startup": False, "interval_days": 1,
                "run_when_idle": False}

    def __init__(self, data_directory: Path, master_script: Path,
                 runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
                 scheduler_applier: Callable[[dict[str, object]], None] | None = None) -> None:
        self.path = data_directory / "configuration.json"
        self.master_script = master_script
        self.runner = runner
        self.scheduler_applier = scheduler_applier

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
        clean = {"enabled": enabled, "run_at_startup": bool(values.get("run_at_startup")),
                 "interval_days": interval, "run_when_idle": bool(values.get("run_when_idle"))}
        if self.scheduler_applier is not None:
            self.scheduler_applier(clean)
        else:
            self.apply_scheduler(clean)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        return clean

    def apply_scheduler(self, values: dict[str, object]) -> None:
        if bool(values.get("enabled")):
            self._register(values)
        else:
            self._delete()

    def _register(self, values: dict[str, object]) -> None:
        if self.runner is None:
            self._register_with_pywin32(values)
            return
        command = f'cmd.exe /c "{self.master_script.resolve()}"'
        self._run(["schtasks", "/Create", "/TN", self.TASK_NAME, "/TR", command,
                   "/SC", "DAILY", "/MO", str(values["interval_days"]), "/F"])
        if values["run_at_startup"]:
            self._run(["schtasks", "/Create", "/TN", f"{self.TASK_NAME}AtStartup", "/TR", command,
                       "/SC", "ONSTART", "/F"])
        else:
            self._delete(f"{self.TASK_NAME}AtStartup")
        # 유휴 실행은 schtasks CLI로 기존 트리거에 안정적으로 병합할 수 없어,
        # 일일 작업의 유휴 대기 시간을 설정하는 PowerShell ScheduledTasks를 사용한다.
        if values["run_when_idle"]:
            script = (f"$s=New-ScheduledTaskSettingsSet -RunOnlyIfIdle; "
                      f"Set-ScheduledTask -TaskName '{self.TASK_NAME}' -Settings $s | Out-Null")
            self._run(["powershell", "-NoProfile", "-Command", script])

    def _delete(self, name: str | None = None) -> None:
        if self.runner is None:
            self._delete_with_pywin32(name)
            return
        for task_name in ([name] if name else [self.TASK_NAME, f"{self.TASK_NAME}AtStartup"]):
            self.runner(["schtasks", "/Delete", "/TN", task_name, "/F"],
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

    def _register_with_pywin32(self, values: dict[str, object]) -> None:
        try:
            scheduler, folder = self._task_folder()
            task = scheduler.NewTask(0)
            task.RegistrationInfo.Description = "restic-gui automatic backup"
            task.Settings.Enabled = True
            task.Settings.StartWhenAvailable = True
            task.Settings.RunOnlyIfIdle = bool(values["run_when_idle"])
            daily = task.Triggers.Create(2)  # TASK_TRIGGER_DAILY
            daily.DaysInterval = int(values["interval_days"])
            daily.StartBoundary = datetime.now().replace(microsecond=0).isoformat()
            if values["run_at_startup"]:
                task.Triggers.Create(8)  # TASK_TRIGGER_BOOT
            action = task.Actions.Create(0)  # TASK_ACTION_EXEC
            action.Path = "cmd.exe"
            action.Arguments = f'/c "{self.master_script.resolve()}"'
            folder.RegisterTaskDefinition(self.TASK_NAME, task, 6, "", "", 3)
        except RuntimeError:
            raise
        except Exception as error:
            if self._is_permission_error(error):
                raise RuntimeError(SCHEDULER_PERMISSION_MESSAGE) from error
            raise RuntimeError(f"자동 실행 작업을 저장하지 못했습니다. {error}") from error

    def _delete_with_pywin32(self, name: str | None = None) -> None:
        _scheduler, folder = self._task_folder()
        for task_name in ([name] if name else [self.TASK_NAME, f"{self.TASK_NAME}AtStartup"]):
            try:
                folder.DeleteTask(task_name, 0)
            except Exception:
                pass
