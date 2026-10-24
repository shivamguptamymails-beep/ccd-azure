output "fqdn" {
  value = azurerm_container_app.ui.ingress[0].fqdn
}
