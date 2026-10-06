"""
Failure-mode analysis: predict WHICH kind of failure is likely.

The main model answers "will this machine fail?". This script trains one
extra model per failure mode (TWF, HDF, PWF, OSF, RNF) so the dashboard can
also say "most likely cause: overstrain" for a risky machine.

Important: here the failure-mode columns are the TARGETS, never inputs.
The inputs are the same raw sensor columns as the main model, so there is
still no leakage.

Run:  venv\\Scripts\\python failure_modes.py
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score, precision_score, recall_score,
)
from sklearn.model_selection import train_test_split

from preprocessing_pipeline import (
    DATA_PATH, ID_COLUMNS, LEAKAGE_COLUMNS, RANDOM_STATE, TARGET, TEST_SIZE,
)
from train_models import make_pipeline

MODEL_PATH = Path("models/failure_mode_models.joblib")
RESULTS_PATH = Path("results/failure_mode_results.csv")

MODE_NAMES = {
    "TWF": "Tool wear failure",
    "HDF": "Heat dissipation failure",
    "PWF": "Power failure",
    "OSF": "Overstrain failure",
    "RNF": "Random failure",
}


def load_split_with_modes():
    """Recreate the exact train/test split, keeping the failure-mode columns.

    train_test_split with the same data, stratify target, test size and
    random_state always picks the same rows, so this matches
    data/train.csv and data/test.csv (checked below).
    """
    df = pd.read_csv(DATA_PATH, encoding="utf-8-sig")
    X = df.drop(columns=[TARGET] + ID_COLUMNS + LEAKAGE_COLUMNS)
    modes = df[LEAKAGE_COLUMNS]
    X_train, X_test, m_train, m_test = train_test_split(
        X, modes, test_size=TEST_SIZE, stratify=df[TARGET],
        random_state=RANDOM_STATE,
    )
    # Safety check: same rows as the saved split used by every other model.
    saved = pd.read_csv("data/test.csv").drop(columns=[TARGET])
    assert np.allclose(saved.select_dtypes("number").values,
                       X_test.select_dtypes("number").values), \
        "Split does not match data/test.csv"
    return X_train, X_test, m_train, m_test


def predict_modes(models, X):
    """Probability of each failure mode for each row (columns = modes)."""
    return pd.DataFrame(
        {mode: m.predict_proba(X)[:, 1] for mode, m in models.items()},
        index=X.index,
    )


def main():
    X_train, X_test, m_train, m_test = load_split_with_modes()

    models, rows = {}, []
    for mode in LEAKAGE_COLUMNS:
        y_train, y_test = m_train[mode], m_test[mode]

        # Each mode is even rarer than failure overall (0.2% to 1.2%), so
        # class weights are needed again. Same preprocessing pipeline.
        model = make_pipeline(RandomForestClassifier(
            n_estimators=300, class_weight="balanced",
            min_samples_leaf=2, random_state=RANDOM_STATE, n_jobs=-1,
        ))
        model.fit(X_train, y_train)
        models[mode] = model

        prob = model.predict_proba(X_test)[:, 1]
        pred = (prob >= 0.5).astype(int)
        rows.append({
            "mode": mode,
            "name": MODE_NAMES[mode],
            "train_cases": int(y_train.sum()),
            "test_cases": int(y_test.sum()),
            "precision": precision_score(y_test, pred, zero_division=0),
            "recall": recall_score(y_test, pred, zero_division=0),
            # PR-AUC of a random guess equals the mode's rate (~0.002-0.012).
            "pr_auc": average_precision_score(y_test, prob),
            "random_baseline_pr_auc": y_test.mean(),
        })

    results = pd.DataFrame(rows)
    RESULTS_PATH.parent.mkdir(exist_ok=True)
    results.to_csv(RESULTS_PATH, index=False)
    joblib.dump(models, MODEL_PATH)

    print("=" * 78)
    print("FAILURE-MODE MODELS (one per mode, evaluated on the TEST set)")
    print("=" * 78)
    print(results.round(3).to_string(index=False))

    # "Most likely cause" check: for test rows with exactly one failure mode
    # flagged, is the highest-probability mode the right one?
    probs = predict_modes(models, X_test)
    single = m_test[m_test.sum(axis=1) == 1]
    true_mode = single.idxmax(axis=1)
    pred_mode = probs.loc[single.index].idxmax(axis=1)
    print(f"\nMost-likely-cause accuracy on {len(single)} test rows with exactly "
          f"one mode flagged: {(true_mode == pred_mode).mean():.1%}")
    print(pd.crosstab(true_mode, pred_mode,
                      rownames=["true"], colnames=["predicted"]).to_string())

    print("\nNote: RNF is a 0.1% random failure by design (it does not depend "
          "on the sensors),\nso it is expected to be unpredictable.")
    print(f"\nSaved: {MODEL_PATH}, {RESULTS_PATH}")


if __name__ == "__main__":
    main()
