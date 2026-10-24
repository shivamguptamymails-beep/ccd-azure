"""
Optional Azure integrations for the inference API.

  - Blob Storage model registry: models live under <container>/<version>/ and
    are downloaded at startup, so a new model version ships without a new image.
  - Cosmos DB prediction log: every scored machine is written to the
    prediction-logs container for audit, history and future retraining data.

Both are no-ops when their settings are absent, so local dev and the test
suite run without any Azure resources. Azure SDKs are imported lazily for
the same reason.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("predictive_maintenance_api")

MODEL_STORAGE_ACCOUNT = os.environ.get("MODEL_STORAGE_ACCOUNT")
MODEL_CONTAINER = os.environ.get("MODEL_CONTAINER", "models")
MODEL_FILES = [
    "final_model.joblib",
    "risk_thresholds.json",
    "failure_mode_models.joblib",
    "random_forest.joblib",
]
OPTIONAL_MODEL_FILES = ["model_comparison.csv"]

COSMOS_CONNECTION_STRING = os.environ.get("COSMOS_CONNECTION_STRING")
COSMOS_DATABASE = os.environ.get("COSMOS_DATABASE", "predictions")
COSMOS_CONTAINER = os.environ.get("COSMOS_CONTAINER", "prediction-logs")


def download_models(version: str, dest: Path) -> bool:
    """Fetch one model version from Blob Storage. False when not configured."""
    if not MODEL_STORAGE_ACCOUNT:
        return False
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import ContainerClient

    container = ContainerClient(
        f"https://{MODEL_STORAGE_ACCOUNT}.blob.core.windows.net",
        MODEL_CONTAINER,
        credential=DefaultAzureCredential(),
    )
    dest.mkdir(parents=True, exist_ok=True)
    for name in MODEL_FILES:
        (dest / name).write_bytes(container.download_blob(f"{version}/{name}").readall())
    for name in OPTIONAL_MODEL_FILES:
        blob = container.get_blob_client(f"{version}/{name}")
        if blob.exists():
            (dest / name).write_bytes(blob.download_blob().readall())
    logger.info("Downloaded model version %s from %s/%s", version,
                MODEL_STORAGE_ACCOUNT, MODEL_CONTAINER)
    return True


class PredictionLog:
    """Cosmos DB writer/reader; disabled when no connection string is set."""

    def __init__(self) -> None:
        self._container = None
        if not COSMOS_CONNECTION_STRING:
            return
        try:
            from azure.cosmos import CosmosClient

            client = CosmosClient.from_connection_string(COSMOS_CONNECTION_STRING)
            self._container = (client.get_database_client(COSMOS_DATABASE)
                               .get_container_client(COSMOS_CONTAINER))
            logger.info("Prediction logging to Cosmos DB %s/%s enabled",
                        COSMOS_DATABASE, COSMOS_CONTAINER)
        except Exception:
            logger.exception("Cosmos DB unavailable; prediction logging disabled")

    @property
    def enabled(self) -> bool:
        return self._container is not None

    def write(self, records: list[dict]) -> None:
        """Called as a background task, so it never adds latency to a prediction."""
        if not self.enabled:
            return
        timestamp = datetime.now(timezone.utc).isoformat()
        for record in records:
            try:
                self._container.create_item({"id": str(uuid.uuid4()),
                                             "timestamp": timestamp, **record})
            except Exception:
                logger.exception("Failed to log prediction for %s", record.get("machine_id"))

    def recent(self, limit: int, machine_id: str | None = None,
               risk_level: str | None = None) -> list[dict]:
        if not self.enabled:
            return []
        filters, params = [], [{"name": "@limit", "value": limit}]
        if machine_id:
            filters.append("c.machine_id = @machine_id")
            params.append({"name": "@machine_id", "value": machine_id})
        if risk_level:
            filters.append("c.risk_level = @risk_level")
            params.append({"name": "@risk_level", "value": risk_level})
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        scope = ({"partition_key": machine_id} if machine_id
                 else {"enable_cross_partition_query": True})
        items = self._container.query_items(
            f"SELECT TOP @limit * FROM c {where} ORDER BY c.timestamp DESC",
            parameters=params, **scope)
        return [{k: v for k, v in item.items() if not k.startswith("_")} for item in items]
