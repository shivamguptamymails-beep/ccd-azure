output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "resource_group_location" {
  value = azurerm_resource_group.this.location
}

output "resource_group_id" {
  value = azurerm_resource_group.this.id
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.this.id
}

output "app_insights_connection_string" {
  value     = azurerm_application_insights.this.connection_string
  sensitive = true
}

output "app_insights_instrumentation_key" {
  value     = azurerm_application_insights.this.instrumentation_key
  sensitive = true
}

# Shared suffix so globally-unique resources (ACR, Storage, Key Vault, Cosmos)
# in other modules land on the same short, unique name per environment.
output "suffix" {
  value = random_string.suffix.result
}
