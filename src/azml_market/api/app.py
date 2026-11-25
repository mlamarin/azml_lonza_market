"""Prediction API serving models from the MLflow registry. All data are synthetic.

Run locally with: uv run uvicorn azml_market.api.app:app --reload
"""

from contextlib import asynccontextmanager

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Request

from azml_market.api.registry import ModelRegistry, UnknownModel
from azml_market.api.schemas import CalibrationResponse, ModelInfo, PredictRequest, PredictResponse
from azml_market.training.models import FEATURES
from azml_market.training.pipeline import CHAMPION


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.registry = ModelRegistry()
    yield


app = FastAPI(
    title="Clinical progression API (synthetic data)",
    description="Probability that a phase transition succeeds, from models in the MLflow registry. "
    "Trained on synthetic data: the probabilities say nothing about real clinical progression.",
    lifespan=lifespan,
)


NOT_FOUND = {404: {"description": "No model version or alias with that name"}}


def get_registry(request: Request) -> ModelRegistry:
    return request.app.state.registry


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/models", response_model=list[ModelInfo])
def list_models(registry: ModelRegistry = Depends(get_registry)) -> list[dict]:
    return registry.list_versions()


@app.post("/predict", response_model=PredictResponse, responses=NOT_FOUND)
def predict(
    body: PredictRequest, model: str = CHAMPION, registry: ModelRegistry = Depends(get_registry)
) -> dict:
    """model: an alias (default champion) or a version number."""
    try:
        version = registry.resolve(model)
    except UnknownModel as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    features = pd.DataFrame([t.model_dump() for t in body.transitions])[FEATURES]
    probabilities = registry.load(version).predict_proba(features)[:, 1]
    return {
        "model_version": version.version,
        "model_kind": registry.model_kind(version),
        "model_ref": model,
        "predictions": [{"p_progress": float(p)} for p in probabilities],
    }


@app.get("/models/{model}/calibration", response_model=CalibrationResponse, responses=NOT_FOUND)
def calibration(model: str, registry: ModelRegistry = Depends(get_registry)) -> dict:
    try:
        return registry.calibration(registry.resolve(model))
    except UnknownModel as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
