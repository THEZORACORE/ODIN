"""Health check endpoints."""

from fastapi import APIRouter, status

router = APIRouter()


@router.get("/")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def ready() -> dict[str, str]:
    return {"status": "ready"}
