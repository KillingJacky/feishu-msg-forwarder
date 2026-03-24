from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from ..models import DeliveryTask, MatchResult, NormalizedMessage


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Repository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def ensure_source_baseline(self, chat_id: str, baseline_ms: int) -> int:
        key = f"baseline:{chat_id}"
        row = self.conn.execute("SELECT value FROM runtime_state WHERE key = ?", (key,)).fetchone()
        if row:
            return int(row["value"])
        self.conn.execute("INSERT INTO runtime_state(key, value) VALUES(?, ?)", (key, str(baseline_ms)))
        self.conn.commit()
        return baseline_ms

    def get_source_cursor(self, chat_id: str, baseline_ms: int) -> tuple[int, set[str]]:
        cursor_key = f"cursor_ms:{chat_id}"
        ids_key = f"cursor_ids:{chat_id}"
        baseline = self.ensure_source_baseline(chat_id, baseline_ms)
        row = self.conn.execute("SELECT value FROM runtime_state WHERE key = ?", (cursor_key,)).fetchone()
        ids_row = self.conn.execute("SELECT value FROM runtime_state WHERE key = ?", (ids_key,)).fetchone()
        cursor_ms = int(row["value"]) if row else baseline
        cursor_ids = set(json.loads(ids_row["value"])) if ids_row and ids_row["value"] else set()
        return cursor_ms, cursor_ids

    def update_source_cursor(self, chat_id: str, cursor_ms: int, cursor_ids: set[str]) -> None:
        self._upsert_runtime_state(f"cursor_ms:{chat_id}", str(cursor_ms))
        self._upsert_runtime_state(f"cursor_ids:{chat_id}", json.dumps(sorted(cursor_ids), ensure_ascii=False))
        self.conn.commit()

    def ingest_message(self, message: NormalizedMessage) -> bool:
        try:
            self.conn.execute(
                """
                INSERT INTO observed_messages(
                  message_id, source_chat_id, sender_id, sender_name, sender_type, is_bot,
                  msg_type, create_time_ms, raw_content_json, normalized_text, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.source_chat_id,
                    message.sender_id,
                    message.sender_name,
                    message.sender_type,
                    1 if message.is_bot else 0,
                    message.msg_type,
                    message.create_time_ms,
                    json.dumps(message.raw_content, ensure_ascii=False) if message.raw_content is not None else None,
                    message.text,
                    utc_now(),
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def record_match(self, message_id: str, result: MatchResult) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO rule_matches(message_id, rule_id, matched_at) VALUES (?, ?, ?)",
            (message_id, result.rule_id, utc_now()),
        )
        self.conn.commit()

    def create_delivery_if_needed(self, task: DeliveryTask) -> bool:
        try:
            now = utc_now()
            self.conn.execute(
                """
                INSERT INTO forward_deliveries(
                  message_id, rule_id, target_chat_id, forward_mode, append_source_info, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    task.message_id,
                    task.rule_id,
                    task.target_chat_id,
                    task.forward_mode,
                    1 if task.append_source_info else 0,
                    now,
                    now,
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def fetch_pending_deliveries(self, limit: int = 100) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT fd.*, om.source_chat_id, om.sender_name, om.msg_type, om.normalized_text, om.raw_content_json
            FROM forward_deliveries fd
            JOIN observed_messages om ON om.message_id = fd.message_id
            WHERE fd.status IN ('pending', 'failed')
            ORDER BY fd.updated_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def mark_delivery_attempt(self, delivery_id: int) -> None:
        self.conn.execute(
            """
            UPDATE forward_deliveries
            SET attempt_count = attempt_count + 1, updated_at = ?
            WHERE id = ?
            """,
            (utc_now(), delivery_id),
        )
        self.conn.commit()

    def mark_delivery_sent(self, delivery_id: int, target_message_id: str) -> None:
        now = utc_now()
        self.conn.execute(
            """
            UPDATE forward_deliveries
            SET status = 'sent', target_message_id = ?, updated_at = ?, sent_at = ?
            WHERE id = ?
            """,
            (target_message_id, now, now, delivery_id),
        )
        self.conn.commit()

    def mark_delivery_failed(self, delivery_id: int, error: str) -> None:
        self.conn.execute(
            """
            UPDATE forward_deliveries
            SET status = 'failed', last_error = ?, updated_at = ?
            WHERE id = ?
            """,
            (error[:1000], utc_now(), delivery_id),
        )
        self.conn.commit()

    def _upsert_runtime_state(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO runtime_state(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
