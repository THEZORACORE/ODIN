"""Command-line utilities for training and evaluation."""

from .config import settings
from .data.nba import build_training_data, get_feature_columns, load_raw_games
from .data.odds import BaselineOddsProvider
from .models.train import train_model


def train() -> None:
    """Train the ODINBET model and baseline odds provider."""
    print("Loading raw games...")
    raw = load_raw_games()
    print("Building game records and team features...")
    data = build_training_data(raw)
    feature_cols = get_feature_columns(data)
    print(f"Feature matrix: {len(data)} rows, {len(feature_cols)} features")

    print("Training baseline odds provider...")
    baseline = BaselineOddsProvider()
    baseline.fit(data, feature_cols)

    print("Training XGBoost model...")
    artifacts = train_model(data, feature_cols)
    print("Metrics:", artifacts["metrics"])
    print(f"Model saved to {settings.model_dir}")


def evaluate() -> None:
    """Print stored model metrics."""
    import json

    metrics_path = settings.model_dir / "metrics.json"
    with open(metrics_path) as fh:
        print(json.load(fh))


if __name__ == "__main__":
    import sys

    command = sys.argv[1] if len(sys.argv) > 1 else "train"
    if command == "train":
        train()
    elif command == "evaluate":
        evaluate()
    else:
        print(f"Unknown command: {command}")
