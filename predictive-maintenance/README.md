# Predictive Maintenance Intelligence System

Explainable machine-failure prediction on the UCI AI4I 2020 Predictive Maintenance dataset
(Machine Learning, CSE 3125 mini project).

## Setup

```
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
```

The dataset is in `data/ai4i2020.csv` (source: https://archive.ics.uci.edu/dataset/601).

## Run order

Each script depends on the outputs of the ones before it.

| # | Command | What it does | Outputs |
|---|---|---|---|
| 1 | `venv\Scripts\python preprocessing_pipeline.py` | Drops IDs and leakage columns, stratified split, builds the preprocessing Pipeline, prints a sanity report | `data/train.csv`, `data/test.csv`, `models/baseline_pipeline.joblib` |
| 2 | `venv\Scripts\python eda.py` | Exploratory data analysis plots and statistics | `results/eda/*.png` |
| 3 | `venv\Scripts\python train_models.py` | Trains and compares Logistic Regression, Decision Tree, Random Forest and XGBoost | `models/<model>.joblib`, `results/model_comparison.csv` |
| 4 | `venv\Scripts\python risk_levels.py` | Calibrates the Random Forest, chooses the Healthy / At Risk / Critical thresholds | `models/final_model.joblib`, `models/risk_thresholds.json`, `results/test_risk_predictions.csv` |
| 5 | `venv\Scripts\python failure_modes.py` | One model per failure mode (TWF, HDF, PWF, OSF, RNF) for the "likely cause" | `models/failure_mode_models.joblib`, `results/failure_mode_results.csv` |
| 6 | `venv\Scripts\python explain.py` | Permutation importance and SHAP explanations | `results/explain/*` |
| 7 | `venv\Scripts\streamlit run app.py` | Interactive dashboard at http://localhost:8501 | |

## Pipeline

```
Machine operating data
  -> preprocessing + feature engineering (temp_diff, power, torque x tool wear)
  -> calibrated Random Forest -> failure probability
  -> thresholds -> Healthy / At Risk / Critical
  -> failure-mode models + SHAP -> likely cause and explanation
  -> maintenance recommendation and priority ranking (dashboard)
```

## Key results (test set: 2,000 machines, 68 failures)

- Random Forest is the best model by cross-validated PR-AUC (0.889). Test: precision 0.93, recall 0.82, F1 0.88.
- Risk levels on the test set: Critical 55 machines (96.4% really failed), At Risk 182 (6.6%), Healthy 1,763 (0.2%).
  Critical and At Risk together catch 65 of the 68 failures.
- Heat-dissipation, power and overstrain failures are predicted almost perfectly. Tool-wear and random failures are hard to predict by design.

## Rules followed to avoid data leakage

- TWF, HDF, PWF, OSF and RNF are never inputs to the failure model (they are only used as targets in `failure_modes.py`).
- The scaler and encoder are fitted inside a Pipeline on training data only.
- The test set keeps the real failure rate and is never resampled.
- Models and thresholds are chosen with cross-validation on the training set. The test set is only used for the final check.

Note: the saved models contain the `FeatureEngineer` class, so any script that loads them must be able to import `preprocessing_pipeline.py`.

## Cloud deployment (Azure + Terraform)

The models above are also served as a stateless REST API, deployed on Azure
Container Apps with automatic scaling. This layer is entirely additive -
`app.py` and the training scripts are unchanged.

| Path | What it is |
|---|---|
| `api/` | FastAPI service (`/predict`, `/predict/batch`, `/explain`, `/model/metadata`, `/health`, `/ready`) |
| `Dockerfile`, `requirements-api.txt` | Serving-only container image (no xgboost/streamlit/dev tooling) |
| `infra/` | Terraform: Container Apps, ACR, Key Vault, Storage, Cosmos DB, API Management, Monitor (see `infra/README.md`) |
| `.github/workflows/ci-cd.yml` | Test → build/push → Terraform apply → health check → auto-rollback |
| `tests/test_model_quality.py` | CI gate: blocks deploy if precision/recall/F1 regress below baseline |
| `load_test/locustfile.py` | Drives traffic to trigger and demo auto-scaling |

Run the API locally:

```
pip install -r requirements-api.txt
uvicorn api.main:app --reload
```

Build and run the container:

```
docker build -t pmaint-api .
docker run -p 8000:8000 pmaint-api
```

Full architecture, design rationale and deployment steps: see
`Predictive_Maintenance_Intelligence_System_Synopsis.docx` and `infra/README.md`.

