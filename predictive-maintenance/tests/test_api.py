"""Smoke tests for the FastAPI inference service.

Run:  pytest tests/test_api.py
These are also the unit-test gate the CI/CD pipeline runs before building
the Docker image (see .github/workflows/ci-cd.yml).
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app

SAMPLE_READING = {
    "machine_id": "TEST-0001",
    "Type": "M",
    "Air temperature [K]": 300.5,
    "Process temperature [K]": 310.2,
    "Rotational speed [rpm]": 1500,
    "Torque [Nm]": 42.0,
    "Tool wear [min]": 120,
}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready(client):
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_model_metadata(client):
    resp = client.get("/model/metadata")
    assert resp.status_code == 200
    body = resp.json()
    assert "thresholds" in body
    assert "t_risk" in body["thresholds"] and "t_critical" in body["thresholds"]


def test_predict_single(client):
    resp = client.post("/predict", json=SAMPLE_READING)
    assert resp.status_code == 200
    body = resp.json()
    assert body["machine_id"] == "TEST-0001"
    assert 0.0 <= body["failure_probability"] <= 1.0
    assert body["risk_level"] in {"Healthy", "At Risk", "Critical"}
    assert len(body["failure_mode_probabilities"]) == 5


def test_predict_rejects_bad_input(client):
    bad = dict(SAMPLE_READING)
    bad["Type"] = "X"  # not one of L/M/H
    resp = client.post("/predict", json=bad)
    assert resp.status_code == 422


def test_predict_batch_sorted_by_priority(client):
    rows = [SAMPLE_READING, {**SAMPLE_READING, "machine_id": "TEST-0002", "Tool wear [min]": 250,
                              "Torque [Nm]": 75}]
    resp = client.post("/predict/batch", json={"readings": rows})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 2
    ranks = [r["priority_rank"] for r in results]
    assert ranks == sorted(ranks)


def test_explain_returns_contributions(client):
    resp = client.post("/explain", json=SAMPLE_READING)
    assert resp.status_code == 200
    contributions = resp.json()["contributions"]
    assert len(contributions) > 0
    assert all({"feature", "value", "contribution", "effect"} <= c.keys() for c in contributions)


def test_predict_matches_dashboard_scoring(client):
    """The API must score a known test-set row identically to risk_levels.predict_risk."""
    test_df = pd.read_csv("data/test.csv")
    row = test_df.iloc[0]
    payload = {
        "Type": str(row["Type"]),
        "Air temperature [K]": float(row["Air temperature [K]"]),
        "Process temperature [K]": float(row["Process temperature [K]"]),
        "Rotational speed [rpm]": float(row["Rotational speed [rpm]"]),
        "Torque [Nm]": float(row["Torque [Nm]"]),
        "Tool wear [min]": float(row["Tool wear [min]"]),
    }
    resp = client.post("/predict", json=payload)
    assert resp.status_code == 200
