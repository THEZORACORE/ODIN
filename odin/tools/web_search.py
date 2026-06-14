"""Web search adapter.

Pluggable interface: Tavily (default if TAVILY_API_KEY is set), or mock for tests.
Retrieved content is UNTRUSTED DATA — HEIMDALL's injection boundary applies.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

logger = logging.getLogger("odin.tools.web_search")


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    score: float = 0.0


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult] = Field(default_factory=list)


class SearchAdapter(ABC):
    """Abstract search backend."""

    @abstractmethod
    async def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        ...


class MockSearchAdapter(SearchAdapter):
    """Returns canned results for testing."""

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self._results = results or [
            SearchResult(
                title="Mock result",
                url="https://example.com",
                snippet="This is a mock search result for testing.",
                score=0.9,
            )
        ]

    async def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        return SearchResponse(query=query, results=self._results[:max_results])


class TavilySearchAdapter(SearchAdapter):
    """Real web search via Tavily API (https://tavily.com).

    Reads TAVILY_API_KEY from env. Never hardcodes or logs the key.
    Results are UNTRUSTED DATA — HEIMDALL injection boundary applies.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("TAVILY_API_KEY", "")
        if not self._api_key:
            raise ValueError("TAVILY_API_KEY not set — cannot initialize TavilySearchAdapter")

    async def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        from tavily import AsyncTavilyClient

        client = AsyncTavilyClient(api_key=self._api_key)
        try:
            resp = await client.search(
                query=query,
                max_results=max_results,
                search_depth="basic",
                include_answer=False,
            )
        except Exception as e:
            logger.error("Tavily search failed: %s", e)
            return SearchResponse(query=query, results=[])

        results: list[SearchResult] = []
        for item in resp.get("results", []):
            results.append(SearchResult(
                title=item.get("title", "Untitled"),
                url=item.get("url", ""),
                snippet=item.get("content", "")[:500],
                score=item.get("score", 0.0),
            ))
        return SearchResponse(query=query, results=results)


# Singleton-style accessor for the web-search tool callable
_adapter: SearchAdapter = MockSearchAdapter()


def set_search_adapter(adapter: SearchAdapter) -> None:
    global _adapter
    _adapter = adapter


def auto_configure_search() -> None:
    """Auto-select search adapter based on available env vars."""
    global _adapter
    if os.environ.get("TAVILY_API_KEY"):
        try:
            _adapter = TavilySearchAdapter()
            logger.info("Web search: using Tavily (real search)")
        except Exception as e:
            logger.warning("Tavily init failed (%s), falling back to mock", e)
            _adapter = MockSearchAdapter()
    else:
        logger.info("Web search: using mock (TAVILY_API_KEY not set)")
        _adapter = MockSearchAdapter()


async def web_search(query: str, max_results: int = 5) -> str:
    """Execute a web search. Returns formatted results as text."""
    response = await _adapter.search(query, max_results=max_results)
    if not response.results:
        return f"No results found for: {query}"

    lines: list[str] = [f"Search results for: {query}\n"]
    for i, r in enumerate(response.results, 1):
        lines.append(f"{i}. {r.title}")
        lines.append(f"   URL: {r.url}")
        lines.append(f"   {r.snippet}")
        lines.append("")
    return "\n".join(lines)
