"""Tests for pluggable memory backends (Phase 2.6)."""

from __future__ import annotations

from odin.memory.backends import (
    InMemoryVectorBackend,
    NetworkXGraphBackend,
)


class TestNetworkXGraphBackend:
    def test_add_and_has(self) -> None:
        g = NetworkXGraphBackend()
        assert not g.has_concept("Python")
        g.add_concept("Python", {"type": "language"})
        assert g.has_concept("Python")
        assert g.concept_count() == 1

    def test_add_relation(self) -> None:
        g = NetworkXGraphBackend()
        g.add_relation("Python", "asyncio", "has_library")
        assert g.has_concept("Python")
        assert g.has_concept("asyncio")
        assert g.concept_count() == 2

    def test_get_related(self) -> None:
        g = NetworkXGraphBackend()
        g.add_relation("A", "B", "knows")
        g.add_relation("B", "C", "likes")
        related = g.get_related("A", max_depth=2)
        concepts = [c for c, _ in related]
        assert "B" in concepts
        assert "C" in concepts

    def test_get_related_nonexistent(self) -> None:
        g = NetworkXGraphBackend()
        assert g.get_related("nonexistent") == []

    def test_depth_limit(self) -> None:
        g = NetworkXGraphBackend()
        g.add_relation("A", "B", "r1")
        g.add_relation("B", "C", "r2")
        g.add_relation("C", "D", "r3")
        # depth=1 should only reach B
        related = g.get_related("A", max_depth=1)
        concepts = [c for c, _ in related]
        assert "B" in concepts
        assert "C" not in concepts


class TestInMemoryVectorBackend:
    def test_add_and_count(self) -> None:
        v = InMemoryVectorBackend()
        assert v.count() == 0
        v.add("doc1", "hello world")
        assert v.count() == 1

    def test_query(self) -> None:
        v = InMemoryVectorBackend()
        v.add("doc1", "python programming language")
        v.add("doc2", "javascript web development")
        results = v.query("python coding")
        assert len(results) == 2
        # doc1 should be more similar (lower distance)
        assert results[0][0] == "doc1"

    def test_query_empty(self) -> None:
        v = InMemoryVectorBackend()
        assert v.query("anything") == []

    def test_delete(self) -> None:
        v = InMemoryVectorBackend()
        v.add("doc1", "test")
        v.delete("doc1")
        assert v.count() == 0

    def test_delete_nonexistent(self) -> None:
        v = InMemoryVectorBackend()
        v.delete("nope")  # Should not raise
        assert v.count() == 0
