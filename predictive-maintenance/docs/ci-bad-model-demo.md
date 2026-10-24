# Demo: the pipeline blocks a bad model

Synopsis outcome 2: *"the CI/CD pipeline automatically blocking deployment of
a model version that fails accuracy validation."*

The gate is `tests/test_model_quality.py`. It scores `models/final_model.joblib`
on the held-out test set (2,000 machines) and fails if the Critical tier drops
below **precision 0.80, recall 0.70 or F1 0.80**.

## Expected results (measured locally)

| Model as `final_model.joblib` | Precision | Recall | F1 | Gate |
|---|---|---|---|---|
| Calibrated Random Forest (current) | 0.964 | 0.779 | 0.862 | PASS, deploys |
| Decision Tree | 0.389 | 0.824 | 0.528 | FAIL, blocked |
| Logistic Regression | 0.160 | 0.897 | 0.272 | FAIL, blocked |

The logistic regression is the "bad retrain": it catches failures but 84% of
its Critical alarms are false, which would send technicians to healthy machines.

## Steps (needs push access and the GitHub secrets)

1. Simulate a bad retrain by replacing the serving model with the weak one:

   ```bash
   cp models/logistic_regression.joblib models/final_model.joblib
   git commit -am "Demo: retrain regressed (logistic regression)"
   git push origin main
   ```

2. In GitHub, open **Actions**. The **Unit + model-quality tests** job fails with
   `Precision regressed: 0.160 < 0.8`. Build, deploy and smoke-test show as
   **skipped**, and the live API keeps serving the good model
   (`/ready` still reports the same version). Screenshot this run.

3. Restore the good model:

   ```bash
   git revert --no-edit HEAD
   git push origin main
   ```

   This run goes green end to end: tests, build, deploy, smoke test.
   Screenshot it as the "after".

Prefer not to touch `main`? Open the bad-model commit as a pull request
instead: pull requests run only the test job, so the red check appears on the
PR and nothing can deploy.
