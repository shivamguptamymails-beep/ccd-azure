output "resource_group_name" {
  value = module.core.resource_group_name
}

output "acr_login_server" {
  value = module.registry.login_server
}

output "current_image_tag" {
  description = "Image tag this state was last applied with - read by CI before the next apply so a failed smoke test can roll back to it."
  value       = var.image_tag
}

output "container_app_fqdn" {
  description = "Direct Container App URL (bypasses API Management even when it's enabled)."
  value       = module.container_app.fqdn
}

output "api_gateway_url" {
  description = "Public entry point once enable_api_management = true; otherwise use container_app_fqdn directly."
  value       = var.enable_api_management ? module.gateway[0].api_path : null
}

output "key_vault_uri" {
  value = module.keyvault.key_vault_uri
}

output "storage_account_name" {
  value = module.data.storage_account_name
}

output "cosmos_endpoint" {
  value = module.data.cosmos_endpoint
}

output "app_insights_connection_string" {
  value     = module.core.app_insights_connection_string
  sensitive = true
}
