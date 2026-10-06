output "identity_id" {
  value = azurerm_user_assigned_identity.container_app.id
}

output "principal_id" {
  value = azurerm_user_assigned_identity.container_app.principal_id
}

output "client_id" {
  value = azurerm_user_assigned_identity.container_app.client_id
}
