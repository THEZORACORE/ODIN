"""MIMIR — Memory, Indexing, and Management for Intelligent Retrieval.

Phase 1 implementation:
- Working memory: in-process dict (current session scratch)
- Episodic memory: ChromaDB for dense retrieval + SQLite for structured metadata
- Semantic memory: NetworkX graph (defer Neo4j)
- Hybrid retrieval: dense (Chroma) + keyword (SQLite FTS) with score fusion
- Recursive summarization / compression via LLM
- Provenance on every record
- Persistence across sessions via SQLite + Chroma on-disk
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import networkx as nx

from odin.routing.llm_adapter import LLMAdapter, LLMMessage, LLMResponse
from odin.schemas import MemoryRecord, MemoryType, Provenance

# ---------------------------------------------------------------------------
# ChromaDB wrapper (lazy import so tests can run without it installed)
# ---------------------------------------------------------------------------

class _ChromaStore:
    """Thin wrapper around ChromaDB for dense vector retrieval."""

    def __init__(self, persist_dir: str) -> None:
        import chromadb
        from chromadb.config import Settings

        self._client = chromadb.Client(Settings(
            persist_directory=persist_dir,
            anonymized_telemetry=False,
            is_persistent=True,
        ))
        self._collection = self._client.get_or_create_collection(
            name="odin_episodic",
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, record: MemoryRecord) -> None:
        self._collection.upsert(
            ids=[record.id],
            documents=[record.content],
            metadatas=[{"type": record.memory_type.value, "tags": ",".join(record.tags)}],
        )

    def query(self, text: str, n: int = 5) -> list[tuple[str, float]]:
        results = self._collection.query(query_texts=[text], n_results=n)
        ids: list[str] = results["ids"][0] if results["ids"] else []
        raw_distances = results.get("distances")
        distances: list[float] = raw_distances[0] if raw_distances else [0.0] * len(ids)
        return list(zip(ids, distances, strict=False))


# ---------------------------------------------------------------------------
# SQLite structured store
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    memory_type TEXT NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    provenance TEXT,
    tags TEXT,
    access_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    session_id TEXT,
    metadata TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content, summary, tags, content_rowid='rowid'
);
"""


