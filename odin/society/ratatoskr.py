"""RATATOSKR — Durable pub/sub message bus for inter-agent communication (8.1).

Named after the squirrel that carries messages between the eagle atop
Yggdrasil and the serpent Níðhöggr beneath.  Typed, persistent, topic-based.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("odin.society.ratatoskr")


class AgentMessage(BaseModel):
    """A typed message between agents."""

    id: str
    topic: str
    sender: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    in_reply_to: str | None = None


class MessageBus:
    """RATATOSKR — durable pub/sub message bus.

    SQLite-backed so messages survive restarts.  Agents publish to topics
    and subscribe by polling (no blocking; fits async orchestration).
    """

    def __init__(self, data_dir: str = ".odin_data") -> None:
        path = Path(data_dir)
        path.mkdir(parents=True, exist_ok=True)
        db_path = path / "ratatoskr.db"
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        self._cursors: dict[str, str] = {}  # subscriber_id → last seen msg timestamp
        logger.info("RATATOSKR message bus initialized: %s", db_path)

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                sender TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                timestamp TEXT NOT NULL,
                in_reply_to TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_msg_topic ON messages(topic);
            CREATE INDEX IF NOT EXISTS idx_msg_sender ON messages(sender);
            CREATE INDEX IF NOT EXISTS idx_msg_time ON messages(timestamp);
        """)
        self._conn.commit()

    def publish(self, message: AgentMessage) -> AgentMessage:
        """Publish a message to a topic."""
        self._conn.execute(
            """INSERT INTO messages (id, topic, sender, content, metadata, timestamp, in_reply_to)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO NOTHING""",
            (message.id, message.topic, message.sender, message.content,
             json.dumps(message.metadata), message.timestamp.isoformat(),
             message.in_reply_to),
        )
        self._conn.commit()
        logger.debug("Published %s to %s from %s", message.id, message.topic, message.sender)
        return message

    def subscribe(
        self,
        topic: str,
        subscriber_id: str,
        limit: int = 50,
    ) -> list[AgentMessage]:
        """Poll for new messages on a topic since last read.

        Tracks per-subscriber cursor so each subscriber sees each message
        exactly once (at-least-once with manual cursor advance).
        """
        cursor = self._cursors.get(subscriber_id, "")
        rows = self._conn.execute(
            """SELECT * FROM messages WHERE topic=? AND timestamp > ?
               ORDER BY timestamp ASC LIMIT ?""",
            (topic, cursor, limit),
        ).fetchall()
        messages = [self._row_to_message(r) for r in rows]
        if messages:
            self._cursors[subscriber_id] = messages[-1].timestamp.isoformat()
        return messages

    def get_thread(self, root_id: str) -> list[AgentMessage]:
        """Get a full reply thread starting from a root message."""
        thread: list[AgentMessage] = []
        queue = [root_id]
        seen: set[str] = set()
        while queue:
            msg_id = queue.pop(0)
            if msg_id in seen:
                continue
            seen.add(msg_id)
            row = self._conn.execute("SELECT * FROM messages WHERE id=?", (msg_id,)).fetchone()
            if row:
                thread.append(self._row_to_message(row))
            replies = self._conn.execute(
                "SELECT * FROM messages WHERE in_reply_to=? ORDER BY timestamp", (msg_id,)
            ).fetchall()
            for r in replies:
                queue.append(r["id"])
        return thread

    def history(self, topic: str, limit: int = 50) -> list[AgentMessage]:
        """Get recent messages on a topic."""
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE topic=? ORDER BY timestamp DESC LIMIT ?",
            (topic, limit),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def topics(self) -> list[str]:
        """List all active topics."""
        rows = self._conn.execute(
            "SELECT DISTINCT topic FROM messages ORDER BY topic"
        ).fetchall()
        return [r["topic"] for r in rows]

    def stats(self) -> dict[str, int]:
        total = self._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        topics = len(self.topics())
        senders = self._conn.execute(
            "SELECT COUNT(DISTINCT sender) FROM messages"
        ).fetchone()[0]
        return {"messages": total, "topics": topics, "senders": senders}

    def _row_to_message(self, row: sqlite3.Row) -> AgentMessage:
        return AgentMessage(
            id=row["id"],
            topic=row["topic"],
            sender=row["sender"],
            content=row["content"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            timestamp=datetime.fromisoformat(row["timestamp"]),
            in_reply_to=row["in_reply_to"],
        )

    def close(self) -> None:
        self._conn.close()
