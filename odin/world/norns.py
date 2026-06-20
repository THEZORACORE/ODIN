"""NORNS — Causal and temporal reasoning engine.

The three Norns:
- Urðr (past):     causal attribution — what caused what?
- Verðandi (now):  current-state estimation from evidence
- Skuld (future):  forecasting under uncertainty

Operates over YGGDRASIL's entity graph + a timeline of events.
Builds a causal graph (DAG) where edges represent causal links
with strength and confidence.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("odin.world.norns")


class TimelineEvent(BaseModel):
    """A timestamped event in the world's history."""

    id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    entity_id: str
    event_type: str
    description: str
    properties: dict[str, Any] = Field(default_factory=dict)
    source: str = ""


class CausalLink(BaseModel):
    """A directed causal relationship: cause → effect."""

    cause_event_id: str
    effect_event_id: str
    strength: float = 1.0
    confidence: float = 1.0
    mechanism: str = ""


class CausalChain(BaseModel):
    """A sequence of causally-linked events."""

    events: list[TimelineEvent]
    links: list[CausalLink]
    total_strength: float = 0.0


class Forecast(BaseModel):
    """A prediction about a future state or event."""

    entity_id: str
    prediction: str
    confidence: float
    reasoning: str
    based_on: list[str] = Field(default_factory=list)


