
#provider "azurerm" {
#  features {}
#}
#
#provider "kubernetes" {
#  host                   = azurerm_kubernetes_cluster.main.kube_config[0].host
#  client_certificate     = base64decode(azurerm_kubernetes_cluster.main.kube_config[0].client_certificate)
#  client_key             = base64decode(azurerm_kubernetes_cluster.main.kube_config[0].client_key)
#  cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.main.kube_config[0].cluster_ca_certificate)
#}

# Resource Group
resource "azurerm_resource_group" "main" {
  name     = local.resource_group_name
  location = var.location
  tags     = local.common_tags
}

# PostgreSQL Flexible Server
resource "azurerm_postgresql_flexible_server" "main" {
  name                   = local.postgres_name
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  administrator_login    = "avataraiuser"
  administrator_password = "AvatarAI2025!@#"
  storage_mb             = 32768
  sku_name               = "B_Standard_B1ms"
  version                = "14"
  tags                   = local.common_tags
}

# Azure Storage Account
resource "azurerm_storage_account" "main" {
  name                     = local.storage_account_name
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  tags                     = local.common_tags
}

# Azure Container Registry
resource "azurerm_container_registry" "main" {
  name                = local.acr_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true
  tags                = local.common_tags
}

# Azure Redis Cache
resource "azurerm_redis_cache" "main" {
  name                = local.redis_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  capacity            = 1
  family              = "C"
  sku_name            = "Basic"
  enable_non_ssl_port = false
  minimum_tls_version = "1.2"
  tags                = local.common_tags
}

# Azure CDN Profile
resource "azurerm_cdn_profile" "avatar_content" {
  name                = local.cdn_profile_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Standard_Microsoft"
  tags                = local.common_tags
}

# Azure Kubernetes Service (AKS)
resource "azurerm_kubernetes_cluster" "main" {
  name                = "${local.project_name_normalized}-${local.env_normalized}-aks"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "${local.project_name_normalized}-${local.short_env}"

  default_node_pool {
    name       = "default"
    node_count = 2
    vm_size    = "Standard_DS2_v2"
  }

  identity {
    type = "SystemAssigned"
  }

  tags = local.common_tags
}

