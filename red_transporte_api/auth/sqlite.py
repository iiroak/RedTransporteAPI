"""SQLite implementation of AuthStorage."""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from red_transporte_api.auth.storage import AuthStorage
from red_transporte_api.auth.models import APISettings, TokenRecord


class SQLiteAuthStorage(AuthStorage):
    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(self._db_path.parent, 0o700)
            except OSError:
                pass
            self._conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False, timeout=30
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=30000")
            try:
                os.chmod(self._db_path, 0o600)
            except OSError:
                pass
        return self._conn

    def initialize(
        self,
        initial_public_api_enabled: bool = True,
        initial_public_ip_limit: int = 20,
    ) -> None:
        with self._lock:
            self._initialize_locked(initial_public_api_enabled, initial_public_ip_limit)

    def _initialize_locked(
        self,
        initial_public_api_enabled: bool = True,
        initial_public_ip_limit: int = 20,
    ) -> None:
        conn = self._connect()
        conn.executescript(f"""
            CREATE TABLE IF NOT EXISTS api_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                public_api_enabled INTEGER NOT NULL DEFAULT 1,
                public_ip_limit_per_minute INTEGER NOT NULL DEFAULT 20,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT OR IGNORE INTO api_settings (id, public_api_enabled, public_ip_limit_per_minute)
                VALUES (1, {int(initial_public_api_enabled)}, {int(initial_public_ip_limit)});

            CREATE TABLE IF NOT EXISTS api_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                is_unlimited INTEGER NOT NULL DEFAULT 0,
                requests_per_minute INTEGER NOT NULL DEFAULT 60,
                allow_gtfs INTEGER NOT NULL DEFAULT 1,
                allow_ibus INTEGER NOT NULL DEFAULT 1,
                allow_red_web INTEGER NOT NULL DEFAULT 1,
                allow_raptor INTEGER NOT NULL DEFAULT 1,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_used_at TEXT
            );

            CREATE TABLE IF NOT EXISTS rate_limit_counters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_type TEXT NOT NULL,
                subject_key TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                window_start INTEGER NOT NULL,
                request_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE(subject_type, subject_key, resource_type, window_start)
            );

            CREATE INDEX IF NOT EXISTS idx_rate_limit ON rate_limit_counters(subject_type, subject_key, resource_type, window_start);
        """)
        conn.commit()
        self._cleanup_old_rate_counters(conn)

    def get_settings(self) -> APISettings:
        with self._lock:
            conn = self._connect()
            row = conn.execute("SELECT public_api_enabled, public_ip_limit_per_minute, updated_at FROM api_settings WHERE id = 1").fetchone()
            return APISettings(
                public_api_enabled=bool(row["public_api_enabled"]),
                public_ip_limit_per_minute=row["public_ip_limit_per_minute"],
                updated_at=row["updated_at"],
            )

    def update_settings(self, settings: APISettings) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute(
                "UPDATE api_settings SET public_api_enabled = ?, public_ip_limit_per_minute = ?, updated_at = datetime('now') WHERE id = 1",
                (int(settings.public_api_enabled), settings.public_ip_limit_per_minute),
            )
            conn.commit()

    def create_token(self, name: str, token_hash: str, is_unlimited: bool, requests_per_minute: int, allow_gtfs: bool, allow_ibus: bool, allow_red_web: bool, allow_raptor: bool) -> int:
        with self._lock:
            conn = self._connect()
            cursor = conn.execute(
                "INSERT INTO api_tokens (name, token_hash, is_unlimited, requests_per_minute, allow_gtfs, allow_ibus, allow_red_web, allow_raptor) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (name, token_hash, int(is_unlimited), requests_per_minute, int(allow_gtfs), int(allow_ibus), int(allow_red_web), int(allow_raptor)),
            )
            conn.commit()
            return cursor.lastrowid

    def get_token_by_hash(self, token_hash: str) -> Optional[TokenRecord]:
        with self._lock:
            conn = self._connect()
            row = conn.execute("SELECT * FROM api_tokens WHERE token_hash = ?", (token_hash,)).fetchone()
            if not row:
                return None
            return self._row_to_token_record(row)

    def list_tokens(self) -> list[TokenRecord]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute("SELECT * FROM api_tokens ORDER BY created_at DESC").fetchall()
            return [self._row_to_token_record(r) for r in rows]

    def get_token_by_id(self, token_id: int) -> Optional[TokenRecord]:
        with self._lock:
            conn = self._connect()
            row = conn.execute("SELECT * FROM api_tokens WHERE id = ?", (token_id,)).fetchone()
            if not row:
                return None
            return self._row_to_token_record(row)

    def update_token(self, token_id: int, name: Optional[str] = None, enabled: Optional[bool] = None, is_unlimited: Optional[bool] = None, requests_per_minute: Optional[int] = None, allow_gtfs: Optional[bool] = None, allow_ibus: Optional[bool] = None, allow_red_web: Optional[bool] = None, allow_raptor: Optional[bool] = None) -> None:
        with self._lock:
            conn = self._connect()
            fields, values = [], []
            if name is not None:
                fields.append("name = ?")
                values.append(name)
            if enabled is not None:
                fields.append("enabled = ?")
                values.append(int(enabled))
            if is_unlimited is not None:
                fields.append("is_unlimited = ?")
                values.append(int(is_unlimited))
            if requests_per_minute is not None:
                fields.append("requests_per_minute = ?")
                values.append(requests_per_minute)
            if allow_gtfs is not None:
                fields.append("allow_gtfs = ?")
                values.append(int(allow_gtfs))
            if allow_ibus is not None:
                fields.append("allow_ibus = ?")
                values.append(int(allow_ibus))
            if allow_red_web is not None:
                fields.append("allow_red_web = ?")
                values.append(int(allow_red_web))
            if allow_raptor is not None:
                fields.append("allow_raptor = ?")
                values.append(int(allow_raptor))
            if not fields:
                return
            values.append(token_id)
            conn.execute(f"UPDATE api_tokens SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()

    def delete_token(self, token_id: int) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute("DELETE FROM api_tokens WHERE id = ?", (token_id,))
            conn.commit()

    def update_token_last_used(self, token_id: int) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute("UPDATE api_tokens SET last_used_at = datetime('now') WHERE id = ?", (token_id,))
            conn.commit()

    def increment_rate_counter(self, subject_type: str, subject_key: str, resource_type: str, window_start: int) -> int:
        with self._lock:
            conn = self._connect()
            cursor = conn.execute(
                "INSERT INTO rate_limit_counters (subject_type, subject_key, resource_type, window_start, request_count) VALUES (?, ?, ?, ?, 1) "
                "ON CONFLICT(subject_type, subject_key, resource_type, window_start) DO UPDATE SET request_count = request_count + 1",
                (subject_type, subject_key, resource_type, window_start),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_rate_counter(self, subject_type: str, subject_key: str, resource_type: str, window_start: int) -> int:
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT request_count FROM rate_limit_counters WHERE subject_type = ? AND subject_key = ? AND resource_type = ? AND window_start = ?",
                (subject_type, subject_key, resource_type, window_start),
            ).fetchone()
            return row["request_count"] if row else 0

    def consume_rate_counter(
        self, subject_type: str, subject_key: str, resource_type: str, window_start: int, limit: int
    ) -> Optional[int]:
        with self._lock:
            conn = self._connect()
            conn.execute(
                "INSERT INTO rate_limit_counters (subject_type, subject_key, resource_type, window_start, request_count) "
                "VALUES (?, ?, ?, ?, 0) "
                "ON CONFLICT(subject_type, subject_key, resource_type, window_start) DO NOTHING",
                (subject_type, subject_key, resource_type, window_start),
            )
            cursor = conn.execute(
                "UPDATE rate_limit_counters SET request_count = request_count + 1 "
                "WHERE subject_type = ? AND subject_key = ? AND resource_type = ? AND window_start = ? "
                "AND request_count < ?",
                (subject_type, subject_key, resource_type, window_start, limit),
            )
            conn.commit()
            if cursor.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT request_count FROM rate_limit_counters "
                "WHERE subject_type = ? AND subject_key = ? AND resource_type = ? AND window_start = ?",
                (subject_type, subject_key, resource_type, window_start),
            ).fetchone()
            return row["request_count"] if row else None

    def _cleanup_old_rate_counters(self, conn: sqlite3.Connection) -> None:
        """Delete rate-limit windows older than 1 hour to prevent unbounded table growth."""
        import time
        cutoff = int(time.time()) - 3600
        conn.execute("DELETE FROM rate_limit_counters WHERE window_start < ?", (cutoff,))
        conn.commit()

    def _row_to_token_record(self, row: sqlite3.Row) -> TokenRecord:
        return TokenRecord(
            id=row["id"],
            name=row["name"],
            token_hash=row["token_hash"],
            is_unlimited=bool(row["is_unlimited"]),
            requests_per_minute=row["requests_per_minute"],
            allow_gtfs=bool(row["allow_gtfs"]),
            allow_ibus=bool(row["allow_ibus"]),
            allow_red_web=bool(row["allow_red_web"]),
            allow_raptor=bool(row["allow_raptor"]),
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            last_used_at=row["last_used_at"],
        )