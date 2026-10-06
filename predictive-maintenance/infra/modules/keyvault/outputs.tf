output "key_vault_id" {
  value = azurerm_key_vault.this.id
}

output "key_vault_uri" {
  value = azurerm_key_vault.this.vault_uri
}

output "cosmos_secret_id" {
  value = azurerm_key_vault_secret.cosmos_connection_string.versionless_id
}

output "app_insights_secret_id" {
  value = azurerm_key_vault_secret.app_insights_connection_string.versionless_id
}
