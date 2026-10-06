"""
FastAPI inference service for the Predictive Maintenance Intelligence System.

Wraps the models trained by risk_levels.py / failure_modes.py / explain.py in a
stateless REST API, so the system can be containerized and horizontally
auto-scaled (Azure Container Apps + KEDA) independently of the Streamlit
exploration dashboard in app.py.

Run locally:  uvicorn api.main:app --reload
"""

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from explain import make_explainer, readable_values, shap_for, transform_for_shap
from failure_modes import MODE_NAMES, predict_modes
from risk_levels import predict_risk

from api.schemas import (
    BatchPredictionRequest,
    BatchPredictionResponse,
    ExplanationResponse,
    FeatureContribution,
    MachineReading,
    ModelMetadata,
    PredictionResult,
    RAW_COLUMNS,
)

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("predictive_maintenance_api")

# Auto-instruments FastAPI/requests/logging and ships traces, metrics and logs
# to the Application Insights resource provisioned in infra/modules/monitoring.
# A no-op when the connection string isn't set (e.g. local dev).
if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(logger_name="predictive_maintenance_api")
    logger.info("Azure Monitor OpenTelemetry instrumentation enabled")

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "models"))
RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", "results"))
MODEL_VERSION = os.environ.get("MODEL_VERSION", "dev")

_state: dict = {}


def _load_models() -> None:
    _state["final"] = joblib.load(MODEL_DIR / "final_model.joblib")
    _state["thresholds"] = json.loads((MODEL_DIR / "risk_thresholds.json").read_text())
    _state["modes"] = joblib.load(MODEL_DIR / "failure_mode_models.joblib")
    _state["rf"] = joblib.load(MODEL_DIR / "random_forest.joblib")
    _state["explainer"] = make_explainer(_state["rf"])
    logger.info("Loaded models from %s (version=%s)", MODEL_DIR, MODEL_VERSION)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_models()
    yield
    _state.clear()


app = FastAPI(
    title="Predictive Maintenance Intelligence API",
    description=(
        "Failure-risk scoring, likely-cause and SHAP explanations for the "
        "AI4I 2020 predictive-maintenance models."
    ),
    version=MODEL_VERSION,
    lifespan=lifespan,
)


@app.middleware("http")
async def add_latency_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - start) * 1000:.1f}"
    return response


def _rows_to_frame(readings: list[MachineReading]) -> pd.DataFrame:
    return pd.DataFrame([r.to_raw_row() for r in readings], columns=RAW_COLUMNS)


def _score(df: pd.DataFrame):
    """Shared scoring logic used by /predict, /predict/batch."""
    ranked = predict_risk(df, _state["final"], _state["thresholds"])
    mode_probs = predict_modes(_state["modes"], ranked[RAW_COLUMNS])
    ranked = ranked.copy()
    ranked["likely_cause"] = mode_probs.idxmax(axis=1).map(MODE_NAMES)
    ranked.loc[ranked["risk_level"] == "Healthy", "likely_cause"] = "-"
    return ranked, mode_probs


def _to_result(machine_id: str, row: pd.Series, mode_row: pd.Series) -> PredictionResult:
    return PredictionResult(
        machine_id=machine_id,
        priority_rank=int(row["priority_rank"]),
        failure_probability=float(row["failure_probability"]),
        risk_level=row["risk_level"],
        recommendation=row["recommendation"],
        likely_cause=row["likely_cause"],
        failure_mode_probabilities={MODE_NAMES[k]: float(v) for k, v in mode_row.items()},
    )


# ---------------------------------------------------------------------------
# Health / readiness (used by Container Apps probes and the load balancer)
# ---------------------------------------------------------------------------
@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["ops"])
def ready():
    if "final" not in _state:
        raise HTTPException(status_code=503, detail="Models not loaded")
    return {"status": "ready", "model_version": MODEL_VERSION}


@app.get("/model/metadata", response_model=ModelMetadata, tags=["ops"])
def model_metadata():
    comparison_path = RESULTS_DIR / "model_comparison.csv"
    comparison = (
        pd.read_csv(comparison_path).round(4).to_dict(orient="records")
        if comparison_path.exists() else []
    )
    return ModelMetadata(
        final_model="Calibrated Random Forest (isotonic calibration)",
        thresholds=_state["thresholds"],
        raw_input_columns=RAW_COLUMNS,
        model_comparison=comparison,
    )


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------
@app.post("/predict", response_model=PredictionResult, tags=["inference"])
def predict(reading: MachineReading):
    df = _rows_to_frame([reading])
    ranked, mode_probs = _score(df)
    idx = ranked.index[0]
    return _to_result(reading.machine_id or "M-0001", ranked.loc[idx], mode_probs.loc[idx])


@app.post("/predict/batch", response_model=BatchPredictionResponse, tags=["inference"])
def predict_batch(request: BatchPredictionRequest):
    if not request.readings:
        raise HTTPException(status_code=400, detail="readings must not be empty")
    df = _rows_to_frame(request.readings)
    ranked, mode_probs = _score(df)
    ids = [r.machine_id or f"M-{i + 1:04d}" for i, r in enumerate(request.readings)]
    results = [
        _to_result(ids[idx], ranked.loc[idx], mode_probs.loc[idx])
        for idx in ranked.index
    ]
    return BatchPredictionResponse(results=results)


@app.post("/explain", response_model=ExplanationResponse, tags=["inference"])
def explain(reading: MachineReading):
    df = _rows_to_frame([reading])
    rf = _state["rf"]
    Xt = transform_for_shap(rf, df)
    sv = shap_for(_state["explainer"], Xt)
    values = readable_values(rf, df, Xt.columns).iloc[0]

    contributions = [
        FeatureContribution(
            feature=feature,
            value=float(values[feature]),
            contribution=float(sv.values[0][i]),
            effect="Raises risk" if sv.values[0][i] > 0 else "Lowers risk",
        )
        for i, feature in enumerate(Xt.columns)
    ]
    contributions.sort(key=lambda c: abs(c.contribution), reverse=True)
    return ExplanationResponse(machine_id=reading.machine_id or "M-0001", contributions=contributions)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal error"})
