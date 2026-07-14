"""Pick generation endpoints."""

from datetime import date

import polars as pl
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


class PickRequest(BaseModel):
    sport: str = Field(default="nba", description="Sport/league key")
    game_date: date = Field(default_factory=date.today)
    min_ev: float = Field(default=0.0, ge=-0.5, le=1.0)
    min_confidence: float = Field(default=0.55, ge=0.0, le=1.0)
    max_picks: int = Field(default=20, ge=1, le=100)
    bankroll: float = Field(default=1000.0, gt=0)


class KeyFactor(BaseModel):
    feature: str
    value: float
    direction: str


class Pick(BaseModel):
    game_id: str
    matchup: str
    market: str
    selection: str
    model_probability: float
    decimal_odds: float
    ev: float
    recommended_units: float
    confidence: float
    rationale: str
    key_factors: list[KeyFactor]


class PickResponse(BaseModel):
    generated_at: str
    sport: str
    odds_source: str
    bankroll: float
    picks: list[Pick]
    warning: str | None = None


class LatestDateResponse(BaseModel):
    latest_date: str | None
    total_games: int


router = APIRouter()


@router.post("/", response_model=PickResponse)
async def get_picks(req: PickRequest, request: Request) -> PickResponse:
    """Return ranked +EV picks for a sport and date."""
    try:
        state = request.app.state
        if not getattr(state, "data_ready", False):
            raise HTTPException(status_code=503, detail="Service is still loading data.")

        game_date = req.game_date.isoformat()
        service = state.model_service
        data: pl.DataFrame = state.training_data
        feature_cols: list[str] = state.feature_cols
        odds_provider = state.odds_provider

        picks = service.build_picks(
            data=data,
            feature_cols=feature_cols,
            odds_provider=odds_provider,
            game_date=game_date,
            min_ev=req.min_ev,
            min_confidence=req.min_confidence,
            max_picks=req.max_picks,
            bankroll=req.bankroll,
        )

        warning = None
        if not picks:
            warning = (
                "No +EV picks met the filters for this date. "
                "The model abstains when the edge is too small or confidence is low."
            )

        return PickResponse(
            generated_at=game_date,
            sport=req.sport,
            odds_source="baseline synthetic",
            bankroll=req.bankroll,
            picks=picks,
            warning=warning,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/latest-date", response_model=LatestDateResponse)
async def get_latest_date(request: Request) -> LatestDateResponse:
    """Return the most recent date with a meaningful slate of games."""
    state = request.app.state
    if not getattr(state, "data_ready", False):
        raise HTTPException(status_code=503, detail="Service is still loading data.")

    data: pl.DataFrame = state.training_data
    if len(data) == 0:
        return LatestDateResponse(latest_date=None, total_games=0)

    # Pick the latest date that has at least 10 games (avoids off-season exhibitions).
    counts = data.group_by("game_date").agg(pl.len().alias("count")).sort(
        "game_date", descending=True
    )
    for row in counts.iter_rows(named=True):
        if row["count"] >= 10:
            return LatestDateResponse(
                latest_date=str(row["game_date"]),
                total_games=row["count"],
            )

    # Fallback to the absolute latest date if no date has enough games.
    latest = data["game_date"].max()
    if latest is None:
        return LatestDateResponse(latest_date=None, total_games=0)
    total = len(data.filter(pl.col("game_date") == latest))
    return LatestDateResponse(latest_date=str(latest), total_games=total)
