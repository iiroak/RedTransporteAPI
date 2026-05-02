"""MySQL/MariaDB implementation of AuthStorage."""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
from typing import Optional
from urllib.parse import urlparse

import aiomysql

from red_transporte_api.auth.storage import AuthStorage
from red_transporte_api.auth.models import APISettings, TokenRecord


def _parse_db_url(url: str) -> dict:
    """Parse a mysql://user:pass@host:port/dbname URL into aiomysql kwargs."""
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 3306,
        "user": parsed.username or "root",
        "password": parsed.password or "",
        "db": (parsed.path or "/red_transporte").lstrip("/") or "red_transporte",
    }


class _LoopThread:
    """A single background thread hosting a persistent asyncio event loop."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro, timeout: float = 30):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)


class MySQLAuthStorage(AuthStorage):
    def __init__(self, db_url: str):
        self._conn_kwargs = _parse_db_url(db_url)
        self._pool: Optional[aiomysql.Pool] = None
        self._loop_thread = _LoopThread()

    def _run(self, coro):
        return self._loop_thread.run(coro)

    async def _get_pool(self) -> aiomysql.Pool:
        if self._pool is None:
            self._pool = await aiomysql.create_pool(
                **self._conn_kwargs,
                autocommit=True,
                minsize=1,
                maxsize=10,
            )
        return self._pool

    def initialize(
        self,
        initial_public_api_enabled: bool = True,
        initial_public_ip_limit: int = 20,
    ) -> None:
        async def _init():
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS api_settings (
                            id INTEGER PRIMARY KEY,
                            public_api_enabled INTEGER NOT NULL DEFAULT 1,
                            public_ip_limit_per_minute INTEGER NOT NULL DEFAULT 20,
                            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP
                        )
                    """)
                    await cur.execute(
                        "INSERT IGNORE INTO api_settings "
                        "(id, public_api_enabled, public_ip_limit_per_minute) "
                        "VALUES (1, %s, %s)",
                        (int(initial_public_api_enabled), int(initial_public_ip_limit)),
                    )
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS api_tokens (
                            id INTEGER PRIMARY KEY AUTO_INCREMENT,
                            name TEXT NOT NULL,
                            token_hash TEXT NOT NULL,
                            is_unlimited INTEGER NOT NULL DEFAULT 0,
                            requests_per_minute INTEGER NOT NULL DEFAULT 60,
                            allow_gtfs INTEGER NOT NULL DEFAULT 1,
                            allow_ibus INTEGER NOT NULL DEFAULT 1,
                            allow_red_web INTEGER NOT NULL DEFAULT 1,
                            allow_raptor INTEGER NOT NULL DEFAULT 1,
                            enabled INTEGER NOT NULL DEFAULT 1,
                            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            last_used_at TIMESTAMP NULL,
                            UNIQUE KEY uq_token_hash (token_hash(64))
                        )
                    """)
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS rate_limit_counters (
                            id INTEGER PRIMARY KEY AUTO_INCREMENT,
                            subject_type TEXT NOT NULL,
                            subject_key TEXT NOT NULL,
                            resource_type TEXT NOT NULL,
                            window_start INTEGER NOT NULL,
                            request_count INTEGER NOT NULL DEFAULT 0,
                            UNIQUE KEY uq_rate (subject_type(32), subject_key(128),
                                                resource_type(32), window_start)
                        )
                    """)
                    await cur.execute(
                        "CREATE INDEX IF NOT EXISTS idx_rate_limit "
                        "ON rate_limit_counters(subject_type, subject_key, "
                        "resource_type, window_start)"
                    )
                    # Cleanup stale rate-limit windows (older than 1 hour)
                    cutoff = int(time.time()) - 3600
                    await cur.execute(
                        "DELETE FROM rate_limit_counters WHERE window_start < %s",
                        (cutoff,),
                    )
        self._run(_init())

    def get_settings(self) -> APISettings:
        async def _get():
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT public_api_enabled, public_ip_limit_per_minute, "
                        "updated_at FROM api_settings WHERE id = 1"
                    )
                    row = await cur.fetchone()
                    return APISettings(
                        public_api_enabled=bool(row[0]),
                        public_ip_limit_per_minute=row[1],
                        updated_at=row[2],
                    )
        return self._run(_get())

    def update_settings(self, settings: APISettings) -> None:
        async def _update():
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "UPDATE api_settings SET public_api_enabled = %s, "
                        "public_ip_limit_per_minute = %s WHERE id = 1",
                        (int(settings.public_api_enabled), settings.public_ip_limit_per_minute),
                    )
        self._run(_update())

    def create_token(
        self,
        name: str,
        token_hash: str,
        is_unlimited: bool,
        requests_per_minute: int,
        allow_gtfs: bool,
        allow_ibus: bool,
        allow_red_web: bool,
        allow_raptor: bool,
    ) -> int:
        async def _create():
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO api_tokens "
                        "(name, token_hash, is_unlimited, requests_per_minute, "
                        "allow_gtfs, allow_ibus, allow_red_web, allow_raptor) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            name, token_hash, int(is_unlimited), requests_per_minute,
                            int(allow_gtfs), int(allow_ibus), int(allow_red_web), int(allow_raptor),
                        ),
                    )
                    return cur.lastrowid
        return self._run(_create())

    def get_token_by_hash(self, token_hash: str) -> Optional[TokenRecord]:
        async def _get():
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT * FROM api_tokens WHERE token_hash = %s", (token_hash,)
                    )
                    row = await cur.fetchone()
                    return self._row_to_token_record(row) if row else None
        return self._run(_get())

    def list_tokens(self) -> list[TokenRecord]:
        async def _list():
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT * FROM api_tokens ORDER BY created_at DESC")
                    rows = await cur.fetchall()
                    return [self._row_to_token_record(r) for r in rows]
        return self._run(_list())

    def get_token_by_id(self, token_id: int) -> Optional[TokenRecord]:
        async def _get():
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT * FROM api_tokens WHERE id = %s", (token_id,)
                    )
                    row = await cur.fetchone()
                    return self._row_to_token_record(row) if row else None
        return self._run(_get())

    def update_token(
        self,
        token_id: int,
        name=None,
        enabled=None,
        is_unlimited=None,
        requests_per_minute=None,
        allow_gtfs=None,
        allow_ibus=None,
        allow_red_web=None,
        allow_raptor=None,
    ) -> None:
        async def _update():
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    fields, values = [], []
                    if name is not None:
                        fields.append("name = %s"); values.append(name)
                    if enabled is not None:
                        fields.append("enabled = %s"); values.append(int(enabled))
                    if is_unlimited is not None:
                        fields.append("is_unlimited = %s"); values.append(int(is_unlimited))
                    if requests_per_minute is not None:
                        fields.append("requests_per_minute = %s"); values.append(requests_per_minute)
                    if allow_gtfs is not None:
                        fields.append("allow_gtfs = %s"); values.append(int(allow_gtfs))
                    if allow_ibus is not None:
                        fields.append("allow_ibus = %s"); values.append(int(allow_ibus))
                    if allow_red_web is not None:
                        fields.append("allow_red_web = %s"); values.append(int(allow_red_web))
                    if allow_raptor is not None:
                        fields.append("allow_raptor = %s"); values.append(int(allow_raptor))
                    if not fields:
                        return
                    values.append(token_id)
                    await cur.execute(
                        f"UPDATE api_tokens SET {', '.join(fields)} WHERE id = %s", values
                    )
        self._run(_update())

    def delete_token(self, token_id: int) -> None:
        async def _delete():
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("DELETE FROM api_tokens WHERE id = %s", (token_id,))
        self._run(_delete())

    def update_token_last_used(self, token_id: int) -> None:
        async def _update():
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "UPDATE api_tokens SET last_used_at = CURRENT_TIMESTAMP WHERE id = %s",
                        (token_id,),
                    )
        self._run(_update())

    def increment_rate_counter(
        self, subject_type: str, subject_key: str, resource_type: str, window_start: int
    ) -> int:
        async def _inc():
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO rate_limit_counters
                            (subject_type, subject_key, resource_type, window_start, request_count)
                        VALUES (%s, %s, %s, %s, 1)
                        ON DUPLICATE KEY UPDATE request_count = request_count + 1
                        """,
                        (subject_type, subject_key, resource_type, window_start),
                    )
                    return cur.lastrowid or 0
        return self._run(_inc())

    def get_rate_counter(
        self, subject_type: str, subject_key: str, resource_type: str, window_start: int
    ) -> int:
        async def _get():
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT request_count FROM rate_limit_counters "
                        "WHERE subject_type = %s AND subject_key = %s "
                        "AND resource_type = %s AND window_start = %s",
                        (subject_type, subject_key, resource_type, window_start),
                    )
                    row = await cur.fetchone()
                    return row[0] if row else 0
        return self._run(_get())

    def _row_to_token_record(self, row) -> TokenRecord:
        return TokenRecord(
            id=row[0],
            name=row[1],
            token_hash=row[2],
            is_unlimited=bool(row[3]),
            requests_per_minute=row[4],
            allow_gtfs=bool(row[5]),
            allow_ibus=bool(row[6]),
            allow_red_web=bool(row[7]),
            allow_raptor=bool(row[8]),
            enabled=bool(row[9]),
            created_at=row[10],
            last_used_at=row[11],
        )
