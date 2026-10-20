"""Regressao de isolamento do LiteLLM (containers descartaveis b-hard-*).

Sobe: Postgres, mock A, mock B e a imagem deste repo. Tenant t1 -> mock A, tenant t2 -> mock B.
Prova que t1 nao alcanca modelo/credencial de t2 por nenhum vetor. Requer Docker.
Uso: pytest tests/ -v
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
NET = "b-hard-net"
PORT = int(os.environ.get("HARD_PORT", "24100"))
BASE = f"http://127.0.0.1:{PORT}"
MASTER = "sk-bhard-master"
ENV = {**os.environ, "MSYS_NO_PATHCONV": "1"}
CONTAINERS = ["b-hard-pg", "b-hard-mock-a", "b-hard-mock-b", "b-hard-litellm"]


def sh(*args, check=True):
    r = subprocess.run(args, capture_output=True, text=True, env=ENV)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(args)}\n{r.stdout}\n{r.stderr}")
    return r


def cleanup():
    sh("docker", "rm", "-f", *CONTAINERS, check=False)
    sh("docker", "network", "rm", NET, check=False)


def mock_stats(name):
    out = sh("docker", "exec", name, "python", "-c",
             "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:9000/stats').read().decode())").stdout
    return json.loads(out)


def mock_reset():
    for n in ("b-hard-mock-a", "b-hard-mock-b"):
        sh("docker", "exec", n, "python", "-c",
           "import urllib.request;urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:9000/reset',data=b'{}',method='POST'))")


def total(name):
    return mock_stats(name)["total"]


@pytest.fixture(scope="module")
def env():
    cleanup()
    sh("docker", "build", "-q", "-t", "b-hard-mock:test", str(ROOT / "tests" / "mock"))
    sh("docker", "build", "-q", "-t", "b-hard-litellm:test", str(ROOT))
    sh("docker", "network", "create", NET)
    sh("docker", "run", "-d", "--name", "b-hard-pg", "--network", NET, "-e", "POSTGRES_PASSWORD=pg",
       "-e", "POSTGRES_DB=litellm", "postgres:16-alpine")
    for mid in ("a", "b"):
        sh("docker", "run", "-d", "--name", f"b-hard-mock-{mid}", "--network", NET, "-e", f"MOCK_ID={mid}",
           "b-hard-mock:test")
    time.sleep(5)
    sh("docker", "run", "-d", "--name", "b-hard-litellm", "--network", NET, "-p", f"127.0.0.1:{PORT}:4000",
       "-e", "DATABASE_URL=postgresql://postgres:pg@b-hard-pg:5432/litellm",
       "-e", f"LITELLM_MASTER_KEY={MASTER}", "-e", "LITELLM_SALT_KEY=sk-bhard-salt-0123456789",
       "-e", "STORE_MODEL_IN_DB=True", "-e", "LITELLM_MODE=PRODUCTION",
       "-e", "ISOLATION_SHARED_ALIASES=shared-gpt", "b-hard-litellm:test")
    for _ in range(90):
        try:
            if httpx.get(f"{BASE}/health/liveliness", timeout=3).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(3)
    else:
        raise RuntimeError(sh("docker", "logs", "b-hard-litellm", check=False).stdout[-3000:])
    adm = httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {MASTER}"}, timeout=60)

    def model(name, mock, key):
        r = adm.post("/model/new", json={"model_name": name, "litellm_params": {
            "model": "openai/m1", "api_base": f"http://b-hard-mock-{mock}:9000/v1", "api_key": key}})
        assert r.status_code in (200, 500), r.text  # 500 benigno conhecido (polling)

    model("tenant_t1_main", "a", "credA")
    model("tenant_t2_main", "b", "credB")
    model("main", "a", "credA")      # nome sem prefixo, colidindo entre tenants
    model("main", "b", "credB")
    model("shared-gpt", "a", "credShared")
    time.sleep(35)  # polling do router
    # provisiona via script idempotente (dentro do container, sem imprimir chaves)
    keys = {}
    for t in ("t1", "t2"):
        out = sh("docker", "exec", "-e", f"LITELLM_MASTER_KEY={MASTER}", "b-hard-litellm", "python",
                 "/app/scripts/provisionar_chave_tenant.py", t, "--emitir-chaves", f"/tmp/{t}.json").stdout
        assert f"tenant_{t}_main" in out
        keys[t] = json.loads(sh("docker", "exec", "b-hard-litellm", "cat", f"/tmp/{t}.json").stdout)[f"{t}-bridge"]
    yield {"adm": adm, "keys": keys}
    cleanup()


def chat(env, tenant, model="tenant_t1_main", extra=None, headers=None, key=None):
    h = {"Authorization": f"Bearer {key or env['keys'][tenant]}"}
    h.update(headers or {})
    body = {"model": model, "messages": [{"role": "user", "content": "oi"}]}
    body.update(extra or {})
    return httpx.post(f"{BASE}/v1/chat/completions", headers=h, json=body, timeout=60)


def test_baseline_t1_alcanca_somente_mock_a(env):
    mock_reset()
    r = chat(env, "t1")
    assert r.status_code == 200 and "mock=a" in r.text and "credA" in r.text
    assert total("b-hard-mock-b") == 0


def test_t2_alcanca_mock_b(env):
    r = chat(env, "t2", model="tenant_t2_main")
    assert r.status_code == 200 and "mock=b" in r.text


@pytest.mark.parametrize("extra", [
    {"fallbacks": ["tenant_t2_main"]},
    {"fallbacks": [{"tenant_t1_main": ["tenant_t2_main"]}]},
    {"context_window_fallbacks": [{"tenant_t1_main": ["tenant_t2_main"]}]},
    {"content_policy_fallbacks": [{"tenant_t1_main": ["tenant_t2_main"]}]},
    {"router_settings_override": {"fallbacks": [{"tenant_t1_main": ["tenant_t2_main"]}]}},
    {"mock_testing_fallbacks": True, "fallbacks": ["tenant_t2_main"]},
    {"mock_testing_rate_limit_error": True},
    {"routing_strategy": "latency-based-routing"},
    {"disable_fallbacks": False},
    {"user_config": {"model_list": []}},
    {"api_base": "http://b-hard-mock-b:9000/v1"},
    {"metadata": {"fallbacks": ["tenant_t2_main"]}},
    {"extra_body": {"fallbacks": ["tenant_t2_main"]}},
])
def test_campos_de_roteamento_do_corpo_sao_barrados(env, extra):
    mock_reset()
    r = chat(env, "t1", extra=extra)
    assert r.status_code in (400, 401, 403), r.text
    assert total("b-hard-mock-b") == 0


@pytest.mark.parametrize("model", [
    "tenant_t2_main", "TENANT_T2_MAIN", " tenant_t2_main", "tenant_t2_*", "*", "all-proxy-models",
    "tenant_t1_main,tenant_t2_main", "openai/m1", "main",
])
def test_modelo_de_outro_tenant_ou_curinga(env, model):
    mock_reset()
    r = chat(env, "t1", model=model)
    assert r.status_code in (400, 401, 403, 404), r.text
    assert total("b-hard-mock-b") == 0


@pytest.mark.parametrize("hdr", [
    {"x-litellm-model": "tenant_t2_main"},
    {"x-litellm-fallbacks": "tenant_t2_main"},
    {"x-litellm-tags": "tenant_t2"},
    {"x-litellm-api-key": "credB"},
    {"x-api-key": "credB"},
    {"api-key": "credB"},
])
def test_headers_nao_desviam(env, hdr):
    mock_reset()
    r = chat(env, "t1", headers=hdr)
    assert total("b-hard-mock-b") == 0
    if r.status_code == 200:
        assert "mock=a" in r.text and "credB" not in r.text


def test_colisao_de_model_name_nao_mistura(env):
    """'main' existe nos dois mocks; mesmo que alguem libere esse nome numa chave, o guard barra."""
    adm = env["adm"]
    team = next(t for t in adm.get("/team/list").json() if t["team_alias"] == "t1")
    k = adm.post("/key/generate", json={"team_id": team["team_id"], "models": ["main"]}).json()["key"]
    mock_reset()
    for _ in range(10):
        r = chat(env, "t1", model="main", key=k)
        assert r.status_code == 403
    assert total("b-hard-mock-a") == 0 and total("b-hard-mock-b") == 0


def test_chave_de_team_sem_models_e_barrada(env):
    adm = env["adm"]
    team = next(t for t in adm.get("/team/list").json() if t["team_alias"] == "t1")
    k = adm.post("/key/generate", json={"team_id": team["team_id"], "models": []}).json()["key"]
    mock_reset()
    r = chat(env, "t1", key=k)
    assert r.status_code == 403
    assert total("b-hard-mock-a") == 0 and total("b-hard-mock-b") == 0


def test_chave_de_team_com_curinga_e_barrada(env):
    adm = env["adm"]
    team = next(t for t in adm.get("/team/list").json() if t["team_alias"] == "t1")
    k = adm.post("/key/generate", json={"team_id": team["team_id"], "models": ["all-proxy-models"]}).json()["key"]
    r = chat(env, "t1", key=k, model="tenant_t2_main")
    assert r.status_code == 403
    assert total("b-hard-mock-b") <= 1 and "mock=b" not in r.text


def test_listagem_so_mostra_modelos_do_tenant(env):
    r = httpx.get(f"{BASE}/v1/models", headers={"Authorization": f"Bearer {env['keys']['t1']}"})
    ids = {m["id"] for m in r.json()["data"]}
    assert "tenant_t2_main" not in ids


def test_provisionamento_idempotente(env):
    out = sh("docker", "exec", "-e", f"LITELLM_MASTER_KEY={MASTER}", "b-hard-litellm", "python",
             "/app/scripts/provisionar_chave_tenant.py", "t1").stdout
    assert json.loads(out)["alteracoes"] == ["nenhuma"]


def test_alias_compartilhado_so_com_allowlist(env):
    """shared-gpt (plataforma) pode entrar em chave de team via ISOLATION_SHARED_ALIASES."""
    adm = env["adm"]
    team = next(t for t in adm.get("/team/list").json() if t["team_alias"] == "t1")
    adm.post("/team/update", json={"team_id": team["team_id"], "models": ["tenant_t1_main", "shared-gpt"]})
    k = adm.post("/key/generate", json={"team_id": team["team_id"],
                                        "models": ["tenant_t1_main", "shared-gpt"]}).json()["key"]
    assert chat(env, "t1", model="shared-gpt", key=k).status_code == 200
