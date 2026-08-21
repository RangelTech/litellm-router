variable "project_id" {
  type    = string
  default = "rangel-tech"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "artifact_registry_repository" {
  description = "Nome do repositório Artifact Registry compartilhado (rangel-tech-foundation/gcp)."
  type        = string
  default     = "containers"
}

variable "image_tag" {
  description = "Tag da imagem já publicada no Artifact Registry (o CI publica antes de rodar terraform apply aqui)."
  type        = string
}

variable "min_instances" {
  description = <<-EOT
    PONTO EM ABERTO PRO DONO (infra-04-litellm-substitui-9router.md, seção 7,
    item 1) — não decidido sozinho aqui. Recomendado 1 (evita cold start no
    caminho quente de toda conversa de IA), mas aumenta custo fixo (~US$15-25/mês
    de 1 instância sempre ligada). Default aqui é 0 (mais barato, cold start
    aceito) até vir a decisão — trocar pra 1 é só mudar este valor, não
    precisa reescrever nada.
  EOT
  type        = number
  default     = 0
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
