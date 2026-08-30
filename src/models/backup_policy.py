from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class BackupPolicy:
    id: int
    name: str
    backup_path: str
    repository_id: int
    exclude: str | None = None
    iexclude: str | None = None
    file_from: str | None = None
    exclude_larger_than: str | None = None
    forget_policy_id: int | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
