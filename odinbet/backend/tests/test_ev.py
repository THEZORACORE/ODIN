"""Tests for expected-value calculations."""

import pytest

from odinbet_backend.ev import compute_ev, vig_free_probability


def test_vig_free_probability_basic() -> None:
    assert vig_free_probability(2.0, 1.0) == pytest.approx(0.5)


def test_compute_ev_positive() -> None:
    # 60% chance at 2.0 decimal odds -> EV = 0.2
    assert compute_ev(0.6, 2.0) == pytest.approx(0.2)


def test_compute_ev_negative() -> None:
    # 40% chance at 1.8 decimal odds -> EV = -0.28
    assert compute_ev(0.4, 1.8) == pytest.approx(-0.28)
