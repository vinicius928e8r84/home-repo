import datetime
import json
import os

Fail = None
crew = None

TITULO = "## Precisa do dono"
DIAS_DE_ESPERA = 7
NADA = "nada precisa de você agora"
LER_ESTADO_DO_LAVISH = 'cat "${LAVISH_AXI_STATE_DIR:-$HOME/.lavish-axi}/state.json" 2>/dev/null || echo "{}"'


def arquivo():
    return os.path.join(crew.STATE, "dono.jsonl")


def itens_locais():
    out = {}
    for linha in crew.file_text(arquivo()).splitlines():
        if linha.strip():
            entrada = json.loads(linha)
            out.setdefault(entrada["id"], {}).update(entrada)
    return out


def gravar(entrada):
    os.makedirs(crew.STATE, exist_ok=True)
    with open(arquivo(), "a", encoding="utf-8") as f:
        f.write(json.dumps(entrada, ensure_ascii=False) + "\n")


def comando(a):
    itens = itens_locais()
    if a.acao == "add":
        texto = " ".join(a.valor.split())
        if not texto:
            raise Fail("dono", "o texto está vazio: diga o que o dono precisa fazer")
        ident = "L%d" % (len(itens) + 1)
        gravar(dict(id=ident, at=crew.now(), text=texto, status="open"))
        return dict(ok=True, id=ident)
    ident = a.valor.upper()
    if ident not in itens:
        raise Fail("dono", "não há item %s na lista (veja `board`)" % a.valor)
    if itens[ident]["status"] != "open":
        raise Fail("dono", "%s já estava feito" % ident)
    gravar(dict(id=ident, status="done", done_at=crew.now()))
    return dict(ok=True, id=ident)


def recente(sessao):
    parado = datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(sessao["updated_at"].replace("Z", "+00:00"))
    return parado < datetime.timedelta(days=DIAS_DE_ESPERA)


def espera_o_dono(sessao, decisoes):
    if sessao.get("status") != "open":
        return False
    if sessao.get("url") and sessao["url"] in decisoes:
        return True
    chat = sessao.get("chat") or []
    return recente(sessao) and not (chat and chat[-1].get("role") == "user")


def paginas_abertas(texto, decisoes=""):
    sessoes = json.loads(texto).get("sessions", {}).values()
    return [(os.path.splitext(os.path.basename(s["file"].replace("\\", "/")))[0], s.get("url")) for s in sessoes if espera_o_dono(s, decisoes)]


def hosts():
    return [h for h in os.environ.get("CREW_LAVISH_HOSTS", "vps").split(",") if h.strip()]


def ler_do_pc():
    pasta = os.environ.get("LAVISH_AXI_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".lavish-axi")
    return crew.file_text(os.path.join(pasta, "state.json")) or "{}"


def ler_de(host):
    return crew.remote().ssh(host, LER_ESTADO_DO_LAVISH, "lavish")


def paginas(decisoes):
    achadas, avisos = [], []
    for onde, ler in [("o PC", ler_do_pc)] + [(h, lambda h=h: ler_de(h)) for h in hosts()]:
        try:
            achadas += paginas_abertas(ler(), decisoes)
        except (Fail, ValueError, KeyError) as e:
            avisos.append("não consegui ler as páginas lavish de %s: %s" % (onde, getattr(e, "error", e)))
    return achadas, avisos


def linhas(decisoes_abertas):
    out = [TITULO]
    itens = []
    for d in sorted(decisoes_abertas, key=lambda d: d["at"]):
        itens.append("- **%s** [%s] %s. Responder: `python scripts/crew.py answer %s \"...\"`" % (d["id"], d["worker"], crew.first_line(d["question"]), d["id"]))
    achadas, avisos = paginas(" ".join("%s %s" % (d["question"], d.get("recommend") or "") for d in decisoes_abertas))
    for nome, link in achadas:
        itens.append("- **página** [%s] responder na página%s" % (nome, " — " + link if link else ""))
    for item in itens_locais().values():
        if item["status"] == "open":
            itens.append("- **%s** %s. Quando fizer: `python scripts/crew.py dono done %s`" % (item["id"], item["text"], item["id"]))
    out += itens or ["- " + NADA]
    out += ["- (%s)" % aviso for aviso in avisos]
    return out + [""]
