"""Deterministic answer-similarity for structured self-consistency.

Phase 1's self-consistency check asked one LLM to re-derive an answer and then a
*second* LLM call to judge whether the two answers agreed — so the judgement
itself could be wrong (ARCHITECTURE_DECISIONS #10). This module replaces that
second LLM judge with a deterministic computation:

- **structured extraction** isolates the concise final answer, then
- **semantic similarity** scores agreement.

By default similarity is a dependency-free lexical measure (token cosine +
containment, so a short canonical answer matches a verbose one). An embedding
function can be injected for true semantic similarity in production.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable

EmbeddingFn = Callable[[list[str]], list[list[float]]]

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def token_cosine(a: str, b: str) -> float:
    """Bag-of-words cosine similarity over normalized tokens."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 1.0 if ta == tb else 0.0
    ca, cb = Counter(ta), Counter(tb)
    common = set(ca) & set(cb)
    dot = sum(ca[t] * cb[t] for t in common)
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    return dot / (na * nb) if na and nb else 0.0


def containment(a: str, b: str) -> float:
    """Fraction of the *smaller* token set contained in the larger.

    Lets a concise answer ("42") match a verbose one ("the answer is 42").
    """
    sa, sb = set(_tokens(a)), set(_tokens(b))
    if not sa or not sb:
        return 1.0 if sa == sb else 0.0
    return len(sa & sb) / min(len(sa), len(sb))


def _vector_cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class SemanticComparator:
    """Scores agreement between two answers without an LLM judge call."""

    def __init__(self, embed: EmbeddingFn | None = None, threshold: float = 0.75) -> None:
        self._embed = embed
        self.threshold = threshold

    def similarity(self, a: str, b: str) -> float:
        na, nb = a.strip(), b.strip()
        if not na and not nb:
            return 1.0
        if na.lower() == nb.lower():
            return 1.0
        if self._embed is not None:
            vecs = self._embed([na, nb])
            if len(vecs) == 2 and vecs[0] and vecs[1]:
                return _vector_cosine(vecs[0], vecs[1])
        return max(token_cosine(na, nb), containment(na, nb))

    def agrees(self, a: str, b: str) -> tuple[bool, float]:
        score = self.similarity(a, b)
        return score >= self.threshold, score
