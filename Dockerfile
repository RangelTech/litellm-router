# Base oficial do LiteLLM fixada por digest (indice multi-arch).
# Tag de origem: ghcr.io/berriai/litellm:main-stable (resolvida em 2026-10-17).
# Para atualizar: docker buildx imagetools inspect ghcr.io/berriai/litellm:main-stable
FROM ghcr.io/berriai/litellm@sha256:b7b9e2c306343721802253d0dd9436b9634a2eb4e14da7c7cf06c5c7b7530802

ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}

WORKDIR /app

# Provider customizado do Codex (codex-direct) + config estatica, sem segredo.
COPY custom_provider.py isolation_guard.py /app/
COPY scripts/provisionar_chave_tenant.py /app/scripts/provisionar_chave_tenant.py
COPY config.yaml /app/config.yaml

EXPOSE 4000

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
  CMD ["python", "-c", "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:4000/health/liveliness',timeout=3).status==200 else 1)"]

# Entrypoint oficial (exec litellm "$@"). Deployments/Teams/keys vem do banco
# (STORE_MODEL_IN_DB=True); config.yaml so registra o provider customizado.
CMD ["--port", "4000", "--config", "/app/config.yaml"]
