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
2. **Azure AD app registration with federated (OIDC) credentials**, scoped to
   this subscription, so GitHub Actions can authenticate without a stored
   client secret. Note the client ID, tenant ID and subscription ID.
3. **GitHub repository secrets**: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
   `AZURE_SUBSCRIPTION_ID`, `ACR_LOGIN_SERVER`, `ALERT_EMAIL`,
   `TFSTATE_RESOURCE_GROUP`, `TFSTATE_STORAGE_ACCOUNT`.

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
terraform apply
```

First apply has no image in ACR yet, so build and push one before (or set
`image_tag` to a placeholder, then re-apply after the first CI build):

```bash
az acr login --name <acr-name>
docker build -t <acr-login-server>/predictive-maintenance-api:bootstrap ..
docker push <acr-login-server>/predictive-maintenance-api:bootstrap
terraform apply -var "image_tag=bootstrap"
```

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
