from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Repository:
    id: int
    name: str
    directory: str
    key: str
    size_bytes: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
