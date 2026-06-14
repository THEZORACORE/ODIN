"""Tests for the deterministic semantic-similarity comparator."""

import pytest

from odin.verify.similarity import SemanticComparator, containment, token_cosine


class TestPrimitives:
    def test_identical_strings(self) -> None:
        assert token_cosine("hello world", "hello world") == pytest.approx(1.0)

    def test_disjoint_strings(self) -> None:
        assert token_cosine("42", "43") == 0.0

    def test_containment_short_in_verbose(self) -> None:
        assert containment("42", "the answer is 42") == 1.0

    def test_containment_disjoint(self) -> None:
        assert containment("43", "the answer is 42") == 0.0


class TestComparator:
    def test_exact_match_case_insensitive(self) -> None:
        c = SemanticComparator()
        agrees, score = c.agrees("Paris", "paris")
        assert agrees is True
        assert score == 1.0

    def test_concise_matches_verbose(self) -> None:
        c = SemanticComparator()
        agrees, score = c.agrees("The answer is 42.", "42")
        assert agrees is True
        assert score >= 0.75

    def test_distinct_numbers_disagree(self) -> None:
        c = SemanticComparator()
        agrees, _ = c.agrees("The answer is 42.", "43")
        assert agrees is False

    def test_threshold_is_configurable(self) -> None:
        loose = SemanticComparator(threshold=0.1)
        strict = SemanticComparator(threshold=0.99)
        a, b = "the result is large", "the result is small"
        assert loose.agrees(a, b)[0] is True
        assert strict.agrees(a, b)[0] is False

    def test_injected_embeddings_are_used(self) -> None:
        # Orthogonal vectors → cosine 0 → disagree, even though tokens overlap.
        def embed(texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0], [0.0, 1.0]]

        c = SemanticComparator(embed=embed, threshold=0.5)
        agrees, score = c.agrees("same words here", "same words here too")
        assert agrees is False
        assert score == 0.0
