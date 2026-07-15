"""Expected-value and odds utility functions."""


def vig_free_probability(decimal_odds: float, market_total: float = 1.0) -> float:
    """Convert decimal odds into a vig-free probability.

    For a two-outcome market the implied probabilities sum to more than 1.
    We normalize by the overround to remove the bookmaker margin.
    """
    if decimal_odds <= 1.0:
        return 0.0
    implied = 1.0 / decimal_odds
    return implied / market_total


def compute_ev(model_probability: float, decimal_odds: float) -> float:
    """Expected value of a unit bet: p*(b+1) - 1 where b = decimal_odds - 1."""
    if decimal_odds <= 1.0:
        return -1.0
    return model_probability * decimal_odds - 1.0
