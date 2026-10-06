"""
Load test for the demo: drives enough concurrent /predict traffic against
the deployed Container App to trigger the KEDA HTTP scale rule
(concurrent_requests_per_replica in infra/variables.tf), then stops so the
audience can watch replica count scale back down to min_replicas.

Run against the deployed API:
    locust -f load_test/locustfile.py --host https://<container-app-fqdn>

Headless, fixed duration (good for a timed demo):
    locust -f load_test/locustfile.py --host https://<container-app-fqdn> \
        --headless --users 200 --spawn-rate 20 --run-time 3m

Watch scaling live in another terminal:
    az containerapp revision list -n ca-pmaint-dev -g rg-pmaint-dev \
        --query "[].{replicas:properties.replicas}" -o table
"""

import random

from locust import HttpUser, between, task

TYPES = ["L", "M", "H"]


def random_reading():
    return {
        "Type": random.choice(TYPES),
        "Air temperature [K]": round(random.uniform(295.0, 304.0), 1),
        "Process temperature [K]": round(random.uniform(305.0, 313.0), 1),
        "Rotational speed [rpm]": random.randint(1150, 2900),
        "Torque [Nm]": round(random.uniform(3.0, 77.0), 1),
        "Tool wear [min]": random.randint(0, 255),
    }


class InferenceUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(5)
    def predict(self):
        self.client.post("/predict", json=random_reading(), name="/predict")

    @task(1)
    def predict_batch(self):
        batch = {"readings": [random_reading() for _ in range(10)]}
        self.client.post("/predict/batch", json=batch, name="/predict/batch")

    @task(1)
    def explain(self):
        self.client.post("/explain", json=random_reading(), name="/explain")

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")
