resource "azurerm_container_registry" "this" {
  # ACR names: alphanumeric only, 5-50 chars, globally unique.
  name                = "${replace(var.project_name, "-", "")}${var.environment}acr${var.suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "Standard"

  # No admin user / static credentials: the Container App pulls images using
  # its user-assigned managed identity (see modules/identity + the AcrPull
  # role assignment wired up in root main.tf), so no registry password ever
  # needs to exist, be rotated, or leak.
  admin_enabled = false

  tags = var.tags
}
