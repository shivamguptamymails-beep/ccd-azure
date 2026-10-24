"""
Predictive Maintenance: cloud dashboard (Streamlit).

A thin client for the FastAPI service on Azure Container Apps. It holds no
models: scores, explanations, metadata and prediction history all come from
the API over HTTPS, and the cloud pages read Azure Monitor, Application
Insights, Resource Manager and Blob Storage with the app's managed identity
(see azure_ops.py).

Pages: Overview · Predict · Fleet · History · Model registry · Cloud ops

Run locally:  API_URL=http://localhost:8000 streamlit run frontend/dashboard.py
"""

import concurrent.futures as cf
import os
import threading
import time

import altair as alt
import numpy as np
import pandas as pd
import requests
import streamlit as st

import azure_ops
import ui

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
AZURE_REGION = os.environ.get("AZURE_REGION", "")
PORTAL_URL = os.environ.get("PORTAL_URL", "")
TELEMETRY = bool(os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"))
REQUEST_TIMEOUT = 120  # the API can take ~50 s to cold start
WIDE = "stretch"

RAW_COLUMNS = ["Type", "Air temperature [K]", "Process temperature [K]",
               "Rotational speed [rpm]", "Torque [Nm]", "Tool wear [min]"]
NUMERIC_RANGES = {  # what-if sweep bounds, inside the API's validation limits
    "Air temperature [K]": (295.0, 305.0),
    "Process temperature [K]": (305.0, 314.0),
    "Rotational speed [rpm]": (1150.0, 2800.0),
    "Torque [Nm]": (5.0, 75.0),
    "Tool wear [min]": (0.0, 250.0),
}
PROB_COLUMN = st.column_config.ProgressColumn("Failure prob.", min_value=0.0, max_value=1.0,
                                              format="percent")

st.set_page_config(page_title="Predictive Maintenance", page_icon="🛠️", layout="wide")
ui.inject_css()

# Ship the dashboard's own traces to Application Insights when running on Azure.
if TELEMETRY:
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        @st.cache_resource
        def _enable_telemetry():
            configure_azure_monitor(logger_name="pm_dashboard")
            return True

        _enable_telemetry()
    except Exception:  # telemetry must never break the UI
        pass


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------
class ApiError(Exception):
    pass


def api(method: str, path: str, **kwargs):
    """Call the API; returns (json, round_trip_ms, server_ms)."""
    start = time.perf_counter()
    try:
        r = requests.request(method, f"{API_URL}{path}", timeout=REQUEST_TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise ApiError(f"Cannot reach the API at {API_URL}: {exc}") from exc
    rtt = (time.perf_counter() - start) * 1000
    if not r.ok:
        raise ApiError(f"{r.status_code} from {path}: {r.text[:300]}")
    return r.json(), rtt, float(r.headers.get("X-Process-Time-Ms", "nan"))


def payload(row: dict) -> dict:
    out = {col: row[col] for col in RAW_COLUMNS}
    if row.get("machine_id"):
        out["machine_id"] = str(row["machine_id"])
    return out


def waking(label: str):
    return st.spinner(f"{label}… the first call after idle can take up to a minute "
                      "while Azure starts a replica and loads the models.")


@st.cache_data(ttl=15, show_spinner=False)
def api_status() -> dict:
    """Fast, non-blocking health check for the sidebar."""
    try:
        r = requests.get(f"{API_URL}/ready", timeout=3)
        return {"state": "ready", **r.json()} if r.ok else {"state": "starting"}
    except requests.RequestException:
        # Scaled to zero: poke it in the background so it is warm by the next click.
        threading.Thread(target=lambda: requests.get(f"{API_URL}/health", timeout=90),
                         daemon=True).start()
        return {"state": "asleep"}


@st.cache_data(ttl=300, show_spinner=False)
def model_metadata() -> dict:
    return api("GET", "/model/metadata")[0]


@st.cache_data(ttl=30, show_spinner=False)
def history(limit: int, machine_id: str | None = None, risk_level: str | None = None) -> dict:
    params = {"limit": limit}
    if machine_id:
        params["machine_id"] = machine_id
    if risk_level:
        params["risk_level"] = risk_level
    return api("GET", "/history", params=params)[0]


def history_frame(records: list[dict]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    df = pd.json_normalize(records)
    df["time"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    df.columns = [c.removeprefix("inputs.") for c in df.columns]
    return df


def safe(fn, *args, **kwargs):
    """(result, error) - cloud panels degrade to a message instead of a traceback."""
    try:
        return fn(*args, **kwargs), None
    except Exception as exc:  # noqa: BLE001 - any SDK/HTTP failure is shown to the user
        return None, f"{type(exc).__name__}: {str(exc)[:300]}"


def thresholds() -> dict | None:
    meta = safe(model_metadata)[0]
    return meta["thresholds"] if meta else None


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------
def sample_fleet(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    air = rng.normal(300, 2, n).clip(295, 305)
    return pd.DataFrame({
        "machine_id": [f"M-{i + 1:04d}" for i in range(n)],
        "Type": rng.choice(["L", "M", "H"], n, p=[0.6, 0.3, 0.1]),
        "Air temperature [K]": air.round(1),
        "Process temperature [K]": (air + 10 + rng.normal(0, 1, n)).clip(305, 315).round(1),
        "Rotational speed [rpm]": rng.normal(1500, 180, n).clip(1100, 2800).round(),
        "Torque [Nm]": rng.normal(40, 10, n).clip(5, 80).round(1),
        "Tool wear [min]": rng.integers(0, 250, n),
    })


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def sidebar() -> None:
    status = api_status()
    with st.sidebar:
        st.markdown("### 🛠️ Predictive Maintenance")
        st.caption("AI4I 2020 · Azure Container Apps")
        if status["state"] == "ready":
            label = ui.pill("● API online", "Healthy")
            detail = (f"model {status.get('model_version', '?')} · "
                      f"loaded from {status.get('model_source', '?')}")
        elif status["state"] == "asleep":
            label = ui.pill("● API waking up", "AtRisk")
            detail = "Scaled to zero; a replica is starting. Refresh in about a minute."
        else:
            label = ui.pill("● API starting", "AtRisk")
            detail = "Models are loading."
        st.markdown(f'<div class="side-status">{label}<small>{detail}</small>'
                    f'<small>{API_URL}</small></div>', unsafe_allow_html=True)
        if st.button("Refresh status", width=WIDE, type="tertiary"):
            api_status.clear()
            st.rerun()
        st.caption("🌗 Light / dark mode: **⋮ → Settings → App theme**")


# ---------------------------------------------------------------------------
# Page: Overview
# ---------------------------------------------------------------------------
def page_overview():
    ui.hero("Fleet health at a glance",
            "Failure-risk scoring, root cause and explanations served from Azure, "
            "with every prediction logged to Cosmos DB.", "Overview")
    status = api_status()
    hist, hist_err = safe(history, 1000)
    df = history_frame(hist["records"]) if hist else pd.DataFrame()
    logging_on = bool(hist and hist["enabled"])

    k = st.columns(4)
    k[0].metric("API", {"ready": "Online", "asleep": "Waking"}.get(status["state"], "Starting"))
    k[1].metric("Serving model", status.get("model_version", "–"),
                f"from {status.get('model_source', '–')}", delta_color="off")
    if not df.empty:
        last_day = df[df["time"] > pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=24)]
        k[2].metric("Predictions (24 h)", f"{len(last_day):,}")
        k[3].metric("Critical (24 h)", int((last_day["risk_level"] == "Critical").sum()))
    else:
        k[2].metric("Predictions (24 h)", "0" if logging_on else "–")
        k[3].metric("Critical (24 h)", "0" if logging_on else "–")

    st.markdown("#### Azure services")
    cfg = azure_ops.configured()
    blob_state = ("on" if status.get("model_source") == "blob"
                  else "warn" if cfg["registry"] else "off")
    ui.chips([
        ("Container Apps", "API + dashboard, KEDA HTTP autoscaling", "on"),
        ("Container Registry", "Images pulled via managed identity", "on"),
        ("Key Vault", "Secrets referenced, never in code", "on"),
        ("Cosmos DB", "Prediction log (serverless)", "on" if logging_on else "off"),
        ("Blob Storage", "Versioned model registry", blob_state),
        ("App Insights", "Traces & request telemetry", "on" if TELEMETRY else "off"),
        ("Azure Monitor", "Replica metrics & alerts", "on" if cfg["metrics"] else "off"),
    ])

    left, right = st.columns([3, 2])
    with left, st.container(border=True):
        st.markdown("**Machines needing attention** · latest reading per machine")
        if hist_err:
            st.info(f"History unavailable: {hist_err}")
        elif df.empty:
            st.caption("No predictions logged yet. Score a machine or a fleet to fill this.")
        else:
            latest = (df.sort_values("time").groupby("machine_id").tail(1)
                      .sort_values("failure_probability", ascending=False))
            attention = latest[latest["risk_level"] != "Healthy"].head(10)
            if attention.empty:
                st.success("Every machine's latest reading is healthy.")
            else:
                st.dataframe(
                    attention[["machine_id", "risk_level", "failure_probability",
                               "likely_cause", "time"]],
                    hide_index=True, width=WIDE,
                    column_config={
                        "failure_probability": PROB_COLUMN,
                        "time": st.column_config.DatetimeColumn("Last seen",
                                                                format="D MMM, HH:mm"),
                    })
    with right, st.container(border=True):
        st.markdown("**Risk mix of logged predictions**")
        if df.empty:
            st.caption("Nothing logged yet.")
        else:
            st.altair_chart(ui.level_donut(df["risk_level"]), width=WIDE)


# ---------------------------------------------------------------------------
# Page: Predict
# ---------------------------------------------------------------------------
def page_predict():
    ui.hero("Assess a machine",
            "Enter live sensor readings to get the failure probability, the likely cause, "
            "what drives the score and how it would change.", "Predict")

    inputs, results = st.columns([2, 3], gap="large")
    with inputs, st.form("reading"):
        st.markdown("**Sensor readings**")
        a, b = st.columns(2)
        machine_id = a.text_input("Machine ID", "M-0001")
        mtype = b.selectbox("Product type", ["L", "M", "H"],
                            help="Quality variant: L low, M medium, H high")
        air = st.slider("Air temperature [K]", 290.0, 320.0, 300.0, 0.1)
        proc = st.slider("Process temperature [K]", 295.0, 320.0, 310.0, 0.1)
        rpm = st.slider("Rotational speed [rpm]", 500, 3000, 1500, 10)
        torque = st.slider("Torque [Nm]", 0.0, 100.0, 40.0, 0.5)
        wear = st.slider("Tool wear [min]", 0, 260, 100)
        submitted = st.form_submit_button("Assess machine", type="primary", width=WIDE)

    row = {"machine_id": machine_id, "Type": mtype, "Air temperature [K]": air,
           "Process temperature [K]": proc, "Rotational speed [rpm]": float(rpm),
           "Torque [Nm]": torque, "Tool wear [min]": float(wear)}

    if submitted:
        try:
            with waking("Scoring"):
                result, rtt, server = api("POST", "/predict", json=payload(row))
                explanation = api("POST", "/explain", json=payload(row))[0]
            st.session_state["prediction"] = dict(row=row, result=result, rtt=rtt,
                                                  server=server, explanation=explanation)
            history.clear()
        except ApiError as exc:
            st.error(str(exc))

    pred = st.session_state.get("prediction")
    with results:
        if not pred:
            with st.container(border=True):
                st.markdown("**Result**")
                st.caption("Set the readings and press **Assess machine**. "
                           "Each assessment is logged to Cosmos DB.")
            return
        res = pred["result"]
        g, v = st.columns([1, 2])
        with g:
            st.altair_chart(ui.gauge(res["failure_probability"], res["risk_level"]))
        with v:
            ui.verdict(res)
            st.caption(f"{pred['row']['machine_id']} · round trip {pred['rtt']:.0f} ms · "
                       f"model compute {pred['server']:.0f} ms")

        why, modes, whatif = st.tabs(["Why this score", "Failure modes", "What-if"])
        with why:
            st.altair_chart(ui.contribution_chart(pred["explanation"]["contributions"]),
                            width=WIDE)
        with modes:
            st.altair_chart(ui.modes_chart(res["failure_mode_probabilities"]), width=WIDE)
        with whatif:
            whatif_panel(pred["row"])


def whatif_panel(row: dict):
    feature = st.selectbox("Vary one reading, hold the rest", list(NUMERIC_RANGES), index=4)
    lo, hi = NUMERIC_RANGES[feature]
    grid = np.linspace(lo, hi, 25).round(1)
    readings = [payload({**row, feature: float(x), "machine_id": f"whatif-{i}"})
                for i, x in enumerate(grid)]
    try:
        # log=false: a sweep is a hypothetical, not a real reading.
        data = api("POST", "/predict/batch", params={"log": "false"},
                   json={"readings": readings})[0]
    except ApiError as exc:
        st.error(str(exc))
        return
    df = pd.DataFrame(data["results"])
    df[feature] = df["machine_id"].str.removeprefix("whatif-").astype(int).map(
        dict(enumerate(grid)))
    limits = thresholds() or {"t_risk": 0.0, "t_critical": 0.0}
    st.altair_chart(ui.whatif_chart(df.sort_values(feature), feature, row[feature], limits),
                    width=WIDE)
    crit = df[df["risk_level"] == "Critical"]
    where = (f"Becomes **Critical** at {feature} ≈ {crit[feature].min():g}."
             if not crit.empty else "Stays below the Critical threshold across this range.")
    st.caption(f"{where} The black line marks the current value.")


# ---------------------------------------------------------------------------
# Page: Fleet
# ---------------------------------------------------------------------------
def page_fleet():
    ui.hero("Fleet priority list",
            "Score a whole fleet in one batch call and see which machines to service first.",
            "Fleet")
    with st.container(border=True):
        source = st.segmented_control("Data", ["Demo fleet", "Upload CSV"],
                                      default="Demo fleet") or "Demo fleet"
        df = None
        if source == "Upload CSV":
            up = st.file_uploader("CSV with columns: " + ", ".join(RAW_COLUMNS), type="csv")
            if up is not None:
                df = pd.read_csv(up, encoding="utf-8-sig")
                missing = [c for c in RAW_COLUMNS if c not in df]
                if missing:
                    st.error(f"Missing columns: {missing}")
                    return
                if "machine_id" not in df:
                    df.insert(0, "machine_id", [f"M-{i + 1:04d}" for i in range(len(df))])
        else:
            c1, c2 = st.columns(2)
            n = c1.slider("Machines", 10, 500, 100, 10)
            seed = c2.number_input("Random seed", 0, 9999, 42)
            df = sample_fleet(n, int(seed))
        log = st.toggle("Log results to Cosmos DB", value=True)
        go = st.button("Score fleet", type="primary", disabled=df is None)

    if go and df is not None:
        if len(df) > 2000:
            st.warning("Scoring the first 2,000 rows only.")
            df = df.head(2000)
        df = df.astype({"machine_id": str})
        body = {"readings": [payload(r) for r in df.to_dict("records")]}
        try:
            with waking("Scoring fleet"):
                data, rtt, _ = api("POST", "/predict/batch",
                                   params={"log": str(log).lower()}, json=body)
        except ApiError as exc:
            st.error(str(exc))
            return
        res = pd.DataFrame(data["results"]).drop(columns=["failure_mode_probabilities"])
        res = res.merge(df[["machine_id", *RAW_COLUMNS]], on="machine_id", how="left")
        st.session_state["fleet"] = (res, rtt)
        history.clear()

    if "fleet" not in st.session_state:
        return
    res, rtt = st.session_state["fleet"]
    k = st.columns(4)
    k[0].metric("Machines scored", f"{len(res):,}")
    k[1].metric("🔴 Critical", int((res["risk_level"] == "Critical").sum()))
    k[2].metric("🟠 At Risk", int((res["risk_level"] == "At Risk").sum()))
    k[3].metric("Batch latency", f"{rtt:.0f} ms", f"{rtt / len(res):.1f} ms / machine",
                delta_color="off")

    a, b = st.columns([2, 3])
    with a, st.container(border=True):
        st.markdown("**Risk distribution**")
        st.altair_chart(ui.level_donut(res["risk_level"]), width=WIDE)
    with b, st.container(border=True):
        st.markdown("**Tool wear vs torque**")
        st.altair_chart(ui.fleet_scatter(res), width=WIDE)

    with st.container(border=True):
        top, dl = st.columns([4, 1], vertical_alignment="bottom")
        levels = top.multiselect("Show", ui.LEVELS, default=["Critical", "At Risk"])
        dl.download_button("Download CSV", res.to_csv(index=False), "fleet_risk.csv",
                           "text/csv", width=WIDE)
        view = res[res["risk_level"].isin(levels)].sort_values("priority_rank")
        st.dataframe(
            view[["priority_rank", "machine_id", "risk_level", "failure_probability",
                  "likely_cause", "recommendation", *RAW_COLUMNS]],
            hide_index=True, width=WIDE,
            column_config={"priority_rank": st.column_config.NumberColumn("#"),
                           "failure_probability": PROB_COLUMN})


# ---------------------------------------------------------------------------
# Page: History (Cosmos DB)
# ---------------------------------------------------------------------------
def page_history():
    ui.hero("Prediction history",
            "Every assessment the API makes is written to Azure Cosmos DB (serverless) "
            "in the background, partitioned by machine.", "History · Cosmos DB")
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        machine = c1.text_input("Machine ID", placeholder="All machines").strip()
        level = c2.selectbox("Risk level", ["All", *ui.LEVELS])
        limit = c3.selectbox("Rows", [100, 250, 500, 1000], index=2)

    data, err = safe(history, limit, machine or None, None if level == "All" else level)
    if err:
        st.error(err)
        return
    if not data["enabled"]:
        st.info("Prediction logging is off: the API has no Cosmos DB connection configured.")
        return
    df = history_frame(data["records"])
    if df.empty:
        st.caption("No matching predictions yet.")
        return

    k = st.columns(4)
    k[0].metric("Predictions shown", f"{len(df):,}")
    k[1].metric("Machines", df["machine_id"].nunique())
    k[2].metric("Critical share", f"{(df['risk_level'] == 'Critical').mean():.1%}")
    k[3].metric("Newest", df["time"].max().strftime("%d %b %H:%M UTC"))

    with st.container(border=True):
        st.markdown("**Predictions per hour**")
        st.altair_chart(ui.history_timeline(df), width=WIDE)

    if machine:
        with st.container(border=True):
            st.markdown(f"**{machine} over time**")
            st.altair_chart(ui.machine_trend(df.sort_values("time"), thresholds()), width=WIDE)

    with st.container(border=True):
        cols = ["time", "machine_id", "risk_level", "failure_probability", "likely_cause",
                "endpoint", "model_version", *[c for c in RAW_COLUMNS if c in df]]
        st.dataframe(
            df[[c for c in cols if c in df]], hide_index=True, width=WIDE,
            column_config={
                "time": st.column_config.DatetimeColumn("Time (UTC)", format="D MMM, HH:mm:ss"),
                "failure_probability": PROB_COLUMN,
            })


# ---------------------------------------------------------------------------
# Page: Model registry (Blob Storage)
# ---------------------------------------------------------------------------
def page_model():
    ui.hero("Model registry",
            "Model versions live in Azure Blob Storage. The API downloads the version set by "
            "Terraform's model_version at startup, so shipping a model needs no image rebuild.",
            "Model · Blob Storage")
    meta, err = safe(model_metadata)
    if err:
        st.error(err)
        return

    k = st.columns(4)
    k[0].metric("Serving version", meta.get("model_version", "–"))
    k[1].metric("Loaded from", {"blob": "Blob Storage", "image": "Container image"}
                .get(meta.get("model_source"), "–"))
    k[2].metric("At Risk above", f"{meta['thresholds']['t_risk']:.1%}")
    k[3].metric("Critical above", f"{meta['thresholds']['t_critical']:.1%}")
    st.caption(f"Final model: {meta['final_model']}")

    with st.container(border=True):
        st.markdown("**Versions in the registry**")
        if not azure_ops.configured()["registry"]:
            st.caption("Set MODEL_STORAGE_ACCOUNT to list versions.")
        else:
            versions, verr = safe(azure_ops.model_versions)
            if verr:
                st.warning(f"Could not list blobs: {verr}")
            elif versions.empty:
                st.caption("No versions uploaded yet.")
            else:
                versions["serving"] = versions["version"] == meta.get("model_version")
                st.dataframe(
                    versions, hide_index=True, width=WIDE,
                    column_config={
                        "serving": st.column_config.CheckboxColumn("Serving"),
                        "size_mb": st.column_config.NumberColumn("Size (MB)", format="%.1f"),
                        "uploaded": st.column_config.DatetimeColumn(format="D MMM YYYY, HH:mm"),
                    })
            st.caption("To roll out a new version: upload a folder such as `v2/` with the same "
                       "files, set `model_version = \"v2\"` and run `terraform apply`.")

    if meta["model_comparison"]:
        comp = pd.DataFrame(meta["model_comparison"])
        with st.container(border=True):
            st.markdown("**Candidate models on the held-out test set**")
            metric = st.segmented_control(
                "Metric", ["pr_auc", "recall", "precision", "f1", "roc_auc"],
                default="pr_auc") or "pr_auc"
            st.altair_chart(
                alt.Chart(comp).mark_bar(cornerRadius=3).encode(
                    x=alt.X(f"{metric}:Q", scale=alt.Scale(domain=[0, 1]), title=metric),
                    y=alt.Y("model:N", sort="-x", title=None),
                    color=alt.condition(alt.datum.model == "Random Forest",
                                        alt.value(ui.ACCENT), alt.value(ui.TRACK)),
                    tooltip=["model", alt.Tooltip(f"{metric}:Q", format=".3f")],
                ).properties(height=190),
                width=WIDE)
            st.dataframe(comp, hide_index=True, width=WIDE)


# ---------------------------------------------------------------------------
# Page: Cloud ops
# ---------------------------------------------------------------------------
def one_request(i: int):
    row = sample_fleet(1, i).iloc[0].to_dict()
    start = time.perf_counter()
    try:
        ok = requests.post(f"{API_URL}/predict", json=payload(row), timeout=REQUEST_TIMEOUT).ok
    except requests.RequestException:
        ok = False
    return (time.perf_counter() - start) * 1000, ok


def page_cloud():
    ui.hero("Cloud operations",
            "Autoscaling, observability, alerting and deployments for the API on "
            "Azure Container Apps.", "Cloud ops")
    cfg = azure_ops.configured()
    top = st.columns(4, vertical_alignment="center")
    top[0].metric("Region", AZURE_REGION or "local")
    top[1].metric("Telemetry", "App Insights" if TELEMETRY else "off")
    top[2].metric("Azure Monitor access", "Yes" if cfg["metrics"] else "No")
    with top[3]:
        if PORTAL_URL:
            st.link_button("Open in Azure Portal ↗", PORTAL_URL, width=WIDE)
        st.link_button("API docs (Swagger) ↗", f"{API_URL}/docs", width=WIDE)

    scaling, observe, alerts, deploys = st.tabs(
        ["⚡ Autoscaling", "📈 Observability", "🔔 Alerts", "🚀 Deployments"])
    with scaling:
        scaling_tab(cfg)
    with observe:
        observability_tab(cfg)
    with alerts:
        alerts_tab(cfg)
    with deploys:
        deployments_tab(cfg)


def scaling_tab(cfg):
    a, b = st.columns([2, 3], gap="large")
    with a, st.container(border=True):
        st.markdown("**Load generator**")
        st.caption("KEDA adds replicas once concurrent requests per replica pass the "
                   "target set in Terraform (`concurrent_requests_per_replica`).")
        total = st.slider("Requests", 20, 1000, 300, 20)
        workers = st.slider("Concurrency", 1, 100, 50)
        run = st.button("Run load test", type="primary", width=WIDE)
        if st.button("Probe cold start (/ready)", width=WIDE):
            try:
                with waking("Waking API"):
                    data, rtt, _ = api("GET", "/ready")
                kind = "cold start" if rtt > 8000 else "warm"
                st.success(f"{data['status']} in {rtt / 1000:.1f} s ({kind})")
            except ApiError as exc:
                st.error(str(exc))

    with b:
        if run:
            bar = st.progress(0.0, "Sending requests…")
            latencies, failures, t0 = [], 0, time.perf_counter()
            with cf.ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(one_request, i) for i in range(total)]
                for i, fut in enumerate(cf.as_completed(futures), 1):
                    ms, ok = fut.result()
                    latencies.append(ms)
                    failures += not ok
                    bar.progress(i / total, f"{i}/{total} requests")
            bar.empty()
            st.session_state["load"] = (latencies, failures, time.perf_counter() - t0)
            history.clear()
        if "load" in st.session_state:
            latencies, failures, elapsed = st.session_state["load"]
            s = pd.Series(latencies)
            m = st.columns(4)
            m[0].metric("Throughput", f"{len(s) / elapsed:.1f} req/s")
            m[1].metric("p50", f"{s.quantile(.5):.0f} ms")
            m[2].metric("p95", f"{s.quantile(.95):.0f} ms")
            m[3].metric("Failures", failures)
            st.altair_chart(
                alt.Chart(pd.DataFrame({"latency_ms": latencies})).mark_bar(
                    color=ui.ACCENT, cornerRadius=2).encode(
                    x=alt.X("latency_ms:Q", bin=alt.Bin(maxbins=40), title="Latency (ms)"),
                    y=alt.Y("count()", title="Requests")).properties(height=190),
                width=WIDE)
        else:
            st.caption("Run a load test to see throughput and the latency distribution here.")

    with st.container(border=True):
        head, btn = st.columns([4, 1], vertical_alignment="center")
        head.markdown("**Replicas and requests** · Azure Monitor, last hour")
        btn.button("Refresh", key="refresh_replicas", width=WIDE)
        if not cfg["metrics"]:
            st.caption("Set API_RESOURCE_ID to chart live replicas.")
            return
        df, err = safe(azure_ops.replica_series, 60)
        if err:
            st.warning(f"Azure Monitor: {err}")
        elif df.empty:
            st.caption("No metric data yet; metrics lag by a minute or two.")
        else:
            reps = df[df["metric"] == "Replicas"]
            if not reps.empty:
                st.caption(f"Current replicas: **{int(reps['value'].iloc[-1])}** · "
                           f"peak this hour: **{int(reps['value'].max())}**")
            st.altair_chart(
                alt.Chart(df).mark_area(interpolate="step-after", opacity=.55).encode(
                    x=alt.X("time:T", title=None),
                    y=alt.Y("value:Q", title=None),
                    color=alt.Color("metric:N", legend=None,
                                    scale=alt.Scale(domain=["Replicas", "Requests"],
                                                    range=[ui.ACCENT, "#14b8a6"])),
                    tooltip=["time:T", "metric", "value"],
                ).properties(height=110).facet(
                    row=alt.Row("metric:N", title=None,
                                header=alt.Header(labelAngle=0, labelAlign="left")),
                ).resolve_scale(y="independent"))


def observability_tab(cfg):
    if not cfg["logs"]:
        st.caption("Set LOG_ANALYTICS_WORKSPACE_ID to query Application Insights.")
        return
    hours = st.segmented_control("Window", [1, 6, 24, 72], default=6,
                                 format_func=lambda h: f"{h} h", key="obs_window") or 6
    timeline, err = safe(azure_ops.request_timeline, hours)
    if err:
        st.warning(f"Log Analytics: {err}")
        return
    if timeline.empty:
        st.caption("No request telemetry in this window yet (ingestion lags 2–5 minutes).")
        return

    totals = timeline[["requests", "failed"]].sum()
    k = st.columns(4)
    k[0].metric("Requests", f"{int(totals['requests']):,}")
    k[1].metric("Failed", int(totals["failed"]))
    k[2].metric("Failure rate", f"{totals['failed'] / max(totals['requests'], 1):.2%}")
    k[3].metric("Worst p95", f"{timeline['p95_ms'].max():,.0f} ms")

    a, b = st.columns(2)
    color = alt.Color("AppRoleName:N", title=None, legend=alt.Legend(orient="bottom"),
                      scale=alt.Scale(range=[ui.ACCENT, "#14b8a6", "#f59e0b"]))
    with a, st.container(border=True):
        st.markdown("**Requests**")
        st.altair_chart(alt.Chart(timeline).mark_bar().encode(
            x=alt.X("TimeGenerated:T", title=None), y=alt.Y("requests:Q", title=None),
            color=color, tooltip=["TimeGenerated:T", "AppRoleName", "requests", "failed"],
        ).properties(height=220), width=WIDE)
    with b, st.container(border=True):
        st.markdown("**p95 latency (ms)**")
        st.altair_chart(alt.Chart(timeline).mark_line(point=True).encode(
            x=alt.X("TimeGenerated:T", title=None), y=alt.Y("p95_ms:Q", title=None),
            color=color, tooltip=["TimeGenerated:T", "AppRoleName",
                                  alt.Tooltip("p95_ms:Q", format=",.0f")],
        ).properties(height=220), width=WIDE)

    with st.container(border=True):
        st.markdown("**Busiest operations**")
        ops, err = safe(azure_ops.top_operations, hours)
        if err:
            st.warning(err)
        else:
            st.dataframe(ops, hide_index=True, width=WIDE)
    with st.expander("Recent exceptions"):
        exc, err = safe(azure_ops.recent_exceptions, hours)
        if err:
            st.warning(err)
        elif exc.empty:
            st.success("No exceptions in this window.")
        else:
            st.dataframe(exc, hide_index=True, width=WIDE)


def alerts_tab(cfg):
    if not cfg["metrics"]:
        st.caption("Set API_RESOURCE_ID to read alert rules.")
        return
    with st.container(border=True):
        st.markdown("**Alert rules**")
        rules, err = safe(azure_ops.alert_rules)
        if err:
            st.warning(err)
        elif rules.empty:
            st.caption("No metric alert rules in this resource group.")
        else:
            st.dataframe(rules, hide_index=True, width=WIDE)
    with st.container(border=True):
        st.markdown("**Fired in the last 30 days**")
        fired, err = safe(azure_ops.fired_alerts, 30)
        if err:
            st.warning(err)
        elif fired.empty:
            st.success("No alerts fired in the last 30 days.")
        else:
            st.dataframe(fired, hide_index=True, width=WIDE)


def deployments_tab(cfg):
    if not cfg["metrics"]:
        st.caption("Set API_RESOURCE_ID to read revisions.")
        return
    info, err = safe(azure_ops.app_overview, azure_ops.API_RESOURCE_ID)
    if err:
        st.warning(err)
        return
    k = st.columns(4)
    k[0].metric("Image tag", info["image"].rsplit(":", 1)[-1])
    k[1].metric("Status", info["running_status"] or "–")
    k[2].metric("Scale range", f"{info['min_replicas'] or 0}–{info['max_replicas']}")
    k[3].metric("Ready revision", (info["ready_revision"] or "–").rsplit("--", 1)[-1])
    with st.container(border=True):
        st.markdown("**Revisions**")
        revs, err = safe(azure_ops.revisions, azure_ops.API_RESOURCE_ID)
        if err:
            st.warning(err)
        else:
            st.dataframe(revs, hide_index=True, width=WIDE,
                         column_config={"created": st.column_config.DatetimeColumn(
                             format="D MMM YYYY, HH:mm")})
        st.caption("Each `terraform apply` that changes the image or settings creates a new "
                   "revision; CI rolls back to the previous tag if the smoke test fails.")


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
sidebar()
st.navigation([
    st.Page(page_overview, title="Overview", icon=":material/dashboard:", url_path="overview",
            default=True),
    st.Page(page_predict, title="Predict", icon=":material/precision_manufacturing:",
            url_path="predict"),
    st.Page(page_fleet, title="Fleet", icon=":material/factory:", url_path="fleet"),
    st.Page(page_history, title="History", icon=":material/history:", url_path="history"),
    st.Page(page_model, title="Model registry", icon=":material/model_training:",
            url_path="model"),
    st.Page(page_cloud, title="Cloud ops", icon=":material/cloud:", url_path="cloud"),
]).run()
