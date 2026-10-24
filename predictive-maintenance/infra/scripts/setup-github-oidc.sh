#!/usr/bin/env bash
# One-time setup so GitHub Actions can deploy to Azure with OIDC (no stored
# client secret). Creates a user-assigned managed identity, trusts this repo's
# main branch and "production" environment, grants the roles Terraform needs,
# and prints the GitHub secrets to add.
#
# A managed identity rather than an Entra ID app registration: student and
# other locked-down tenants block app registrations, while a managed identity
# only needs Azure RBAC on a resource group. It lives in the Terraform state
# resource group so `terraform destroy` never removes CI's own credentials.
#
# Usage (from a shell where `az login` is done):
#   bash infra/scripts/setup-github-oidc.sh <github-owner>/<repo>
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash on Windows: don't rewrite /subscriptions/... paths

REPO="${1:?usage: setup-github-oidc.sh <owner>/<repo>}"
IDENTITY_NAME="${IDENTITY_NAME:-id-pmaint-github-deploy}"
RG="${RG:-rg-pmaint-dev}"
TFSTATE_RG="${TFSTATE_RG:-rg-pmaint-tfstate}"
TFSTATE_SA="${TFSTATE_SA:-pmaintstateb9b8c773}"

SUB_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)

az identity create -g "$TFSTATE_RG" -n "$IDENTITY_NAME" -o none
CLIENT_ID=$(az identity show -g "$TFSTATE_RG" -n "$IDENTITY_NAME" --query clientId -o tsv)
PRINCIPAL_ID=$(az identity show -g "$TFSTATE_RG" -n "$IDENTITY_NAME" --query principalId -o tsv)

# Jobs with `environment: production` present an environment subject;
# the others present the branch subject. Trust both.
for SUBJECT in "repo:${REPO}:ref:refs/heads/main" "repo:${REPO}:environment:production"; do
  NAME="github-${SUBJECT##*:}"
  NAME="${NAME//\//-}"   # github-main / github-production
  az identity federated-credential create -g "$TFSTATE_RG" --identity-name "$IDENTITY_NAME" \
    -n "$NAME" --issuer "https://token.actions.githubusercontent.com" \
    --subject "$SUBJECT" --audiences "api://AzureADTokenExchange" -o none
done

sleep 20   # let the new principal replicate before assigning roles
assign() {  # role scope
  az role assignment create --assignee-object-id "$PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal --role "$1" --scope "$2" -o none
}
RG_SCOPE="/subscriptions/${SUB_ID}/resourceGroups/${RG}"
assign "Contributor" "$RG_SCOPE"
assign "User Access Administrator" "$RG_SCOPE"   # Terraform creates role assignments
assign "Contributor" "/subscriptions/${SUB_ID}/resourceGroups/${TFSTATE_RG}"   # state + its keys
ACR_ID=$(az acr list -g "$RG" --query "[0].id" -o tsv)
assign "AcrPush" "$ACR_ID"
KV_ID=$(az keyvault list -g "$RG" --query "[0].id" -o tsv)
assign "Key Vault Secrets Officer" "$KV_ID"   # Terraform reads/writes the connection-string secrets

cat <<EOF

Done. Add these repository secrets in GitHub (Settings -> Secrets and variables -> Actions):
  AZURE_CLIENT_ID          ${CLIENT_ID}
  AZURE_TENANT_ID          ${TENANT_ID}
  AZURE_SUBSCRIPTION_ID    ${SUB_ID}
  ACR_LOGIN_SERVER         $(az acr list -g "$RG" --query "[0].loginServer" -o tsv)
  TFSTATE_RESOURCE_GROUP   ${TFSTATE_RG}
  TFSTATE_STORAGE_ACCOUNT  ${TFSTATE_SA}
  ALERT_EMAIL              <the address that should receive alerts>
And create an environment named "production" (Settings -> Environments).
EOF
