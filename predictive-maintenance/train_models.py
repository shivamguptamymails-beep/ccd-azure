"""
Model training and comparison for the AI4I 2020 Predictive Maintenance project.

Steps:
  1. Load the fixed train/test split made by preprocessing_pipeline.py
  2. Build one Pipeline per model (same preprocessing, different classifier)
  3. Compare models with 5-fold stratified cross-validation on TRAIN only
  4. Fit each model on the full training set and evaluate once on TEST
  5. Save the fitted pipelines and a results table

Run:  venv\\Scripts\\python train_models.py
(Run preprocessing_pipeline.py first so data/train.csv and data/test.csv exist.)
"""

from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score, confusion_matrix, f1_score,
    precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier

# Reuse the exact same preprocessing so every model sees identical features.
from preprocessing_pipeline import (
    RANDOM_STATE, TARGET, FeatureEngineer, build_preprocessor,
)

MODELS_DIR = Path("models")
RESULTS_DIR = Path("results")

# Probability above which we call a row a "failure". 0.5 is the standard
# default; tuning it is a separate decision (see the risk-level stage).
THRESHOLD = 0.5


def make_pipeline(classifier):
    """Raw columns -> feature engineering -> scale/encode -> classifier."""
    return Pipeline([
        ("features", FeatureEngineer()),
        ("preprocess", build_preprocessor()),
        ("model", classifier),
    ])


def get_models(scale_pos_weight):
    """The four models from the synopsis, from simple to powerful.

    Every model handles class imbalance by weighting failures more,
    so none of them can 'win' by always predicting no failure.

    xgboost is imported here, not at module level: only the training/
    comparison path (this function) needs it, and its Linux wheel pulls in
    multi-hundred-MB nvidia-nccl GPU libraries as dependencies. The saved
    final model is a Random Forest (see risk_levels.py), so the serving API
    - which imports make_pipeline from this module - never needs xgboost
    installed at all, keeping the inference container small.
    """
    from xgboost import XGBClassifier

    return {
        # Simple, interpretable baseline: a weighted sum of features.
        "Logistic Regression": LogisticRegression(
            class_weight="balanced", max_iter=1000,
        ),
        # Interpretable if/else rules. max_depth limits the tree so it
        # cannot memorise the training data (overfitting).
        "Decision Tree": DecisionTreeClassifier(
            max_depth=6, class_weight="balanced", random_state=RANDOM_STATE,
        ),
        # Many trees on random subsets of data, averaged: more stable
        # than a single tree.
        "Random Forest": RandomForestClassifier(
            n_estimators=300, class_weight="balanced",
            random_state=RANDOM_STATE, n_jobs=-1,
        ),
        # Boosting: each new tree fixes the errors of the previous ones.
        # XGBoost has no class_weight option; scale_pos_weight does the
        # same job (failures count ~29x more).
        "XGBoost": XGBClassifier(
            n_estimators=300, learning_rate=0.1, max_depth=4,
            scale_pos_weight=scale_pos_weight, eval_metric="aucpr",
            random_state=RANDOM_STATE, n_jobs=-1,
        ),
    }


def evaluate(y_true, y_prob):
    """All the metrics from the synopsis, computed on one set of predictions."""
    y_pred = (y_prob >= THRESHOLD).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    return {
        # Of the machines we flagged, how many really failed?
        # (Low precision = wasted inspections.)
        "precision": precision_score(y_true, y_pred, zero_division=0),
        # Of the machines that really failed, how many did we catch?
        # (Low recall = missed breakdowns, usually the costlier mistake.)
        "recall": recall_score(y_true, y_pred),
        # Balance of precision and recall in one number.
        "f1": f1_score(y_true, y_pred),
        # How well the model ranks failures above non-failures (0.5 = random).
        "roc_auc": roc_auc_score(y_true, y_prob),
        # Like ROC-AUC but focused on the rare failure class. More honest
        # than ROC-AUC on imbalanced data (random = the failure rate, ~0.034).
        "pr_auc": average_precision_score(y_true, y_prob),
        "TN": tn, "FP": fp, "FN": fn, "TP": tp,
    }


