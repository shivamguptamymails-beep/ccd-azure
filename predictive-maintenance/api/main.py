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
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from explain import make_explainer, readable_values, shap_for, transform_for_shap
from failure_modes import MODE_NAMES, predict_modes
from risk_levels import predict_risk

from api.cloud import PredictionLog, download_models
from api.schemas import (
    BatchPredictionRequest,
    BatchPredictionResponse,
    ExplanationResponse,
    FeatureContribution,
    HistoryResponse,
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
    TELEMETRY = True
    logger.info("Azure Monitor OpenTelemetry instrumentation enabled")
else:
    TELEMETRY = False

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "models"))
RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", "results"))
MODEL_VERSION = os.environ.get("MODEL_VERSION", "dev")

_state: dict = {}


def _resolve_model_dir() -> tuple[Path, str]:
    """Prefer the Blob Storage registry; fall back to the models baked into the image."""
    blob_dir = Path("/tmp/models") / MODEL_VERSION
    try:
        if download_models(MODEL_VERSION, blob_dir):
            return blob_dir, "blob"
    except Exception:
        logger.exception("Model download failed; using models baked into the image")
    return MODEL_DIR, "image"


def _load_models() -> None:
    model_dir, source = _resolve_model_dir()
    _state["final"] = joblib.load(model_dir / "final_model.joblib")
    _state["thresholds"] = json.loads((model_dir / "risk_thresholds.json").read_text())
    _state["modes"] = joblib.load(model_dir / "failure_mode_models.joblib")
    _state["rf"] = joblib.load(model_dir / "random_forest.joblib")
    _state["explainer"] = make_explainer(_state["rf"])
    _state["model_dir"], _state["model_source"] = model_dir, source
    _state["log"] = PredictionLog()
    logger.info("Loaded models from %s (version=%s, source=%s)", model_dir, MODEL_VERSION, source)


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


# FastAPI was imported above before configure_azure_monitor() could patch the
# class, so instrument this app explicitly or incoming requests never reach
# Application Insights' requests table.
if TELEMETRY:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready")


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


def _log_records(results: list[PredictionResult], readings: list[MachineReading],
                 endpoint: str) -> list[dict]:
    return [
        {**result.model_dump(exclude={"failure_mode_probabilities", "priority_rank"}),
         "inputs": reading.to_raw_row(), "endpoint": endpoint, "model_version": MODEL_VERSION}
        for result, reading in zip(results, readings)
    ]


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
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


# Probe endpoints are async so they answer from the event loop: sync handlers
# (the CPU-heavy scoring below) run in a thread pool, and under load a probe
# queued behind them would time out and get a healthy replica restarted.
@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok"}


@app.get("/ready", tags=["ops"])
async def ready():
    if "final" not in _state:
        raise HTTPException(status_code=503, detail="Models not loaded")
    return {"status": "ready", "model_version": MODEL_VERSION,
            "model_source": _state["model_source"],
            "prediction_logging": _state["log"].enabled}


@app.get("/model/metadata", response_model=ModelMetadata, tags=["ops"])
def model_metadata():
    comparison_path = _state["model_dir"] / "model_comparison.csv"
    if not comparison_path.exists():
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
        model_version=MODEL_VERSION,
        model_source=_state["model_source"],
    )


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------
@app.post("/predict", response_model=PredictionResult, tags=["inference"])
def predict(reading: MachineReading, background: BackgroundTasks):
    df = _rows_to_frame([reading])
    ranked, mode_probs = _score(df)
    idx = ranked.index[0]
    result = _to_result(reading.machine_id or "M-0001", ranked.loc[idx], mode_probs.loc[idx])
    background.add_task(_state["log"].write, _log_records([result], [reading], "predict"))
    return result


@app.post("/predict/batch", response_model=BatchPredictionResponse, tags=["inference"])
def predict_batch(request: BatchPredictionRequest, background: BackgroundTasks,
                  log: bool = Query(True, description="Write results to the prediction log")):
    if not request.readings:
        raise HTTPException(status_code=400, detail="readings must not be empty")
    df = _rows_to_frame(request.readings)
    ranked, mode_probs = _score(df)
    ids = [r.machine_id or f"M-{i + 1:04d}" for i, r in enumerate(request.readings)]
    results = [
        _to_result(ids[idx], ranked.loc[idx], mode_probs.loc[idx])
        for idx in ranked.index
    ]
    if log:
        background.add_task(_state["log"].write, _log_records(
            results, [request.readings[idx] for idx in ranked.index], "predict/batch"))
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


@app.get("/history", response_model=HistoryResponse, tags=["history"])
def history(limit: int = Query(200, ge=1, le=1000), machine_id: str | None = None,
            risk_level: str | None = None):
    """Most recent logged predictions from Cosmos DB, newest first."""
    log = _state["log"]
    return HistoryResponse(enabled=log.enabled,
                           records=log.recent(limit, machine_id, risk_level))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal error"})
