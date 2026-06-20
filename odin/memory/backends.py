"""Pluggable memory backends (Phase 2.6).

Abstract interfaces for graph and vector storage so MIMIR can swap
between lightweight defaults and production-grade backends:

- GraphBackend: NetworkX (default) or Neo4j
- VectorBackend: ChromaDB (default) or any embedding store

Callers use the abstract interface; concrete implementations are
selected via configuration without changing MIMIR's core logic.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("odin.memory.backends")


# ---------------------------------------------------------------------------
# Graph backend
# ---------------------------------------------------------------------------

class GraphBackend(ABC):
    """Abstract graph storage for semantic memory."""

    @abstractmethod
    def add_concept(self, concept: str, metadata: dict[str, Any] | None = None) -> None:
        ...

    @abstractmethod
    def add_relation(self, source: str, target: str, relation: str) -> None:
        ...

    @abstractmethod
    def get_related(self, concept: str, max_depth: int = 2) -> list[tuple[str, str]]:
        """Return (concept, relation) pairs reachable from the given concept."""
        ...

    @abstractmethod
    def has_concept(self, concept: str) -> bool:
        ...

    @abstractmethod
    def concept_count(self) -> int:
        ...


class NetworkXGraphBackend(GraphBackend):
    """Default in-memory graph using NetworkX."""

    def __init__(self) -> None:
        import networkx as nx
        self._graph: nx.DiGraph[str] = nx.DiGraph()

    def add_concept(self, concept: str, metadata: dict[str, Any] | None = None) -> None:
        self._graph.add_node(concept, **(metadata or {}))

    def add_relation(self, source: str, target: str, relation: str) -> None:
        if not self._graph.has_node(source):
            self._graph.add_node(source)
        if not self._graph.has_node(target):
            self._graph.add_node(target)
        self._graph.add_edge(source, target, relation=relation)

    def get_related(self, concept: str, max_depth: int = 2) -> list[tuple[str, str]]:
        if not self._graph.has_node(concept):
            return []
        related: list[tuple[str, str]] = []
        visited: set[str] = {concept}
        queue: list[tuple[str, int]] = [(concept, 0)]
        while queue:
            node, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for _, neighbor, data in self._graph.edges(node, data=True):
                rel = data.get("relation", "related_to")
                related.append((neighbor, rel))
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, depth + 1))
        return related

    def has_concept(self, concept: str) -> bool:
        return self._graph.has_node(concept)

    def concept_count(self) -> int:
        return self._graph.number_of_nodes()


class Neo4jGraphBackend(GraphBackend):
    """Neo4j-backed graph for production-scale semantic memory.

    Requires neo4j Python driver and a running Neo4j instance.
    Connection via NEO4J_URI + NEO4J_USER + NEO4J_PASSWORD env vars.
    """

    def __init__(self, uri: str, user: str, password: str) -> None:
        try:
            from neo4j import GraphDatabase  # type: ignore[import-not-found]
            self._driver = GraphDatabase.driver(uri, auth=(user, password))
            logger.info("Neo4j graph backend connected: %s", uri)
        except ImportError as exc:
            raise ImportError("neo4j package required: pip install neo4j") from exc

    def add_concept(self, concept: str, metadata: dict[str, Any] | None = None) -> None:
        props = metadata or {}
        with self._driver.session() as session:
            session.run(
                "MERGE (c:Concept {name: $name}) SET c += $props",
                name=concept, props=props,
            )

    def add_relation(self, source: str, target: str, relation: str) -> None:
        with self._driver.session() as session:
            session.run(
                """
                MERGE (s:Concept {name: $source})
                MERGE (t:Concept {name: $target})
                MERGE (s)-[r:RELATES_TO {type: $rel}]->(t)
                """,
                source=source, target=target, rel=relation,
            )

    def get_related(self, concept: str, max_depth: int = 2) -> list[tuple[str, str]]:
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (c:Concept {name: $name})-[r*1..$depth]->(related)
                RETURN related.name AS concept, r[-1].type AS relation
                """,
                name=concept, depth=max_depth,
            )
            return [(record["concept"], record["relation"] or "related_to") for record in result]

    def has_concept(self, concept: str) -> bool:
        with self._driver.session() as session:
            result = session.run(
                "MATCH (c:Concept {name: $name}) RETURN count(c) AS cnt",
                name=concept,
            )
            row = result.single()
            return bool(row["cnt"] > 0) if row else False

    def concept_count(self) -> int:
        with self._driver.session() as session:
            result = session.run("MATCH (c:Concept) RETURN count(c) AS cnt")
            row = result.single()
            return int(row["cnt"]) if row else 0

    def close(self) -> None:
        self._driver.close()


# ---------------------------------------------------------------------------
# Vector backend
# ---------------------------------------------------------------------------

class VectorBackend(ABC):
    """Abstract vector storage for dense retrieval."""

    @abstractmethod
    def add(self, doc_id: str, text: str) -> None:
        ...

    @abstractmethod
    def query(self, text: str, n: int = 5) -> list[tuple[str, float]]:
        """Return (doc_id, distance) pairs sorted by relevance."""
        ...

    @abstractmethod
    def delete(self, doc_id: str) -> None:
        ...

    @abstractmethod
    def count(self) -> int:
        ...


class ChromaVectorBackend(VectorBackend):
    """ChromaDB-backed vector store (the Phase 1 default)."""

    def __init__(self, persist_dir: str, collection_name: str = "odin_memory") -> None:
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=persist_dir)
            self._collection = self._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB vector backend: %s", persist_dir)
        except ImportError as exc:
            raise ImportError("chromadb package required: pip install chromadb") from exc

    def add(self, doc_id: str, text: str) -> None:
        self._collection.upsert(ids=[doc_id], documents=[text])

    def query(self, text: str, n: int = 5) -> list[tuple[str, float]]:
        results = self._collection.query(query_texts=[text], n_results=n)
        ids_list = results.get("ids") or [[]]
        dist_list = results.get("distances") or [[]]
        ids = ids_list[0]
        distances = dist_list[0]
        return list(zip(ids, distances, strict=False))

    def delete(self, doc_id: str) -> None:
        import contextlib

        with contextlib.suppress(Exception):
            self._collection.delete(ids=[doc_id])

    def count(self) -> int:
        return self._collection.count()


class InMemoryVectorBackend(VectorBackend):
    """Simple in-memory vector backend using TF-IDF for testing/lightweight use.

    No external dependencies. Uses bag-of-words cosine similarity.
    """

    def __init__(self) -> None:
        self._docs: dict[str, str] = {}

    def add(self, doc_id: str, text: str) -> None:
        self._docs[doc_id] = text

    def query(self, text: str, n: int = 5) -> list[tuple[str, float]]:
        if not self._docs:
            return []
        query_tokens = set(text.lower().split())
        scores: list[tuple[str, float]] = []
        for doc_id, doc_text in self._docs.items():
            doc_tokens = set(doc_text.lower().split())
            intersection = query_tokens & doc_tokens
            union = query_tokens | doc_tokens
            similarity = len(intersection) / len(union) if union else 0.0
            # Return as distance (lower = better)
            scores.append((doc_id, 1.0 - similarity))
        scores.sort(key=lambda x: x[1])
        return scores[:n]

    def delete(self, doc_id: str) -> None:
        self._docs.pop(doc_id, None)

    def count(self) -> int:
        return len(self._docs)
