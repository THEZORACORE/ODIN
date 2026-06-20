"""YGGDRASIL — Typed knowledge graph (the world model).

A persistent, evolving model of the world that all agents read and write.
Entities have typed attributes and state; Relations encode connections
with labels.  The graph is continuously updated from MIMIR memories
and live research findings.

Unlike the semantic graph in MIMIR (concept → concept), YGGDRASIL models
*stateful entities* with properties that change over time.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("odin.world.yggdrasil")


class Entity(BaseModel):
    """A node in the world model — a thing with typed state."""

    id: str
    entity_type: str
    name: str
    properties: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Relation(BaseModel):
    """A directed edge in the world model."""

    source_id: str
    target_id: str
    relation_type: str
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WorldModel:
    """YGGDRASIL — the typed knowledge graph that represents ODIN's world model.

    SQLite-backed for persistence.  Provides entity CRUD, relation management,
    traversal, and state snapshots.
    """

    def __init__(self, data_dir: str = ".odin_data") -> None:
        path = Path(data_dir)
        path.mkdir(parents=True, exist_ok=True)
        db_path = path / "yggdrasil.db"
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info("YGGDRASIL world model initialized: %s", db_path)

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                tags TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(entity_type);
            CREATE INDEX IF NOT EXISTS idx_entity_name ON entities(name);

            CREATE TABLE IF NOT EXISTS relations (
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                confidence REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                PRIMARY KEY (source_id, target_id, relation_type),
                FOREIGN KEY (source_id) REFERENCES entities(id),
                FOREIGN KEY (target_id) REFERENCES entities(id)
            );
            CREATE INDEX IF NOT EXISTS idx_rel_source ON relations(source_id);
            CREATE INDEX IF NOT EXISTS idx_rel_target ON relations(target_id);
        """)
        self._conn.commit()

    # -- Entity operations --

    def add_entity(self, entity: Entity) -> Entity:
        """Insert or update an entity."""
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """INSERT INTO entities (id, entity_type, name, properties, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, properties=excluded.properties,
                 tags=excluded.tags, updated_at=?""",
            (entity.id, entity.entity_type, entity.name,
             json.dumps(entity.properties), ",".join(entity.tags),
             entity.created_at.isoformat(), now, now),
        )
        self._conn.commit()
        return entity

    def get_entity(self, entity_id: str) -> Entity | None:
        row = self._conn.execute(
            "SELECT * FROM entities WHERE id=?", (entity_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_entity(row)

    def find_entities(
        self,
        entity_type: str | None = None,
        name_contains: str | None = None,
        limit: int = 50,
    ) -> list[Entity]:
        """Search entities by type and/or name substring."""
        conditions: list[str] = []
        params: list[str | int] = []
        if entity_type:
            conditions.append("entity_type=?")
            params.append(entity_type)
        if name_contains:
            conditions.append("name LIKE ?")
            params.append(f"%{name_contains}%")

        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM entities WHERE {where} ORDER BY updated_at DESC LIMIT ?",  # noqa: S608
            params,
        ).fetchall()
        return [self._row_to_entity(r) for r in rows]

    def update_properties(self, entity_id: str, updates: dict[str, Any]) -> Entity | None:
        """Merge new properties into an existing entity."""
        entity = self.get_entity(entity_id)
        if entity is None:
            return None
        entity.properties.update(updates)
        entity.updated_at = datetime.now(UTC)
        return self.add_entity(entity)

    def remove_entity(self, entity_id: str) -> bool:
        """Remove an entity and all its relations."""
        self._conn.execute("DELETE FROM relations WHERE source_id=? OR target_id=?",
                           (entity_id, entity_id))
        cursor = self._conn.execute("DELETE FROM entities WHERE id=?", (entity_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    # -- Relation operations --

    def add_relation(self, relation: Relation) -> Relation:
        """Insert or update a relation."""
        self._conn.execute(
            """INSERT INTO relations (source_id, target_id, relation_type, properties, confidence, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(source_id, target_id, relation_type) DO UPDATE SET
                 properties=excluded.properties, confidence=excluded.confidence""",
            (relation.source_id, relation.target_id, relation.relation_type,
             json.dumps(relation.properties), relation.confidence,
             relation.created_at.isoformat()),
        )
        self._conn.commit()
        return relation

    def get_relations(
        self,
        entity_id: str,
        direction: str = "outgoing",
        relation_type: str | None = None,
    ) -> list[Relation]:
        """Get relations for an entity (outgoing, incoming, or both)."""
        conditions: list[str] = []
        params: list[str] = []

        if direction == "outgoing":
            conditions.append("source_id=?")
            params.append(entity_id)
        elif direction == "incoming":
            conditions.append("target_id=?")
            params.append(entity_id)
        else:
            conditions.append("(source_id=? OR target_id=?)")
            params.extend([entity_id, entity_id])

        if relation_type:
            conditions.append("relation_type=?")
            params.append(relation_type)

        where = " AND ".join(conditions)
        rows = self._conn.execute(
            f"SELECT * FROM relations WHERE {where}",  # noqa: S608
            params,
        ).fetchall()
        return [self._row_to_relation(r) for r in rows]

    def remove_relation(self, source_id: str, target_id: str, relation_type: str) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM relations WHERE source_id=? AND target_id=? AND relation_type=?",
            (source_id, target_id, relation_type),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # -- Traversal --

    def neighbors(self, entity_id: str, max_depth: int = 2) -> list[tuple[Entity, str]]:
        """BFS traversal — returns (entity, relation_type) pairs reachable from entity_id."""
        visited: set[str] = {entity_id}
        queue: list[tuple[str, int]] = [(entity_id, 0)]
        results: list[tuple[Entity, str]] = []

        while queue:
            current, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for rel in self.get_relations(current, direction="outgoing"):
                if rel.target_id not in visited:
                    visited.add(rel.target_id)
                    entity = self.get_entity(rel.target_id)
                    if entity:
                        results.append((entity, rel.relation_type))
                        queue.append((rel.target_id, depth + 1))

        return results

    # -- Stats --

    def stats(self) -> dict[str, int]:
        entity_count = self._conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        relation_count = self._conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        type_count = self._conn.execute(
            "SELECT COUNT(DISTINCT entity_type) FROM entities"
        ).fetchone()[0]
        return {
            "entities": entity_count,
            "relations": relation_count,
            "entity_types": type_count,
        }

    # -- Snapshot --

    def snapshot(self) -> dict[str, Any]:
        """Export the full world state as a serializable dict."""
        entities = self.find_entities(limit=10000)
        all_rels: list[Relation] = []
        for e in entities:
            all_rels.extend(self.get_relations(e.id, direction="outgoing"))
        return {
            "entities": [e.model_dump(mode="json") for e in entities],
            "relations": [r.model_dump(mode="json") for r in all_rels],
            "stats": self.stats(),
        }

    # -- Helpers --

    def _row_to_entity(self, row: sqlite3.Row) -> Entity:
        tags = [t for t in row["tags"].split(",") if t] if row["tags"] else []
        return Entity(
            id=row["id"],
            entity_type=row["entity_type"],
            name=row["name"],
            properties=json.loads(row["properties"]) if row["properties"] else {},
            tags=tags,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _row_to_relation(self, row: sqlite3.Row) -> Relation:
        return Relation(
            source_id=row["source_id"],
            target_id=row["target_id"],
            relation_type=row["relation_type"],
            properties=json.loads(row["properties"]) if row["properties"] else {},
            confidence=row["confidence"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def close(self) -> None:
        self._conn.close()
