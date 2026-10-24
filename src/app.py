"""
Project: Telecom Tower Failure Prediction Service
Group: Group 3 (Nishant & Bitu)
Course: Elective II: Machine Learning Operations (MLOps)
Faculty: Dr. Santosh Kumar

Module: app.py
Purpose: Production FastAPI prediction service (Task 3 & 5)
Endpoints:
  - POST /predict       : Single tower or batch telemetry prediction
  - POST /predict/batch : Explicit multi-tower batch prediction
  - GET  /health        : Health check endpoint (model status, uptime)
  - GET  /version       : Model version, metadata, feature contract
  - GET  /metrics       : Prometheus scraping endpoint with custom instrumentation

Acceptance Criteria Enforced:
1. Loads model exactly ONCE at startup (via lifespan context manager).
2. Never crashes on invalid/malformed input; returns HTTP 422 with clear diagnostics.
3. Full Prometheus metrics: request counter, latency histogram (p50, p95, p99),
   failure prediction share gauge/counter, error counter.
"""

import time
import os
import joblib
import pandas as pd
from typing import Union, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

from src.schemas import (
    TowerTelemetryInput,
    BatchTelemetryInput,
    TowerPredictionOutput,
    BatchPredictionOutput,
    HealthResponse,
    VersionResponse,
)

# -------------------------------------------------------------
# Prometheus Metrics Instrumentation (Task 5)
# -------------------------------------------------------------
REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests received by endpoint and status code",
    ["method", "endpoint", "status"],
)

REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency distribution in seconds",
    ["endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

PREDICTIONS_TOTAL = Counter(
    "tower_predictions_total",
    "Total individual tower failure predictions generated",
    ["prediction_class"],  # 'failure' (1) or 'normal' (0)
)

FAILURE_PREDICTION_RATIO = Gauge(
    "tower_failure_prediction_ratio",
    "Rolling window or instantaneous share of towers predicted to fail",
)

MODEL_UPTIME_SECONDS = Gauge(
    "service_uptime_seconds",
    "Total elapsed seconds since the service started",
)

# -------------------------------------------------------------
# Global Application State
# -------------------------------------------------------------
MODEL_STATE = {
    "bundle": None,
    "model": None,
    "transformer": None,
    "threshold": 0.5,
    "version": "unknown",
    "features": [],
    "start_time": time.time(),
    "total_predictions": 0,
    "total_failures": 0,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: Loads the model once into memory.
    Shutdown: Gracefully cleans up resources.
    """
    model_path = os.getenv("MODEL_PATH", "artifacts/model_v1.0.0.joblib")
    print(f"[*] Initializing service. Loading model artifact from '{model_path}'...")
    if not os.path.exists(model_path):
        raise RuntimeError(f"Fatal: Model artifact '{model_path}' not found!")

    bundle = joblib.load(model_path)
    MODEL_STATE["bundle"] = bundle
    MODEL_STATE["model"] = bundle["model"]
    MODEL_STATE["transformer"] = bundle["transformer"]
    MODEL_STATE["threshold"] = bundle.get("threshold", 0.5)
    MODEL_STATE["version"] = bundle.get("version", "v1.0.0")
    MODEL_STATE["features"] = bundle.get("feature_names", [])
    MODEL_STATE["start_time"] = time.time()
    print(f"[+] Model '{MODEL_STATE['version']}' successfully loaded at startup.")
    yield
    print("[*] Service shutting down.")


app = FastAPI(
    title="Telecom Tower Failure Prediction Service",
    description="Production-grade MLOps prediction service with Prometheus observability.",
    version="1.0.0",
    lifespan=lifespan,
)


# -------------------------------------------------------------
# Middleware for Request Timing & Global Error Handling
# -------------------------------------------------------------
@app.middleware("http")
async def prometheus_metrics_middleware(request: Request, call_next):
    start_time = time.time()
    endpoint = request.url.path
    # Normalize paths for Prometheus metric cardinality
    metric_endpoint = endpoint if endpoint in ["/predict", "/predict/batch", "/health", "/version", "/metrics"] else "other"

    try:
        response = await call_next(request)
        status_code = str(response.status_code)
    except Exception as exc:
        status_code = "500"
        REQUESTS_TOTAL.labels(method=request.method, endpoint=metric_endpoint, status=status_code).inc()
        raise exc

    duration = time.time() - start_time
    REQUEST_DURATION_SECONDS.labels(endpoint=metric_endpoint).observe(duration)
    REQUESTS_TOTAL.labels(method=request.method, endpoint=metric_endpoint, status=status_code).inc()
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Task 3 Acceptance Criterion: Clear error responses for invalid inputs, never crashes.
    """
    error_details = []
    for err in exc.errors():
        field = ".".join(str(loc) for loc in err.get("loc", []))
        msg = err.get("msg", "Invalid value")
        error_details.append({"field": field, "message": msg})

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY if hasattr(status, "HTTP_422_UNPROCESSABLE_ENTITY") else 422,
        content={
            "error": "InputValidationFailed",
            "message": "Telemetry readings violate domain contract boundaries.",
            "details": error_details,
        },
    )


# -------------------------------------------------------------
# Core Prediction Logic
# -------------------------------------------------------------
def _score_records(records: List[TowerTelemetryInput]) -> List[TowerPredictionOutput]:
    """Helper that transforms raw inputs and executes model scoring."""
    if MODEL_STATE["model"] is None or MODEL_STATE["transformer"] is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model is not loaded or service is initializing.",
        )

    # Convert Pydantic records into DataFrame
    raw_dicts = [r.model_dump() for r in records]
    df_raw = pd.DataFrame(raw_dicts)

    # Run through the identical shared feature engineering pipeline
    transformer = MODEL_STATE["transformer"]
    model = MODEL_STATE["model"]
    threshold = MODEL_STATE["threshold"]
    version = MODEL_STATE["version"]

    df_transformed = transformer.transform(df_raw)
    probs = model.predict_proba(df_transformed)[:, 1]

    results = []
    for idx, r in enumerate(records):
        prob = float(probs[idx])
        pred_class = int(prob >= threshold)

        # Risk categorization for field dispatch
        if prob >= 0.70:
            risk = "CRITICAL"
        elif prob >= threshold:
            risk = "HIGH"
        elif prob >= 0.30:
            risk = "MODERATE"
        else:
            risk = "LOW"

        # Update metrics
        if pred_class == 1:
            PREDICTIONS_TOTAL.labels(prediction_class="failure").inc()
            MODEL_STATE["total_failures"] += 1
        else:
            PREDICTIONS_TOTAL.labels(prediction_class="normal").inc()

        MODEL_STATE["total_predictions"] += 1

        results.append(
            TowerPredictionOutput(
                Tower_ID=r.Tower_ID,
                failure_probability=round(prob, 4),
                predicted_failure_48h=pred_class,
                risk_level=risk,
                model_version=version,
            )
        )

    # Update gauge
    if MODEL_STATE["total_predictions"] > 0:
        ratio = MODEL_STATE["total_failures"] / MODEL_STATE["total_predictions"]
        FAILURE_PREDICTION_RATIO.set(round(ratio, 4))

    return results


