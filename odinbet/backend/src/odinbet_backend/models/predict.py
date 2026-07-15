"""Inference utilities: probabilities, key-factor explanations, and pick construction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import polars as pl

from ..bankroll import kelly_stake
from ..config import settings
from ..ev import compute_ev
from .explain import rationale_from_factors, top_key_factors


class ModelService:
    """Load a trained model and produce ranked picks."""

    def __init__(self, model_dir: Path | None = None):
        self.model_dir = model_dir or settings.model_dir
        self._artifacts: dict | None = None

    def load(self) -> dict:
        if self._artifacts is None:
            artifact_path = self.model_dir / "model_v1.pkl"
            if not artifact_path.exists():
                raise FileNotFoundError(
                    f"No trained model found at {artifact_path}. Run training first."
                )
            self._artifacts = joblib.load(artifact_path)
        return self._artifacts

    def _impute(self, X: np.ndarray) -> np.ndarray:
        """Impute missing values using the stored median imputer."""
        artifacts = self.load()
        imputer = artifacts["imputer"]
        return imputer.transform(X)

    def predict(self, data: pl.DataFrame, feature_cols: list[str]) -> np.ndarray:
        """Return calibrated home-win probabilities."""
        artifacts = self.load()
        X = data.select(feature_cols).to_numpy()
        X_imp = self._impute(X)
        model = artifacts["model"]
        return model.predict_proba(X_imp)[:, 1]

    def build_picks(
        self,
        data: pl.DataFrame,
        feature_cols: list[str],
        odds_provider: Any,
        game_date: str | None = None,
        min_ev: float = 0.0,
        min_confidence: float = 0.5,
        max_picks: int = 50,
        bankroll: float = 1000.0,
        max_daily_exposure: float = 0.05,
    ) -> list[dict]:
        """Build ranked pick objects for the requested date.

        Stakes are sized with fractional Kelly and then scaled so the total daily
        bankroll exposure does not exceed ``max_daily_exposure``.
        """
        if game_date:
            year, month, day = map(int, game_date.split("-"))
            games = data.filter(pl.col("game_date") == pl.date(year, month, day))
        else:
            games = data

        if len(games) == 0:
            return []

        games = odds_provider.get_probabilities(games, feature_cols)
        home_probs = self.predict(games, feature_cols)
        away_probs = 1.0 - home_probs

        artifacts = self.load()
        importance = artifacts["importance"]
        direction_map = artifacts["direction_map"]

        picks: list[dict] = []
        for i, row in enumerate(games.iter_rows(named=True)):
            home_prob = float(home_probs[i])
            away_prob = float(away_probs[i])
            if home_prob >= away_prob:
                selection = row["home_team_abbreviation"]
                market = "moneyline"
                model_prob = home_prob
                decimal_odds = float(row["home_decimal_odds"])
                side = "home"
                opp_abbr = row["away_team_abbreviation"]
            else:
                selection = row["away_team_abbreviation"]
                market = "moneyline"
                model_prob = away_prob
                decimal_odds = float(row["away_decimal_odds"])
                side = "away"
                opp_abbr = row["home_team_abbreviation"]

            ev = compute_ev(model_prob, decimal_odds)
            if ev < min_ev or model_prob < min_confidence:
                continue

            units = kelly_stake(bankroll, decimal_odds, model_prob)
            key_factors = top_key_factors(
                row=row,
                feature_cols=feature_cols,
                importance=importance,
                direction_map=direction_map,
                selection_side=side,
                top_n=5,
            )
            rationale = rationale_from_factors(selection, opp_abbr, key_factors)

            picks.append(
                {
                    "game_id": row["game_id"],
                    "matchup": f"{row['away_team_abbreviation']} @ {row['home_team_abbreviation']}",
                    "market": market,
                    "selection": selection,
                    "model_probability": round(model_prob, 4),
                    "decimal_odds": round(decimal_odds, 3),
                    "ev": round(ev, 4),
                    "recommended_units": round(units, 4),
                    "raw_units": round(units, 4),
                    "confidence": round(model_prob, 4),
                    "rationale": rationale,
                    "key_factors": key_factors,
                }
            )

        picks.sort(key=lambda p: p["ev"], reverse=True)
        picks = picks[:max_picks]

        total = sum(p["recommended_units"] for p in picks)
        max_total = bankroll * max_daily_exposure
        if total > max_total > 0:
            scale = max_total / total
            for p in picks:
                p["recommended_units"] = round(p["recommended_units"] * scale, 4)

        return picks
