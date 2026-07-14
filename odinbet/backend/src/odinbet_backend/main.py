"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import health, picks
from .config import settings
from .data.nba import build_training_data, get_feature_columns, load_raw_games
from .data.odds import BaselineOddsProvider
from .models.predict import ModelService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load data, features, and model on startup."""
    app.state.data_dir = settings.data_dir
    app.state.model_dir = settings.model_dir

    raw = load_raw_games()
    data = build_training_data(raw)
    feature_cols = get_feature_columns(data)

    app.state.training_data = data
    app.state.feature_cols = feature_cols
    app.state.odds_provider = BaselineOddsProvider()
    app.state.model_service = ModelService()
    app.state.model_service.load()
    app.state.data_ready = True
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI-powered sports betting picker API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(picks.router, prefix="/picks", tags=["picks"])
