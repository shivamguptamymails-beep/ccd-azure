"""
Predictive Maintenance Intelligence System: Streamlit dashboard.

Brings together the saved models:
  - final_model.joblib          -> failure probability (calibrated Random Forest)
  - risk_thresholds.json        -> Healthy / At Risk / Critical
  - failure_mode_models.joblib  -> most likely failure cause
  - random_forest.joblib        -> SHAP explanations per machine

Run:  venv\\Scripts\\streamlit run app.py
(Run the scripts in README order first so the models exist.)
"""

import json
from pathlib import Path

import altair as alt
import joblib
import pandas as pd
import streamlit as st

from explain import make_explainer, readable_values, shap_for, transform_for_shap
from failure_modes import MODE_NAMES, predict_modes
from preprocessing_pipeline import TARGET
from risk_levels import RECOMMENDATIONS, predict_risk

RAW_COLUMNS = ["Type", "Air temperature [K]", "Process temperature [K]",
               "Rotational speed [rpm]", "Torque [Nm]", "Tool wear [min]"]
LEVELS = ["Critical", "At Risk", "Healthy"]
# Show every bar label in full (Altair hides overlapping/long labels by default).
LABEL_AXIS = alt.Axis(labelOverlap=False, labelLimit=260)
# Status colours, always shown together with the level's name.
LEVEL_COLORS = {"Critical": "#d03b3b", "At Risk": "#fab219", "Healthy": "#0ca30c"}
LEVEL_ICONS = {"Critical": "🔴", "At Risk": "🟠", "Healthy": "🟢"}
UP_COLOR, DOWN_COLOR = "#e34948", "#2a78d6"

st.set_page_config(page_title="Predictive Maintenance", page_icon="🛠️",
                   layout="wide")


# ---------------------------------------------------------------------------
# Loading (cached so models load once, not on every click)
# ---------------------------------------------------------------------------
@st.cache_resource
def load_models():
    return {
        "final": joblib.load("models/final_model.joblib"),
        "thresholds": json.loads(Path("models/risk_thresholds.json").read_text()),
        "modes": joblib.load("models/failure_mode_models.joblib"),
        "rf": joblib.load("models/random_forest.joblib"),
    }


@st.cache_resource
def load_explainer():
    return make_explainer(load_models()["rf"])


@st.cache_data
def score_machines(df):
    """Probability, risk level, recommendation, likely cause and rank."""
    m = load_models()
    ranked = predict_risk(df[RAW_COLUMNS], m["final"], m["thresholds"])
    mode_probs = predict_modes(m["modes"], ranked[RAW_COLUMNS])
    ranked["likely_cause"] = mode_probs.idxmax(axis=1).map(MODE_NAMES)
    # A cause only makes sense for machines that are actually at risk.
    ranked.loc[ranked["risk_level"] == "Healthy", "likely_cause"] = "-"
    ranked["machine_id"] = df.loc[ranked.index, "machine_id"]
    if TARGET in df:
        ranked[TARGET] = df.loc[ranked.index, TARGET]
    return ranked, mode_probs


def load_data(source, upload):
    if source == "Upload CSV" and upload is not None:
        df = pd.read_csv(upload, encoding="utf-8-sig")
        missing = [c for c in RAW_COLUMNS if c not in df]
        if missing:
            st.error(f"Uploaded file is missing columns: {missing}")
            st.stop()
    else:
        df = pd.read_csv("data/test.csv")
    ids = df["Product ID"] if "Product ID" in df else \
        [f"M-{i:04d}" for i in range(1, len(df) + 1)]
    df = df.reset_index(drop=True)
    df["machine_id"] = list(ids)
    return df


def explain_machine(row):
    """SHAP contributions for one machine, with values in real units."""
    rf = load_models()["rf"]
    Xt = transform_for_shap(rf, row[RAW_COLUMNS])
    sv = shap_for(load_explainer(), Xt)
    values = readable_values(rf, row[RAW_COLUMNS], Xt.columns).iloc[0]
    out = pd.DataFrame({"feature": Xt.columns, "value": values.values,
                        "contribution": sv.values[0]})
    out["label"] = out["feature"] + " = " + out["value"].map("{:g}".format)
    out["effect"] = out["contribution"].map(
        lambda c: "Raises risk" if c > 0 else "Lowers risk")
    return out.reindex(out["contribution"].abs().sort_values(ascending=False).index)


def contribution_chart(contrib, top=8):
    data = contrib.head(top)
    return alt.Chart(data).mark_bar(cornerRadius=3, height=16).encode(
        x=alt.X("contribution:Q", title="Contribution to failure risk score"),
        y=alt.Y("label:N", sort=None, title=None, axis=LABEL_AXIS),
        color=alt.Color("effect:N", title=None,
                        scale=alt.Scale(domain=["Raises risk", "Lowers risk"],
                                        range=[UP_COLOR, DOWN_COLOR]),
                        legend=alt.Legend(orient="top")),
        tooltip=["feature", "value", alt.Tooltip("contribution:Q", format="+.3f")],
    ).properties(height=36 * len(data))


