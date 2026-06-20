"""Tests for the ResearchAgent (Phase 5.4)."""

from __future__ import annotations

import tempfile

import pytest

from odin.agents.research import ResearchAgent, ResearchBrief, ResearchFinding
from odin.memory.mimir import Mimir
from odin.routing.llm_adapter import FakeLLM
from odin.tools.web_search import MockSearchAdapter, SearchResult


def _make_adapter(results: list[SearchResult] | None = None) -> MockSearchAdapter:
    return MockSearchAdapter(results=results)


class TestResearchAgent:
    @pytest.mark.asyncio
    async def test_basic_research(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            llm = FakeLLM(responses=[])
            mimir = Mimir(data_dir=tmp, llm=llm, use_chroma=False)
            adapter = _make_adapter()
            agent = ResearchAgent(adapter, mimir)

            brief = await agent.research("Python async")
            assert isinstance(brief, ResearchBrief)
            assert brief.topic == "Python async"
            assert len(brief.findings) == 1
            mimir.close()

    @pytest.mark.asyncio
    async def test_stores_in_mimir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results = [
                SearchResult(title="Result A", url="https://a.com", snippet="Info A", score=0.9),
                SearchResult(title="Result B", url="https://b.com", snippet="Info B", score=0.8),
            ]
            llm = FakeLLM(responses=[])
            mimir = Mimir(data_dir=tmp, llm=llm, use_chroma=False)
            adapter = _make_adapter(results)
            agent = ResearchAgent(adapter, mimir)

            brief = await agent.research("test topic")
            assert brief.stored_count == 2

            # Check MIMIR has semantic records via retrieve
            records = mimir.retrieve("test topic", n=10)
            assert len(records) >= 2
            urls = [r.provenance[0].source_id for r in records if r.provenance]
            assert "https://a.com" in urls
            assert "https://b.com" in urls
            mimir.close()

    @pytest.mark.asyncio
    async def test_filters_by_relevance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results = [
                SearchResult(title="Good", url="https://good.com", snippet="ok", score=0.9),
                SearchResult(title="Bad", url="https://bad.com", snippet="meh", score=0.1),
            ]
            llm = FakeLLM(responses=[])
            mimir = Mimir(data_dir=tmp, llm=llm, use_chroma=False)
            adapter = _make_adapter(results)
            agent = ResearchAgent(adapter, mimir, min_relevance=0.5)

            brief = await agent.research("filter test")
            assert brief.stored_count == 1
            assert len(brief.findings) == 2
            mimir.close()

    @pytest.mark.asyncio
    async def test_multi_research(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            llm = FakeLLM(responses=[])
            mimir = Mimir(data_dir=tmp, llm=llm, use_chroma=False)
            adapter = _make_adapter()
            agent = ResearchAgent(adapter, mimir)

            briefs = await agent.multi_research(["topic A", "topic B"])
            assert len(briefs) == 2
            assert briefs[0].topic == "topic A"
            assert briefs[1].topic == "topic B"
            mimir.close()


class TestResearchBrief:
    def test_as_text_with_findings(self) -> None:
        findings = [
            ResearchFinding("Title A", "https://a.com", "snippet a", 0.9),
            ResearchFinding("Title B", "https://b.com", "snippet b", 0.7),
        ]
        brief = ResearchBrief("test topic", findings, stored_count=2)
        text = brief.as_text()
        assert "test topic" in text
        assert "Title A" in text
        assert "2 findings stored in MIMIR" in text

    def test_as_text_empty(self) -> None:
        brief = ResearchBrief("empty topic", [], stored_count=0)
        assert "No findings" in brief.as_text()