# -------------------------------------------------------------
# API Endpoints & Operations Console
# -------------------------------------------------------------
@app.get("/", include_in_schema=False)
def serve_console():
    """Serves the interactive live operations console for Group 3 (Nishant & Bitu)."""
    index_file = os.path.join(os.path.dirname(__file__), "..", "static", "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Telecom Tower Prediction Service Online. Visit /docs or /metrics"}


@app.post("/predict", response_model=Union[TowerPredictionOutput, BatchPredictionOutput])
def predict(payload: Union[TowerTelemetryInput, BatchTelemetryInput, List[TowerTelemetryInput]]):
    """
    Single or batch prediction endpoint. Accepts:
    - A single TowerTelemetryInput object
    - A BatchTelemetryInput object (with 'towers' key)
    - A raw JSON list of TowerTelemetryInput objects
    """
    if isinstance(payload, TowerTelemetryInput):
        scored = _score_records([payload])
        return scored[0]
    elif isinstance(payload, BatchTelemetryInput):
        scored = _score_records(payload.towers)
        fail_count = sum(1 for p in scored if p.predicted_failure_48h == 1)
        return BatchPredictionOutput(
            count=len(scored),
            failures_predicted=fail_count,
            predictions=scored,
        )
    elif isinstance(payload, list):
        scored = _score_records(payload)
        fail_count = sum(1 for p in scored if p.predicted_failure_48h == 1)
        return BatchPredictionOutput(
            count=len(scored),
            failures_predicted=fail_count,
            predictions=scored,
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported payload structure.")


@app.post("/predict/batch", response_model=BatchPredictionOutput)
def predict_batch(payload: BatchTelemetryInput):
    """Explicit batch prediction endpoint accepting {'towers': [...]}."""
    scored = _score_records(payload.towers)
    fail_count = sum(1 for p in scored if p.predicted_failure_48h == 1)
    return BatchPredictionOutput(
        count=len(scored),
        failures_predicted=fail_count,
        predictions=scored,
    )


@app.get("/health", response_model=HealthResponse)
def health():
    """Service health inspection endpoint (Task 3 & 7)."""
    uptime = time.time() - MODEL_STATE["start_time"]
    MODEL_UPTIME_SECONDS.set(uptime)
    is_ready = MODEL_STATE["model"] is not None
    return HealthResponse(
        status="healthy" if is_ready else "degraded",
        model_loaded=is_ready,
        version=MODEL_STATE["version"],
        uptime_seconds=round(uptime, 2),
    )


@app.get("/version", response_model=VersionResponse)
def version():
    """Model version and serving configuration metadata (Task 3)."""
    return VersionResponse(
        service_name="telecom-tower-failure-service",
        model_version=MODEL_STATE["version"],
        algorithm="HistGradientBoostingClassifier",
        features=MODEL_STATE["features"],
        threshold=MODEL_STATE["threshold"],
    )


@app.get("/metrics")
def metrics():
    """Prometheus exposition format metrics scraping endpoint (Task 5)."""
    uptime = time.time() - MODEL_STATE["start_time"]
    MODEL_UPTIME_SECONDS.set(uptime)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
