"""Bankroll management and stake sizing utilities."""


def kelly_stake(
    bankroll: float,
    decimal_odds: float,
    model_probability: float,
    fraction: float = 0.25,
    max_risk: float = 0.02,
) -> float:
    """Return a currency stake using fractional Kelly with a hard cap.

    Args:
        bankroll: Total bankroll in currency.
        decimal_odds: Decimal odds for the selection.
        model_probability: Model-estimated probability of winning.
        fraction: Kelly fraction (default 1/4 to reduce variance).
        max_risk: Maximum percentage of bankroll to risk on one pick.

    Returns:
        Recommended stake amount.
    """
    if decimal_odds <= 1.0 or model_probability <= 0.0:
        return 0.0
    net_odds = decimal_odds - 1.0
    kelly = (net_odds * model_probability - (1.0 - model_probability)) / net_odds
    stake = bankroll * max(0.0, kelly) * fraction
    return min(stake, bankroll * max_risk)


def daily_exposure_limit(bankroll: float, pct: float = 0.05) -> float:
    """Return maximum aggregate stake allowed for a single day."""
    return bankroll * pct
