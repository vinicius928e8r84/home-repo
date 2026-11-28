import json
import os
import socket
import types

crew = None

ATRASOS_DA_API = (2, 5, 15, 30)
TENTATIVAS_COM_CONDICAO = 3
ESPERA_DO_PI = 90
ESPERA_DA_MENSAGEM = 20
SITE_DA_REDE = ("api.anthropic.com", 443)
ESPERA_DA_REDE = 5
DO_DONO = {
    "crédito": "a conta da API ficou sem crédito (Plans & Billing)",
    "credencial": "a chave ou o login da API foi recusado",
}
SOZINHAS = ("API fora", "rede", "limite de uso")
CAUSAS = SOZINHAS + ("disco",) + tuple(DO_DONO)
SEM_AVISO_NA_HORA = SOZINHAS + tuple(DO_DONO)


def arquivo(meta):
    return os.path.join(crew.STATE, meta["name"], "retomada-sozinha.json")


def gravar(meta, registro):
    crew.write_text(arquivo(meta), json.dumps(registro, ensure_ascii=False))


def esquecer(meta):
    try:
        os.remove(arquivo(meta))
    except OSError:
        return


def epoca(texto):
    momento = crew.module("crew_causa").instante(texto)
    return momento.timestamp() if momento else None


def maximo(causa):
    return len(ATRASOS_DA_API) if causa == "API fora" else TENTATIVAS_COM_CONDICAO


def atraso_passou(registro, parou):
    base = max(parou, registro.get("ultima", 0))
    return crew.time.time() >= base + ATRASOS_DA_API[registro["tentativas"]] * 60


def disco_voltou():
    recursos = crew.module("crew_recursos")
    leitura = crew.module("crew_fila").leitura_de(recursos.aqui())
    livre = (leitura.get("disco") or {}).get("livre_gb")
    return isinstance(livre, (int, float)) and livre >= recursos.DISCO_MINIMO_GB[1]


def rede_voltou():
    try:
        socket.create_connection(SITE_DA_REDE, timeout=ESPERA_DA_REDE).close()
    except OSError:
        return False
    return True


def reset_passou(parou):
    cota = crew.module("crew_cota")
    leitura = cota.ler_arquivo()
    janela = (leitura.get("janelas") or {}).get(cota.JANELAS.get(leitura.get("limitante"))) or {}
    lida, reset = epoca(leitura.get("at")), epoca(janela.get("reset"))
    return lida is not None and reset is not None and lida >= parou and crew.time.time() >= reset


def vencida(causa, registro, parou):
    if causa == "API fora":
        return atraso_passou(registro, parou)
    if causa == "disco":
        return disco_voltou()
    if causa == "rede":
        return rede_voltou()
    return reset_passou(parou)


def tentar(meta, registro):
    registro["tentativas"] += 1
    registro["ultima"] = crew.time.time()
    gravar(meta, registro)
    pedido = types.SimpleNamespace(name=meta["name"], start_timeout=ESPERA_DO_PI, prompt_timeout=ESPERA_DA_MENSAGEM)
    crew.module("crew_retomada").retomar(pedido)


def avisar(meta, causa, registro):
    if registro.get("avisada"):
        return
    registro["avisada"] = True
    gravar(meta, registro)
    crew.emit("retomada_esgotada", meta["name"], causa=causa, tentativas=registro["tentativas"])


def pedir_ao_dono(meta, causa, registro):
    pergunta = "%s parou por %s: %s. Resolva e responda aqui; o Vigia reabre o Worker na mesma conversa." % (meta["name"], causa, DO_DONO[causa])
    decisao = crew.module("crew_conversa").register(meta["name"], meta["repo"], dict(question=pergunta, recommend="Resolver e responder `feito`."), "dono")
    registro.update(decisao=decisao["id"], consumida=False)
    gravar(meta, registro)


def pi_vivo(meta):
    causa = crew.module("crew_causa")
    pid = causa.pid_do(crew.file_state(meta["state_file"]))
    return pid is not None and causa.vivo(pid)


def pelo_dono(meta, causa, registro):
    decisao = crew.decisions().get(registro.get("decisao"))
    if decisao is None or registro.get("consumida"):
        pedir_ao_dono(meta, causa, registro)
    elif decisao.get("status") != "open":
        registro["consumida"] = True
        if pi_vivo(meta):
            gravar(meta, registro)
        else:
            tentar(meta, registro)


def saudavel(visto):
    return visto.get("state") == "idle" and visto.get("turns", 0) >= 1 and not visto.get("outcome")


def seguir(meta):
    visto = crew.file_state(meta["state_file"])
    causa = crew.module("crew_causa").da_parada(visto)
    if causa is None:
        if saudavel(visto):
            esquecer(meta)
        return
    parou = epoca(visto.get("at"))
    if parou is None or causa not in CAUSAS:
        return
    registro = crew.file_state(arquivo(meta))
    if registro.get("causa") != causa:
        registro = dict(causa=causa, tentativas=0)
    if causa in DO_DONO:
        pelo_dono(meta, causa, registro)
    elif registro["tentativas"] >= maximo(causa):
        avisar(meta, causa, registro)
    elif vencida(causa, registro, parou):
        tentar(meta, registro)


def rodada():
    erros = []
    for meta in crew.workers():
        if meta.get("host") or meta.get("closing"):
            continue
        try:
            seguir(meta)
        except crew.Fail as e:
            erros.append("%s: %s" % (meta["name"], e.error))
    return "; ".join(erros) or None
