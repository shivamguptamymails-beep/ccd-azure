output "gateway_url" {
  value = azurerm_api_management.this.gateway_url
}

output "api_path" {
  value = "${azurerm_api_management.this.gateway_url}/${azurerm_api_management_api.predictive_maintenance.path}"
}
