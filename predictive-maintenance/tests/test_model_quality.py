"""Model-validation gate for the CI/CD pipeline.

This is the automated check the synopsis refers to as "validates model
accuracy against a held-out test set" before a new model/image is allowed to
deploy. If a retrained model regresses below these floors, CI fails and the
Terraform-driven deployment step never runs.

Thresholds are set comfortably below the documented baseline (precision
0.93, recall 0.82, F1 0.88 on the 2,000-machine test set; see README.md) so
normal retraining noise does not block releases, while a real regression
still gets caught.

Run:  pytest tests/test_model_quality.py
"""

import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score

from preprocessing_pipeline import TARGET
from risk_levels import predict_risk

MIN_PRECISION = 0.80
MIN_RECALL = 0.70
MIN_F1 = 0.80


def test_final_model_meets_quality_bar():
    test = pd.read_csv("data/test.csv")
    X_test, y_test = test.drop(columns=[TARGET]), test[TARGET]

    ranked = predict_risk(X_test)
    # "Critical" is the alarm tier (matches risk_levels.py's own quality check);
    # "At Risk" intentionally trades precision for recall and is not a fair
    # target for a precision floor.
    y_pred = (ranked["risk_level"] == "Critical").astype(int)
    y_true = y_test.loc[ranked.index]

    precision = precision_score(y_true, y_pred)
    recall = recall_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred)

    assert precision >= MIN_PRECISION, f"Precision regressed: {precision:.3f} < {MIN_PRECISION}"
    assert recall >= MIN_RECALL, f"Recall regressed: {recall:.3f} < {MIN_RECALL}"
    assert f1 >= MIN_F1, f"F1 regressed: {f1:.3f} < {MIN_F1}"
