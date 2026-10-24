locals {
  alert_email = var.alert_email != "" ? var.alert_email : var.publisher_email
}

module "core" {
  source = "./modules/core"

  project_name = var.project_name
  environment  = var.environment
  location     = var.location
  tags         = var.tags
}

module "registry" {
  source = "./modules/registry"

  project_name        = var.project_name
  environment         = var.environment
  location            = module.core.resource_group_location
  resource_group_name = module.core.resource_group_name
  suffix              = module.core.suffix
  tags                = var.tags
}

module "identity" {
  source = "./modules/identity"

  project_name        = var.project_name
  environment         = var.environment
  location            = module.core.resource_group_location
  resource_group_name = module.core.resource_group_name
  acr_id              = module.registry.id
  tags                = var.tags
}

module "data" {
  source = "./modules/data"

  cosmos_location = var.cosmos_location

  project_name        = var.project_name
  environment         = var.environment
  location            = module.core.resource_group_location
  resource_group_name = module.core.resource_group_name
  suffix              = module.core.suffix
  tags                = var.tags

  blob_reader_principal_id = module.identity.principal_id
}

module "keyvault" {
  source = "./modules/keyvault"

  project_name                        = var.project_name
  location                            = module.core.resource_group_location
  resource_group_name                 = module.core.resource_group_name
  suffix                              = module.core.suffix
  container_app_identity_principal_id = module.identity.principal_id
  cosmos_connection_string            = module.data.cosmos_primary_connection_string
  app_insights_connection_string      = module.core.app_insights_connection_string
  tags                                = var.tags
}

module "container_app" {
  source = "./modules/container_app"

  project_name                        = var.project_name
  environment                         = var.environment
  location                            = module.core.resource_group_location
  resource_group_name                 = module.core.resource_group_name
  log_analytics_workspace_id          = module.core.log_analytics_workspace_id
  log_analytics_workspace_customer_id = module.core.log_analytics_workspace_customer_id
  log_analytics_workspace_shared_key  = module.core.log_analytics_workspace_shared_key
  acr_login_server                    = module.registry.login_server
  image_tag                           = var.image_tag
  identity_id                         = module.identity.identity_id
  app_insights_secret_id              = module.keyvault.app_insights_secret_id
  cosmos_secret_id                    = module.keyvault.cosmos_secret_id
  identity_client_id                  = module.identity.client_id
  model_storage_account               = module.data.storage_account_name
  model_version                       = var.model_version
  min_replicas                        = var.min_replicas
  max_replicas                        = var.max_replicas
  concurrent_requests_per_replica     = var.concurrent_requests_per_replica
  cpu                                 = var.container_cpu
  memory                              = var.container_memory
  tags                                = var.tags

  depends_on = [module.identity]
}

module "gateway" {
  count  = var.enable_api_management ? 1 : 0
  source = "./modules/gateway"

  project_name        = var.project_name
  environment         = var.environment
  location            = module.core.resource_group_location
  resource_group_name = module.core.resource_group_name
  publisher_name      = var.publisher_name
  publisher_email     = var.publisher_email
  backend_fqdn        = module.container_app.fqdn
  tags                = var.tags
}

module "monitoring" {
  source = "./modules/monitoring"

  project_name        = var.project_name
  environment         = var.environment
  resource_group_name = module.core.resource_group_name
  location            = module.core.resource_group_location
  container_app_id    = module.container_app.id
  max_replicas        = var.max_replicas

  log_analytics_workspace_id = module.core.log_analytics_workspace_id
  alert_email                = local.alert_email
  tags                       = var.tags
}

module "frontend" {
  count  = var.enable_frontend ? 1 : 0
  source = "./modules/frontend"

  project_name                 = var.project_name
  environment                  = var.environment
  location                     = module.core.resource_group_location
  resource_group_name          = module.core.resource_group_name
  container_app_environment_id = module.container_app.environment_id
  acr_login_server             = module.registry.login_server
  image_tag                    = var.frontend_image_tag
  identity_id                  = module.identity.identity_id
  identity_principal_id        = module.identity.principal_id
  identity_client_id           = module.identity.client_id
  app_insights_secret_id       = module.keyvault.app_insights_secret_id
  api_url                      = "https://${module.container_app.fqdn}"
  api_resource_id              = module.container_app.id
  resource_group_id            = module.core.resource_group_id
  model_storage_account        = module.data.storage_account_name

  log_analytics_workspace_customer_id = module.core.log_analytics_workspace_customer_id
  tags                                = var.tags
}

module "functions" {
  count  = var.enable_functions ? 1 : 0
  source = "./modules/functions"

  project_name               = var.project_name
  environment                = var.environment
  location                   = module.core.resource_group_location
  resource_group_name        = module.core.resource_group_name
  suffix                     = module.core.suffix
  identity_id                = module.identity.identity_id
  cosmos_secret_id           = module.keyvault.cosmos_secret_id
  app_insights_secret_id     = module.keyvault.app_insights_secret_id
  log_analytics_workspace_id = module.core.log_analytics_workspace_id
  action_group_id            = module.monitoring.action_group_id
  tags                       = var.tags
}
