"""Explainability helpers: directional key factors derived from feature importances."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from ..config import settings


def _split_prefix(col: str) -> tuple[str, str]:
    """Return (prefix, base_name) for a feature like 'home_pts_avg10'."""
    if col.startswith("home_"):
        return ("home", col[5:])
    if col.startswith("away_"):
        return ("away", col[5:])
    return ("", col)


def build_direction_map(
    data: pl.DataFrame,
    feature_cols: list[str],
    target: str = "home_win",
) -> dict[str, float]:
    """Return Pearson correlation of each feature with the target."""
    correlations: dict[str, float] = {}
    y = data[target].to_numpy()
    for col in feature_cols:
        x = data[col].to_numpy()
        mask = ~(np.isnan(x) | np.isnan(y))
        if mask.sum() < 2:
            correlations[col] = 0.0
            continue
        corr = float(np.corrcoef(x[mask], y[mask])[0, 1])
        correlations[col] = corr if not np.isnan(corr) else 0.0
    return correlations


def load_or_build_direction_map(
    data: pl.DataFrame,
    feature_cols: list[str],
    path: Path | None = None,
) -> dict[str, float]:
    if path is None:
        path = settings.model_dir / "direction_map.json"
    if path.exists():
        with open(path) as fh:
            return json.load(fh)
    direction_map = build_direction_map(data, feature_cols)
    with open(path, "w") as fh:
        json.dump(direction_map, fh)
    return direction_map


def _base_importance(importance: dict[str, float]) -> dict[str, float]:
    """Aggregate home/away prefixed importances by the base metric name."""
    base: dict[str, float] = {}
    for col, imp in importance.items():
        _, base_name = _split_prefix(col)
        base[base_name] = base.get(base_name, 0.0) + imp
    return base


def top_key_factors(
    row: dict,
    feature_cols: list[str],
    importance: dict[str, float],
    direction_map: dict[str, float],
    selection_side: str,
    top_n: int = 5,
) -> list[dict]:
    """Return the top directional key factors for a single pick."""
    base_imp = _base_importance(importance)
    sorted_features = sorted(base_imp.items(), key=lambda kv: -kv[1])
    drivers: list[dict] = []

    for base_name, _ in sorted_features:
        if len(drivers) >= top_n:
            break
        home_key = f"home_{base_name}"
        away_key = f"away_{base_name}"
        if home_key not in row or away_key not in row:
            continue

        home_val = row[home_key]
        away_val = row[away_key]
        if home_val is None or away_val is None:
            continue

        corr = direction_map.get(home_key, 0.0)
        # Positive diff_for_home means the home team has more of this trait.
        # If the trait is positively correlated with home wins, that favors home.
        diff_for_home = home_val - away_val
        effective = diff_for_home * (1.0 if corr >= 0 else -1.0)
        if selection_side == "away":
            effective = -effective

        if abs(effective) < 1e-9:
            continue

        drivers.append(
            {
                "feature": base_name.replace("_", " ").replace("avg", " rolling ").strip(),
                "value": round(abs(float(diff_for_home)), 4),
                "direction": "up" if effective > 0 else "down",
            }
        )
    return drivers


def rationale_from_factors(selection: str, opponent: str, factors: list[dict]) -> str:
    if not factors:
        return f"Model sees no clear edge for {selection} over {opponent}."
    top = factors[0]
    direction = "favors" if top["direction"] == "up" else "opposes"
    return (
        f"Model gives {selection} the edge over {opponent}. "
        f"The strongest factor is '{top['feature']}' which {direction} the pick."
    )
