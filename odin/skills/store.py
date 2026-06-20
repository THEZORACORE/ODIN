"""SkillStore — SQLite-backed persistence for procedural skills.

Stores, retrieves, scores, and retires learned skills.  Uses FTS5 for
goal→skill matching so retrieval is fast and deterministic (no LLM call).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from odin.schemas import Skill

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    steps TEXT NOT NULL,        -- JSON list[str]
    preconditions TEXT NOT NULL,-- JSON list[str]
    tools_used TEXT NOT NULL,   -- JSON list[str]
    tags TEXT NOT NULL,         -- comma-separated
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    usage_count INTEGER DEFAULT 0,
    avg_cost_tokens REAL DEFAULT 0.0,
    avg_latency_seconds REAL DEFAULT 0.0,
    retired INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    last_used TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(
    name, description, tags, content_rowid='rowid'
);
"""


class SkillStore:
    """SQLite-backed skill persistence with FTS5 retrieval."""

    def __init__(self, data_dir: str = ".odin_data") -> None:
        path = Path(data_dir)
        path.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path / "skills.db"))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    # -- write --

    def save(self, skill: Skill) -> Skill:
        """Insert or update a skill."""
        tags_str = ",".join(skill.tags)
        self._conn.execute(
            """INSERT INTO skills
               (id, name, description, steps, preconditions, tools_used, tags,
                success_count, failure_count, usage_count,
                avg_cost_tokens, avg_latency_seconds, retired,
                created_at, last_used)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, description=excluded.description,
                 steps=excluded.steps, preconditions=excluded.preconditions,
                 tools_used=excluded.tools_used, tags=excluded.tags,
                 success_count=excluded.success_count,
                 failure_count=excluded.failure_count,
                 usage_count=excluded.usage_count,
                 avg_cost_tokens=excluded.avg_cost_tokens,
                 avg_latency_seconds=excluded.avg_latency_seconds,
                 retired=excluded.retired,
                 last_used=excluded.last_used""",
            (
                skill.id, skill.name, skill.description,
                json.dumps(skill.steps), json.dumps(skill.preconditions),
                json.dumps(skill.tools_used), tags_str,
                skill.success_count, skill.failure_count, skill.usage_count,
                skill.avg_cost_tokens, skill.avg_latency_seconds,
                int(skill.retired),
                skill.created_at.isoformat(), skill.last_used.isoformat(),
            ),
        )
        # FTS sync
        row = self._conn.execute(
            "SELECT rowid FROM skills WHERE id=?", (skill.id,)
        ).fetchone()
        if row:
            rowid = row[0]
            self._conn.execute("DELETE FROM skills_fts WHERE rowid=?", (rowid,))
            self._conn.execute(
                "INSERT INTO skills_fts (rowid, name, description, tags) VALUES (?,?,?,?)",
                (rowid, skill.name, skill.description, tags_str),
            )
        self._conn.commit()
        return skill

    def find(self, goal: str, *, n: int = 3, include_retired: bool = False) -> list[Skill]:
        """FTS5 keyword search: match a goal description to stored skills."""
        safe_query = " ".join(f'"{t}"' for t in goal.split() if t)
        if not safe_query:
            return []
        retirement_clause = "" if include_retired else "AND s.retired = 0"
        rows = self._conn.execute(
            f"""SELECT s.* FROM skills s
                JOIN skills_fts f ON s.rowid = f.rowid
                WHERE skills_fts MATCH ?
                {retirement_clause}
                LIMIT ?""",
            (safe_query, n),
        ).fetchall()
        return [self._row_to_skill(r) for r in rows]

    def get(self, skill_id: str) -> Skill | None:
        row = self._conn.execute(
            "SELECT * FROM skills WHERE id=?", (skill_id,)
        ).fetchone()
        return self._row_to_skill(row) if row else None

    def all_active(self) -> list[Skill]:
        rows = self._conn.execute(
            "SELECT * FROM skills WHERE retired=0 ORDER BY usage_count DESC"
        ).fetchall()
        return [self._row_to_skill(r) for r in rows]

    def all_skills(self) -> list[Skill]:
        rows = self._conn.execute(
            "SELECT * FROM skills ORDER BY usage_count DESC"
        ).fetchall()
        return [self._row_to_skill(r) for r in rows]

    # -- scoring --

    def record_outcome(
        self,
        skill_id: str,
        *,
        success: bool,
        cost_tokens: float = 0.0,
        latency_seconds: float = 0.0,
    ) -> Skill | None:
        """Update a skill's stats after it was used in a run."""
        skill = self.get(skill_id)
        if skill is None:
            return None
        skill.usage_count += 1
        if success:
            skill.success_count += 1
        else:
            skill.failure_count += 1
        # Running average for cost/latency
        prev = skill.usage_count - 1
        if prev > 0:
            skill.avg_cost_tokens = (
                skill.avg_cost_tokens * prev + cost_tokens
            ) / skill.usage_count
            skill.avg_latency_seconds = (
                skill.avg_latency_seconds * prev + latency_seconds
            ) / skill.usage_count
        else:
            skill.avg_cost_tokens = cost_tokens
            skill.avg_latency_seconds = latency_seconds
        skill.last_used = datetime.now(UTC)
        return self.save(skill)

    def retire(self, skill_id: str) -> Skill | None:
        """Mark a skill as retired (bad performance)."""
        skill = self.get(skill_id)
        if skill is None:
            return None
        skill.retired = True
        return self.save(skill)

    # -- internal --

    def _row_to_skill(self, row: sqlite3.Row) -> Skill:
        return Skill(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            steps=json.loads(row["steps"]),
            preconditions=json.loads(row["preconditions"]),
            tools_used=json.loads(row["tools_used"]),
            tags=[t for t in row["tags"].split(",") if t],
            success_count=row["success_count"],
            failure_count=row["failure_count"],
            usage_count=row["usage_count"],
            avg_cost_tokens=row["avg_cost_tokens"],
            avg_latency_seconds=row["avg_latency_seconds"],
            retired=bool(row["retired"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            last_used=datetime.fromisoformat(row["last_used"]),
        )

    def close(self) -> None:
        self._conn.close()