def level_badge(level):
    return f"{LEVEL_ICONS[level]} **{level}**"


def show_machine_detail(row, mode_row):
    level = row["risk_level"].iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Failure probability", f"{row['failure_probability'].iloc[0]:.1%}")
    c2.markdown(f"Risk level  \n### {LEVEL_ICONS[level]} {level}")
    c3.markdown(f"Recommended action  \n{RECOMMENDATIONS[level]}")

    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Why this score?** Top factors (SHAP)")
        st.altair_chart(contribution_chart(explain_machine(row)),
                        width="stretch")
    with right:
        st.markdown("**Failure-mode probabilities**")
        modes = (mode_row.rename(MODE_NAMES).sort_values(ascending=False)
                 .rename("probability").reset_index()
                 .rename(columns={"index": "mode"}))
        st.altair_chart(
            alt.Chart(modes).mark_bar(cornerRadius=3, height=16,
                                      color="#eb6834").encode(
                x=alt.X("probability:Q", scale=alt.Scale(domain=[0, 1]),
                        axis=alt.Axis(format="%"), title=None),
                y=alt.Y("mode:N", sort=None, title=None, axis=LABEL_AXIS),
                tooltip=["mode", alt.Tooltip("probability:Q", format=".1%")],
            ).properties(height=36 * len(modes)),
            width="stretch",
        )


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("🛠️ Data source")
source = st.sidebar.radio("Machines to analyse",
                          ["Test set (2,000 machines)", "Upload CSV"])
upload = None
if source == "Upload CSV":
    upload = st.sidebar.file_uploader(
        "CSV with the raw AI4I columns", type="csv",
        help="Needs: " + ", ".join(RAW_COLUMNS))
thresholds = load_models()["thresholds"]
st.sidebar.markdown(
    f"**Risk thresholds** (chosen on training data)  \n"
    f"🔴 Critical: p ≥ {thresholds['t_critical']:.3f}  \n"
    f"🟠 At Risk: p ≥ {thresholds['t_risk']:.3f}  \n"
    f"🟢 Healthy: below {thresholds['t_risk']:.3f}")

df = load_data(source, upload)
ranked, mode_probs = score_machines(df)

# ---------------------------------------------------------------------------
# Header + KPIs
# ---------------------------------------------------------------------------
st.title("Predictive Maintenance Intelligence System")
st.caption("Explainable machine-failure prediction on the UCI AI4I 2020 dataset")

counts = ranked["risk_level"].value_counts().reindex(LEVELS, fill_value=0)
k = st.columns(6)
k[0].metric("Total machines analysed", f"{len(ranked):,}")
k[1].metric("🟢 Healthy", f"{counts['Healthy']:,}")
k[2].metric("🟠 At risk", f"{counts['At Risk']:,}")
k[3].metric("🔴 Predicted critical", f"{counts['Critical']:,}")
if TARGET in ranked:
    k[4].metric("Actual failure rate", f"{ranked[TARGET].mean():.2%}")
else:
    k[4].metric("Predicted critical rate", f"{counts['Critical'] / len(ranked):.2%}")
k[5].metric("Avg failure probability", f"{ranked['failure_probability'].mean():.2%}")

tab_overview, tab_rank, tab_machine, tab_whatif, tab_perf = st.tabs(
    ["Overview", "Priority ranking", "Machine explanation",
     "What-if simulator", "Model performance"])

# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
with tab_overview:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Machines by risk level")
        dist = counts.rename("machines").reset_index()
        st.altair_chart(
            alt.Chart(dist).mark_bar(cornerRadius=3, height=28).encode(
                x=alt.X("machines:Q", title="Machines"),
                y=alt.Y("risk_level:N", sort=LEVELS, title=None),
                color=alt.Color("risk_level:N", legend=None,
                                scale=alt.Scale(domain=LEVELS,
                                                range=list(LEVEL_COLORS.values()))),
                tooltip=["risk_level", "machines"],
            ).properties(height=170)
            + alt.Chart(dist).mark_text(align="left", dx=4, color="gray").encode(
                x="machines:Q", y=alt.Y("risk_level:N", sort=LEVELS),
                text="machines:Q"),
            width="stretch",
        )
        if TARGET in ranked:
            st.markdown("**Real failure rate in each level** (labels available)")
            check = (ranked.groupby("risk_level")[TARGET]
                     .agg(machines="count", real_failures="sum",
                          failure_rate="mean").reindex(LEVELS))
            check["failure_rate"] = check["failure_rate"].map("{:.1%}".format)
            st.dataframe(check, width="stretch")

    with c2:
        st.subheader("Most important failure factors")
        imp = pd.read_csv("results/explain/shap_importance.csv")
        st.altair_chart(
            alt.Chart(imp).mark_bar(cornerRadius=3, height=14,
                                    color=DOWN_COLOR).encode(
                x=alt.X("mean_abs_shap:Q", title="Mean |SHAP value|"),
                y=alt.Y("feature:N", sort=None, title=None, axis=LABEL_AXIS),
                tooltip=["feature", alt.Tooltip("mean_abs_shap:Q", format=".3f")],
            ).properties(height=320),
            width="stretch",
        )

    at_risk = ranked[ranked["risk_level"] != "Healthy"]
    if len(at_risk):
        st.subheader("Likely cause among At Risk and Critical machines")
        causes = (at_risk.groupby(["likely_cause", "risk_level"]).size()
                  .rename("machines").reset_index())
        st.altair_chart(
            alt.Chart(causes).mark_bar(cornerRadius=3, height=18).encode(
                x=alt.X("machines:Q", stack=True, title="Machines"),
                y=alt.Y("likely_cause:N", title=None,
                        sort=alt.EncodingSortField("machines", "sum", "descending")),
                color=alt.Color("risk_level:N", title="Risk level",
                                scale=alt.Scale(domain=LEVELS[:2],
                                                range=[LEVEL_COLORS["Critical"],
                                                       LEVEL_COLORS["At Risk"]])),
                tooltip=["likely_cause", "risk_level", "machines"],
            ).properties(height=40 * causes["likely_cause"].nunique()),
            width="stretch",
        )

