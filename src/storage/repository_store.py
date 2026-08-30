import sqlite3
from contextlib import closing
from pathlib import Path

from src.models.backup_policy import BackupPolicy
from src.models.forget_policy import ForgetPolicy
from src.models.repository import Repository


class RepositoryStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS repository (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                directory TEXT NOT NULL, key TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS forget_policy (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                keep_daily INTEGER, keep_weekly INTEGER, keep_monthly INTEGER,
                keep_yearly INTEGER, keep_within_daily TEXT, keep_within_weekly TEXT,
                keep_within_monthly TEXT, keep_within_yearly TEXT, keep_last INTEGER,
                auto_prune INTEGER NOT NULL DEFAULT 0)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS backup_policy (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                backup_path TEXT NOT NULL, repository_id INTEGER NOT NULL,
                exclude TEXT, iexclude TEXT, file_from TEXT, exclude_larger_than TEXT,
                forget_policy_id INTEGER,
                FOREIGN KEY(repository_id) REFERENCES repository(id) ON DELETE CASCADE,
                FOREIGN KEY(forget_policy_id) REFERENCES forget_policy(id) ON DELETE SET NULL)""")
            self._migrate(connection)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        forget_columns = {row[1] for row in connection.execute("PRAGMA table_info(forget_policy)")}
        if "name" not in forget_columns:
            connection.execute("ALTER TABLE forget_policy ADD COLUMN name TEXT")
            connection.execute("UPDATE forget_policy SET name='legacy-' || id WHERE name IS NULL")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS forget_policy_name ON forget_policy(name)")
        policy_columns = {row[1] for row in connection.execute("PRAGMA table_info(backup_policy)")}
        if "backup_interval_days" in policy_columns:
            connection.execute("ALTER TABLE backup_policy DROP COLUMN backup_interval_days")
        if "backup_path" not in policy_columns:
            connection.execute("ALTER TABLE backup_policy ADD COLUMN backup_path TEXT")
            for row in connection.execute("SELECT id,file_from FROM backup_policy").fetchall():
                value = ""
                if row[1] and Path(row[1]).is_file():
                    value = Path(row[1]).read_text(encoding="utf-8").strip()
                connection.execute("UPDATE backup_policy SET backup_path=? WHERE id=?", (value, row[0]))
        if "forget_policy_id" not in policy_columns:
            connection.execute("ALTER TABLE backup_policy ADD COLUMN forget_policy_id INTEGER")
            if "forget_policy" in policy_columns:
                connection.execute("UPDATE backup_policy SET forget_policy_id=forget_policy")

    def list_all(self) -> list[Repository]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT id,name,directory,key FROM repository ORDER BY id DESC").fetchall()
        return [Repository(**dict(row)) for row in rows]

    def name_exists(self, name: str) -> bool:
        with closing(self._connect()) as connection:
            return connection.execute("SELECT 1 FROM repository WHERE name=?", (name,)).fetchone() is not None

    def add(self, name: str, directory: str, key: str) -> Repository:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute("INSERT INTO repository(name,directory,key) VALUES(?,?,?)", (name, directory, key))
        return Repository(int(cursor.lastrowid), name, directory, key)

    def get(self, repository_id: int) -> Repository | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT id,name,directory,key FROM repository WHERE id=?", (repository_id,)).fetchone()
        return Repository(**dict(row)) if row else None

    def delete(self, repository_id: int) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM backup_policy WHERE repository_id=?", (repository_id,))
            connection.execute("DELETE FROM repository WHERE id=?", (repository_id,))

    def list_policies(self, repository_id: int) -> list[BackupPolicy]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT id,name,backup_path,repository_id,exclude,iexclude,file_from,exclude_larger_than,forget_policy_id FROM backup_policy WHERE repository_id=? ORDER BY id DESC", (repository_id,)).fetchall()
        return [BackupPolicy(**dict(row)) for row in rows]

    def get_policy(self, policy_id: int) -> BackupPolicy | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT id,name,backup_path,repository_id,exclude,iexclude,file_from,exclude_larger_than,forget_policy_id FROM backup_policy WHERE id=?", (policy_id,)).fetchone()
        return BackupPolicy(**dict(row)) if row else None

    def save_policy(self, repository_id: int, name: str, backup_path: str,
                    files: dict[str, str | None], forget_policy_id: int | None,
                    policy_id: int | None = None) -> BackupPolicy:
        data = (name, backup_path, repository_id, files.get("exclude"), files.get("iexclude"),
                files.get("file_from"), files.get("exclude_larger_than"), forget_policy_id)
        with closing(self._connect()) as connection, connection:
            if policy_id is None:
                cursor = connection.execute("""INSERT INTO backup_policy
                    (name,backup_path,repository_id,exclude,iexclude,file_from,exclude_larger_than,forget_policy_id)
                    VALUES(?,?,?,?,?,?,?,?)""", data)
                policy_id = int(cursor.lastrowid)
            else:
                cursor = connection.execute("""UPDATE backup_policy SET name=?,backup_path=?,repository_id=?,
                    exclude=?,iexclude=?,file_from=?,exclude_larger_than=?,forget_policy_id=? WHERE id=?""", (*data, policy_id))
                if cursor.rowcount == 0:
                    raise ValueError("백업 정책을 찾을 수 없습니다.")
        policy = self.get_policy(policy_id)
        assert policy is not None
        return policy

    def delete_policy(self, policy_id: int) -> BackupPolicy | None:
        policy = self.get_policy(policy_id)
        if policy:
            with closing(self._connect()) as connection, connection:
                connection.execute("DELETE FROM backup_policy WHERE id=?", (policy_id,))
        return policy

    def list_forget_policies(self) -> list[ForgetPolicy]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT id,name,keep_daily,keep_weekly,keep_monthly,keep_yearly,keep_within_daily,keep_within_weekly,keep_within_monthly,keep_within_yearly,keep_last,auto_prune FROM forget_policy ORDER BY id DESC").fetchall()
        return [self._forget_from_row(row) for row in rows]

    def get_forget_policy(self, policy_id: int) -> ForgetPolicy | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT id,name,keep_daily,keep_weekly,keep_monthly,keep_yearly,keep_within_daily,keep_within_weekly,keep_within_monthly,keep_within_yearly,keep_last,auto_prune FROM forget_policy WHERE id=?", (policy_id,)).fetchone()
        return self._forget_from_row(row) if row else None

    def save_forget_policy(self, name: str, values: dict[str, object], policy_id: int | None = None) -> ForgetPolicy:
        keys = ("keep_daily", "keep_weekly", "keep_monthly", "keep_yearly", "keep_within_daily", "keep_within_weekly", "keep_within_monthly", "keep_within_yearly", "keep_last", "auto_prune")
        data = (name, *(values.get(key) for key in keys[:-1]), int(bool(values.get("auto_prune"))))
        with closing(self._connect()) as connection, connection:
            if policy_id is None:
                cursor = connection.execute(f"INSERT INTO forget_policy(name,{','.join(keys)}) VALUES({','.join('?' for _ in data)})", data)
                policy_id = int(cursor.lastrowid)
            else:
                assignments = ",".join(f"{key}=?" for key in ("name", *keys))
                cursor = connection.execute(f"UPDATE forget_policy SET {assignments} WHERE id=?", (*data, policy_id))
                if cursor.rowcount == 0:
                    raise ValueError("Forget 정책을 찾을 수 없습니다.")
        policy = self.get_forget_policy(policy_id)
        assert policy is not None
        return policy

    def delete_forget_policy(self, policy_id: int) -> ForgetPolicy | None:
        policy = self.get_forget_policy(policy_id)
        if policy:
            with closing(self._connect()) as connection, connection:
                connection.execute("UPDATE backup_policy SET forget_policy_id=NULL WHERE forget_policy_id=?", (policy_id,))
                connection.execute("DELETE FROM forget_policy WHERE id=?", (policy_id,))
        return policy

    @staticmethod
    def _forget_from_row(row: sqlite3.Row) -> ForgetPolicy:
        values = dict(row)
        values["auto_prune"] = bool(values["auto_prune"])
        return ForgetPolicy(**values)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection
