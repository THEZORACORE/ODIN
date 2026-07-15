"""Model training, calibration, and persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import polars as pl
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.impute import SimpleImputer
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import train_test_split

from ..config import settings
from .explain import build_direction_map


def expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """Compute expected calibration error (ECE) for binary probabilities."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = (y_prob >= bins[i]) & (y_prob < bins[i + 1])
        if i == n_bins - 1:
            mask = (y_prob >= bins[i]) & (y_prob <= bins[i + 1])
        if mask.sum() == 0:
            continue
        bin_acc = y_true[mask].mean()
        bin_conf = y_prob[mask].mean()
        ece += mask.sum() * abs(bin_acc - bin_conf)
    return ece / len(y_true)


def chronological_data_split(
    data: pl.DataFrame,
    train_frac: float = 0.6,
    calibration_frac: float = 0.2,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Return chronological train / calibration / test DataFrames."""
    data = data.sort("game_date", "game_id")
    n = len(data)
    train_end = int(n * train_frac)
    calib_end = int(n * (train_frac + calibration_frac))
    return data[:train_end], data[train_end:calib_end], data[calib_end:]


def _arrays_from_frame(
    data: pl.DataFrame, feature_cols: list[str], target_col: str
) -> tuple[np.ndarray, np.ndarray]:
    X = data.select(feature_cols).to_numpy()
    y = data[target_col].to_numpy().ravel()
    return X, y


def train_model(
    data: pl.DataFrame,
    feature_cols: list[str],
    target_col: str = "home_win",
    model_dir: Path | None = None,
    split: tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame] | None = None,
) -> dict[str, Any]:
    """Train an XGBoost classifier, calibrate it, and persist artifacts."""
    if model_dir is None:
        model_dir = settings.model_dir
    model_dir.mkdir(parents=True, exist_ok=True)

    if split is None:
        train_df, calib_df, test_df = chronological_data_split(data)
    else:
        train_df, calib_df, test_df = split

    X_train, y_train = _arrays_from_frame(train_df, feature_cols, target_col)
    X_calib, y_calib = _arrays_from_frame(calib_df, feature_cols, target_col)
    X_test, y_test = _arrays_from_frame(test_df, feature_cols, target_col)

    imputer = SimpleImputer(strategy="median")
    X_train = imputer.fit_transform(X_train)
    X_calib = imputer.transform(X_calib)
    X_test = imputer.transform(X_test)

    # Split a small validation set from the end of the training period for early stopping.
    X_tr, X_val, y_tr, y_val = train_test_split(
        X_train, y_train, test_size=0.15, shuffle=False
    )

    base = xgb.XGBClassifier(
        n_estimators=400,
        learning_rate=0.05,
        max_depth=5,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        early_stopping_rounds=20,
        random_state=42,
        n_jobs=-1,
    )

    base.fit(
        X_tr,
        y_tr,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )

    calibrated = CalibratedClassifierCV(base, method="isotonic", cv="prefit")
    calibrated.fit(X_calib, y_calib)

    y_proba = calibrated.predict_proba(X_test)[:, 1]

    metrics = {
        "log_loss": float(log_loss(y_test, y_proba)),
        "brier_score": float(brier_score_loss(y_test, y_proba)),
        "roc_auc": float(roc_auc_score(y_test, y_proba)),
        "ece": float(expected_calibration_error(y_test, y_proba)),
        "accuracy": float(np.mean((y_proba >= 0.5).astype(int) == y_test)),
    }

    # Feature importance from the base XGBoost model.
    importance = {
        feature_cols[i]: float(base.feature_importances_[i])
        for i in range(len(feature_cols))
        if base.feature_importances_[i] > 0
    }

    direction_map = build_direction_map(train_df, feature_cols)

    artifacts = {
        "model": calibrated,
        "base_estimator": base,
        "imputer": imputer,
        "feature_cols": feature_cols,
        "metrics": metrics,
        "importance": importance,
        "direction_map": direction_map,
    }

    joblib.dump(artifacts, model_dir / "model_v1.pkl")
    with open(model_dir / "metrics.json", "w") as fh:
        json.dump(metrics, fh, indent=2)
    with open(model_dir / "features.json", "w") as fh:
        json.dump(feature_cols, fh, indent=2)
    with open(model_dir / "direction_map.json", "w") as fh:
        json.dump(direction_map, fh, indent=2)

    return artifacts
