"""Backtest and model-performance endpoints."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..models.backtest import run_backtest


class BacktestResponse(BaseModel):
    n_games: int
    roi: float
    profit: float
    wagered: float
    final_bankroll: float
    bankroll_return: float
    wins: int
    losses: int
    pushes: int


class MetricsResponse(BaseModel):
    metrics: dict
    top_features: list[dict]


router = APIRouter()


@router.get("/", response_model=BacktestResponse)
async def get_backtest(request: Request) -> BacktestResponse:
    """Run a backtest on the chronological held-out test set."""
    state = request.app.state
    if not getattr(state, "data_ready", False):
        raise HTTPException(status_code=503, detail="Service is still loading data.")

    try:
        result = run_backtest(
            data=state.training_data,
            feature_cols=state.feature_cols,
            model_service=state.model_service,
            odds_provider=state.odds_provider,
            bankroll=1000.0,
        )
        return BacktestResponse(**result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/metrics/", response_model=MetricsResponse)
async def get_metrics(request: Request) -> MetricsResponse:
    """Return the last trained model's test metrics and top features."""
    state = request.app.state
    if not getattr(state, "data_ready", False):
        raise HTTPException(status_code=503, detail="Service is still loading data.")

    model_dir: Path = state.model_dir
    metrics_path = model_dir / "metrics.json"
    if not metrics_path.exists():
        raise HTTPException(status_code=503, detail="Model metrics not available.")

    with open(metrics_path) as fh:
        metrics = json.load(fh)

    artifacts = state.model_service.load()
    importance = artifacts.get("importance", {})
    top_features = sorted(
        ({"feature": k, "importance": v} for k, v in importance.items()),
        key=lambda x: -x["importance"],
    )[:20]

    return MetricsResponse(metrics=metrics, top_features=top_features)
