locals {
  # Normalize project and environment to lowercase & remove dashes
  project_name_normalized = replace(lower(var.project_name), "-", "")
  env_normalized          = lower(var.environment)

  # Short environment name for resources that require it
  short_env = substr(local.env_normalized, 0, 6)

  # Resource names (adjust length as per Azure limits)

  # PostgreSQL Flexible Server: max 63 chars, lowercase, numbers, hyphens
  postgres_name = substr("${local.project_name_normalized}-${local.env_normalized}-pg", 0, 63)

  # Storage account: only lowercase letters & numbers, 3–24 chars
  storage_account_name = substr("${local.project_name_normalized}${local.short_env}sa", 0, 24)

  # Azure Container Registry: only lowercase letters & numbers, max 50 chars
  acr_name = substr("${local.project_name_normalized}${local.short_env}acr", 0, 50)

  # Redis Cache: max 63 chars, lowercase, numbers, hyphens
  redis_name = substr("${local.project_name_normalized}-${local.env_normalized}-redis", 0, 63)

  # CDN Profile: max 63 chars, lowercase, numbers, hyphens
  cdn_profile_name = substr("${local.project_name_normalized}-${local.env_normalized}-cdn", 0, 63)

  # Resource Group: max 90 chars, keep readable
  resource_group_name = "${local.project_name_normalized}-${local.env_normalized}-rg"

  # General tags for consistency
  common_tags = {
    project     = var.project_name
    environment = var.environment
    owner       = "ai-team"
    costcenter  = "ai-avatars"
  }
}

