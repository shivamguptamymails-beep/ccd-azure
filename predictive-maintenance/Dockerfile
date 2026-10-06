# Serving image for the Predictive Maintenance Intelligence API.
# Training-only files (data/, notebooks-style scripts' raw CSVs, EDA output)
# are deliberately left out - see .dockerignore - to keep the image small
# and the attack surface (and Container Registry storage cost) minimal.

FROM python:3.12-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/tmp/matplotlib

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Model code the saved .joblib pipelines need to import (FeatureEngineer,
# make_pipeline, SHAP helpers) plus the API package itself.
COPY preprocessing_pipeline.py risk_levels.py failure_modes.py explain.py train_models.py ./
COPY api ./api
COPY models ./models
COPY results/model_comparison.csv results/failure_mode_results.csv ./results/

# Non-root runtime user.
RUN useradd --no-create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl --fail http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
