"""
Data preprocessing pipeline for the AI4I 2020 Predictive Maintenance dataset.

Steps:
  1. Load the raw CSV
  2. Separate target and inputs (drop IDs and leakage columns)
  3. Stratified train/test split
  4. Build a scikit-learn Pipeline:
        FeatureEngineer -> ColumnTransformer (scale + encode) -> classifier
  5. Fit on training data only and save the pipeline
  6. Print a sanity report

Run:  venv\\Scripts\\python preprocessing_pipeline.py
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_PATH = Path("data/ai4i2020.csv")
MODEL_PATH = Path("models/baseline_pipeline.joblib")
RANDOM_STATE = 42   # fixed seed so the split is the same every run
TEST_SIZE = 0.20    # 80% train, 20% test

TARGET = "Machine failure"

# Identifiers: unique per row, carry no information about failure.
# Keeping them would let a model memorise rows instead of learning patterns.
ID_COLUMNS = ["UDI", "Product ID"]

# Failure-mode flags. They are only known AFTER a machine fails, and
# "Machine failure" is 1 whenever any of them is 1. Using them as inputs
# would leak the answer into the model (data leakage).
LEAKAGE_COLUMNS = ["TWF", "HDF", "PWF", "OSF", "RNF"]

# Set to True to try SMOTE oversampling instead of class weights.
# SMOTE then runs only inside the training pipeline, never on the test set.
USE_SMOTE = False


# ---------------------------------------------------------------------------
# Feature engineering (a transformer, so it lives inside the Pipeline)
# ---------------------------------------------------------------------------
class FeatureEngineer(BaseEstimator, TransformerMixin):
    """Renames raw columns and adds physics-based features.

    It is a Pipeline step (not a one-off pandas edit) so the saved model
    can be given the raw CSV columns and will build the features itself.
    It learns nothing from data, so it cannot leak test information.
    """

    # Short names without "[K]"-style brackets, which XGBoost does not accept.
    RENAME = {
        "Type": "type",
        "Air temperature [K]": "air_temp",
        "Process temperature [K]": "process_temp",
        "Rotational speed [rpm]": "rot_speed",
        "Torque [Nm]": "torque",
        "Tool wear [min]": "tool_wear",
    }

    def fit(self, X, y=None):
        return self  # nothing to learn

    def transform(self, X):
        X = X.rename(columns=self.RENAME).copy()

        # Heat-dissipation failures happen when the process runs hot
        # relative to the surrounding air, so the gap matters more than
        # either temperature on its own.
        X["temp_diff"] = X["process_temp"] - X["air_temp"]

        # Mechanical power (W) = torque (Nm) x angular speed (rad/s).
        # rpm -> rad/s: multiply by 2*pi/60. Power failures happen when
        # power is too low or too high.
        X["power"] = X["torque"] * X["rot_speed"] * 2 * np.pi / 60

        # Overstrain failures happen when a worn tool is under high torque,
        # so the product of the two captures that combined stress.
        X["torque_x_wear"] = X["torque"] * X["tool_wear"]
        return X


NUMERIC_FEATURES = [
    "air_temp", "process_temp", "rot_speed", "torque", "tool_wear",
    "temp_diff", "power", "torque_x_wear",
]
CATEGORICAL_FEATURES = ["type"]


def build_preprocessor():
    """Scaling + encoding. Fitted inside the Pipeline, so on training data only."""
    return ColumnTransformer([
        # Features have very different ranges (e.g. rpm ~1500 vs temp_diff ~10).
        # Scaling to mean 0 / std 1 stops large-valued features dominating
        # distance- or gradient-based models such as Logistic Regression.
        ("num", StandardScaler(), NUMERIC_FEATURES),
        # "Type" is a letter (L / M / H). Models need numbers, so one-hot
        # encode it into three 0/1 columns. handle_unknown="ignore" stops a
        # crash if an unseen category ever appears at prediction time.
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])


def build_pipeline():
    """Full pipeline: raw columns in -> failure prediction out."""
    if USE_SMOTE:
        # imblearn's Pipeline applies SMOTE during fit() only. At predict
        # time it is skipped, so the test set is never resampled.
        from imblearn.over_sampling import SMOTE
        from imblearn.pipeline import Pipeline as ImbPipeline
        return ImbPipeline([
            ("features", FeatureEngineer()),
            ("preprocess", build_preprocessor()),
            ("smote", SMOTE(random_state=RANDOM_STATE)),
            ("model", LogisticRegression(max_iter=1000)),
        ])

    # Default: class weights. Failures are only ~3.4% of rows, so a model
    # could score 96.6% accuracy by always predicting "no failure".
    # class_weight="balanced" makes each failure count ~29x more in the
    # loss, so the model is pushed to actually detect failures.
    # (For XGBoost the equivalent is scale_pos_weight = negatives / positives.)
    return Pipeline([
        ("features", FeatureEngineer()),
        ("preprocess", build_preprocessor()),
        ("model", LogisticRegression(class_weight="balanced", max_iter=1000)),
    ])


def main():
    # -----------------------------------------------------------------------
    # 1. Load data
    # -----------------------------------------------------------------------
    # "utf-8-sig" strips the invisible BOM character at the start of the
    # file; without it the first column is read as "﻿UDI", not "UDI".
    df = pd.read_csv(DATA_PATH, encoding="utf-8-sig")

    # -----------------------------------------------------------------------
    # 2. Separate target (y) and inputs (X)
    # -----------------------------------------------------------------------
    y = df[TARGET]
    X = df.drop(columns=[TARGET] + ID_COLUMNS + LEAKAGE_COLUMNS)

    # -----------------------------------------------------------------------
    # 3. Stratified train/test split
    # -----------------------------------------------------------------------
    # stratify=y keeps the failure rate (~3.4%) the same in both sets.
    # Without it, a random split could put very few failures in the test set.
    # The test set is never resampled, so it reflects real-world conditions.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
    )

    # Save the raw split so every model the team trains later is evaluated
    # on exactly the same untouched test rows.
    X_train.assign(**{TARGET: y_train}).to_csv("data/train.csv", index=False)
    X_test.assign(**{TARGET: y_test}).to_csv("data/test.csv", index=False)

    # -----------------------------------------------------------------------
    # 4-5. Fit pipeline on TRAINING data only, then save it
    # -----------------------------------------------------------------------
    # Calling fit() on X_train means the scaler's mean/std and the encoder's
    # categories are learned from training rows only. The test set is
    # transformed with those training statistics, just like unseen data.
    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)

    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)

    # -----------------------------------------------------------------------
    # 6. Sanity report
    # -----------------------------------------------------------------------
    feature_names = list(pipeline.named_steps["preprocess"].get_feature_names_out())

    print("=" * 60)
    print("SANITY REPORT")
    print("=" * 60)
    print(f"Raw dataset shape        : {df.shape}")
    print(f"Missing values           : {df.isna().sum().sum()}")
    print(f"Input columns (raw)      : {list(X.columns)}")
    print(f"Train shape / test shape : {X_train.shape} / {X_test.shape}")
    print(f"Failure rate - full data : {y.mean():.2%}")
    print(f"Failure rate - train     : {y_train.mean():.2%}  ({y_train.sum()} failures)")
    print(f"Failure rate - test      : {y_test.mean():.2%}  ({y_test.sum()} failures)")
    print(f"Imbalance handling       : {'SMOTE (train only)' if USE_SMOTE else 'class_weight=balanced'}")
    print(f"\nFinal model features ({len(feature_names)}):")
    for name in feature_names:
        print(f"  - {name}")

    # Leakage check: no ID, failure-mode or target column may reach the model.
    forbidden = set(LEAKAGE_COLUMNS + ID_COLUMNS + [TARGET])
    leaked = [c for c in list(X_train.columns) + feature_names
              if any(c == f or c.endswith("__" + f) for f in forbidden)]
    assert not leaked, f"LEAKAGE DETECTED: {leaked}"
    print("\nLeakage check            : PASSED (no TWF/HDF/PWF/OSF/RNF, IDs or target in inputs)")

    # Smoke test: the saved file accepts raw CSV columns directly.
    loaded = joblib.load(MODEL_PATH)
    probs = loaded.predict_proba(X_test.head(3))[:, 1]
    print(f"Saved pipeline smoke test: failure probabilities for 3 raw test rows = {np.round(probs, 3)}")
    print(f"Pipeline saved to        : {MODEL_PATH}")


if __name__ == "__main__":
    # Run main() through the module name, not as "__main__". joblib stores
    # where FeatureEngineer lives; this makes it "preprocessing_pipeline",
    # so other scripts (and the dashboard) can load the saved model.
    import preprocessing_pipeline
    preprocessing_pipeline.main()
