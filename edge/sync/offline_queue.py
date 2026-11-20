import hashlib
import hmac
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import httpx


def sign_payload(raw_bytes: bytes, hmac_secret: str) -> str:
    return "sha256=" + hmac.new(hmac_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()


class OfflineEventQueue:
    """
    SQLite WAL persistent ring buffer for Edge AI nodes.
    Guarantees zero lost vehicle entries/exits during garage internet outages.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS queued_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    payload_json TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )

    def enqueue(self, idempotency_key: str, payload: dict) -> bool:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO queued_events (idempotency_key, payload_json, attempts, created_at) VALUES (?, ?, 0, ?)",
                    (idempotency_key, json.dumps(payload), now),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def pending_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM queued_events").fetchone()
            return int(row[0]) if row else 0

    def flush(
        self,
        *,
        endpoint_url: str,
        hmac_secret: str,
        client: httpx.Client | None = None,
        max_batch: int = 25,
    ) -> dict[str, int]:
        """Deliver queued events in FIFO order with HMAC-SHA256 signatures."""
        sent = 0
        failed = 0
        own_client = client is None
        http = client or httpx.Client(timeout=10.0)

        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT id, payload_json FROM queued_events ORDER BY id ASC LIMIT ?",
                    (max_batch,),
                ).fetchall()

            for row_id, payload_json in rows:
                raw_bytes = payload_json.encode("utf-8")
                sig = sign_payload(raw_bytes, hmac_secret)
                try:
                    resp = http.post(
                        endpoint_url,
                        content=raw_bytes,
                        headers={
                            "Content-Type": "application/json",
                            "X-ParkVektor-Signature": sig,
                        },
                    )
                    if resp.status_code in (200, 201, 202):
                        with self._connect() as conn:
                            conn.execute("DELETE FROM queued_events WHERE id = ?", (row_id,))
                        sent += 1
                    else:
                        with self._connect() as conn:
                            conn.execute(
                                "UPDATE queued_events SET attempts = attempts + 1 WHERE id = ?",
                                (row_id,),
                            )
                        failed += 1
                except Exception:
                    with self._connect() as conn:
                        conn.execute(
                            "UPDATE queued_events SET attempts = attempts + 1 WHERE id = ?",
                            (row_id,),
                        )
                    failed += 1
                    break  # Stop flushing on network outage; preserve FIFO order
        finally:
            if own_client:
                http.close()

        return {"sent": sent, "failed": failed, "remaining": self.pending_count()}
