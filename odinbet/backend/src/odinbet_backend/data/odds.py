"""Odds / market-implied probability providers."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

import joblib
import numpy as np
import polars as pl
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ..config import settings


class OddsProvider(ABC):
    """Abstract source of market-implied win probabilities and decimal odds."""

    @abstractmethod
    def get_probabilities(self, games: pl.DataFrame, feature_cols: list[str]) -> pl.DataFrame:
        """Return `market_home_prob` and derived decimal odds per game."""
        ...


class BaselineOddsProvider(OddsProvider):
    """A simple logistic-regression baseline that acts as the synthetic market line."""

    def __init__(self, model_path: Path | None = None, metadata_path: Path | None = None):
        self.model_path = model_path or (settings.model_dir / "baseline_odds.pkl")
        self.metadata_path = metadata_path or (settings.model_dir / "baseline_odds.json")
        self._model: Pipeline | None = None

    def fit(self, data: pl.DataFrame, feature_cols: list[str]) -> BaselineOddsProvider:
        X = data.select(feature_cols).to_numpy()
        y = data["home_win"].to_numpy().ravel()
        model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("logreg", LogisticRegression(max_iter=5000, C=1.0, class_weight="balanced")),
            ]
        )
        model.fit(X, y)
        self._model = model
        joblib.dump(model, self.model_path)
        with open(self.metadata_path, "w") as fh:
            json.dump({"feature_cols": feature_cols}, fh)
        return self

    def _load(self) -> Pipeline:
        if self._model is None:
            self._model = joblib.load(self.model_path)
        return self._model

    def get_probabilities(self, games: pl.DataFrame, feature_cols: list[str]) -> pl.DataFrame:
        model = self._load()
        X = games.select(feature_cols).to_numpy()
        probs = model.predict_proba(X)[:, 1]
        # Clip to avoid divide-by-zero and to add a small synthetic vig.
        market_home = np.clip(probs, 0.05, 0.95)
        market_away = 1.0 - market_home
        home_decimal = 1.0 / market_home * 0.97  # 3% vig
        away_decimal = 1.0 / market_away * 0.97
        return games.with_columns(
            pl.Series("market_home_prob", market_home),
            pl.Series("market_away_prob", market_away),
            pl.Series("home_decimal_odds", home_decimal),
            pl.Series("away_decimal_odds", away_decimal),
        )


class FivethirtyeightOddsProvider(OddsProvider):
    """Use FiveThirtyEight historical `forecast` column as market probability where available."""

    def __init__(self, csv_path: Path | None = None):
        self.csv_path = csv_path or (settings.data_dir / "nbaallelo.csv")
        self._df: pl.DataFrame | None = None

    def _load(self) -> pl.DataFrame:
        if self._df is None:
            self._df = pl.read_csv(self.csv_path)
            self._df = self._df.with_columns(
                pl.col("date_game").str.to_date(format="%m/%d/%Y").alias("game_date"),
            )
        return self._df

    def get_probabilities(self, games: pl.DataFrame, feature_cols: list[str]) -> pl.DataFrame:
        df = self._load()
        # forecast column is the win probability for the team in that row.
        home = df.filter(pl.col("game_location") == "H").select(
            ["game_id", "game_date", "forecast"]
        ).rename({"forecast": "market_home_prob"})
        away = df.filter(pl.col("game_location") == "A").select(
            ["game_id", "forecast"]
        ).rename({"forecast": "market_away_prob"})
        odds = home.join(away, on="game_id", how="inner")
        odds = odds.with_columns(
            (1.0 / pl.col("market_home_prob") * 0.97).alias("home_decimal_odds"),
            (1.0 / pl.col("market_away_prob") * 0.97).alias("away_decimal_odds"),
        )
        merged = games.join(odds, on=["game_id", "game_date"], how="left")
        # Fall back to baseline where 538 data is missing.
        missing = merged.filter(pl.col("market_home_prob").is_null())
        if len(missing) > 0:
            fallback = BaselineOddsProvider().get_probabilities(missing, feature_cols)
            merged = merged.filter(pl.col("market_home_prob").is_not_null()).vstack(fallback)
        return merged
