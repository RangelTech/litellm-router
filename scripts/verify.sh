#!/usr/bin/env bash
# Gate local e do CI: constroi a MESMA imagem de producao, sobe com Postgres descartavel
# (rootfs read-only + tmpfs, como na VPS) e confere /health/liveliness e o carregamento do config.
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
IMG="litellm-router-verify:local"
NET="litellm-verify-$$"
PORT="${VERIFY_PORT:-14000}"
docker build -q --build-arg GIT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo local)" -t "$IMG" .
docker network create "$NET" >/dev/null
cleanup() {
  docker rm -f "pg-$NET" "app-$NET" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT
docker run -d --name "pg-$NET" --network "$NET" -e POSTGRES_USER=litellm -e POSTGRES_PASSWORD=verify -e POSTGRES_DB=litellm postgres:16-alpine >/dev/null
for i in $(seq 1 30); do
  docker exec "pg-$NET" pg_isready -U litellm >/dev/null 2>&1 && break
  sleep 1
  [ "$i" -eq 30 ] && { echo "postgres nao subiu"; exit 1; }
done
docker run -d --name "app-$NET" --network "$NET" -p "$PORT:4000" \
  --read-only --tmpfs /tmp --tmpfs /root/.cache \
  -e DATABASE_URL="postgresql://litellm:verify@pg-$NET:5432/litellm" \
  -e LITELLM_MASTER_KEY=sk-verify -e LITELLM_SALT_KEY=sk-verify-salt \
  -e STORE_MODEL_IN_DB=True -e LITELLM_MODE=PRODUCTION \
  "$IMG" >/dev/null
for i in $(seq 1 120); do
  if curl -fsS "http://127.0.0.1:$PORT/health/liveliness" >/dev/null 2>&1; then break; fi
  sleep 2
  if [ "$i" -eq 120 ]; then echo "liveliness nao respondeu"; docker logs "app-$NET" | tail -40; exit 1; fi
done
if docker logs "app-$NET" 2>&1 | grep -Ei 'Traceback|Failed to (load|register)|ModuleNotFoundError|read-only file system'; then
  echo "erros nos logs"; docker logs "app-$NET" | tail -40; exit 1
fi
docker exec "app-$NET" python -c "import custom_provider,yaml;c=yaml.safe_load(open('/app/config.yaml'));assert c['litellm_settings']['custom_provider_map'][0]['provider']=='codex-direct';print('config ok')"
curl -fsS "http://127.0.0.1:$PORT/health/liveliness" | grep -qi alive
echo "verify OK"
