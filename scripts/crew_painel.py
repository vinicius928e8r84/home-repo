import datetime
import os

import crew_causa
import crew_sessao

HORAS_DOS_FECHADOS = 12
TEXTO_MAXIMO = 60
ORDEM = {"!": 0, "?": 1, " ": 2, "-": 4}


def ler_json(caminho):
    return crew_sessao.ler_json(caminho)


def instante(texto):
    try:
        return datetime.datetime.fromisoformat(str(texto).replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def hora(texto):
    quando = instante(texto)
    return quando.strftime("%H:%M") if quando else "?"


def minutos(texto, agora):
    quando = instante(texto)
    return max(0, int((agora - quando).total_seconds() // 60)) if quando else 0


def curto(texto):
    junto = " ".join(str(texto or "").split())
    return junto if len(junto) <= TEXTO_MAXIMO else junto[: TEXTO_MAXIMO - 1] + "…"


def mil(tokens):
    return "%dk" % round(tokens / 1000)


def sessao_do(meta, contexto):
    if meta.get("host"):
        return ler_json(os.path.join(contexto["estado"], meta["name"], "session.json"))
    return crew_sessao.resumo(contexto["pi_dir"], meta["worktree"], meta.get("started"))


def modelo_e_esforco(meta, sessao, contexto):
    modelo = sessao.get("modelo") or meta.get("model", "").split("/")[-1]
    nome = sessao.get("nome") or crew_sessao.catalogo(contexto["pi_dir"], modelo)[0] or modelo
    esforco = sessao.get("esforco") or meta.get("thinking") or ""
    return ("%s %s" % (nome.replace("Claude ", ""), esforco)).strip()


def contexto_e_compactacoes(sessao, vivo):
    partes = []
    atual, limite = sessao.get("contexto"), sessao.get("compacta_em")
    feitas = sessao.get("compactacoes") or []
    if vivo and sessao.get("depois_de_compactar") and feitas:
        partes.append("compactou às %s" % hora(feitas[-1]["em"]))
    elif vivo and atual is not None and limite:
        partes.append("faltam %s até compactar" % mil(max(0, limite - atual)))
    elif vivo and atual is not None:
        partes.append("contexto %s" % mil(atual))
    if feitas:
        horas = ", ".join(hora(c["em"]) for c in feitas)
        partes.append("%d compactaç%s (%s)" % (len(feitas), "ão" if len(feitas) == 1 else "ões", horas))
    return " · ".join(partes)


def pedidos_abertos(meta, decisoes):
    return [d for d in decisoes.values() if d.get("worker") == meta["name"] and d.get("status") == "open"]


def parada_de(meta, visto, sessao, agora):
    causa = None if meta.get("host") else crew_causa.da_parada(visto, agora)
    if causa:
        return "parou: %s" % causa
    if sessao.get("erro") and visto.get("state", "starting") != "working":
        return "ERRO: %s" % curto(sessao["erro"])
    return None


def estado_de(meta, contexto, sessao):
    visto = ler_json(meta.get("state_file", ""))
    vigia = ler_json(os.path.join(contexto["estado"], meta["name"], "watch.json"))
    estado, agora = visto.get("state", "starting"), contexto["agora"]
    desde = minutos(visto.get("at"), agora)
    if meta.get("closed"):
        return "-", "fechado às %s" % hora(meta["closed"])
    if meta.get("error"):
        return "!", "ERRO: %s" % curto(meta["error"].get("error"))
    if estado == "gone":
        return "!", "painel fechou"
    parada = parada_de(meta, visto, sessao, agora)
    if parada:
        return "!", parada
    if vigia.get("stalled") and estado == "working":
        return "!", "parado há %d min" % minutos((vigia.get("progress") or {}).get("at") or visto.get("at"), agora)
    esperando = pedidos_abertos(meta, contexto["decisoes"])
    if esperando:
        return "?", "espera dono: %s" % curto(esperando[0].get("question"))
    if estado == "working":
        return " ", "trabalhando · turno %d min" % desde
    return " ", "ocioso há %d min" % desde if estado == "idle" else "abrindo"


def pr_de(meta, contexto):
    prs = contexto["prs"]
    if prs is None:
        return "PR sem leitura"
    achadas = [p for p in prs.get(meta["repo"], []) if p.get("branch") == meta.get("branch")]
    if not achadas:
        return "sem PR"
    pr = sorted(achadas, key=lambda p: (p.get("state") == "OPEN", p["number"]))[-1]
    return "PR #%d %s %s" % (pr["number"], pr["head"][:7], pr.get("estado", ""))


def linha_de(meta, contexto):
    sessao = sessao_do(meta, contexto)
    marca, estado = estado_de(meta, contexto, sessao)
    partes = ["%s %s" % (marca, meta["name"]), "%s · %s" % (meta["repo"], meta.get("type", "?")), modelo_e_esforco(meta, sessao, contexto), estado,
              "aberto %s" % hora(meta.get("started")), contexto_e_compactacoes(sessao, marca != "-" and estado != "painel fechou"), pr_de(meta, contexto)]
    return dict(marca=marca, aberto=meta.get("started") or "", ocioso=estado.startswith("ocioso"), texto="  ".join(p for p in partes if p))


def chave_de_ordem(linha):
    grupo = ORDEM.get(linha["marca"], 2) + (1 if linha["ocioso"] else 0)
    return (grupo, linha["aberto"])


def deve_aparecer(meta, fechados, agora):
    if not meta.get("closed"):
        return True
    return fechados or minutos(meta["closed"], agora) < HORAS_DOS_FECHADOS * 60


def prs_do_vigia(estado):
    achado = ler_json(os.path.join(estado, "prs.json")).get("prs")
    return achado if isinstance(achado, dict) else None


def montar(metas, contexto):
    linhas = [linha_de(m, contexto) for m in metas if deve_aparecer(m, contexto["fechados"], contexto["agora"])]
    linhas.sort(key=chave_de_ordem)
    atencao = len([x for x in linhas if x["marca"] in "!?"])
    cabecalho = "Time: %d workers · %d precisam de atenção" % (len(linhas), atencao)
    return "\n".join([cabecalho] + [x["texto"] for x in linhas])


def painel(metas, decisoes, estado, fechados=False):
    pi_dir = os.environ.get("PI_CODING_AGENT_DIR") or os.path.expanduser("~/.pi/agent")
    contexto = dict(estado=estado, decisoes=decisoes, pi_dir=pi_dir, fechados=fechados, prs=prs_do_vigia(estado),
                    agora=datetime.datetime.now().astimezone())
    return montar(metas, contexto)
