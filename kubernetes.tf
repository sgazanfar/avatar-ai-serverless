# kubernetes.tf - Kubernetes configurations for serverless GPU deployment

# Kubernetes namespace for the application
resource "kubernetes_namespace" "avatar_ai" {
  metadata {
    name = "avatar-ai"
    labels = {
      environment = var.environment
      project     = var.project_name
    }
  }

  depends_on = [azurerm_kubernetes_cluster.main]
}

# Secret for container registry
resource "kubernetes_secret" "acr_secret" {
  metadata {
    name      = "acr-secret"
    namespace = kubernetes_namespace.avatar_ai.metadata[0].name
  }

  type = "kubernetes.io/dockerconfigjson"

  data = {
    ".dockerconfigjson" = jsonencode({
      auths = {
        "${azurerm_container_registry.main.login_server}" = {
          "username" = azurerm_container_registry.main.admin_username
          "password" = azurerm_container_registry.main.admin_password
          "auth"     = base64encode("${azurerm_container_registry.main.admin_username}:${azurerm_container_registry.main.admin_password}")
        }
      }
    })
  }
}

# ConfigMap for application configuration
resource "kubernetes_config_map" "app_config" {
  metadata {
    name      = "avatar-ai-config"
    namespace = kubernetes_namespace.avatar_ai.metadata[0].name
  }

  data = {
    "REDIS_URL"             = "redis://${azurerm_redis_cache.main.hostname}:6380"
    "DATABASE_URL"          = "postgresql://avataraiuser:AvatarAI2025!@#@${azurerm_postgresql_flexible_server.main.fqdn}:5432/avatar_ai_db"
    "AZURE_STORAGE_ACCOUNT" = azurerm_storage_account.main.name
    # "CDN_ENDPOINT_URL"      = "https://${azurerm_cdn_endpoint.avatar_content.fqdn}"
    "ENVIRONMENT"          = var.environment
    "LOG_LEVEL"            = "INFO"
    "MAX_CONCURRENT_USERS" = "1000"
    "GPU_MEMORY_LIMIT"     = "16Gi"
  }
}

# Secret for API keys
resource "kubernetes_secret" "api_keys" {
  metadata {
    name      = "avatar-ai-secrets"
    namespace = kubernetes_namespace.avatar_ai.metadata[0].name
  }

  type = "Opaque"

  data = {
    "openai-api-key"     = base64encode("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")
    "did-api-key"        = base64encode("c3llZEBsaXZyLmNv:wF0s079zhwMixieIpgC6m")
    "elevenlabs-api-key" = base64encode("sk_c049dc4df58ef34fd04c059b791f1ecc0a1cf6c85cb2a888")
    "azure-storage-key"  = base64encode(azurerm_storage_account.main.primary_access_key)
  }
}

