"""
Threshold tuning and risk levels for the AI4I 2020 Predictive Maintenance project.

Steps:
  1. Load the fixed train/test split
  2. Build the final model: Random Forest (best by cross-validation in
     train_models.py) wrapped in probability calibration
  3. Get honest "out-of-fold" probabilities on TRAIN with cross-validation
  4. Choose two thresholds from those probabilities (never from the test set):
        Critical  : probability >= t_critical  (best balance of precision/recall)
        At Risk   : probability >= t_risk      (catches ~95% of failures)
        Healthy   : below t_risk
  5. Fit the final model on all training data, evaluate the risk levels
     once on the untouched test set, and save model + thresholds

Run:  venv\\Scripts\\python risk_levels.py
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    brier_score_loss, confusion_matrix, f1_score,
    precision_recall_curve, precision_score, recall_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from preprocessing_pipeline import RANDOM_STATE, TARGET
from train_models import make_pipeline

MODEL_PATH = Path("models/final_model.joblib")
THRESHOLDS_PATH = Path("models/risk_thresholds.json")
PREDICTIONS_PATH = Path("results/test_risk_predictions.csv")

# Share of real failures the "At Risk" band (and above) should catch.
# 95% means we accept more inspections so that few breakdowns are missed.
TARGET_RECALL_AT_RISK = 0.95

# What the maintenance team should do at each level.
RECOMMENDATIONS = {
    "Critical": "Stop or schedule immediate maintenance; inspect tool, "
                "cooling and load before next run.",
    "At Risk": "Schedule inspection within the next shift; monitor "
               "torque, tool wear and temperature closely.",
    "Healthy": "No action needed; continue routine monitoring.",
}


def build_final_model():
    """Random Forest pipeline with calibrated probabilities.

    class_weight="balanced" helps the model find failures but pushes its
    probabilities too high (a score of 0.6 does not mean a 60% chance).
    CalibratedClassifierCV learns a correction on held-out folds so the
    output can be read as a real probability, which the dashboard shows.
    Isotonic calibration is a flexible, non-parametric mapping that suits
    tree models.
    """
    rf = RandomForestClassifier(
        n_estimators=300, class_weight="balanced",
        random_state=RANDOM_STATE, n_jobs=-1,
    )
    return CalibratedClassifierCV(make_pipeline(rf), method="isotonic", cv=5)


def choose_thresholds(y_true, y_prob):
    """Pick the two cut-offs from out-of-fold training probabilities."""
    precision, recall, thresholds = precision_recall_curve(y_true, y_prob)
    # precision/recall have one more value than thresholds; drop the last.
    precision, recall = precision[:-1], recall[:-1]

    # Critical: the threshold with the best F1 (balance of catching failures
    # and avoiding false alarms). These are the machines to act on now.
    f1 = 2 * precision * recall / (precision + recall + 1e-12)
    t_critical = thresholds[np.argmax(f1)]

    # At Risk: the HIGHEST threshold that still catches the target share of
    # failures. Highest = fewest false alarms for that level of recall.
    meets_target = recall >= TARGET_RECALL_AT_RISK
    t_risk = thresholds[meets_target].max()

    # Safety: the "At Risk" cut-off must sit below "Critical".
    t_risk = min(t_risk, t_critical)
    return float(t_risk), float(t_critical)


def assign_risk(probabilities, t_risk, t_critical):
    """Map failure probabilities to Healthy / At Risk / Critical."""
    return np.select(
        [probabilities >= t_critical, probabilities >= t_risk],
        ["Critical", "At Risk"],
        default="Healthy",
    )


def predict_risk(df, model=None, thresholds=None):
    """For the dashboard: raw machine rows in -> probability, level, action.

    Rows are returned sorted by failure probability, highest first,
    which is the maintenance priority ranking.
    """
    model = model or joblib.load(MODEL_PATH)
    thresholds = thresholds or json.loads(THRESHOLDS_PATH.read_text())
    out = df.copy()
    out["failure_probability"] = model.predict_proba(df)[:, 1]
    out["risk_level"] = assign_risk(
        out["failure_probability"], thresholds["t_risk"], thresholds["t_critical"],
    )
    out["recommendation"] = out["risk_level"].map(RECOMMENDATIONS)
    out = out.sort_values("failure_probability", ascending=False)
    out.insert(0, "priority_rank", range(1, len(out) + 1))
    return out


def report_thresholds(name, y_true, y_prob, t_risk, t_critical):
    """Recall/precision at each cut-off, plus the size of each band."""
    print(f"\n{name}")
    for label, t in [("Critical", t_critical), ("At Risk+", t_risk)]:
        y_pred = (y_prob >= t).astype(int)
        print(f"  {label:<9} (p >= {t:.3f}): "
              f"recall = {recall_score(y_true, y_pred):.3f}, "
              f"precision = {precision_score(y_true, y_pred, zero_division=0):.3f}, "
              f"flagged = {y_pred.sum()}")


def main():
    # -----------------------------------------------------------------------
    # 1. Load the fixed split
    # -----------------------------------------------------------------------
    train = pd.read_csv("data/train.csv")
    test = pd.read_csv("data/test.csv")
    X_train, y_train = train.drop(columns=[TARGET]), train[TARGET]
    X_test, y_test = test.drop(columns=[TARGET]), test[TARGET]

    # -----------------------------------------------------------------------
    # 2-3. Out-of-fold probabilities on TRAIN
    # -----------------------------------------------------------------------
    # cross_val_predict trains on 4/5 of the training rows and predicts the
    # remaining 1/5, five times. Every training row therefore gets a
    # probability from a model that never saw it, which is an honest basis
    # for choosing thresholds without touching the test set.
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    print("Computing out-of-fold probabilities on the training set...")
    oof_prob = cross_val_predict(
        build_final_model(), X_train, y_train, cv=cv, method="predict_proba",
    )[:, 1]

    # -----------------------------------------------------------------------
    # 4. Choose thresholds (training data only)
    # -----------------------------------------------------------------------
    t_risk, t_critical = choose_thresholds(y_train, oof_prob)
    report_thresholds("Chosen on TRAIN (out-of-fold):",
                      y_train, oof_prob, t_risk, t_critical)

    # -----------------------------------------------------------------------
    # 5. Fit on all training data, evaluate once on TEST
    # -----------------------------------------------------------------------
    model = build_final_model()
    model.fit(X_train, y_train)
    test_prob = model.predict_proba(X_test)[:, 1]

    report_thresholds("Checked on TEST (never used for choosing):",
                      y_test, test_prob, t_risk, t_critical)

    # Calibration check: Brier score = mean squared error of probabilities
    # (lower is better). Compare with the uncalibrated Random Forest.
    uncalibrated = joblib.load("models/random_forest.joblib")
    print(f"\nBrier score on TEST: calibrated = "
          f"{brier_score_loss(y_test, test_prob):.4f}, uncalibrated RF = "
          f"{brier_score_loss(y_test, uncalibrated.predict_proba(X_test)[:, 1]):.4f}")

    # Confusion matrix if every "Critical" machine is treated as a failure.
    tn, fp, fn, tp = confusion_matrix(y_test, (test_prob >= t_critical)).ravel()
    print(f"Critical as the alarm on TEST: TN={tn} FP={fp} FN={fn} TP={tp}, "
          f"F1 = {f1_score(y_test, test_prob >= t_critical):.3f}")

    # Each band should contain a clearly different real failure rate.
    thresholds = {"t_risk": t_risk, "t_critical": t_critical,
                  "target_recall_at_risk": TARGET_RECALL_AT_RISK}
    ranked = predict_risk(X_test, model, thresholds)
    ranked[TARGET] = y_test.loc[ranked.index]
    summary = (ranked.groupby("risk_level")[TARGET]
               .agg(machines="count", real_failures="sum", failure_rate="mean")
               .reindex(["Critical", "At Risk", "Healthy"]))
    print("\nRisk levels on TEST:")
    print(summary.to_string(formatters={"failure_rate": "{:.1%}".format}))

    # Save the final model, thresholds and ranked test predictions.
    joblib.dump(model, MODEL_PATH)
    THRESHOLDS_PATH.write_text(json.dumps(thresholds, indent=2))
    PREDICTIONS_PATH.parent.mkdir(exist_ok=True)
    ranked.to_csv(PREDICTIONS_PATH, index=False)

    print("\nTop 5 machines by maintenance priority (TEST):")
    print(ranked[["priority_rank", "failure_probability", "risk_level", TARGET]]
          .head().round(3).to_string(index=False))
    print(f"\nSaved: {MODEL_PATH}, {THRESHOLDS_PATH}, {PREDICTIONS_PATH}")


if __name__ == "__main__":
    main()
