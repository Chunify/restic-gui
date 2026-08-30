import re

from src.models.forget_policy import ForgetPolicy
from src.storage.repository_store import RepositoryStore


class ForgetPolicyService:
    INTEGER_FIELDS = ("keep_daily", "keep_weekly", "keep_monthly", "keep_yearly", "keep_last")
    WITHIN_FIELDS = ("keep_within_daily", "keep_within_weekly", "keep_within_monthly", "keep_within_yearly")

    def __init__(self, store: RepositoryStore) -> None:
        self.store = store

    def list_policies(self) -> list[ForgetPolicy]:
        return self.store.list_forget_policies()

    def save_policy(self, name: str, values: dict[str, object] | None,
                    policy_id: int | None = None) -> ForgetPolicy:
        clean_name = str(name).strip()
        if not re.fullmatch(r"[A-Za-z0-9]+", clean_name):
            raise ValueError("정책 이름은 영문과 숫자만 사용할 수 있습니다.")
        clean: dict[str, object] = {"auto_prune": bool((values or {}).get("auto_prune"))}
        for field in self.INTEGER_FIELDS:
            value = (values or {}).get(field)
            if value in (None, ""):
                clean[field] = None
                continue
            try:
                number = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"{field.replace('_', '-')} 값은 숫자여야 합니다.") from None
            if number < 1:
                raise ValueError(f"{field.replace('_', '-')} 값은 1 이상이어야 합니다.")
            clean[field] = number
        for field in self.WITHIN_FIELDS:
            clean[field] = str((values or {}).get(field) or "").strip() or None
        return self.store.save_forget_policy(clean_name, clean, policy_id)

    def delete_policy(self, policy_id: int, confirmation: str) -> None:
        policy = self.store.get_forget_policy(policy_id)
        if not policy:
            raise ValueError("Forget 정책을 찾을 수 없습니다.")
        if confirmation != policy.name:
            raise ValueError("정책 이름을 정확히 입력해 주세요.")
        self.store.delete_forget_policy(policy_id)
