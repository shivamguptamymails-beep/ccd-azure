resource "azurerm_user_assigned_identity" "container_app" {
  name                = "id-${var.project_name}-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
}

# Lets the Container App pull images from ACR without an admin
# username/password - the identity itself is the credential.
resource "azurerm_role_assignment" "acr_pull" {
  scope                = var.acr_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.container_app.principal_id
}
