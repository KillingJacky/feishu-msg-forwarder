from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS observed_messages (
  message_id TEXT PRIMARY KEY,
  source_chat_id TEXT NOT NULL,
  sender_id TEXT,
  sender_name TEXT,
  sender_type TEXT,
  is_bot INTEGER NOT NULL,
  msg_type TEXT NOT NULL,
  create_time_ms INTEGER NOT NULL,
  raw_content_json TEXT,
  normalized_text TEXT,
  ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rule_matches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id TEXT NOT NULL,
  rule_id TEXT NOT NULL,
  matched_at TEXT NOT NULL,
  UNIQUE(message_id, rule_id)
);

CREATE TABLE IF NOT EXISTS forward_deliveries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id TEXT NOT NULL,
  rule_id TEXT NOT NULL,
  target_chat_id TEXT NOT NULL,
  forward_mode TEXT NOT NULL,
  append_source_info INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  target_message_id TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  sent_at TEXT,
  UNIQUE(message_id, target_chat_id)
);

CREATE TABLE IF NOT EXISTS runtime_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
