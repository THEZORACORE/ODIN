"""Integration tests for FastAPI endpoints."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from odinbet_backend.config import settings
from odinbet_backend.main import app


def _required_data_exists() -> bool:
    return (
        Path(settings.data_dir / "gamelogs.parquet").exists()
        and Path(settings.model_dir / "model_v1.pkl").exists()
    )


@pytest.mark.skipif(not _required_data_exists(), reason="trained model/data not available")
def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.skipif(not _required_data_exists(), reason="trained model/data not available")
def test_picks_latest_date() -> None:
    with TestClient(app) as client:
        response = client.get("/picks/latest-date")
    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_date"] is not None
    assert payload["total_games"] >= 0


@pytest.mark.skipif(not _required_data_exists(), reason="trained model/data not available")
def test_get_picks() -> None:
    with TestClient(app) as client:
        latest = client.get("/picks/latest-date").json()
        response = client.post(
            "/picks/",
            json={
                "sport": "nba",
                "game_date": latest["latest_date"],
                "min_ev": 0.0,
                "min_confidence": 0.5,
                "max_picks": 20,
                "bankroll": 1000.0,
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["sport"] == "nba"
    assert isinstance(payload["picks"], list)
    if payload["picks"]:
        first = payload["picks"][0]
        assert "matchup" in first
        assert "ev" in first
        assert "recommended_units" in first
