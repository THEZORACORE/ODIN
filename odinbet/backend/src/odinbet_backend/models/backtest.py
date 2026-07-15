"""Backtest utilities: simulate betting the model on the held-out test set."""

from __future__ import annotations

import polars as pl

from ..bankroll import kelly_stake
from ..data.nba import build_training_data, get_feature_columns, load_raw_games
from ..data.odds import BaselineOddsProvider
from .predict import ModelService
from .train import chronological_data_split


def _chronological_test_split(data: pl.DataFrame) -> pl.DataFrame:
    """Return the chronological test set (same split used during training)."""
    _, _, test_df = chronological_data_split(data)
    return test_df


def run_backtest(
    data: pl.DataFrame | None = None,
    feature_cols: list[str] | None = None,
    model_service: ModelService | None = None,
    odds_provider: BaselineOddsProvider | None = None,
    bankroll: float = 1000.0,
) -> dict:
    """Simulate flat Kelly-sized wagers on the chronological test set."""
    if data is None:
        raw = load_raw_games()
        data = build_training_data(raw)
    if feature_cols is None:
        feature_cols = get_feature_columns(data)
    if model_service is None:
        model_service = ModelService()
    if odds_provider is None:
        odds_provider = BaselineOddsProvider()

    test_data = _chronological_test_split(data)
    if len(test_data) == 0:
        return {
            "n_games": 0,
            "roi": 0.0,
            "profit": 0.0,
            "wagered": 0.0,
            "wins": 0,
            "losses": 0,
            "pushes": 0,
        }

    test_data = odds_provider.get_probabilities(test_data, feature_cols)
    home_probs = model_service.predict(test_data, feature_cols)

    current_bankroll = bankroll
    total_wagered = 0.0
    wins = 0
    losses = 0
    pushes = 0

    for i, row in enumerate(test_data.iter_rows(named=True)):
        home_prob = float(home_probs[i])
        away_prob = 1.0 - home_prob
        if home_prob >= away_prob:
            prob = home_prob
            odds = float(row["home_decimal_odds"])
            won = bool(row["home_win"])
        else:
            prob = away_prob
            odds = float(row["away_decimal_odds"])
            won = not bool(row["home_win"])

        stake = kelly_stake(current_bankroll, odds, prob)
        if stake <= 0:
            continue

        total_wagered += stake
        if won:
            current_bankroll += stake * (odds - 1.0)
            wins += 1
        else:
            current_bankroll -= stake
            losses += 1

    profit = current_bankroll - bankroll
    bankroll_return = (profit / bankroll) if bankroll > 0 else 0.0
    roi = (profit / total_wagered) if total_wagered > 0 else 0.0
    return {
        "n_games": len(test_data),
        "roi": round(roi, 4),
        "profit": round(profit, 2),
        "wagered": round(total_wagered, 2),
        "final_bankroll": round(current_bankroll, 2),
        "bankroll_return": round(bankroll_return, 4),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
    }
