"""JobStore — SQLite-backed persistence for durable, resumable jobs.

Stores, retrieves, and updates orchestration jobs.  Jobs survive
process restarts via SQLite; optional checkpoint blobs enable resume.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from odin.schemas import BudgetState, Job, JobStatus

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    parent_job_id TEXT,
    session_id TEXT,
    checkpoint TEXT,
    result_summary TEXT,
    budget TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(priority DESC);
"""


class JobStore:
    """SQLite-backed job persistence."""

    def __init__(self, data_dir: str = ".odin_data") -> None:
        path = Path(data_dir)
        path.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path / "jobs.db"))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    # -- write --

    def save(self, job: Job) -> Job:
        """Insert or update a job."""
        self._conn.execute(
            """INSERT INTO jobs
               (id, goal, status, parent_job_id, session_id, checkpoint,
                result_summary, budget, priority, tags, created_at,
                started_at, completed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 goal=excluded.goal, status=excluded.status,
                 parent_job_id=excluded.parent_job_id,
                 session_id=excluded.session_id,
                 checkpoint=excluded.checkpoint,
                 result_summary=excluded.result_summary,
                 budget=excluded.budget, priority=excluded.priority,
                 tags=excluded.tags, started_at=excluded.started_at,
                 completed_at=excluded.completed_at""",
            (
                job.id, job.goal, job.status.value,
                job.parent_job_id, job.session_id, job.checkpoint,
                job.result_summary, job.budget.model_dump_json(),
                job.priority, ",".join(job.tags),
                job.created_at.isoformat(),
                job.started_at.isoformat() if job.started_at else None,
                job.completed_at.isoformat() if job.completed_at else None,
            ),
        )
        self._conn.commit()
        return job

    def get(self, job_id: str) -> Job | None:
        row = self._conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    # -- queries --

    def next_queued(self) -> Job | None:
        """Pop the highest-priority queued job."""
        row = self._conn.execute(
            "SELECT * FROM jobs WHERE status='queued' ORDER BY priority DESC, created_at ASC LIMIT 1"
        ).fetchone()
        return self._row_to_job(row) if row else None

    def by_status(self, status: JobStatus) -> list[Job]:
        rows = self._conn.execute(
            "SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC", (status.value,)
        ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def all_jobs(self, *, limit: int = 50) -> list[Job]:
        rows = self._conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def children(self, parent_job_id: str) -> list[Job]:
        rows = self._conn.execute(
            "SELECT * FROM jobs WHERE parent_job_id=? ORDER BY created_at", (parent_job_id,)
        ).fetchall()
        return [self._row_to_job(r) for r in rows]

    # -- lifecycle --

    def mark_running(self, job_id: str) -> Job | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        return self.save(job)

    def mark_completed(self, job_id: str, result_summary: str) -> Job | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = JobStatus.COMPLETED
        job.result_summary = result_summary
        job.completed_at = datetime.now(UTC)
        return self.save(job)

    def mark_failed(self, job_id: str, result_summary: str) -> Job | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = JobStatus.FAILED
        job.result_summary = result_summary
        job.completed_at = datetime.now(UTC)
        return self.save(job)

    def checkpoint(self, job_id: str, state: str) -> Job | None:
        """Store a checkpoint blob for resumability."""
        job = self.get(job_id)
        if job is None:
            return None
        job.checkpoint = state
        return self.save(job)

    def cancel(self, job_id: str) -> Job | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(UTC)
        return self.save(job)

    # -- internal --

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        budget = BudgetState.model_validate(json.loads(row["budget"]))
        return Job(
            id=row["id"],
            goal=row["goal"],
            status=JobStatus(row["status"]),
            parent_job_id=row["parent_job_id"],
            session_id=row["session_id"],
            checkpoint=row["checkpoint"],
            result_summary=row["result_summary"],
            budget=budget,
            priority=row["priority"],
            tags=[t for t in row["tags"].split(",") if t],
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        )

    def close(self) -> None:
        self._conn.close()
