variable "project_id" {
  type    = string
  default = "rangel-tech"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "litellm_image" {
  description = "Imagem pública oficial do LiteLLM (ghcr.io/berriai/litellm) — não builda imagem própria, ver README."
  type        = string
  default     = "ghcr.io/berriai/litellm:main-stable"
}

variable "min_instances" {
  description = <<-EOT
    Decisão do dono (24/08/2026): min=1. Cold start real medido ~28s, na
    borda do timeout de 30s de `litellm_client` (achado ao testar o
    auto-provisionamento de tenant, agent-platform) -- travava criação de
    Team pra tenant novo e deixaria qualquer chamada de IA real lenta no
    pior caso. Prioriza fluidez sobre custo fixo (~US$15-25/mês de 1
    instância sempre ligada) pra este serviço especificamente -- está no
    caminho quente de toda conversa de IA de todo tenant.
  EOT
  type        = number
  default     = 1
}

variable "max_instances" {
  type    = number
  default = 10
}

variable "database_url_secret_id" {
  description = "Nome do secret no Secret Manager com a DATABASE_URL do Postgres dedicado do LiteLLM na VPS (infra-04 seção 3)."
  type        = string
  default     = "litellm-database-url"
}

variable "redis_url_secret_id" {
  description = "Secret com REDIS_URL do Redis dedicado do LiteLLM na VPS (infra-04 seção 3 — NÃO é o Redis do Sidekiq/resto do stack, isolamento de blast radius)."
  type        = string
  default     = "litellm-redis-url"
}

variable "master_key_secret_id" {
  description = "Secret com o LITELLM_MASTER_KEY — credencial de serviço-a-serviço (agent-platform/kernel-llm falando com o admin API do LiteLLM), nunca a virtual key de nenhum tenant."
  type        = string
  default     = "litellm-master-key"
}
