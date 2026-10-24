output "id" {
  value = azurerm_container_app.api.id
}

output "fqdn" {
  value = azurerm_container_app.api.ingress[0].fqdn
}

output "name" {
  value = azurerm_container_app.api.name
}

output "environment_id" {
  value = azurerm_container_app_environment.this.id
}
