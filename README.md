# litellm-router

> **DESCONTINUADO.** O proxy LiteLLM dá lugar ao gateway multi-tenant do Luar.
>
> Substituto: o gateway de LLM multi-tenant da Fase G (futuro `luar_ai_gateway`). O proxy LiteLLM ainda roda em produção até a conclusão do G-10; só então este repositório será arquivado.
>
> Este repositório fica público e somente para consulta. Não receberá novas funcionalidades e será arquivado no GitHub quando a condição acima for cumprida.

Imagem do LiteLLM (proxy) com o provider customizado do Codex (`codex-direct`, `custom_provider.py`)
registrado via `config.yaml`. Deployments, Teams e virtual keys vivem no Postgres (`STORE_MODEL_IN_DB=True`).

## Entrega

Release por tag `v*` (ou `workflow_dispatch`): `.github/workflows/release.yml` roda `scripts/verify.sh`,
gera `image.tar.gz` (docker-archive) e `release-manifest.json` (schema 1). Quem implanta e so o `vps_rt_infra`.
Este repo nao guarda credencial de VPS nem faz deploy.

- Base fixada por digest no `Dockerfile` (tag de origem: `ghcr.io/berriai/litellm:main-stable`).
- Servico `litellm`, porta 4000, healthcheck `/health/liveliness` (timeout 240s: a migracao Prisma roda no start).
- `HEALTHCHECK` na imagem via Python/urllib; `GIT_COMMIT` embutido como ENV.

## Variaveis de ambiente

Obrigatorias: `DATABASE_URL`, `REDIS_URL`, `LITELLM_MASTER_KEY`, `LITELLM_SALT_KEY`, `STORE_MODEL_IN_DB`.
Opcional: `LITELLM_MODE=PRODUCTION`. Chaves de provider ficam cifradas no banco (por deployment), nao no ambiente.
`LITELLM_SALT_KEY` cifra as credenciais do banco: nao trocar depois de cadastrar deployments.

## Rootfs read-only

Validado com `docker run --read-only --tmpfs /tmp --tmpfs /root/.cache ...` (o gate usa exatamente isso).
Os binarios do Prisma ja vem na imagem (`/opt/prisma`). Nenhum volume e necessario; se algum dia o litellm
gravar em outro caminho, o log mostra `read-only file system`. A imagem roda como root (herdado da base).

## Gate

`bash scripts/verify.sh`: build, Postgres descartavel, container read-only, espera `/health/liveliness`,
confere que o `config.yaml` e o `custom_provider` carregam. Nao precisa de chave de provider.

## Isolamento entre tenants

`isolation_guard.py` (pre-call hook, registrado em `config.yaml`) rejeita `fallbacks`, `context_window_fallbacks`,
`content_policy_fallbacks`, `router_settings_override`, `mock_testing_*`, `api_base` etc. vindos do cliente, `model` com
virgula/curinga, e chaves de team sem `models` explicito ou fora do namespace `tenant_<alias>_`.
`ISOLATION_SHARED_ALIASES` (csv) libera aliases de plataforma (ex. `ninerouter-*`) em chaves de team;
`ISOLATION_ENFORCE_KEY_MODELS=false` desliga so a regra de chave de team (etapa de rollout).
`scripts/provisionar_chave_tenant.py <tenant>` (idempotente, tambem em `/app/scripts` na imagem) fixa `models` no team e nas chaves.
Regressao: `python -m pytest tests -v` (Docker; containers `b-hard-*`).