# GPU-enabled deployment for AI processing
resource "kubernetes_deployment" "ai_processor" {
  metadata {
    name      = "avatar-ai-processor"
    namespace = kubernetes_namespace.avatar_ai.metadata[0].name
    labels = {
      app = "avatar-ai-processor"
    }
  }

  spec {
    replicas = 0 # Start with 0, scale up with HPA

    selector {
      match_labels = {
        app = "avatar-ai-processor"
      }
    }

    template {
      metadata {
        labels = {
          app = "avatar-ai-processor"
        }
      }

      spec {
        image_pull_secrets {
          name = kubernetes_secret.acr_secret.metadata[0].name
        }

        # Node selector for GPU nodes
        node_selector = {
          "accelerator" = "nvidia"
        }

        # Toleration for GPU nodes
        toleration {
          key      = "nvidia.com/gpu"
          operator = "Equal"
          value    = "true"
          effect   = "NoSchedule"
        }

        container {
          name  = "ai-processor"
          image = "${azurerm_container_registry.main.login_server}/avatar-ai-backend:latest"

          port {
            container_port = 8000
            name           = "http"
          }

          port {
            container_port = 8080
            name           = "websocket"
          }

          # Resource limits and requests
          resources {
            limits = {
              "nvidia.com/gpu" = "1"
              "memory"         = "16Gi"
              "cpu"            = "4"
            }
            requests = {
              "nvidia.com/gpu" = "1"
              "memory"         = "8Gi"
              "cpu"            = "2"
            }
          }

          # Environment variables from ConfigMap
          env_from {
            config_map_ref {
              name = kubernetes_config_map.app_config.metadata[0].name
            }
          }

          # Environment variables from secrets
          env {
            name = "OPENAI_API_KEY"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.api_keys.metadata[0].name
                key  = "openai-api-key"
              }
            }
          }

          env {
            name = "DID_API_KEY"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.api_keys.metadata[0].name
                key  = "did-api-key"
              }
            }
          }

          env {
            name = "AZURE_STORAGE_KEY"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.api_keys.metadata[0].name
                key  = "azure-storage-key"
              }
            }
          }

          # Health checks
          liveness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 30
            period_seconds        = 10
            timeout_seconds       = 5
            failure_threshold     = 3
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 10
            period_seconds        = 5
            timeout_seconds       = 5
            failure_threshold     = 3
          }

          # Volume mounts for models cache
          volume_mount {
            name       = "models-cache"
            mount_path = "/app/models"
          }
        }

        # Volumes
        volume {
          name = "models-cache"
          empty_dir {
            size_limit = "50Gi"
          }
        }
      }
    }
  }
}

# Service for AI processor
resource "kubernetes_service" "ai_processor" {
  metadata {
    name      = "avatar-ai-processor-service"
    namespace = kubernetes_namespace.avatar_ai.metadata[0].name
  }

  spec {
    selector = {
      app = "avatar-ai-processor"
    }

    port {
      name        = "http"
      port        = 8000
      target_port = 8000
      protocol    = "TCP"
    }

    port {
      name        = "websocket"
      port        = 8080
      target_port = 8080
      protocol    = "TCP"
    }

    type = "ClusterIP"
  }
}

# CPU-only deployment for web API
resource "kubernetes_deployment" "web_api" {
  metadata {
    name      = "avatar-ai-web-api"
    namespace = kubernetes_namespace.avatar_ai.metadata[0].name
    labels = {
      app = "avatar-ai-web-api"
    }
  }

  spec {
    replicas = 3

    selector {
      match_labels = {
        app = "avatar-ai-web-api"
      }
    }

    template {
      metadata {
        labels = {
          app = "avatar-ai-web-api"
        }
      }

      spec {
        image_pull_secrets {
          name = kubernetes_secret.acr_secret.metadata[0].name
        }

        container {
          name  = "web-api"
          image = "${azurerm_container_registry.main.login_server}/avatar-ai-web:latest"

          port {
            container_port = 3000
            name           = "http"
          }

          resources {
            limits = {
              "memory" = "2Gi"
              "cpu"    = "1"
            }
            requests = {
              "memory" = "1Gi"
              "cpu"    = "500m"
            }
          }

          env_from {
            config_map_ref {
              name = kubernetes_config_map.app_config.metadata[0].name
            }
          }

          liveness_probe {
            http_get {
              path = "/"
              port = 3000
            }
            initial_delay_seconds = 30
            period_seconds        = 10
          }

          readiness_probe {
            http_get {
              path = "/"
              port = 3000
            }
            initial_delay_seconds = 5
            period_seconds        = 5
          }
        }
      }
    }
  }
}

# Service for web API
resource "kubernetes_service" "web_api" {
  metadata {
    name      = "avatar-ai-web-service"
    namespace = kubernetes_namespace.avatar_ai.metadata[0].name
  }

  spec {
    selector = {
      app = "avatar-ai-web-api"
    }

    port {
      name        = "http"
      port        = 3000
      target_port = 3000
      protocol    = "TCP"
    }

    type = "ClusterIP"
  }
}

