"""Tests for bankroll / stake sizing utilities."""

import pytest

from odinbet_backend.bankroll import kelly_stake


def test_full_kelly() -> None:
    # b = 1.0 (decimal 2.0), p = 0.6, q = 0.4 -> f* = 0.2
    stake = kelly_stake(1000.0, 2.0, 0.6, fraction=1.0, max_risk=1.0)
    assert stake == pytest.approx(200.0, rel=1e-12)


def test_fractional_kelly_caps_at_max_risk() -> None:
    # Even with a strong edge, the 2% max risk caps the stake.
    stake = kelly_stake(1000.0, 2.0, 0.75, fraction=1.0, max_risk=0.02)
    assert stake == 20.0


def test_kelly_zero_on_invalid_odds() -> None:
    assert kelly_stake(1000.0, 1.0, 0.6) == 0.0
    assert kelly_stake(1000.0, 2.0, 0.0) == 0.0
