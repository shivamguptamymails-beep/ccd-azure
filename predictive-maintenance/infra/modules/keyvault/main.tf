data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "this" {
  name                = substr("kv-${var.project_name}-${var.suffix}", 0, 24)
  resource_group_name = var.resource_group_name
  location            = var.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  enable_rbac_authorization = true

  tags = var.tags
}

# The identity running `terraform apply` needs write access to create secrets...
resource "azurerm_role_assignment" "deployer_secrets_officer" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id

  # Applies run as a person locally and as the CI identity in GitHub Actions.
  # Without this, each switch would replace the assignment and lock the other
  # one out; the CI identity gets its own grant from the OIDC setup script.
  lifecycle {
    ignore_changes = [principal_id]
  }
}

# ...and the running Container App only needs read access at runtime.
resource "azurerm_role_assignment" "container_app_secrets_user" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = var.container_app_identity_principal_id
}

resource "azurerm_key_vault_secret" "cosmos_connection_string" {
  name         = "cosmos-connection-string"
  value        = var.cosmos_connection_string
  key_vault_id = azurerm_key_vault.this.id

  depends_on = [azurerm_role_assignment.deployer_secrets_officer]
}

resource "azurerm_key_vault_secret" "app_insights_connection_string" {
  name         = "appinsights-connection-string"
  value        = var.app_insights_connection_string
  key_vault_id = azurerm_key_vault.this.id

  depends_on = [azurerm_role_assignment.deployer_secrets_officer]
}