def main():
    # -----------------------------------------------------------------------
    # 1. Load the fixed split (test set was never resampled or seen)
    # -----------------------------------------------------------------------
    train = pd.read_csv("data/train.csv")
    test = pd.read_csv("data/test.csv")
    X_train, y_train = train.drop(columns=[TARGET]), train[TARGET]
    X_test, y_test = test.drop(columns=[TARGET]), test[TARGET]

    # Ratio used by XGBoost to weight failures: negatives / positives.
    scale_pos_weight = (y_train == 0).sum() / (y_train == 1).sum()
    print(f"Train: {X_train.shape}, failures {y_train.mean():.2%} | "
          f"Test: {X_test.shape}, failures {y_test.mean():.2%}")
    print(f"XGBoost scale_pos_weight = {scale_pos_weight:.1f}\n")

    # Stratified folds keep ~3.4% failures in every fold.
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)

    MODELS_DIR.mkdir(exist_ok=True)
    RESULTS_DIR.mkdir(exist_ok=True)
    rows = []

    for name, classifier in get_models(scale_pos_weight).items():
        pipeline = make_pipeline(classifier)

        # -------------------------------------------------------------------
        # 3. Cross-validation on TRAIN only
        # -------------------------------------------------------------------
        # We compare models here, not on the test set. If we picked the best
        # model by its test score, the test score would no longer be an
        # honest estimate of performance on new data.
        cv_scores = cross_val_score(
            pipeline, X_train, y_train, cv=cv, scoring="average_precision",
        )

        # -------------------------------------------------------------------
        # 4. Fit on all training data, evaluate once on the untouched test set
        # -------------------------------------------------------------------
        pipeline.fit(X_train, y_train)
        y_prob = pipeline.predict_proba(X_test)[:, 1]
        metrics = evaluate(y_test, y_prob)

        rows.append({
            "model": name,
            "cv_pr_auc_mean": cv_scores.mean(),
            "cv_pr_auc_std": cv_scores.std(),
            **metrics,
        })

        # 5. Save the fitted pipeline (accepts raw CSV columns).
        file_name = name.lower().replace(" ", "_") + ".joblib"
        joblib.dump(pipeline, MODELS_DIR / file_name)
        print(f"Trained {name:<20} CV PR-AUC = "
              f"{cv_scores.mean():.3f} +/- {cv_scores.std():.3f}")

    # -----------------------------------------------------------------------
    # Results
    # -----------------------------------------------------------------------
    results = pd.DataFrame(rows).sort_values("cv_pr_auc_mean", ascending=False)
    results.to_csv(RESULTS_DIR / "model_comparison.csv", index=False)

    pd.set_option("display.width", 200)
    print("\n" + "=" * 80)
    print(f"TEST SET RESULTS (threshold = {THRESHOLD}, "
          f"{int(y_test.sum())} real failures out of {len(y_test)})")
    print("=" * 80)
    print(results[["model", "cv_pr_auc_mean", "precision", "recall", "f1",
                   "roc_auc", "pr_auc"]].round(3).to_string(index=False))

    print("\nConfusion matrices (TN = correct 'healthy', FP = false alarm, "
          "FN = missed failure, TP = caught failure):")
    for _, r in results.iterrows():
        print(f"  {r['model']:<20} TN={r['TN']:<5} FP={r['FP']:<5} "
              f"FN={r['FN']:<4} TP={r['TP']}")

    best = results.iloc[0]["model"]
    print(f"\nBest model by cross-validated PR-AUC: {best}")
    print(f"Saved: {MODELS_DIR}/*.joblib and {RESULTS_DIR}/model_comparison.csv")


if __name__ == "__main__":
    main()
