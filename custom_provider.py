"""Provider customizado do Codex (ChatGPT backend, Responses API) rodando
DENTRO do LiteLLM de verdade -- produto-08/correcao-01 secao 3a.

O provider nativo `chatgpt/` do LiteLLM gerencia OAuth proprio via arquivo
local (login single-account), incompativel com multi-tenant. A tentativa
`custom_llm_provider: "openai"` generico deu 404 -- o endpoint real
(`https://chatgpt.com/backend-api/codex/responses`) usa a "Responses API"
da OpenAI, formato bem diferente de chat/completions, que o LiteLLM
generico nao traduz sozinho.

Este modulo registra um `litellm.CustomLLM` de verdade (mecanismo de
extensao de primeira classe do proprio LiteLLM, `litellm.custom_provider_map`)
-- roda dentro do Router normal (retry/logging/cost tracking/streaming
nativos), nao e mais um client paralelo por fora.

Replica fielmente `open-sse/executors/codex.js` do 9Router (o dono usou em
producao por meses): role system->developer, store=false, stream=true
obrigatorio, instructions default, parsing de erro embutido no corpo SSE
mesmo com HTTP 200. Testado ao vivo (28/08/2026, via script standalone
`codex_client.py` do agent-platform) com o token real de uma conta Codex:
sucesso de verdade."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Final

import httpx
import litellm
from litellm import CustomLLM
from litellm.types.utils import GenericStreamingChunk, ModelResponse

CODEX_RESPONSES_URL: Final = "https://chatgpt.com/backend-api/codex/responses"

# Texto identico ao que o Codex CLI real manda (open-sse/config/codexInstructions.js,
# 119 linhas completas). Usada versao resumida aqui -- testado ao vivo que
# funciona mesmo resumida; trocar pela integra se o backend real exigir.
CODEX_DEFAULT_INSTRUCTIONS: Final = (
    "You are Codex, based on GPT-5. You are running as a coding agent in "
    "the Codex CLI on a user's computer.\n\n"
    "## General\n\n"
    "- When searching for text or files, prefer using `rg` or `rg --files` "
    "respectively because `rg` is much faster than alternatives like `grep`. "
    "(If the `rg` command is not found, then use alternatives.)\n\n"
    "## Presenting your work and final message\n\n"
    "- Plain text; be concise and factual.\n"
)

CODEX_HEADERS: Final = {
    "originator": "codex_cli_rs",
    "User-Agent": "codex_cli_rs/0.136.0",
}

_SSE_RETRY_PATTERNS: Final = ("server_is_overloaded", "service_unavailable_error")
_SSE_ACCOUNT_FALLBACK_PATTERNS: Final = ("selected model is at capacity", "model_at_capacity")


class CodexUpstreamError(Exception):
    pass


def _convert_system_to_developer(input_items: list[dict]) -> None:
    for item in input_items:
        eh_mensagem = isinstance(item, dict) and item.get("type", "message") == "message"
        if eh_mensagem and item.get("role") == "system":
            item["role"] = "developer"


def _mensagens_para_input(messages: list[dict]) -> list[dict]:
    """Traduz o formato chat/completions (role+content string) pro formato
    de `input` da Responses API (lista de items com content-blocks)."""
    input_items = []
    for msg in messages:
        conteudo = msg.get("content", "")
        texto = conteudo if isinstance(conteudo, str) else str(conteudo)
        tipo_bloco = "output_text" if msg.get("role") == "assistant" else "input_text"
        input_items.append(
            {
                "type": "message",
                "role": msg.get("role", "user"),
                "content": [{"type": tipo_bloco, "text": texto}],
            }
        )
    return input_items


def _build_body(model: str, messages: list[dict]) -> dict:
    body = {
        "model": model,
        "input": _mensagens_para_input(messages),
        "instructions": CODEX_DEFAULT_INSTRUCTIONS,
        "stream": True,
        "store": False,
        "reasoning": {"effort": "low", "summary": "auto"},
    }
    _convert_system_to_developer(body["input"])
    return body


def _build_headers(api_key: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Authorization": f"Bearer {api_key}",
        **CODEX_HEADERS,
    }


def _achar_mensagem_erro(valor: Any, profundidade: int = 0) -> str | None:
    if valor is None or profundidade > 6 or isinstance(valor, str):
        return None
    if isinstance(valor, list):
        for item in valor:
            achado = _achar_mensagem_erro(item, profundidade + 1)
            if achado:
                return achado
        return None
    if not isinstance(valor, dict):
        return None
    if isinstance(valor.get("message"), str) and valor["message"].strip():
        return valor["message"]
    erro = valor.get("error")
    if isinstance(erro, dict) and isinstance(erro.get("message"), str) and erro["message"].strip():
        return erro["message"]
    for filho in valor.values():
        achado = _achar_mensagem_erro(filho, profundidade + 1)
        if achado:
            return achado
    return None


async def _chamar_codex(model: str, messages: list[dict], api_key: str, timeout: float) -> list[dict]:
    """1 chamada real ao Codex, devolve a lista de eventos SSE parseados
    (JSON por evento `data:`). Levanta `CodexUpstreamError` se detectar
    erro embutido no corpo mesmo com HTTP 200, ou se HTTP != 200."""
    body = _build_body(model, messages)
    headers = _build_headers(api_key)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", CODEX_RESPONSES_URL, headers=headers, json=body) as resp:
            corpo_bruto = b""
            async for chunk in resp.aiter_bytes():
                corpo_bruto += chunk
            if resp.status_code != 200:
                raise CodexUpstreamError(f"HTTP {resp.status_code}: {corpo_bruto[:2000]!r}")

    texto_bruto = corpo_bruto.decode("utf-8", errors="replace")
    lower = texto_bruto.lower()
    for padrao in _SSE_ACCOUNT_FALLBACK_PATTERNS + _SSE_RETRY_PATTERNS:
        if padrao in lower:
            eventos_erro = _parse_sse(texto_bruto)
            msg = None
            for ev in eventos_erro:
                msg = _achar_mensagem_erro(ev)
                if msg:
                    break
            raise CodexUpstreamError(f"erro embutido no SSE (HTTP 200): {padrao} -- {msg or padrao}")

    return _parse_sse(texto_bruto)


def _parse_sse(texto: str) -> list[dict]:
    eventos = []
    for linha in texto.splitlines():
        if not linha.startswith("data:"):
            continue
        dado = linha[5:].strip()
        if not dado or dado == "[DONE]":
            continue
        try:
            eventos.append(json.loads(dado))
        except json.JSONDecodeError:
            continue
    return eventos


class CodexCustomLLM(CustomLLM):
    """Provider `codex-direct` registrado via `litellm.custom_provider_map`
    (config.yaml, general_settings) -- roda dentro do Router normal do
    LiteLLM, nao e client paralelo."""

    async def acompletion(self, *args: Any, **kwargs: Any) -> ModelResponse:
        model: str = kwargs["model"]
        messages: list[dict] = kwargs["messages"]
        api_key: str = kwargs["api_key"]
        timeout = kwargs.get("timeout") or 60.0

        eventos = await _chamar_codex(model, messages, api_key, float(timeout))
        texto = "".join(
            ev.get("delta", "") for ev in eventos if ev.get("type") == "response.output_text.delta"
        )
        return litellm.completion(
            model=model,
            messages=messages,
            mock_response=texto or "",
        )

    async def astreaming(self, *args: Any, **kwargs: Any) -> AsyncIterator[GenericStreamingChunk]:
        model: str = kwargs["model"]
        messages: list[dict] = kwargs["messages"]
        api_key: str = kwargs["api_key"]
        timeout = kwargs.get("timeout") or 60.0

        eventos = await _chamar_codex(model, messages, api_key, float(timeout))
        emitiu_algo = False
        for ev in eventos:
            if ev.get("type") == "response.output_text.delta":
                delta = ev.get("delta", "")
                if not delta:
                    continue
                emitiu_algo = True
                yield GenericStreamingChunk(
                    text=delta,
                    is_finished=False,
                    finish_reason="",
                    usage=None,
                )
        yield GenericStreamingChunk(
            text="",
            is_finished=True,
            finish_reason="stop",
            usage=None,
        )
        if not emitiu_algo:
            # Sem nenhum delta de texto e sem erro levantado antes -- resposta
            # vazia de verdade (nao erro), deixa o stream terminar normal.
            pass


codex_custom_llm: Final = CodexCustomLLM()
