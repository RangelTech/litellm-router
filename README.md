# litellm-router

Cloud Run do LiteLLM — substitui o 9Router (`infra-04-litellm-substitui-9router.md`).

**28/08/2026: passou a buildar imagem própria** (`Dockerfile`, `FROM
ghcr.io/berriai/litellm:main-stable` + `custom_provider.py` + `config.yaml`)
— necessário pra registrar o provider customizado do Codex (`codex-direct`,
via `litellm.custom_provider_map`), que roda dentro do Router de verdade em
vez de client paralelo (ver `correcao-01-execucao-completa.md` seção 3a,
`personal-skills/mega-spec-reestrutura`).

`STORE_MODEL_IN_DB=True` continua valendo pra tudo que É dinâmico
(deployments/Teams/virtual keys por tenant, via banco) — `config.yaml`
só registra coisa estática de código (o provider customizado), nunca
credencial nem deployment de tenant.

## Deploy

`.github/workflows/deploy.yml` builda a imagem (`infra/cloudbuild-litellm-router.yaml`,
Artifact Registry `containers/litellm-router`) e aplica o Terraform em
`terraform/` a cada push em `main` — mesmo padrão do `deploy-oauth-browser.yml`
do `agent-platform`. Roda `terraform import` antes do apply (tolerante a
falha) porque o `.tfstate` é local/gitignored, não compartilhado entre
execuções do CI.

## Terraform (apply manual local, se precisar)

```
cd terraform
terraform init
terraform plan
terraform apply
```

`litellm_image` (variável) tem um default de imagem oficial só pra apply
manual isolado — o workflow real sempre passa `TF_VAR_litellm_image`
apontando pra imagem recém-buildada com o SHA do commit.

## Ponto em aberto

`beeper/chatwoot` (Facebook/Instagram via Matrix, `correcao-01` seção 4)
não depende deste repo — é peça separada, mas se algum dia rodar dentro
do mesmo Cloud Run compartilhado, revisar aqui.
