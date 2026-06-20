"""HUGINN & MUNINN — Live research agents.

Phase 5.4: proactively search the web for a topic, store cited findings
as semantic memories in MIMIR, and return a structured research brief.
Named after Odin's ravens — Huginn (thought) scouts, Muninn (memory) stores.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from odin.memory.mimir import Mimir
from odin.schemas import MemoryRecord, MemoryType, Provenance
from odin.tools.web_search import SearchAdapter, SearchResponse

logger = logging.getLogger("odin.agents.research")


class ResearchFinding:
    """A single cited finding from a research sweep."""

    __slots__ = ("title", "url", "snippet", "relevance")

    def __init__(self, title: str, url: str, snippet: str, relevance: float) -> None:
        self.title = title
        self.url = url
        self.snippet = snippet
        self.relevance = relevance

    def __repr__(self) -> str:
        return f"Finding({self.title!r}, relevance={self.relevance:.2f})"


class ResearchBrief:
    """Structured output from a research sweep."""

    __slots__ = ("topic", "findings", "stored_count", "timestamp")

    def __init__(
        self, topic: str, findings: list[ResearchFinding], stored_count: int
    ) -> None:
        self.topic = topic
        self.findings = findings
        self.stored_count = stored_count
        self.timestamp = datetime.now(UTC)

    def as_text(self) -> str:
        if not self.findings:
            return f"No findings for: {self.topic}"
        lines = [f"Research brief: {self.topic}", f"({len(self.findings)} sources)\n"]
        for i, f in enumerate(self.findings, 1):
            lines.append(f"{i}. [{f.title}]({f.url})")
            lines.append(f"   {f.snippet}")
            lines.append("")
        lines.append(f"{self.stored_count} findings stored in MIMIR.")
        return "\n".join(lines)


class ResearchAgent:
    """Proactive research agent — searches, filters, stores in MIMIR.

    Usage:
        agent = ResearchAgent(search_adapter, mimir)
        brief = await agent.research("Python async best practices", max_results=5)
    """

    def __init__(
        self,
        search: SearchAdapter,
        mimir: Mimir,
        *,
        min_relevance: float = 0.3,
        session_id: str | None = None,
    ) -> None:
        self._search = search
        self._mimir = mimir
        self._min_relevance = min_relevance
        self._session_id = session_id

    async def research(
        self, topic: str, *, max_results: int = 5
    ) -> ResearchBrief:
        """Search for a topic, store cited results in MIMIR, return a brief."""
        logger.info("Researching: %s", topic)
        response: SearchResponse = await self._search.search(
            topic, max_results=max_results
        )

        findings: list[ResearchFinding] = []
        stored = 0

        for result in response.results:
            finding = ResearchFinding(
                title=result.title,
                url=result.url,
                snippet=result.snippet,
                relevance=result.score,
            )
            findings.append(finding)

            if result.score >= self._min_relevance:
                self._store_finding(topic, finding)
                stored += 1

        brief = ResearchBrief(topic=topic, findings=findings, stored_count=stored)
        logger.info(
            "Research complete: %d findings, %d stored", len(findings), stored
        )
        return brief

    async def multi_research(
        self, topics: list[str], *, max_results: int = 3
    ) -> list[ResearchBrief]:
        """Research multiple topics and return all briefs."""
        briefs: list[ResearchBrief] = []
        for topic in topics:
            brief = await self.research(topic, max_results=max_results)
            briefs.append(brief)
        return briefs

    def _store_finding(self, topic: str, finding: ResearchFinding) -> None:
        """Store a single finding as a semantic memory in MIMIR."""
        content = (
            f"[{finding.title}]({finding.url})\n{finding.snippet}"
        )
        record = MemoryRecord(
            memory_type=MemoryType.SEMANTIC,
            content=content,
            summary=f"Research: {topic} — {finding.title}",
            provenance=[
                Provenance(source_type="web_search", source_id=finding.url),
            ],
            tags=["research", "web_source", topic.split()[0].lower()],
            session_id=self._session_id,
            metadata={
                "topic": topic,
                "url": finding.url,
                "relevance": finding.relevance,
            },
        )
        self._mimir.store(record)