# Horizontal Pod Autoscaler for GPU pods
resource "kubernetes_horizontal_pod_autoscaler_v2" "ai_processor_hpa" {
  metadata {
    name      = "avatar-ai-processor-hpa"
    namespace = kubernetes_namespace.avatar_ai.metadata[0].name
  }

  spec {
    scale_target_ref {
      api_version = "apps/v1"
      kind        = "Deployment"
      name        = kubernetes_deployment.ai_processor.metadata[0].name
    }

    min_replicas = 0
    max_replicas = 10

    metric {
      type = "Resource"
      resource {
        name = "cpu"
        target {
          type                = "Utilization"
          average_utilization = 70
        }
      }
    }

    metric {
      type = "Resource"
      resource {
        name = "memory"
        target {
          type                = "Utilization"
          average_utilization = 80
        }
      }
    }

    behavior {
      scale_up {
        stabilization_window_seconds = 60
        policy {
          type           = "Percent"
          value          = 100
          period_seconds = 15
        }
      }
      scale_down {
        stabilization_window_seconds = 300
        policy {
          type           = "Percent"
          value          = 50
          period_seconds = 60
        }
      }
    }
  }
}

# HPA for web API
resource "kubernetes_horizontal_pod_autoscaler_v2" "web_api_hpa" {
  metadata {
    name      = "avatar-ai-web-hpa"
    namespace = kubernetes_namespace.avatar_ai.metadata[0].name
  }

  spec {
    scale_target_ref {
      api_version = "apps/v1"
      kind        = "Deployment"
      name        = kubernetes_deployment.web_api.metadata[0].name
    }

    min_replicas = 2
    max_replicas = 20

    metric {
      type = "Resource"
      resource {
        name = "cpu"
        target {
          type                = "Utilization"
          average_utilization = 60
        }
      }
    }
  }
}

# Ingress for external access
resource "kubernetes_ingress_v1" "main" {
  metadata {
    name      = "avatar-ai-ingress"
    namespace = kubernetes_namespace.avatar_ai.metadata[0].name
    annotations = {
      "kubernetes.io/ingress.class"                     = "azure/application-gateway"
      "appgw.ingress.kubernetes.io/backend-path-prefix" = "/"
      "appgw.ingress.kubernetes.io/request-timeout"     = "60"
    }
  }

  spec {
    rule {
      http {
        path {
          path      = "/api/*"
          path_type = "Prefix"
          backend {
            service {
              name = kubernetes_service.ai_processor.metadata[0].name
              port {
                number = 8000
              }
            }
          }
        }

        path {
          path      = "/ws/*"
          path_type = "Prefix"
          backend {
            service {
              name = kubernetes_service.ai_processor.metadata[0].name
              port {
                number = 8080
              }
            }
          }
        }

        path {
          path      = "/*"
          path_type = "Prefix"
          backend {
            service {
              name = kubernetes_service.web_api.metadata[0].name
              port {
                number = 3000
              }
            }
          }
        }
      }
    }
  }
}

# KEDA ScaledObject for advanced auto-scaling based on Redis queue
#resource "kubernetes_manifest" "keda_scaler" {
#  manifest = {
#    apiVersion = "keda.sh/v1alpha1"
#    kind       = "ScaledObject"
#    metadata = {
#      name      = "avatar-ai-redis-scaler"
#      namespace = kubernetes_namespace.avatar_ai.metadata[0].name
#    }
#    spec = {
#      scaleTargetRef = {
#        name = kubernetes_deployment.ai_processor.metadata[0].name
#      }
#      minReplicaCount = 0
#      maxReplicaCount = 15
#      triggers = [
#        {
#          type = "redis"
#          metadata = {
#            address     = "${azurerm_redis_cache.main.hostname}:6380"
#            listName    = "avatar_processing_queue"
#            listLength  = "5"
#            enableTLS   = "true"
#            requireAuth = "true"
#          }
#          authenticationRef = {
#            name = "redis-auth"
#          }
#        }
#      ]
#    }
#  }
#}

