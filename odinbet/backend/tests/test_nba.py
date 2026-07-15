"""Tests for the NBA data pipeline."""

import polars as pl

from odinbet_backend.data.nba import build_game_records, build_team_features, get_feature_columns


def _make_team_log() -> pl.DataFrame:
    """Return a minimal team-game log for two teams over a few games."""
    rows = [
        # team A home vs B
        {
            "game_n": 1,
            "season_year": "2023-24",
            "team_id": 1,
            "team_abbreviation": "AAA",
            "game_id": "G1",
            "game_date": "2023-10-24",
            "matchup": "AAA vs. BBB",
            "wl": "W",
            "pts": 110.0,
            "pts_allowed": 100.0,
            "fg_pct": 0.5,
            "fg3_pct": 0.35,
            "ft_pct": 0.8,
            "oreb": 10.0,
            "dreb": 30.0,
            "reb": 40.0,
            "ast": 25.0,
            "tov": 12.0,
            "stl": 8.0,
            "blk": 5.0,
            "off_rating": 110.0,
            "def_rating": 105.0,
            "net_rating": 5.0,
            "pace": 100.0,
            "pie": 0.55,
            "efg_pct": 0.55,
            "ts_pct": 0.6,
            "ast_to": 2.0,
            "ast_ratio": 18.0,
            "tm_tov_pct": 12.0,
            "oreb_pct": 0.25,
            "dreb_pct": 0.75,
            "reb_pct": 0.5,
        },
        # team B away at A
        {
            "game_n": 1,
            "season_year": "2023-24",
            "team_id": 2,
            "team_abbreviation": "BBB",
            "game_id": "G1",
            "game_date": "2023-10-24",
            "matchup": "BBB @ AAA",
            "wl": "L",
            "pts": 100.0,
            "pts_allowed": 110.0,
            "fg_pct": 0.45,
            "fg3_pct": 0.3,
            "ft_pct": 0.75,
            "oreb": 8.0,
            "dreb": 28.0,
            "reb": 36.0,
            "ast": 22.0,
            "tov": 14.0,
            "stl": 7.0,
            "blk": 4.0,
            "off_rating": 105.0,
            "def_rating": 110.0,
            "net_rating": -5.0,
            "pace": 100.0,
            "pie": 0.45,
            "efg_pct": 0.5,
            "ts_pct": 0.55,
            "ast_to": 1.5,
            "ast_ratio": 16.0,
            "tm_tov_pct": 14.0,
            "oreb_pct": 0.25,
            "dreb_pct": 0.75,
            "reb_pct": 0.5,
        },
        # second game: A away at B
        {
            "game_n": 2,
            "season_year": "2023-24",
            "team_id": 1,
            "team_abbreviation": "AAA",
            "game_id": "G2",
            "game_date": "2023-10-26",
            "matchup": "AAA @ BBB",
            "wl": "L",
            "pts": 95.0,
            "pts_allowed": 105.0,
            "fg_pct": 0.4,
            "fg3_pct": 0.25,
            "ft_pct": 0.7,
            "oreb": 9.0,
            "dreb": 25.0,
            "reb": 34.0,
            "ast": 20.0,
            "tov": 15.0,
            "stl": 6.0,
            "blk": 3.0,
            "off_rating": 100.0,
            "def_rating": 112.0,
            "net_rating": -12.0,
            "pace": 98.0,
            "pie": 0.4,
            "efg_pct": 0.45,
            "ts_pct": 0.5,
            "ast_to": 1.3,
            "ast_ratio": 15.0,
            "tm_tov_pct": 15.0,
            "oreb_pct": 0.2,
            "dreb_pct": 0.7,
            "reb_pct": 0.45,
        },
        # second game: B home vs A
        {
            "game_n": 2,
            "season_year": "2023-24",
            "team_id": 2,
            "team_abbreviation": "BBB",
            "game_id": "G2",
            "game_date": "2023-10-26",
            "matchup": "BBB vs. AAA",
            "wl": "W",
            "pts": 105.0,
            "pts_allowed": 95.0,
            "fg_pct": 0.48,
            "fg3_pct": 0.38,
            "ft_pct": 0.78,
            "oreb": 12.0,
            "dreb": 32.0,
            "reb": 44.0,
            "ast": 26.0,
            "tov": 11.0,
            "stl": 9.0,
            "blk": 6.0,
            "off_rating": 112.0,
            "def_rating": 100.0,
            "net_rating": 12.0,
            "pace": 98.0,
            "pie": 0.6,
            "efg_pct": 0.58,
            "ts_pct": 0.62,
            "ast_to": 2.3,
            "ast_ratio": 19.0,
            "tm_tov_pct": 11.0,
            "oreb_pct": 0.3,
            "dreb_pct": 0.8,
            "reb_pct": 0.55,
        },
    ]
    return pl.DataFrame(rows).with_columns(
        pl.col("game_date").str.to_date(format="%Y-%m-%d").alias("game_date"),
        pl.col("pts").cast(pl.Float64),
        pl.col("team_id").cast(pl.Int64),
    )


def test_build_game_records() -> None:
    df = _make_team_log()
    games = build_game_records(df)
    assert len(games) == 2
    first = games.filter(pl.col("game_id") == "G1").to_dicts()[0]
    assert first["home_team_abbreviation"] == "AAA"
    assert first["away_team_abbreviation"] == "BBB"
    assert first["home_win"] == 1


def test_rolling_features_are_lagged() -> None:
    """Ensure rolling averages for game 2 use only game 1 stats."""
    df = _make_team_log()
    features = build_team_features(df)
    # For team AAA game 2, pts_avg5 should equal 110 (only previous game).
    row = features.filter((pl.col("team_id") == 1) & (pl.col("game_id") == "G2")).to_dicts()[0]
    assert row["pts_avg5"] == 110.0
    # For team BBB game 2, pts_allowed_avg5 should equal 110 (pts allowed in game 1).
    row_b = features.filter((pl.col("team_id") == 2) & (pl.col("game_id") == "G2")).to_dicts()[0]
    assert row_b["pts_allowed_avg5"] == 110.0


def test_feature_columns_exclude_non_numeric_and_ids() -> None:
    df = _make_team_log()
    games = build_game_records(df)
    features = build_team_features(df)
    # Join manually to create a training-like frame.
    key_cols = {"team_id", "game_id", "game_date", "season_year"}
    home_features = features.rename({"team_id": "home_team_id"}).rename(
        {c: f"home_{c}" for c in features.columns if c not in key_cols}
    )
    away_features = features.rename({"team_id": "away_team_id"}).rename(
        {c: f"away_{c}" for c in features.columns if c not in key_cols}
    )
    data = games.join(
        home_features,
        on=["game_id", "game_date", "season_year", "home_team_id"],
        how="inner",
    ).join(
        away_features,
        on=["game_id", "game_date", "season_year", "away_team_id"],
        how="inner",
    )
    cols = get_feature_columns(data)
    assert "home_win" not in cols
    assert "home_team_abbreviation" not in cols
    assert "home_pts" not in cols
    assert "home_pts_avg5" in cols
    assert "away_pts_avg5" in cols
