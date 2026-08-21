# litellm-router

Cloud Run do LiteLLM — substitui o 9Router (`infra-04-litellm-substitui-9router.md`).

Não builda imagem própria: usa `ghcr.io/berriai/litellm:main-latest` como
base (mesma imagem validada na Fase A, sandbox local) — se algum dia precisar
customizar, aí sim vira um `Dockerfile` neste repo publicando pro Artifact
Registry compartilhado (`rangel-tech-foundation`).

## Terraform

```
cd terraform
terraform init
terraform validate
terraform plan -var="image_tag=main-latest" -var="database_url_secret_id=..." ...
```

**Não rodar `apply` ainda** — depende da fundação (`rangel-tech-foundation`)
já ter sido aplicada (Artifact Registry, secrets no Secret Manager) e da org
GitHub existir. Ver `personal-skills/mega-spec-reestrutura/memoria.md` pros
bloqueios atuais.

## Ponto em aberto

`min_instances` (variável em `terraform/variables.tf`) — recomendado `1`
(evita cold start no caminho quente de toda conversa de IA) mas aumenta
custo fixo. Fica default `0` até o dono decidir — ver `infra-04` seção 7.
