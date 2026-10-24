"""
Stepped capacity test: the same traffic mix as locustfile.py, but the user
count climbs in stages (and then drops to zero) so one run shows where the
API stays healthy, how replicas scale out with each step, and how they scale
back in afterwards.

    locust -f load_test/step_load.py --host https://<container-app-fqdn> \
        --headless --csv load_test/results/step --csv-full-history

Each stage holds long enough (3 min) for KEDA to react and new replicas to
finish loading the models, so the later part of each stage shows the
scaled-out steady state rather than the transition.
"""

from locust import LoadTestShape

from locustfile import InferenceUser  # noqa: F401  (Locust discovers the user class here)

# (users, seconds at that level)
STAGES = [(20, 180), (50, 180), (100, 180)]
SPAWN_RATE = 5


class StepShape(LoadTestShape):
    def tick(self):
        elapsed = self.get_run_time()
        end = 0
        for users, duration in STAGES:
            end += duration
            if elapsed < end:
                return users, SPAWN_RATE
        return None  # stop: the scale-in afterwards is watched separately
