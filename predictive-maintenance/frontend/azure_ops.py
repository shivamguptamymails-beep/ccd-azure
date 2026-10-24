"""
Read-only Azure helpers for the dashboard's cloud pages.

Everything authenticates with DefaultAzureCredential: the shared user-assigned
managed identity on Azure (AZURE_CLIENT_ID), or your `az login` locally. The
identity holds Monitoring Reader on the resource group and Storage Blob Data
Reader on the model storage account - nothing here can change a resource.

Each function raises on failure; the UI decides how to show the error.
"""

import os
from datetime import timedelta
from functools import lru_cache

import pandas as pd
import requests

API_RESOURCE_ID = os.environ.get("API_RESOURCE_ID", "")
WORKSPACE_ID = os.environ.get("LOG_ANALYTICS_WORKSPACE_ID", "")
MODEL_STORAGE_ACCOUNT = os.environ.get("MODEL_STORAGE_ACCOUNT", "")
MODEL_CONTAINER = os.environ.get("MODEL_CONTAINER", "models")
ARM = "https://management.azure.com"


def configured() -> dict[str, bool]:
    return {"metrics": bool(API_RESOURCE_ID), "logs": bool(WORKSPACE_ID),
            "registry": bool(MODEL_STORAGE_ACCOUNT)}


@lru_cache(maxsize=1)
def credential():
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential(
        managed_identity_client_id=os.environ.get("AZURE_CLIENT_ID"),
        exclude_interactive_browser_credential=True,
    )


def _scope() -> tuple[str, str]:
    """(subscription id, resource group name) parsed from the API resource id."""
    parts = API_RESOURCE_ID.strip("/").split("/")
    return parts[1], parts[3]


