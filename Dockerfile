# Estende a imagem oficial do LiteLLM só pra registrar o provider
# customizado do Codex (correcao-01 secao 3a) -- sem isso a imagem oficial
# pura nao tem como saber que "codex-direct" existe.
FROM ghcr.io/berriai/litellm:main-stable

WORKDIR /app

COPY custom_provider.py /app/custom_provider.py
COPY config.yaml /app/config.yaml

# Mesmo entrypoint da imagem oficial (docker/prod_entrypoint.sh -> exec
# litellm "$@"), só adiciona --config apontando pro nosso registro do
# provider customizado. STORE_MODEL_IN_DB continua True (env var, ver
# terraform/main.tf) -- deployments/Teams/keys seguem vindo do banco.
CMD ["--port", "4000", "--config", "/app/config.yaml"]
