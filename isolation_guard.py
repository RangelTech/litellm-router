"""Guard de isolamento entre tenants (pre-call hook do LiteLLM).

Fecha o furo achado no estudo B: o corpo da requisicao podia carregar
`fallbacks` (e afins) apontando para o modelo/credencial de outro tenant, e as
chaves de team com `models=[]` herdavam o team inteiro.

Regras (fail-closed):
  1. Campos de roteamento/falha sintetica vindos do cliente sao rejeitados (403).
  2. `model` com virgula (batch) ou curinga e rejeitado.
  3. Chave de team: precisa ter `models` explicito (nao vazio, sem `all-proxy-models`
     nem curinga) e todos com o prefixo do tenant (`tenant_<alias>_`) ou estar em
     ISOLATION_SHARED_ALIASES (aliases de plataforma, ex. ninerouter-*).
  4. O modelo pedido tem que estar nos `models` da chave.
Chaves sem team (plataforma, ex. rt-hermes-pool) so passam pelas regras 1, 2 e 4.

Env: ISOLATION_ENFORCE_KEY_MODELS=false desliga a regra 3 (etapa de rollout);
ISOLATION_SHARED_ALIASES=csv de aliases compartilhados permitidos em chaves de team.
"""
import os
import re

from fastapi import HTTPException
from litellm.integrations.custom_logger import CustomLogger

FORBIDDEN_FIELDS = frozenset({
    "fallbacks", "context_window_fallbacks", "content_policy_fallbacks",
    "default_fallbacks", "disable_fallbacks", "router_settings_override",
    "routing_strategy", "model_group_retry_policy", "enable_tag_filtering",
    "user_config", "api_base", "base_url", "api_key", "custom_llm_provider",
    "mock_response", "mock_timeout", "mock_delay", "fastest_response",
})
FORBIDDEN_PREFIXES = ("mock_testing",)
WILDCARD_ALIASES = {"all-proxy-models", "all-team-models", "*"}


def tenant_prefix(team_alias):
    if not team_alias:
        return None
    return "tenant_" + re.sub(r"[^a-z0-9]+", "_", team_alias.lower()).strip("_") + "_"


def _deny(msg):
    raise HTTPException(status_code=403, detail={"error": "isolation_guard: " + msg})


def _shared():
    return {a.strip() for a in os.environ.get("ISOLATION_SHARED_ALIASES", "").split(",") if a.strip()}


def _enforce_keys():
    return os.environ.get("ISOLATION_ENFORCE_KEY_MODELS", "true").lower() != "false"


def _bad(k):
    return k in FORBIDDEN_FIELDS or str(k).startswith(FORBIDDEN_PREFIXES)


class IsolationGuard(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        if not isinstance(data, dict):
            return data
        for k in list(data.keys()):
            if _bad(k):
                _deny(f"campo '{k}' nao e aceito no corpo da requisicao")
        for container in ("metadata", "litellm_metadata", "extra_body"):
            sub = data.get(container)
            if isinstance(sub, dict):
                for k in sub:
                    if _bad(k):
                        _deny(f"campo '{container}.{k}' nao e aceito")
        model = data.get("model")
        if isinstance(model, str) and ("," in model or "*" in model):
            _deny("model com virgula ou curinga nao e aceito")

        team_id = getattr(user_api_key_dict, "team_id", None)
        key_models = list(getattr(user_api_key_dict, "models", None) or [])
        if team_id and _enforce_keys():
            if not key_models:
                _deny("chave de team sem 'models' explicito")
            if any(m in WILDCARD_ALIASES or "*" in m for m in key_models):
                _deny("chave de team com curinga em 'models'")
            prefix = tenant_prefix(getattr(user_api_key_dict, "team_alias", None))
            shared = _shared()
            for m in key_models:
                if m not in shared and m != "__sem_acesso__" and (prefix is None or not m.startswith(prefix)):
                    _deny(f"modelo '{m}' fora do namespace do tenant")
        if key_models and isinstance(model, str) and model not in key_models:
            _deny(f"modelo '{model}' nao liberado para esta chave")
        return data


isolation_guard = IsolationGuard()
