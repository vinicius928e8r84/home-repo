import datetime
import json
import os
import re

RESERVA_PADRAO = 16384


def pasta_da_sessao(cwd):
    return "--" + re.sub(r"[/\\:]", "-", re.sub(r"^[/\\]", "", cwd)) + "--"


def ler_json(caminho):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def linhas_de(caminho):
    try:
        with open(caminho, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []


def abertura(caminho):
    for linha in linhas_de(caminho)[:1]:
        try:
            return json.loads(linha).get("timestamp", "")
        except ValueError:
            return ""
    return ""


def em_utc(instante):
    try:
        return datetime.datetime.fromisoformat(instante).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        return ""


def sessoes_do_worker(pi_dir, cwd, aberto):
    desde = em_utc(aberto)
    pasta = os.path.join(pi_dir, "sessions", pasta_da_sessao(cwd))
    achadas = []
    for nome in os.listdir(pasta) if os.path.isdir(pasta) else []:
        caminho = os.path.join(pasta, nome)
        criada = abertura(caminho)
        if nome.endswith(".jsonl") and criada and criada[:19] >= desde:
            achadas.append((criada, caminho))
    return [caminho for _, caminho in sorted(achadas)]


def decodificar(linha):
    try:
        return json.loads(linha)
    except ValueError:
        return {}


def eventos(caminhos):
    for caminho in caminhos:
        for linha in linhas_de(caminho):
            if '"role":"assistant"' in linha or '"type":"compaction"' in linha:
                yield decodificar(linha)


def tamanho_do_contexto(usage):
    return sum(int(usage.get(campo) or 0) for campo in ("input", "output", "cacheRead", "cacheWrite"))


def modelos_do_catalogo(pasta):
    for provedor in ler_json(os.path.join(pasta, "models-store.json")).values():
        yield from provedor.get("models", []) if isinstance(provedor, dict) else []


def catalogo(pi_dir, modelo):
    for pasta in (pi_dir, os.path.expanduser("~/.pi/agent")):
        for item in modelos_do_catalogo(pasta):
            if item.get("id") == modelo:
                return item.get("name"), item.get("contextWindow")
    return None, None


def reserva_de(pi_dir, cwd, provedor, modelo):
    reserva = RESERVA_PADRAO
    for caminho in (os.path.join(pi_dir, "settings.json"), os.path.join(cwd, ".pi", "settings.json")):
        compactacao = ler_json(caminho).get("compaction") or {}
        reserva = compactacao.get("reserveTokens", reserva)
        reserva = (compactacao.get("modelOverrides") or {}).get("%s/%s" % (provedor, modelo), {}).get("reserveTokens", reserva)
    return reserva


def somar(caminhos):
    achado = dict(resposta=None, contexto=None, compactacoes=[], depois_de_compactar=False)
    for evento in eventos(caminhos):
        if evento.get("type") == "compaction":
            achado["compactacoes"].append(dict(em=evento.get("timestamp"), antes=evento.get("tokensBefore")))
            achado["depois_de_compactar"] = True
            continue
        resposta = evento.get("message") or {}
        if resposta.get("role") != "assistant":
            continue
        achado["resposta"], achado["depois_de_compactar"] = dict(resposta, em=evento.get("timestamp")), False
        tamanho = tamanho_do_contexto(resposta.get("usage") or {})
        achado["contexto"] = tamanho or achado["contexto"]
    return achado


def resumo(pi_dir, cwd, aberto):
    caminhos = sessoes_do_worker(pi_dir, cwd, aberto)
    achado = somar(caminhos)
    resposta = achado["resposta"] or {}
    modelo, provedor = resposta.get("model"), resposta.get("provider")
    nome, janela = catalogo(pi_dir, modelo)
    limite = janela - reserva_de(pi_dir, cwd, provedor, modelo) if janela else None
    falha = resposta.get("stopReason") == "error"
    return dict(sessoes=len(caminhos), modelo=modelo, nome=nome, esforco=resposta.get("thinkingLevel"), contexto=achado["contexto"],
                compacta_em=limite, compactacoes=achado["compactacoes"], depois_de_compactar=achado["depois_de_compactar"],
                erro=(resposta.get("errorMessage") or "erro sem mensagem") if falha else None, resposta_em=resposta.get("em"))