class CausalEngine:
    """NORNS — causal reasoning over timeline events.

    SQLite-backed event log + causal graph.  Supports:
    - Recording events (Verðandi)
    - Causal attribution / root-cause analysis (Urðr)
    - Forward reasoning / forecasting (Skuld)
    """

    def __init__(self, data_dir: str = ".odin_data") -> None:
        path = Path(data_dir)
        path.mkdir(parents=True, exist_ok=True)
        db_path = path / "norns.db"
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info("NORNS causal engine initialized: %s", db_path)

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                description TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                source TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_event_entity ON events(entity_id);
            CREATE INDEX IF NOT EXISTS idx_event_time ON events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_event_type ON events(event_type);

            CREATE TABLE IF NOT EXISTS causal_links (
                cause_event_id TEXT NOT NULL,
                effect_event_id TEXT NOT NULL,
                strength REAL DEFAULT 1.0,
                confidence REAL DEFAULT 1.0,
                mechanism TEXT DEFAULT '',
                PRIMARY KEY (cause_event_id, effect_event_id),
                FOREIGN KEY (cause_event_id) REFERENCES events(id),
                FOREIGN KEY (effect_event_id) REFERENCES events(id)
            );
            CREATE INDEX IF NOT EXISTS idx_cause ON causal_links(cause_event_id);
            CREATE INDEX IF NOT EXISTS idx_effect ON causal_links(effect_event_id);
        """)
        self._conn.commit()

    # -- Verðandi: record current events --

    def record_event(self, event: TimelineEvent) -> TimelineEvent:
        """Record an event in the timeline."""
        self._conn.execute(
            """INSERT INTO events (id, timestamp, entity_id, event_type, description, properties, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 description=excluded.description, properties=excluded.properties""",
            (event.id, event.timestamp.isoformat(), event.entity_id,
             event.event_type, event.description,
             json.dumps(event.properties), event.source),
        )
        self._conn.commit()
        return event

    def add_causal_link(self, link: CausalLink) -> CausalLink:
        """Record a causal relationship between two events."""
        self._conn.execute(
            """INSERT INTO causal_links (cause_event_id, effect_event_id, strength, confidence, mechanism)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(cause_event_id, effect_event_id) DO UPDATE SET
                 strength=excluded.strength, confidence=excluded.confidence,
                 mechanism=excluded.mechanism""",
            (link.cause_event_id, link.effect_event_id,
             link.strength, link.confidence, link.mechanism),
        )
        self._conn.commit()
        return link

    # -- Urðr: look back (causal attribution) --

    def get_causes(self, event_id: str, max_depth: int = 5) -> CausalChain:
        """Trace backward to find root causes of an event (Urðr)."""
        visited: set[str] = set()
        events: list[TimelineEvent] = []
        links: list[CausalLink] = []
        total_strength = 0.0

        queue: list[tuple[str, int]] = [(event_id, 0)]
        while queue:
            eid, depth = queue.pop(0)
            if eid in visited or depth > max_depth:
                continue
            visited.add(eid)

            event = self._get_event(eid)
            if event:
                events.append(event)

            rows = self._conn.execute(
                "SELECT * FROM causal_links WHERE effect_event_id=?", (eid,)
            ).fetchall()
            for row in rows:
                link = self._row_to_link(row)
                links.append(link)
                total_strength += link.strength * link.confidence
                queue.append((link.cause_event_id, depth + 1))

        return CausalChain(events=events, links=links, total_strength=total_strength)

    def get_effects(self, event_id: str, max_depth: int = 5) -> CausalChain:
        """Trace forward to find effects of an event (Skuld)."""
        visited: set[str] = set()
        events: list[TimelineEvent] = []
        links: list[CausalLink] = []
        total_strength = 0.0

        queue: list[tuple[str, int]] = [(event_id, 0)]
        while queue:
            eid, depth = queue.pop(0)
            if eid in visited or depth > max_depth:
                continue
            visited.add(eid)

            event = self._get_event(eid)
            if event:
                events.append(event)

            rows = self._conn.execute(
                "SELECT * FROM causal_links WHERE cause_event_id=?", (eid,)
            ).fetchall()
            for row in rows:
                link = self._row_to_link(row)
                links.append(link)
                total_strength += link.strength * link.confidence
                queue.append((link.effect_event_id, depth + 1))

        return CausalChain(events=events, links=links, total_strength=total_strength)

    # -- Timeline queries --

    def get_timeline(
        self,
        entity_id: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[TimelineEvent]:
        """Query events, optionally filtered by entity or type."""
        conditions: list[str] = []
        params: list[str | int] = []
        if entity_id:
            conditions.append("entity_id=?")
            params.append(entity_id)
        if event_type:
            conditions.append("event_type=?")
            params.append(event_type)

        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM events WHERE {where} ORDER BY timestamp DESC LIMIT ?",  # noqa: S608
            params,
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def entity_history(self, entity_id: str) -> list[TimelineEvent]:
        """Get all events for an entity, ordered chronologically."""
        return self.get_timeline(entity_id=entity_id, limit=1000)

    # -- Skuld: forecasting --

    def forecast(self, entity_id: str, context: str = "") -> Forecast:
        """Generate a simple forecast based on event patterns (Skuld).

        This is a pattern-based heuristic; for LLM-based forecasting,
        the orchestrator wraps this with an LLM call.
        """
        events = self.entity_history(entity_id)
        if not events:
            return Forecast(
                entity_id=entity_id,
                prediction="insufficient data",
                confidence=0.0,
                reasoning="No events recorded for this entity.",
            )

        type_counts: dict[str, int] = {}
        for e in events:
            type_counts[e.event_type] = type_counts.get(e.event_type, 0) + 1

        most_common = max(type_counts, key=lambda k: type_counts[k])
        frequency = type_counts[most_common] / len(events)

        return Forecast(
            entity_id=entity_id,
            prediction=f"Most likely next event: {most_common} (frequency: {frequency:.0%})",
            confidence=min(frequency, 0.9),
            reasoning=f"Based on {len(events)} events. Dominant type: {most_common} ({type_counts[most_common]} occurrences).",
            based_on=[e.id for e in events[:5]],
        )

    # -- Stats --

    def stats(self) -> dict[str, int]:
        events = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        links = self._conn.execute("SELECT COUNT(*) FROM causal_links").fetchone()[0]
        entities = self._conn.execute(
            "SELECT COUNT(DISTINCT entity_id) FROM events"
        ).fetchone()[0]
        return {"events": events, "causal_links": links, "entities_tracked": entities}

    # -- Helpers --

    def _get_event(self, event_id: str) -> TimelineEvent | None:
        row = self._conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return self._row_to_event(row) if row else None

    def _row_to_event(self, row: sqlite3.Row) -> TimelineEvent:
        return TimelineEvent(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            entity_id=row["entity_id"],
            event_type=row["event_type"],
            description=row["description"],
            properties=json.loads(row["properties"]) if row["properties"] else {},
            source=row["source"],
        )

    def _row_to_link(self, row: sqlite3.Row) -> CausalLink:
        return CausalLink(
            cause_event_id=row["cause_event_id"],
            effect_event_id=row["effect_event_id"],
            strength=row["strength"],
            confidence=row["confidence"],
            mechanism=row["mechanism"],
        )

    def close(self) -> None:
        self._conn.close()
