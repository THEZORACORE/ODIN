# ODINBET MVP

AI-powered, explainable NBA moneyline picker. Research and advisory only — no real-money wagering is handled.

## Quick start

### Backend

```bash
cd odinbet/backend
python -m venv .venv  # or uv venv
source .venv/bin/activate
uv sync  # or pip install -e .
python -m odinbet_backend.cli train
uvicorn odinbet_backend.main:app --reload --port 8000
```

The backend downloads the public `llimllib/nba_data` gamelogs parquet on first load if `data/gamelogs.parquet` is missing, then trains and caches `data/models/model_v1.pkl`.

### Frontend

```bash
cd odinbet/frontend
npm install
npm run dev
```

Open <http://localhost:3000>.

## Architecture

- **Data pipeline** (`src/odinbet_backend/data/nba.py`): loads team box-score logs, builds lagged rolling home/away features with no target leakage.
- **Odds provider** (`src/odinbet_backend/data/odds.py`): pluggable abstraction. `BaselineOddsProvider` supplies synthetic market lines from a logistic regression; can be swapped for The-Odds-API or FiveThirtyEight providers.
- **Model** (`src/odinbet_backend/models/train.py`): chronological train/calibration/test split, XGBoost, isotonic calibration, median imputation.
- **Picks** (`src/odinbet_backend/models/predict.py`): ranked by expected value, sized with fractional Kelly, capped at 2% per pick and 5% daily exposure.
- **Explainability** (`src/odinbet_backend/models/explain.py`): directional key factors comparing home vs away rolling stats.
- **API** (`src/odinbet_backend/api/picks.py`): `/picks/` and `/picks/latest-date` endpoints.
- **Frontend** (`src/components/Dashboard.tsx`, `PickCard.tsx`): pick list, filters, bankroll widget, responsible-gambling banner.

## Running tests

```bash
cd odinbet/backend
source .venv/bin/activate
ruff check src tests
mypy src
pytest tests -q

cd ../frontend
npm run lint
npm run build
```

## Notes

- Odds are synthetic because no live odds API key is configured.
- The platform abstains when the model sees no +EV edge.
