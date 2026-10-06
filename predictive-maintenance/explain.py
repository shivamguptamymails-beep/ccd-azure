"""
Explainability: which factors drive failure risk, overall and per machine.

Two complementary methods:
  1. Permutation importance (on the final calibrated model):
     shuffle one raw input column at a time and measure how much PR-AUC
     drops on the test set. A big drop = the model relies on that input.
  2. SHAP values (on the Random Forest inside the pipeline):
     split each prediction into a contribution per feature, so we can say
     "this machine is risky mainly because torque_x_wear is high".

Why SHAP uses the uncalibrated Random Forest: the final model is the same
Random Forest plus isotonic calibration, which only re-maps scores
monotonically (a higher score stays higher). So the direction and ranking
of feature effects are the same, and TreeExplainer can compute exact SHAP
values quickly on a single forest.

Run:  venv\\Scripts\\python explain.py
"""

from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from sklearn.inspection import permutation_importance

from preprocessing_pipeline import RANDOM_STATE, TARGET

OUT_DIR = Path("results/explain")
FINAL_MODEL_PATH = Path("models/final_model.joblib")
RF_PATH = Path("models/random_forest.joblib")

INK, INK_2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
UP_COLOR, DOWN_COLOR = "#e34948", "#2a78d6"   # raises risk / lowers risk

plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
    "axes.edgecolor": "#c3c2b7", "axes.labelcolor": INK_2,
    "axes.titlecolor": INK, "axes.titlesize": 12, "axes.titleweight": "bold",
    "xtick.color": MUTED, "ytick.color": INK_2, "text.color": INK,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.axisbelow": True, "font.size": 10,
})


def clean_name(name):
    """'num__torque' -> 'torque', 'cat__type_L' -> 'type_L'."""
    return name.split("__", 1)[-1]


def transform_for_shap(rf_pipeline, X):
    """Run the feature + preprocessing steps so SHAP sees model inputs."""
    pre = rf_pipeline[:-1]   # everything except the classifier
    Xt = pre.transform(X)
    names = [clean_name(n) for n in pre[-1].get_feature_names_out()]
    return pd.DataFrame(Xt, columns=names, index=X.index)


def readable_values(rf_pipeline, X, columns):
    """Unscaled feature values (real units) to show next to SHAP values.

    SHAP is computed on scaled inputs, but "torque = 65 Nm" is easier to
    explain than "torque = 2.5 standard deviations".
    """
    engineered = rf_pipeline.named_steps["features"].transform(X)
    out = pd.DataFrame(index=X.index)
    for col in columns:
        if col.startswith("type_"):
            out[col] = (engineered["type"] == col.split("_", 1)[1]).astype(int)
        else:
            out[col] = engineered[col].round(1)
    return out


def make_explainer(rf_pipeline):
    return shap.TreeExplainer(rf_pipeline.named_steps["model"])


def shap_for(explainer, Xt):
    """SHAP values for the 'failure' class, one row per machine."""
    values = explainer(Xt, check_additivity=False)
    return values[:, :, 1]   # class 1 = failure


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT_DIR / name, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {OUT_DIR / name}")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    test = pd.read_csv("data/test.csv")
    X_test, y_test = test.drop(columns=[TARGET]), test[TARGET]

    final_model = joblib.load(FINAL_MODEL_PATH)
    rf = joblib.load(RF_PATH)

    # -----------------------------------------------------------------------
    # 1. Permutation importance on the final model (raw input columns)
    # -----------------------------------------------------------------------
    # Done on the TEST set, so it measures what matters for unseen data.
    print("Permutation importance (10 shuffles per column)...")
    perm = permutation_importance(
        final_model, X_test, y_test, scoring="average_precision",
        n_repeats=10, random_state=RANDOM_STATE, n_jobs=-1,
    )
    perm_df = (pd.DataFrame({"feature": X_test.columns,
                             "pr_auc_drop": perm.importances_mean,
                             "std": perm.importances_std})
               .sort_values("pr_auc_drop", ascending=False))
    perm_df.to_csv(OUT_DIR / "permutation_importance.csv", index=False)
    print(perm_df.round(3).to_string(index=False))

    fig, ax = plt.subplots(figsize=(7, 3.6))
    p = perm_df.iloc[::-1]
    ax.barh(p["feature"], p["pr_auc_drop"], xerr=p["std"], color=DOWN_COLOR,
            height=0.55, error_kw={"ecolor": MUTED, "elinewidth": 1})
    ax.set_xlabel("Drop in test PR-AUC when the column is shuffled")
    ax.set_title("Permutation importance (final model, raw inputs)")
    ax.grid(axis="y", visible=False)
    save(fig, "01_permutation_importance.png")

    # -----------------------------------------------------------------------
    # 2. SHAP values
    # -----------------------------------------------------------------------
    # Explain all test failures plus a random sample of healthy machines
    # (exact SHAP on every row is slow and adds little).
    healthy_sample = X_test[y_test == 0].sample(432, random_state=RANDOM_STATE)
    X_explain = pd.concat([X_test[y_test == 1], healthy_sample])
    Xt = transform_for_shap(rf, X_explain)

    print(f"\nComputing SHAP values for {len(Xt)} test machines...")
    sv = shap_for(make_explainer(rf), Xt)
    sv.data = readable_values(rf, X_explain, Xt.columns).values

    # Global importance = average size of each feature's contribution.
    shap_imp = (pd.DataFrame({"feature": Xt.columns,
                              "mean_abs_shap": np.abs(sv.values).mean(axis=0)})
                .sort_values("mean_abs_shap", ascending=False))
    shap_imp.to_csv(OUT_DIR / "shap_importance.csv", index=False)
    print(shap_imp.round(4).to_string(index=False))

    fig, ax = plt.subplots(figsize=(7, 4.2))
    s = shap_imp.iloc[::-1]
    ax.barh(s["feature"], s["mean_abs_shap"], color=DOWN_COLOR, height=0.6)
    ax.set_xlabel("Mean |SHAP value| (average impact on failure score)")
    ax.set_title("Most important failure factors (SHAP)")
    ax.grid(axis="y", visible=False)
    save(fig, "02_shap_importance.png")

    # Beeswarm: each dot is a machine. Colour = feature value (red = high),
    # position = push towards failure (right) or towards healthy (left).
    shap.plots.beeswarm(sv, max_display=11, show=False, plot_size=(8, 5))
    plt.title("How each feature pushes failure risk (SHAP)")
    save(plt.gcf(), "03_shap_beeswarm.png")

    # Waterfall for the riskiest machine: why did it get its score?
    top = int(np.argmax(sv.values.sum(axis=1) + sv.base_values))
    shap.plots.waterfall(sv[top], max_display=10, show=False)
    plt.title("Why the highest-risk test machine was flagged")
    save(plt.gcf(), "04_shap_waterfall_top_machine.png")


if __name__ == "__main__":
    main()
