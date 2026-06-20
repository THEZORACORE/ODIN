"""RunHistory — SQLite-backed audit trail for orchestration runs.

Stores a structured record of every run: goal, plan summary, verdicts,
budget usage, outcome, and timing.  Powers `odin history` and feeds
the observability dashboard.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    goal TEXT NOT NULL,
    success INTEGER NOT NULL,
    node_count INTEGER DEFAULT 0,
    nodes_completed INTEGER DEFAULT 0,
    nodes_failed INTEGER DEFAULT 0,
    verdict_count INTEGER DEFAULT 0,
    verdicts_passed INTEGER DEFAULT 0,
    verdicts_failed INTEGER DEFAULT 0,
    tokens_used INTEGER DEFAULT 0,
    llm_calls_used INTEGER DEFAULT 0,
    tool_calls_used INTEGER DEFAULT 0,
    duration_seconds REAL DEFAULT 0.0,
    answer_preview TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
"""


class RunRecord(BaseModel):
    """A single orchestration run record for the audit trail."""

    id: str
    session_id: str
    goal: str
    success: bool
    node_count: int = 0
    nodes_completed: int = 0
    nodes_failed: int = 0
    verdict_count: int = 0
    verdicts_passed: int = 0
    verdicts_failed: int = 0
    tokens_used: int = 0
    llm_calls_used: int = 0
    tool_calls_used: int = 0
    duration_seconds: float = 0.0
    answer_preview: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RunHistory:
    """SQLite-backed run history / audit trail."""

    def __init__(self, data_dir: str = ".odin_data") -> None:
        path = Path(data_dir)
        path.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path / "history.db"))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    def record(self, run: RunRecord) -> RunRecord:
        """Store a run record."""
        self._conn.execute(
            """INSERT INTO runs
               (id, session_id, goal, success, node_count, nodes_completed,
                nodes_failed, verdict_count, verdicts_passed, verdicts_failed,
                tokens_used, llm_calls_used, tool_calls_used,
                duration_seconds, answer_preview, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 success=excluded.success,
                 nodes_completed=excluded.nodes_completed,
                 nodes_failed=excluded.nodes_failed,
                 verdicts_passed=excluded.verdicts_passed,
                 verdicts_failed=excluded.verdicts_failed,
                 tokens_used=excluded.tokens_used,
                 llm_calls_used=excluded.llm_calls_used,
                 tool_calls_used=excluded.tool_calls_used,
                 duration_seconds=excluded.duration_seconds,
                 answer_preview=excluded.answer_preview""",
            (
                run.id, run.session_id, run.goal, int(run.success),
                run.node_count, run.nodes_completed, run.nodes_failed,
                run.verdict_count, run.verdicts_passed, run.verdicts_failed,
                run.tokens_used, run.llm_calls_used, run.tool_calls_used,
                run.duration_seconds, run.answer_preview,
                run.created_at.isoformat(),
            ),
        )
        self._conn.commit()
        return run

    def recent(self, *, limit: int = 20) -> list[RunRecord]:
        rows = self._conn.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def by_session(self, session_id: str) -> list[RunRecord]:
        rows = self._conn.execute(
            "SELECT * FROM runs WHERE session_id=? ORDER BY created_at DESC",
            (session_id,),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def stats(self) -> dict[str, object]:
        """Aggregate statistics across all runs."""
        row = self._conn.execute(
            """SELECT
                 COUNT(*) as total,
                 SUM(success) as successes,
                 SUM(tokens_used) as total_tokens,
                 SUM(llm_calls_used) as total_llm_calls,
                 SUM(tool_calls_used) as total_tool_calls,
                 AVG(duration_seconds) as avg_duration,
                 AVG(CASE WHEN node_count > 0 THEN nodes_completed * 1.0 / node_count END) as avg_completion_rate
               FROM runs"""
        ).fetchone()
        if row is None or row["total"] == 0:
            return {"total": 0}
        total = row["total"]
        return {
            "total_runs": total,
            "success_rate": (row["successes"] or 0) / total,
            "total_tokens": row["total_tokens"] or 0,
            "total_llm_calls": row["total_llm_calls"] or 0,
            "total_tool_calls": row["total_tool_calls"] or 0,
            "avg_duration_seconds": round(row["avg_duration"] or 0, 2),
            "avg_completion_rate": round(row["avg_completion_rate"] or 0, 3),
        }

    def _row_to_record(self, row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            id=row["id"],
            session_id=row["session_id"],
            goal=row["goal"],
            success=bool(row["success"]),
            node_count=row["node_count"],
            nodes_completed=row["nodes_completed"],
            nodes_failed=row["nodes_failed"],
            verdict_count=row["verdict_count"],
            verdicts_passed=row["verdicts_passed"],
            verdicts_failed=row["verdicts_failed"],
            tokens_used=row["tokens_used"],
            llm_calls_used=row["llm_calls_used"],
            tool_calls_used=row["tool_calls_used"],
            duration_seconds=row["duration_seconds"],
            answer_preview=row["answer_preview"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def close(self) -> None:
        self._conn.close()
