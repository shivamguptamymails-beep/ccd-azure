output "storage_account_name" {
  value = azurerm_storage_account.models.name
}

output "storage_container_name" {
  value = azurerm_storage_container.models.name
}

output "cosmos_account_name" {
  value = azurerm_cosmosdb_account.this.name
}

output "cosmos_endpoint" {
  value = azurerm_cosmosdb_account.this.endpoint
}

output "cosmos_primary_connection_string" {
  value     = azurerm_cosmosdb_account.this.primary_sql_connection_string
  sensitive = true
}