# ---------------------------------------------------------------------------
# Priority ranking
# ---------------------------------------------------------------------------
with tab_rank:
    st.subheader("Maintenance priority ranking")
    chosen = st.multiselect("Show risk levels", LEVELS, default=LEVELS[:2])
    view = ranked[ranked["risk_level"].isin(chosen)]
    cols = (["priority_rank", "machine_id", "failure_probability", "risk_level",
             "likely_cause", "recommendation"] + RAW_COLUMNS
            + ([TARGET] if TARGET in ranked else []))
    table = view[cols].copy()
    table["risk_level"] = table["risk_level"].map(lambda l: f"{LEVEL_ICONS[l]} {l}")
    st.dataframe(
        table, width="stretch", hide_index=True, height=480,
        column_config={"failure_probability": st.column_config.ProgressColumn(
            "Failure probability", format="percent", min_value=0, max_value=1)},
    )
    st.download_button("Download ranking as CSV",
                       view[cols].to_csv(index=False), "maintenance_priority.csv")

# ---------------------------------------------------------------------------
# Machine explanation
# ---------------------------------------------------------------------------
with tab_machine:
    st.subheader("Explain one machine")
    options = ranked["machine_id"].tolist()
    picked = st.selectbox(
        "Machine (sorted by priority)", options,
        format_func=lambda m: (f"#{int(ranked.loc[ranked.machine_id == m, 'priority_rank'].iloc[0])}"
                               f"  {m}  ({ranked.loc[ranked.machine_id == m, 'risk_level'].iloc[0]})"))
    row = ranked[ranked["machine_id"] == picked]
    show_machine_detail(row, mode_probs.loc[row.index[0]])
    st.markdown("**Sensor readings**")
    st.dataframe(row[RAW_COLUMNS], hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# What-if simulator
# ---------------------------------------------------------------------------
with tab_whatif:
    st.subheader("What-if simulator")
    st.caption("Change operating conditions and see how the risk responds.")
    s1, s2, s3 = st.columns(3)
    machine = pd.DataFrame([{
        "Type": s1.selectbox("Product quality Type", ["L", "M", "H"]),
        "Air temperature [K]": s1.slider("Air temperature [K]", 295.0, 305.0, 300.0, 0.1),
        "Process temperature [K]": s2.slider("Process temperature [K]", 305.0, 314.0, 310.0, 0.1),
        "Rotational speed [rpm]": s2.slider("Rotational speed [rpm]", 1150, 2900, 1500, 10),
        "Torque [Nm]": s3.slider("Torque [Nm]", 3.0, 77.0, 40.0, 0.5),
        "Tool wear [min]": s3.slider("Tool wear [min]", 0, 255, 100, 1),
    }])
    m = load_models()
    sim = predict_risk(machine, m["final"], m["thresholds"])
    sim_modes = predict_modes(m["modes"], machine).iloc[0]
    show_machine_detail(sim, sim_modes)

# ---------------------------------------------------------------------------
# Model performance
# ---------------------------------------------------------------------------
with tab_perf:
    st.subheader("Model comparison (test set, threshold 0.5)")
    comp = pd.read_csv("results/model_comparison.csv")
    st.dataframe(comp.round(3), hide_index=True, width="stretch")
    st.caption("Models were compared by cross-validated PR-AUC on the training "
               "set; Random Forest was chosen and then calibrated.")
    st.subheader("Failure-mode models (test set)")
    st.dataframe(pd.read_csv("results/failure_mode_results.csv").round(3),
                 hide_index=True, width="stretch")
    st.subheader("Explainability plots")
    e1, e2 = st.columns(2)
    e1.image("results/explain/03_shap_beeswarm.png")
    e2.image("results/explain/01_permutation_importance.png")
