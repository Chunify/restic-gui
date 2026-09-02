from dataclasses import dataclass


@dataclass(frozen=True)
class WindowsIdentity:
    user_id: str
    sid: str


def current_windows_identity() -> WindowsIdentity:
    """Return the identity of the process before any UAC elevation occurs."""
    try:
        import win32api
        import win32con
        import win32security

        token = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
        )
        sid_object = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        sid = win32security.ConvertSidToStringSid(sid_object)
        name, domain, _account_type = win32security.LookupAccountSid(None, sid_object)
        user_id = f"{domain}\\{name}" if domain else name
        return WindowsIdentity(user_id=user_id, sid=sid)
    except (ImportError, OSError) as error:
        raise RuntimeError("Windows 사용자 계정 정보를 확인할 수 없습니다.") from error
