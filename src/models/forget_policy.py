from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ForgetPolicy:
    id: int
    name: str
    keep_daily: int | None = None
    keep_weekly: int | None = None
    keep_monthly: int | None = None
    keep_yearly: int | None = None
    keep_within_daily: str | None = None
    keep_within_weekly: str | None = None
    keep_within_monthly: str | None = None
    keep_within_yearly: str | None = None
    keep_last: int | None = None
    auto_prune: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
