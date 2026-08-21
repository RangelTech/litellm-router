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
  name     = "litellm-router"
  location = var.region
  project  = var.project_id

  template {
    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_registry_repository}/litellm-router:${var.image_tag}"

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

      startup_probe {
        http_get {
          path = "/health/liveliness"
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 12
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
