"""NBA data ingestion and game-feature construction."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import polars as pl

RAW_FILE = "gamelogs.parquet"

# Columns for which we compute team-level rolling averages.
ROLLING_COLS = [
    "pts",
    "pts_allowed",
    "fg_pct",
    "fg3_pct",
    "ft_pct",
    "oreb",
    "dreb",
    "reb",
    "ast",
    "tov",
    "stl",
    "blk",
    "off_rating",
    "def_rating",
    "net_rating",
    "pace",
    "pie",
    "efg_pct",
    "ts_pct",
    "ast_to",
    "ast_ratio",
    "tm_tov_pct",
    "oreb_pct",
    "dreb_pct",
    "reb_pct",
]

WINDOWS: Iterable[int] = (5, 10, 20)


def load_raw_games(path: Path | None = None) -> pl.DataFrame:
    """Load the raw NBA game-log parquet file."""
    if path is None:
        from ..config import DATA_DIR

        path = DATA_DIR / RAW_FILE
    df = pl.read_parquet(path)
    df = df.with_columns(
        pl.col("game_date")
        .str.to_datetime(format="%Y-%m-%dT%H:%M:%S")
        .dt.date()
        .alias("game_date"),
        pl.col("pts").cast(pl.Float64),
        pl.col("team_id").cast(pl.Int64),
    )
    df = _add_opponent_points(df)
    return df


def _add_opponent_points(df: pl.DataFrame) -> pl.DataFrame:
    """Add `pts_allowed` per team row by joining opponent points for the same game."""
    opponent = df.select(["game_id", "team_id", "pts"]).rename(
        {"team_id": "opponent_team_id", "pts": "pts_allowed"}
    )
    return (
        df.join(opponent, on="game_id", how="left")
        .filter(pl.col("team_id") != pl.col("opponent_team_id"))
        .drop("opponent_team_id")
    )


def build_game_records(df: pl.DataFrame) -> pl.DataFrame:
    """Build a single-row-per-game DataFrame with home/away sides and results."""
    df = df.with_columns(
        pl.col("matchup")
        .str.split_exact(" ", 2)
        .struct.rename_fields(["_self_abbr", "_sep", "_opp_abbr"])
        .alias("_parsed")
    ).unnest("_parsed")

    df = df.with_columns(
        pl.when(pl.col("_sep") == "vs.")
        .then(pl.lit("home"))
        .otherwise(pl.lit("away"))
        .alias("location")
    ).drop(["_self_abbr", "_sep", "_opp_abbr"])

    rename_map = {
        col: f"home_{col}"
        for col in df.columns
        if col not in ("game_id", "game_date", "season_year")
    }
    home = df.filter(pl.col("location") == "home").rename(rename_map)

    rename_map_away = {
        col: f"away_{col}"
        for col in df.columns
        if col not in ("game_id", "game_date", "season_year")
    }
    away = df.filter(pl.col("location") == "away").rename(rename_map_away)

    games = home.join(away, on=["game_id", "game_date", "season_year"], how="inner")

    games = games.with_columns(
        (pl.col("home_pts") > pl.col("away_pts")).cast(pl.Int8).alias("home_win"),
        (pl.col("home_pts") + pl.col("away_pts")).alias("total_pts"),
        (pl.col("home_pts") - pl.col("away_pts")).alias("home_margin"),
    )

    keep = [
        "game_id",
        "game_date",
        "season_year",
        "home_team_id",
        "home_team_abbreviation",
        "home_pts",
        "away_team_id",
        "away_team_abbreviation",
        "away_pts",
        "home_margin",
        "total_pts",
        "home_win",
    ]
    return games.select(keep).sort("game_date", "game_id")


def _build_team_log(df: pl.DataFrame) -> pl.DataFrame:
    """Sort each team's game log chronologically and add days rest."""
    df = df.sort(["team_id", "game_date"])
    df = df.with_columns(
        (pl.col("game_date") - pl.col("game_date").shift(1).over("team_id"))
        .dt.total_days()
        .fill_null(7)
        .cast(pl.Int16)
        .alias("days_rest")
    )
    return df


def build_team_features(df: pl.DataFrame, windows: Iterable[int] = WINDOWS) -> pl.DataFrame:
    """Compute lagged rolling averages per team and per game.

    No target leakage: features are computed from games *before* the current game.
    Only rolling aggregates and `days_rest` are returned; raw per-game box-score
    columns are intentionally dropped to avoid target leakage.
    """
    df = _build_team_log(df)

    exprs: list[pl.Expr] = []
    rolling_cols: list[str] = []
    for col in ROLLING_COLS:
        for window in windows:
            exprs.append(
                pl.col(col)
                .shift(1)
                .rolling_mean(window_size=window, min_samples=1)
                .over("team_id")
                .alias(f"{col}_avg{window}")
            )
            rolling_cols.append(f"{col}_avg{window}")
    exprs.append(
        pl.col("pts")
        .shift(1)
        .rolling_std(window_size=10, min_samples=1)
        .over("team_id")
        .alias("pts_std10")
    )
    rolling_cols.append("pts_std10")

    df = df.with_columns(exprs)
    return df.select(["team_id", "game_id", "game_date", "season_year", "days_rest", *rolling_cols])


def build_training_data(
    df: pl.DataFrame,
    game_records: pl.DataFrame | None = None,
    team_features: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Join home and away team features onto each game record."""
    if game_records is None:
        game_records = build_game_records(df)
    if team_features is None:
        team_features = build_team_features(df)

    key_cols = {"game_id", "game_date", "season_year", "team_id"}
    home_features = team_features.rename({"team_id": "home_team_id"}).rename(
        {col: f"home_{col}" for col in team_features.columns if col not in key_cols}
    )
    away_features = team_features.rename({"team_id": "away_team_id"}).rename(
        {col: f"away_{col}" for col in team_features.columns if col not in key_cols}
    )

    data = game_records.join(
        home_features,
        on=["game_id", "game_date", "season_year", "home_team_id"],
        how="inner",
    ).join(
        away_features,
        on=["game_id", "game_date", "season_year", "away_team_id"],
        how="inner",
    )
    return data


def get_feature_columns(data: pl.DataFrame) -> list[str]:
    """Return numeric feature columns usable by a model."""
    excluded = {
        "game_id",
        "game_date",
        "season_year",
        "home_team_id",
        "home_team_abbreviation",
        "away_team_id",
        "away_team_abbreviation",
        "home_pts",
        "away_pts",
        "home_margin",
        "total_pts",
        "home_win",
    }
    cols = []
    for col, dtype in zip(data.columns, data.dtypes, strict=True):
        if col in excluded:
            continue
        if dtype.is_numeric():
            cols.append(col)
    return cols