class _SQLiteStore:
    """Structured record store with FTS5 keyword search."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    def upsert(self, record: MemoryRecord) -> None:
        prov_json = json.dumps([p.model_dump(mode="json") for p in record.provenance])
        meta_json = json.dumps(record.metadata)
        tags_str = ",".join(record.tags)

        self._conn.execute(
            """INSERT INTO memories (id, memory_type, content, summary, provenance,
               tags, access_count, created_at, updated_at, session_id, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 content=excluded.content, summary=excluded.summary,
                 provenance=excluded.provenance, tags=excluded.tags,
                 access_count=excluded.access_count, updated_at=excluded.updated_at,
                 metadata=excluded.metadata""",
            (
                record.id, record.memory_type.value, record.content, record.summary,
                prov_json, tags_str, record.access_count,
                record.created_at.isoformat(), record.updated_at.isoformat(),
                record.session_id, meta_json,
            ),
        )
        # FTS sync: delete old, insert new
        # Use rowid lookup for FTS
        row = self._conn.execute("SELECT rowid FROM memories WHERE id=?", (record.id,)).fetchone()
        if row:
            rowid = row[0]
            self._conn.execute("DELETE FROM memories_fts WHERE rowid=?", (rowid,))
            self._conn.execute(
                "INSERT INTO memories_fts (rowid, content, summary, tags) VALUES (?, ?, ?, ?)",
                (rowid, record.content, record.summary or "", tags_str),
            )
        self._conn.commit()

    def get(self, record_id: str) -> MemoryRecord | None:
        row = self._conn.execute("SELECT * FROM memories WHERE id=?", (record_id,)).fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def keyword_search(self, query: str, limit: int = 10) -> list[MemoryRecord]:
        # FTS5 search — quote individual terms to handle special chars like dots
        safe_query = " ".join(f'"{t}"' for t in query.split() if t)
        if not safe_query:
            return []
        rows = self._conn.execute(
            """SELECT m.* FROM memories m
               JOIN memories_fts f ON m.rowid = f.rowid
               WHERE memories_fts MATCH ?
               LIMIT ?""",
            (safe_query, limit),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_by_session(self, session_id: str) -> list[MemoryRecord]:
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE session_id=? ORDER BY created_at", (session_id,)
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def all_records(self) -> list[MemoryRecord]:
        rows = self._conn.execute("SELECT * FROM memories ORDER BY created_at").fetchall()
        return [self._row_to_record(r) for r in rows]

    def _row_to_record(self, row: sqlite3.Row) -> MemoryRecord:
        prov_data = json.loads(row["provenance"]) if row["provenance"] else []
        provenance = [Provenance(**p) for p in prov_data]
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        tags = [t for t in row["tags"].split(",") if t] if row["tags"] else []
        return MemoryRecord(
            id=row["id"],
            memory_type=MemoryType(row["memory_type"]),
            content=row["content"],
            summary=row["summary"],
            provenance=provenance,
            tags=tags,
            access_count=row["access_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            session_id=row["session_id"],
            metadata=meta,
        )

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# Semantic graph (NetworkX)
# ---------------------------------------------------------------------------

class _SemanticGraph:
    """Lightweight semantic graph for concept relationships."""

    def __init__(self) -> None:
        self.graph: nx.DiGraph[str] = nx.DiGraph()

    def add_concept(self, concept: str, metadata: dict[str, Any] | None = None) -> None:
        self.graph.add_node(concept, **(metadata or {}))

    def add_relation(self, source: str, target: str, relation: str) -> None:
        if source not in self.graph:
            self.graph.add_node(source)
        if target not in self.graph:
            self.graph.add_node(target)
        self.graph.add_edge(source, target, relation=relation)

    def get_related(self, concept: str, max_depth: int = 2) -> list[tuple[str, str]]:
        """BFS from concept, return (node, relation) pairs."""
        if concept not in self.graph:
            return []
        results: list[tuple[str, str]] = []
        visited = {concept}
        frontier = [(concept, 0)]
        while frontier:
            node, depth = frontier.pop(0)
            if depth >= max_depth:
                continue
            for _, neighbor, data in self.graph.edges(node, data=True):
                if neighbor not in visited:
                    visited.add(neighbor)
                    rel = data.get("relation", "related_to")
                    results.append((neighbor, rel))
                    frontier.append((neighbor, depth + 1))
        return results

    def save(self, path: str) -> None:
        data = nx.node_link_data(self.graph)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str) -> None:
        p = Path(path)
        if p.exists():
            with open(path) as f:
                data = json.load(f)
            self.graph = nx.node_link_graph(data, directed=True)


# ---------------------------------------------------------------------------
# MIMIR — unified memory interface
# ---------------------------------------------------------------------------

class Mimir:
    """Unified memory facade.

    Backends are swappable — Phase 1 uses SQLite + Chroma + NetworkX.
    All writes include provenance.  All reads are hybrid (dense + keyword).
    """

    def __init__(
        self,
        data_dir: str = ".odin_data",
        llm: LLMAdapter | None = None,
        use_chroma: bool = True,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._llm = llm

        # Working memory — in-process, per-session
        self._working: dict[str, MemoryRecord] = {}

        # Episodic / structured — persisted
        self._sqlite = _SQLiteStore(str(self._data_dir / "mimir.db"))

        # Dense vector store
        self._chroma: _ChromaStore | None = None
        if use_chroma:
            try:
                self._chroma = _ChromaStore(str(self._data_dir / "chroma"))
            except Exception:
                # Chroma not available — degrade to keyword-only
                self._chroma = None

        # Semantic graph
        self._graph = _SemanticGraph()
        self._graph.load(str(self._data_dir / "semantic_graph.json"))

    # -- Write --

    def store(self, record: MemoryRecord) -> MemoryRecord:
        """Store a memory record with provenance."""
        record.updated_at = datetime.now(UTC)

        if record.memory_type == MemoryType.WORKING:
            self._working[record.id] = record
        else:
            self._sqlite.upsert(record)
            if self._chroma is not None:
                self._chroma.add(record)

        return record

    def store_working(self, key: str, content: str, source_id: str = "system") -> MemoryRecord:
        """Convenience: store a working-memory entry."""
        record = MemoryRecord(
            id=key,
            memory_type=MemoryType.WORKING,
            content=content,
            provenance=[Provenance(source_type="system", source_id=source_id)],
        )
        return self.store(record)

    def store_episodic(
        self,
        content: str,
        *,
        source_type: str = "llm",
        source_id: str = "unknown",
        tags: list[str] | None = None,
        session_id: str | None = None,
    ) -> MemoryRecord:
        """Convenience: store an episodic memory with provenance."""
        record = MemoryRecord(
            memory_type=MemoryType.EPISODIC,
            content=content,
            provenance=[Provenance(source_type=source_type, source_id=source_id)],
            tags=tags or [],
            session_id=session_id,
        )
        return self.store(record)

    def add_concept(self, concept: str, metadata: dict[str, Any] | None = None) -> None:
        self._graph.add_concept(concept, metadata)

    def add_relation(self, source: str, target: str, relation: str) -> None:
        self._graph.add_relation(source, target, relation)

    # -- Read --

    def get_working(self, key: str) -> str | None:
        rec = self._working.get(key)
        return rec.content if rec else None

    def get(self, record_id: str) -> MemoryRecord | None:
        rec = self._working.get(record_id)
        if rec:
            return rec
        return self._sqlite.get(record_id)

    def retrieve(self, query: str, n: int = 5) -> list[MemoryRecord]:
        """Hybrid retrieval: fuse dense (Chroma) + keyword (FTS5) results."""
        seen: dict[str, MemoryRecord] = {}
        scores: dict[str, float] = {}

        # Dense retrieval
        if self._chroma is not None:
            for rid, dist in self._chroma.query(query, n=n):
                rec = self._sqlite.get(rid)
                if rec:
                    seen[rid] = rec
                    # Chroma returns L2 distance — convert to similarity
                    scores[rid] = max(0, 1.0 - dist)

        # Keyword retrieval
        for rec in self._sqlite.keyword_search(query, limit=n):
            if rec.id not in seen:
                seen[rec.id] = rec
                scores[rec.id] = 0.5  # FTS matches get a baseline score

        # Sort by score descending, return top n
        ranked = sorted(seen.keys(), key=lambda rid: scores.get(rid, 0), reverse=True)
        results = [seen[rid] for rid in ranked[:n]]
        for r in results:
            r.access_count += 1
            self._sqlite.upsert(r)
        return results

    def get_related_concepts(self, concept: str, max_depth: int = 2) -> list[tuple[str, str]]:
        return self._graph.get_related(concept, max_depth)

    def get_session_memories(self, session_id: str) -> list[MemoryRecord]:
        return self._sqlite.get_by_session(session_id)

    def all_working(self) -> dict[str, str]:
        return {k: v.content for k, v in self._working.items()}

    # -- Compression / Summarization --

    async def compress_memories(self, memories: list[MemoryRecord]) -> MemoryRecord | None:
        """Recursively summarize a list of memories into one consolidated record.

        Requires an LLM adapter.  If none is set, returns None (graceful degrade).
        """
        if not self._llm or not memories:
            return None

        combined = "\n\n".join(
            f"[{m.created_at.isoformat()}] {m.content}" for m in memories
        )
        prompt = (
            "Summarize the following episodic memories into a concise, factual summary. "
            "Preserve key facts, decisions, and outcomes.  Drop redundancy.\n\n"
            f"{combined}"
        )
        resp: LLMResponse = await self._llm.complete(
            [LLMMessage(role="user", content=prompt)],
            temperature=0.0,
            max_tokens=1024,
        )
        source_ids = [m.id for m in memories]
        consolidated = MemoryRecord(
            memory_type=MemoryType.EPISODIC,
            content=resp.content,
            summary="Consolidated summary",
            provenance=[Provenance(source_type="compression", source_id=",".join(source_ids))],
            tags=["consolidated"],
        )
        return self.store(consolidated)

    # -- Persistence --

    def save(self) -> None:
        """Flush graph to disk.  SQLite and Chroma auto-persist."""
        self._graph.save(str(self._data_dir / "semantic_graph.json"))

    def close(self) -> None:
        self.save()
        self._sqlite.close()
