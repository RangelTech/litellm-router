# LiteLLM — substitui o 9Router (infra-04-litellm-substitui-9router.md).
#
# Postgres e Redis do LiteLLM ficam na VPS (Contabo), fora deste projeto GCP
# — este serviço só consome os dois via rede pública TLS+senha (mesmo modelo
# de acesso do resto do stack, infra-01 seção 3: sem VPC/VPN por decisão
# explícita do dono, revisar só quando tiver cliente pagante de verdade).
#
# Artifact Registry e o resto da fundação (budget, WIF, etc.) vêm de
# `rangel-tech-foundation/gcp` — este repo só declara o serviço em si.

resource "google_cloud_run_v2_service" "litellm" {
  name                = "litellm-router"
  location            = var.region
  project             = var.project_id
  deletion_protection = false

  template {
    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.litellm_image

      env {
        name  = "STORE_MODEL_IN_DB"
        value = "True"
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = var.database_url_secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "REDIS_URL"
        value_source {
          secret_key_ref {
            secret  = var.redis_url_secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "LITELLM_MASTER_KEY"
        value_source {
          secret_key_ref {
            secret  = var.master_key_secret_id
            version = "latest"
          }
        }
      }

      ports {
        container_port = 4000
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      startup_probe {
        http_get {
          path = "/health/liveliness"
        }
        initial_delay_seconds = 10
        period_seconds        = 10
        failure_threshold     = 30
        timeout_seconds       = 5
      }
    }
  }
}

# Chamado por: agent-platform (provisionamento, contas/combos), kernel-llm
# (chamada de IA em si), Chatwoot (AI Assist, produto-05 seção 2) — todos via
# API key própria (master key pros dois primeiros, virtual key por tenant no
# kernel/Chatwoot), nunca acesso público sem autenticação.
resource "google_cloud_run_v2_service_iam_member" "invoker" {
  name     = google_cloud_run_v2_service.litellm.name
  location = var.region
  project  = var.project_id
  role     = "roles/run.invoker"
  member   = "allUsers"
}

data "google_project" "current" {
  project_id = var.project_id
}

# SA runtime do Cloud Run (default compute SA, nenhuma custom SA setada acima)
# precisa ler os 3 secrets referenciados via secret_key_ref.
resource "google_secret_manager_secret_iam_member" "litellm_runtime_secrets" {
  for_each = toset([
    var.database_url_secret_id,
    var.redis_url_secret_id,
    var.master_key_secret_id,
  ])

  project   = var.project_id
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}