def _arm_get(path: str, api_version: str, **params) -> dict:
    token = credential().get_token(f"{ARM}/.default").token
    resp = requests.get(f"{ARM}{path}", params={"api-version": api_version, **params},
                        headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Azure Monitor metrics
# ---------------------------------------------------------------------------
def replica_series(minutes: int = 60) -> pd.DataFrame:
    from azure.monitor.query import MetricAggregationType, MetricsQueryClient

    client = MetricsQueryClient(credential())
    resp = client.query_resource(
        API_RESOURCE_ID, metric_names=["Replicas", "Requests"],
        timespan=timedelta(minutes=minutes), granularity=timedelta(minutes=1),
        aggregations=[MetricAggregationType.MAXIMUM, MetricAggregationType.TOTAL])
    frames = []
    for metric in resp.metrics:
        agg = "maximum" if metric.name == "Replicas" else "total"
        for series in metric.timeseries:
            frames.append(pd.DataFrame(
                [{"time": p.timestamp, "metric": metric.name, "value": getattr(p, agg) or 0}
                 for p in series.data]))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------------------
# Application Insights (workspace-based, queried through Log Analytics)
# ---------------------------------------------------------------------------
def _logs(query: str, hours: int) -> pd.DataFrame:
    from azure.monitor.query import LogsQueryClient, LogsQueryStatus

    resp = LogsQueryClient(credential()).query_workspace(
        WORKSPACE_ID, query, timespan=timedelta(hours=hours))
    if resp.status != LogsQueryStatus.SUCCESS:
        raise RuntimeError(getattr(resp, "partial_error", "Log query failed"))
    table = resp.tables[0]
    return pd.DataFrame(table.rows, columns=table.columns)


def request_timeline(hours: int) -> pd.DataFrame:
    bin_size = "5m" if hours <= 6 else "30m"
    return _logs(f"""
        AppRequests
        | summarize requests = count(),
                    failed = countif(Success == false),
                    p95_ms = percentile(DurationMs, 95)
          by bin(TimeGenerated, {bin_size}), AppRoleName
        | order by TimeGenerated asc""", hours)


def top_operations(hours: int) -> pd.DataFrame:
    return _logs("""
        AppRequests
        | summarize requests = count(),
                    failed = countif(Success == false),
                    p50_ms = round(percentile(DurationMs, 50), 0),
                    p95_ms = round(percentile(DurationMs, 95), 0)
          by service = AppRoleName, operation = Name
        | order by requests desc
        | take 15""", hours)


def recent_exceptions(hours: int) -> pd.DataFrame:
    return _logs("""
        AppExceptions
        | project TimeGenerated, service = AppRoleName, type = ExceptionType,
                  message = OuterMessage
        | order by TimeGenerated desc
        | take 20""", hours)


# ---------------------------------------------------------------------------
# Alerts and deployments (Azure Resource Manager)
# ---------------------------------------------------------------------------
def alert_rules() -> pd.DataFrame:
    sub, rg = _scope()
    body = _arm_get(f"/subscriptions/{sub}/resourceGroups/{rg}/providers/"
                    "Microsoft.Insights/metricAlerts", "2018-03-01")
    rows = []
    for rule in body.get("value", []):
        p = rule["properties"]
        crit = (p.get("criteria", {}).get("allOf") or [{}])[0]
        rows.append({
            "rule": rule["name"],
            "enabled": p.get("enabled"),
            "severity": f"Sev {p.get('severity')}",
            "condition": f"{crit.get('timeAggregation', '')} {crit.get('metricName', '')} "
                         f"{crit.get('operator', '')} {crit.get('threshold', '')}".strip(),
            "window": p.get("windowSize", ""),
            "description": p.get("description", ""),
        })
    return pd.DataFrame(rows)


def fired_alerts(days: int = 30) -> pd.DataFrame:
    sub, rg = _scope()
    time_range = "30d" if days > 7 else "7d"
    body = _arm_get(f"/subscriptions/{sub}/providers/Microsoft.AlertsManagement/alerts",
                    "2019-05-05-preview", targetResourceGroup=rg, timeRange=time_range)
    rows = []
    for alert in body.get("value", []):
        ess = alert["properties"]["essentials"]
        rows.append({
            "fired": ess.get("startDateTime"),
            "alert": alert["name"],
            "severity": ess.get("severity"),
            "state": ess.get("monitorCondition"),
            "status": ess.get("alertState"),
        })
    return pd.DataFrame(rows)


def app_overview(resource_id: str) -> dict:
    p = _arm_get(resource_id, "2024-03-01")["properties"]
    return {
        "image": p["template"]["containers"][0]["image"],
        "latest_revision": p.get("latestRevisionName"),
        "ready_revision": p.get("latestReadyRevisionName"),
        "running_status": p.get("runningStatus") or p.get("provisioningState"),
        "min_replicas": p["template"].get("scale", {}).get("minReplicas"),
        "max_replicas": p["template"].get("scale", {}).get("maxReplicas"),
        "fqdn": (p.get("configuration", {}).get("ingress") or {}).get("fqdn"),
    }


def revisions(resource_id: str) -> pd.DataFrame:
    body = _arm_get(f"{resource_id}/revisions", "2024-03-01")
    rows = []
    for rev in body.get("value", []):
        p = rev["properties"]
        rows.append({
            "revision": rev["name"],
            "created": p.get("createdTime"),
            "active": p.get("active"),
            "replicas": p.get("replicas"),
            "traffic_%": p.get("trafficWeight"),
            "health": p.get("healthState"),
            "image": p["template"]["containers"][0]["image"].split("/")[-1],
        })
    df = pd.DataFrame(rows)
    return df.sort_values("created", ascending=False) if not df.empty else df


# ---------------------------------------------------------------------------
# Blob Storage model registry
# ---------------------------------------------------------------------------
def model_versions() -> pd.DataFrame:
    """One row per version folder (blob prefix) in the models container."""
    from azure.storage.blob import ContainerClient

    container = ContainerClient(f"https://{MODEL_STORAGE_ACCOUNT}.blob.core.windows.net",
                                MODEL_CONTAINER, credential=credential())
    rows = [{"version": b.name.split("/")[0], "file": b.name.split("/", 1)[-1],
             "size_mb": b.size / 1e6, "modified": b.last_modified}
            for b in container.list_blobs() if "/" in b.name]
    if not rows:
        return pd.DataFrame(columns=["version", "files", "size_mb", "uploaded"])
    df = pd.DataFrame(rows)
    return (df.groupby("version")
              .agg(files=("file", "count"), size_mb=("size_mb", "sum"),
                   uploaded=("modified", "max"))
              .reset_index().sort_values("uploaded", ascending=False))
