"""
Azure Function: Critical-prediction notifier (the synopsis's "Lambda" module).

Event-driven and serverless: it runs only when the API writes predictions to
Cosmos DB. The Cosmos DB change feed delivers each batch of new documents;
for every Critical one it emits a structured CRITICAL_PREDICTION log event.
Application Insights stores the event, and a log alert (infra/modules/functions)
emails the on-call address through the shared Azure Monitor action group.

Keeping the notification out of the API means scoring latency never depends
on alerting, and alerting keeps working however the API is scaled.
"""

import logging

import azure.functions as func

app = func.FunctionApp()
logger = logging.getLogger("critical_notifier")


@app.cosmos_db_trigger(
    arg_name="documents",
    connection="COSMOS_CONNECTION",
    database_name="predictions",
    container_name="prediction-logs",
    lease_container_name="leases",
    create_lease_container_if_not_exists=True,
)
def critical_notifier(documents: func.DocumentList) -> None:
    critical = [d for d in documents if d.get("risk_level") == "Critical"]
    for doc in critical:
        logger.warning(
            "CRITICAL_PREDICTION machine=%s probability=%.3f cause=%s endpoint=%s model=%s",
            doc.get("machine_id"), float(doc.get("failure_probability", 0.0)),
            doc.get("likely_cause"), doc.get("endpoint"), doc.get("model_version"),
        )
    logger.info("Processed %d prediction(s), %d critical", len(documents), len(critical))
