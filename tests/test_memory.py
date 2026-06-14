"""Tests for MIMIR — memory storage, retrieval, and cross-session persistence."""

import tempfile

import pytest

from odin.memory.mimir import Mimir
from odin.routing.llm_adapter import FakeLLM
from odin.schemas import MemoryType


class TestWorkingMemory:
    def test_store_and_retrieve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            m = Mimir(data_dir=tmp, use_chroma=False)
            m.store_working("key1", "value1")
            assert m.get_working("key1") == "value1"
            m.close()

    def test_missing_key_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            m = Mimir(data_dir=tmp, use_chroma=False)
            assert m.get_working("nonexistent") is None
            m.close()

    def test_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            m = Mimir(data_dir=tmp, use_chroma=False)
            m.store_working("key1", "v1")
            m.store_working("key1", "v2")
            assert m.get_working("key1") == "v2"
            m.close()


class TestEpisodicMemory:
    def test_store_episodic_with_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            m = Mimir(data_dir=tmp, use_chroma=False)
            rec = m.store_episodic(
                "The answer is 42",
                source_type="tool",
                source_id="code_interpreter_1",
                tags=["math", "answer"],
                session_id="session_1",
            )
            assert rec.memory_type == MemoryType.EPISODIC
            assert len(rec.provenance) == 1
            assert rec.provenance[0].source_type == "tool"
            m.close()

    def test_retrieve_by_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            m = Mimir(data_dir=tmp, use_chroma=False)
            rec = m.store_episodic("test content", source_id="s1")
            fetched = m.get(rec.id)
            assert fetched is not None
            assert fetched.content == "test content"
            m.close()

    def test_keyword_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            m = Mimir(data_dir=tmp, use_chroma=False)
            m.store_episodic("Python is a programming language", source_id="s1")
            m.store_episodic("Copenhagen is a city in Denmark", source_id="s2")

            results = m.retrieve("Python programming")
            # At minimum, keyword search should find the Python-related record
            assert len(results) >= 1
            m.close()


class TestCrossSessionMemory:
    """Memories must persist across sessions (close + reopen)."""

    def test_persistence_across_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Session 1: store
            m1 = Mimir(data_dir=tmp, use_chroma=False)
            rec = m1.store_episodic(
                "Important fact from session 1",
                source_id="session1_tool",
                session_id="session_1",
            )
            rec_id = rec.id
            m1.save()
            m1.close()

            # Session 2: retrieve
            m2 = Mimir(data_dir=tmp, use_chroma=False)
            fetched = m2.get(rec_id)
            assert fetched is not None
            assert fetched.content == "Important fact from session 1"
            assert fetched.session_id == "session_1"
            m2.close()

    def test_session_memory_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            m = Mimir(data_dir=tmp, use_chroma=False)
            m.store_episodic("fact A", source_id="s", session_id="sess_1")
            m.store_episodic("fact B", source_id="s", session_id="sess_1")
            m.store_episodic("fact C", source_id="s", session_id="sess_2")

            sess1 = m.get_session_memories("sess_1")
            assert len(sess1) == 2
            sess2 = m.get_session_memories("sess_2")
            assert len(sess2) == 1
            m.close()


class TestSemanticGraph:
    def test_add_and_query_concepts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            m = Mimir(data_dir=tmp, use_chroma=False)
            m.add_concept("Python")
            m.add_concept("asyncio")
            m.add_relation("Python", "asyncio", "has_feature")

            related = m.get_related_concepts("Python")
            assert len(related) == 1
            assert related[0] == ("asyncio", "has_feature")
            m.close()

    def test_graph_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            m1 = Mimir(data_dir=tmp, use_chroma=False)
            m1.add_concept("A")
            m1.add_concept("B")
            m1.add_relation("A", "B", "relates_to")
            m1.save()
            m1.close()

            m2 = Mimir(data_dir=tmp, use_chroma=False)
            related = m2.get_related_concepts("A")
            assert len(related) == 1
            m2.close()


class TestMemoryCompression:
    @pytest.mark.asyncio
    async def test_compress_memories(self) -> None:
        llm = FakeLLM(responses=["Consolidated: facts A and B are both important."])
        with tempfile.TemporaryDirectory() as tmp:
            m = Mimir(data_dir=tmp, llm=llm, use_chroma=False)
            rec_a = m.store_episodic("Fact A is true", source_id="s1")
            rec_b = m.store_episodic("Fact B is also true", source_id="s2")

            consolidated = await m.compress_memories([rec_a, rec_b])
            assert consolidated is not None
            assert "consolidated" in consolidated.content.lower() or len(consolidated.content) > 0
            assert "consolidated" in consolidated.tags
            m.close()

    @pytest.mark.asyncio
    async def test_compress_without_llm_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            m = Mimir(data_dir=tmp, llm=None, use_chroma=False)
            rec = m.store_episodic("test", source_id="s")
            result = await m.compress_memories([rec])
            assert result is None
            m.close()
