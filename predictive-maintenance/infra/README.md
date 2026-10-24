# Infrastructure (Terraform, Azure)

Modular Terraform for deploying the Predictive Maintenance API to Azure
Container Apps with auto-scaling, a managed API gateway, versioned model
storage, prediction logging, Key Vault-backed secrets and monitoring/alerting.

```
infra/
  providers.tf              # azurerm + random providers, remote state backend
  variables.tf               # all tunables (region, scaling, feature flags...)
  main.tf                     # wires the modules together
  outputs.tf
  terraform.tfvars.example
  modules/
    core/            # resource group, Log Analytics, Application Insights
    registry/        # Azure Container Registry
    identity/        # user-assigned managed identity + AcrPull role
    container_app/   # Container Apps Environment + the API, KEDA HTTP autoscaling
    data/            # Blob Storage (model artifacts) + Cosmos DB (prediction logs)
    keyvault/        # Key Vault (RBAC) holding connection strings
    gateway/         # Azure API Management (Consumption tier) - optional
    monitoring/      # Action Group + metric alerts (scaled-to-max, restarts)
```

## One-time setup

1. **Terraform state storage** (create once, by hand or a small bootstrap
   script - not managed by this config, to avoid a chicken-and-egg problem):
   a resource group + storage account + blob container for remote state.
2. **GitHub Actions identity (OIDC)** - run once after the first deploy:

   ```bash
   bash infra/scripts/setup-github-oidc.sh <github-owner>/<repo>
   ```

   It creates a user-assigned managed identity (app registrations are often
   blocked on student tenants) trusted for this repo's `main` branch and
   `production` environment (no client secret), grants it Contributor + User
   Access Administrator on the resource group, Contributor on the state
   resource group, AcrPush and Key Vault Secrets Officer, then prints the
   secrets to add.
3. **GitHub repository secrets**: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
   `AZURE_SUBSCRIPTION_ID`, `ACR_LOGIN_SERVER`, `ALERT_EMAIL`,
   `TFSTATE_RESOURCE_GROUP`, `TFSTATE_STORAGE_ACCOUNT`; plus an environment
   named `production`.

The workflow lives at the repository root (`.github/workflows/ci-cd.yml`) -
GitHub ignores workflows inside sub-folders. Because `terraform.tfvars` is
gitignored, the workflow pins every non-default setting (`location`,
`cosmos_location`, replica limits, `model_version`) as `TF_VAR_*`; keep those
in step with your local `terraform.tfvars`.

## Deploying by hand (first deploy, or local iteration)

```bash
az login
cd infra
terraform init \
  -backend-config="resource_group_name=<tfstate-rg>" \
  -backend-config="storage_account_name=<tfstate-storage-account>" \
  -backend-config="container_name=tfstate" \
  -backend-config="key=predictive-maintenance.tfstate"

cp terraform.tfvars.example terraform.tfvars   # fill in publisher_email at least
terraform plan
terraform apply -target=module.registry
```

The targeted first apply creates the registry and its dependencies. Build
and push the image before the full apply so the app can pull a valid image:

```bash
az acr login --name <acr-name>
docker build -t <acr-login-server>/predictive-maintenance-api:bootstrap ..
docker push <acr-login-server>/predictive-maintenance-api:bootstrap
terraform apply -var "image_tag=bootstrap"
```

Keep the deployed `image_tag` in your local `terraform.tfvars` for later
applies. Run a full `terraform plan` after bootstrap; targeted applies are
only for resolving this first-deployment dependency.

Student subscriptions can restrict regions. Check your subscription's
allowed locations before choosing `location`. If Cosmos DB reports regional
capacity exhaustion, set `cosmos_location` to another allowed region; other
resources continue using `location`.

The API uses one worker per replica for the default 0.5 vCPU allocation.
The startup probe allows model loading to finish before liveness checks
can restart the container; HTTP autoscaling still adds replicas under load.
The environment explicitly uses the standard Consumption workload profile,
which supports the direct Key Vault references required by this configuration.
An AzAPI update sets `environmentMode = WorkloadProfiles` before creating
the app, because AzureRM 3.x does not expose this newer Azure API field.

## Watching auto-scaling live

```bash
az containerapp revision list \
  -n ca-pmaint-dev -g rg-pmaint-dev \
  --query "[].{replicas:properties.replicas}" -o table
```

Run `load_test/locustfile.py` against `terraform output container_app_fqdn`
and watch replica count rise, then fall back to `min_replicas` once the load
test stops.

## Feature flags

- `enable_api_management` (default `false`): Azure API Management Consumption
  tier can take 20-40 minutes to provision. Turn it on for the gateway/
  auth/throttling demo; leave it off for fast iteration on the core
  Container Apps scaling story.
- `min_replicas = 0` allows scale-to-zero between demos, at the cost of a
  cold start on the next request.

## Teardown

```bash
terraform destroy
```

## Dashboard (Streamlit frontend)

`frontend/` holds a Streamlit dashboard deployed as a second Container App
(`enable_frontend = true`). It calls the API over HTTPS; its cloud pages read
Azure directly with the shared managed identity, which holds Monitoring
Reader on the resource group and Storage Blob Data Reader on the model
storage account (read-only).

| Page | Azure service |
|---|---|
| Overview | status of every service below |
| Predict / Fleet | API on Container Apps; results logged to Cosmos DB |
| History | Cosmos DB `prediction-logs` (via the API's `/history`) |
| Model registry | Blob Storage `models/<version>/` |
| Cloud ops | Azure Monitor metrics, App Insights (Log Analytics), alert rules, revisions |

```bash
docker build -t <acr-login-server>/predictive-maintenance-ui:<tag> ../frontend
docker push <acr-login-server>/predictive-maintenance-ui:<tag>
terraform apply -var "image_tag=<api-tag>" -var "frontend_image_tag=<tag>"
terraform output dashboard_url
```

Push the UI image before the apply, otherwise the app cannot pull it.

## Model registry and prediction log

The API loads the model version named by `model_version` (default `v1`) from
the `models` blob container at startup, falling back to the models baked into
the image if the download fails. To ship a retrained model without a new
image, upload a new folder and point the app at it:

```bash
az storage blob upload-batch --account-name <storage-account> --auth-mode key   -d models --destination-path v2 -s ../models
az storage blob upload --account-name <storage-account> --auth-mode key   -c models -n v2/model_comparison.csv -f ../results/model_comparison.csv
terraform apply -var "model_version=v2"
```

Every `/predict` and `/predict/batch` result is written to Cosmos DB as a
background task (no added latency); `GET /history` returns the newest entries.
Pass `?log=false` to `/predict/batch` for hypothetical sweeps you don't want
logged.
