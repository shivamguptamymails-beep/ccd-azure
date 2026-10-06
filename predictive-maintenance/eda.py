"""
Exploratory Data Analysis (EDA) for the AI4I 2020 Predictive Maintenance dataset.

Answers the questions the synopsis lists before modelling:
  - How imbalanced is the target?
  - How often does each failure mode occur?
  - How do feature distributions differ between failed and healthy machines?
  - Which features are correlated with each other and with failure?
  - Does product Type change the failure rate?

Plots are saved to results/eda/ and key numbers are printed.

Run:  venv\\Scripts\\python eda.py
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # save to files, no window needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from preprocessing_pipeline import (
    DATA_PATH, LEAKAGE_COLUMNS, TARGET, FeatureEngineer,
)

OUT_DIR = Path("results/eda")

# One consistent colour scheme for every plot.
HEALTHY_COLOR = "#2a78d6"   # blue
FAILURE_COLOR = "#eb6834"   # orange
INK, INK_2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"

plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
    "axes.edgecolor": "#c3c2b7", "axes.labelcolor": INK_2,
    "axes.titlecolor": INK, "axes.titlesize": 12, "axes.titleweight": "bold",
    "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.axisbelow": True, "font.size": 10,
})

FEATURE_LABELS = {
    "air_temp": "Air temperature [K]",
    "process_temp": "Process temperature [K]",
    "rot_speed": "Rotational speed [rpm]",
    "torque": "Torque [Nm]",
    "tool_wear": "Tool wear [min]",
    "temp_diff": "temp_diff [K]  (engineered)",
    "power": "power [W]  (engineered)",
    "torque_x_wear": "torque x tool wear  (engineered)",
}


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT_DIR / name, dpi=130)
    plt.close(fig)
    print(f"  saved {OUT_DIR / name}")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(DATA_PATH, encoding="utf-8-sig")

    # Same feature engineering as the model, so EDA shows what the model sees.
    df = FeatureEngineer().transform(raw)
    failed = df[TARGET] == 1

    # -----------------------------------------------------------------------
    # 1. Basic facts
    # -----------------------------------------------------------------------
    print("=" * 60)
    print("DATASET OVERVIEW")
    print("=" * 60)
    print(f"Shape: {raw.shape}, missing values: {raw.isna().sum().sum()}, "
          f"duplicate rows: {raw.duplicated().sum()}")
    print(f"Machine failures: {failed.sum()} of {len(df)} ({failed.mean():.2%})")
    print("\nSummary statistics:")
    print(df[list(FEATURE_LABELS)].describe().round(2).T.to_string())

    # -----------------------------------------------------------------------
    # 2. Class balance
    # -----------------------------------------------------------------------
    # Shows why accuracy is misleading and why we need class weights.
    print("\nPlots:")
    counts = df[TARGET].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(5, 3.6))
    bars = ax.bar(["No failure", "Failure"], counts.values,
                  color=[HEALTHY_COLOR, FAILURE_COLOR], width=0.55)
    for bar, n in zip(bars, counts.values):
        ax.annotate(f"{n:,}  ({n / len(df):.1%})",
                    (bar.get_x() + bar.get_width() / 2, n),
                    ha="center", va="bottom", xytext=(0, 3),
                    textcoords="offset points", color=INK_2)
    ax.set_title("Class balance: only 3.4% of rows are failures")
    ax.set_ylabel("Number of rows")
    ax.grid(axis="x", visible=False)
    save(fig, "01_class_balance.png")

    # -----------------------------------------------------------------------
    # 3. Failure modes
    # -----------------------------------------------------------------------
    mode_names = {"TWF": "Tool wear (TWF)", "HDF": "Heat dissipation (HDF)",
                  "PWF": "Power (PWF)", "OSF": "Overstrain (OSF)",
                  "RNF": "Random (RNF)"}
    mode_counts = df[LEAKAGE_COLUMNS].sum().sort_values()
    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.barh([mode_names[m] for m in mode_counts.index], mode_counts.values,
            color=FAILURE_COLOR, height=0.55)
    for i, n in enumerate(mode_counts.values):
        ax.annotate(str(n), (n, i), xytext=(4, 0), textcoords="offset points",
                    va="center", color=INK_2)
    ax.set_title("How often each failure mode occurs")
    ax.set_xlabel("Number of rows")
    ax.grid(axis="y", visible=False)
    save(fig, "02_failure_modes.png")

    # Data-quality facts worth knowing for the viva.
    any_mode = df[LEAKAGE_COLUMNS].sum(axis=1) > 0
    n_modes = df.loc[failed, LEAKAGE_COLUMNS].sum(axis=1)
    print(f"\n  Failures with no mode flagged        : {(failed & ~any_mode).sum()}")
    print(f"  Mode flagged but no machine failure  : {(~failed & any_mode).sum()} "
          f"(RNF on its own: {((df['RNF'] == 1) & ~failed).sum()})")
    print(f"  Failures with more than one mode     : {(n_modes > 1).sum()}")

    # -----------------------------------------------------------------------
    # 4. Feature distributions: failed vs healthy
    # -----------------------------------------------------------------------
    # Densities (not counts) so the small failure group is visible next to
    # the large healthy group. Big shifts = useful features.
    fig, axes = plt.subplots(2, 4, figsize=(15, 6.5))
    for ax, (col, label) in zip(axes.ravel(), FEATURE_LABELS.items()):
        bins = np.histogram_bin_edges(df[col], bins=40)
        ax.hist(df.loc[~failed, col], bins=bins, density=True, alpha=0.55,
                color=HEALTHY_COLOR, label="No failure")
        ax.hist(df.loc[failed, col], bins=bins, density=True, alpha=0.55,
                color=FAILURE_COLOR, label="Failure")
        ax.set_title(label, fontsize=10)
        ax.set_yticks([])
        ax.grid(axis="x", visible=False)
    axes[0, 0].legend(frameon=False)
    fig.suptitle("Feature distributions: failed vs healthy machines",
                 fontweight="bold", color=INK)
    save(fig, "03_feature_distributions.png")

    # -----------------------------------------------------------------------
    # 5. Correlation heatmap
    # -----------------------------------------------------------------------
    # Shows which features move together (e.g. air and process temperature,
    # speed and torque) and which relate most to failure.
    corr_cols = list(FEATURE_LABELS) + [TARGET]
    corr = df[corr_cols].corr()
    cmap = LinearSegmentedColormap.from_list(
        "diverging", ["#2a78d6", "#f0efec", "#e34948"])
    fig, ax = plt.subplots(figsize=(8, 6.5))
    im = ax.imshow(corr, cmap=cmap, vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr_cols)), corr_cols, rotation=45, ha="right")
    ax.set_yticks(range(len(corr_cols)), corr_cols)
    ax.grid(False)
    for i in range(len(corr_cols)):
        for j in range(len(corr_cols)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center",
                    fontsize=8, color=INK)
    fig.colorbar(im, ax=ax, shrink=0.8, label="Pearson correlation")
    ax.set_title("Correlation between features and machine failure")
    save(fig, "04_correlation_heatmap.png")

    print("\n  Correlation with Machine failure:")
    print(corr[TARGET].drop(TARGET).sort_values(key=abs, ascending=False)
          .round(3).to_string())

    # -----------------------------------------------------------------------
    # 6. Failure rate by product Type
    # -----------------------------------------------------------------------
    rate = df.groupby("type")[TARGET].mean().reindex(["L", "M", "H"])
    n = df["type"].value_counts().reindex(["L", "M", "H"])
    fig, ax = plt.subplots(figsize=(5, 3.6))
    ax.bar([f"{t}\n({n[t]:,} rows)" for t in rate.index], rate.values * 100,
           color=FAILURE_COLOR, width=0.55)
    for i, r in enumerate(rate.values):
        ax.annotate(f"{r:.1%}", (i, r * 100), ha="center", va="bottom",
                    xytext=(0, 3), textcoords="offset points", color=INK_2)
    ax.set_title("Failure rate by product quality Type")
    ax.set_ylabel("Failure rate (%)")
    ax.grid(axis="x", visible=False)
    save(fig, "05_failure_rate_by_type.png")
    print(f"\n  Failure rate by Type: "
          + ", ".join(f"{t} = {r:.2%}" for t, r in rate.items()))

    # -----------------------------------------------------------------------
    # 7. Speed vs torque scatter
    # -----------------------------------------------------------------------
    # Failures cluster at the extremes (low speed + high torque = overstrain
    # or power failure; high speed + low torque = power failure). That is a
    # non-linear pattern, which explains why tree models beat Logistic
    # Regression.
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(df.loc[~failed, "rot_speed"], df.loc[~failed, "torque"],
               s=6, alpha=0.25, color=HEALTHY_COLOR, label="No failure",
               linewidths=0)
    ax.scatter(df.loc[failed, "rot_speed"], df.loc[failed, "torque"],
               s=18, alpha=0.9, color=FAILURE_COLOR, label="Failure",
               edgecolors="#fcfcfb", linewidths=0.6)
    ax.set_xlabel("Rotational speed [rpm]")
    ax.set_ylabel("Torque [Nm]")
    ax.set_title("Failures sit at the extremes of speed and torque")
    ax.legend(frameon=False, markerscale=2)
    save(fig, "06_speed_vs_torque.png")


if __name__ == "__main__":
    main()
