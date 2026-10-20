#!/usr/bin/env python3
"""Provisiona (idempotente) o team e as chaves virtuais de um tenant com `models` explicito.

Uso (a master key vem do ambiente, nunca de argumento):
  LITELLM_BASE_URL=http://litellm:4000 LITELLM_MASTER_KEY=... \
  python provisionar_chave_tenant.py <tenant_key> [--aliases a,b] [--chaves bridge,ai-assist] \
         [--dry-run] [--emitir-chaves arquivo]

Efeito: o team passa a ter `models` = aliases do tenant (prefixo tenant_<tenant_key>_ no banco,
mais --aliases explicitos); cada chave <tenant_key>-<sufixo> e criada se faltar ou atualizada
(models = o mesmo conjunto). Chaves existentes mantem o valor; o valor de chave nova so e gravado
em --emitir-chaves (0600), nunca impresso. Rodar de novo nao muda nada.
"""
import argparse
import json
import os
import re
import sys
import urllib.request

BASE = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000").rstrip("/")


def call(method, path, body=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + os.environ["LITELLM_MASTER_KEY"],
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def prefixo(tenant_key):
    return "tenant_" + re.sub(r"[^a-z0-9]+", "_", tenant_key.lower()).strip("_") + "_"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("tenant_key")
    ap.add_argument("--aliases", default="")
    ap.add_argument("--chaves", default="bridge,ai-assist")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--emitir-chaves")
    a = ap.parse_args(argv)
    pre = prefixo(a.tenant_key)
    infos = call("GET", "/model/info").get("data", [])
    nomes = {m["model_name"] for m in infos if m["model_name"].startswith(pre)}
    nomes |= {x for x in a.aliases.split(",") if x}
    models = sorted(nomes)
    # sem modelos, `models` vazio significaria "todos": usa alias inexistente (fail-closed)
    models_team = models or ["__sem_acesso__"]
    teams = call("GET", "/team/list")
    team = next((t for t in teams if t.get("team_alias") == a.tenant_key), None)
    mudou = []
    if team is None:
        mudou.append("team criado")
        if not a.dry_run:
            team = call("POST", "/team/new", {"team_alias": a.tenant_key, "models": models_team})
    elif sorted(team.get("models") or []) != sorted(models_team):
        mudou.append("team.models atualizado")
        if not a.dry_run:
            call("POST", "/team/update", {"team_id": team["team_id"], "models": models_team})
    team_id = (team or {}).get("team_id")
    chave_models = models_team
    existentes = {}
    if team_id:
        listado = call("GET", f"/key/list?team_id={team_id}&return_full_object=true&size=100")
        existentes = {k["key_alias"]: k for k in listado.get("keys", [])}
    novas = {}
    for suf in [s for s in a.chaves.split(",") if s]:
        alias = f"{a.tenant_key}-{suf}"
        k = existentes.get(alias)
        if k is None:
            mudou.append(f"chave {alias} criada")
            if not a.dry_run and team_id:
                novas[alias] = call("POST", "/key/generate", {
                    "team_id": team_id, "key_alias": alias, "models": chave_models}).get("key")
        elif sorted(k.get("models") or []) != sorted(chave_models):
            mudou.append(f"chave {alias} models atualizado")
            if not a.dry_run:
                call("POST", "/key/update", {"key": k["token"], "models": chave_models})
    if novas and a.emitir_chaves:
        fd = os.open(a.emitir_chaves, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(novas, f)
    print(json.dumps({"tenant": a.tenant_key, "models": models,
                      "alteracoes": mudou or ["nenhuma"], "dry_run": a.dry_run}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
