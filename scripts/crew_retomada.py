import json
import os

Fail = None
crew = None

CAUSA_DO_BRIDGE = "conversa quebrada no bridge"
SEM_CAUSA = "não registrada"
ESPERA_DA_RESPOSTA = 120


def sessao():
    return crew.module("crew_sessao")


def pi_dir():
    return os.environ.get("PI_CODING_AGENT_DIR") or os.path.join(os.path.expanduser("~"), ".pi", "agent")


def pasta_das_conversas(meta):
    return os.path.join(pi_dir(), "sessions", sessao().pasta_da_sessao(meta["worktree"]))


def conversa_de(meta):
    return meta.get("conversa") or meta["name"]


def arquivo_da_conversa(meta, conversa):
    pasta = pasta_das_conversas(meta)
    nomes = os.listdir(pasta) if os.path.isdir(pasta) else []
    achados = sorted(nome for nome in nomes if nome.partition("_")[2] == conversa + ".jsonl")
    return os.path.join(pasta, achados[-1]) if achados else None


def proxima_conversa(meta):
    numero = 2
    while arquivo_da_conversa(meta, "%s-%d" % (meta["name"], numero)):
        numero += 1
    return "%s-%d" % (meta["name"], numero)


def copiar_conversa(meta):
    origem = arquivo_da_conversa(meta, conversa_de(meta))
    linhas = sessao().linhas_de(origem) if origem else []
    try:
        cabeca = json.loads(linhas[0])
    except (IndexError, ValueError):
        return None
    novo = proxima_conversa(meta)
    cabeca["id"] = novo
    destino = os.path.join(os.path.dirname(origem), "%s_%s.jsonl" % (os.path.basename(origem).partition("_")[0], novo))
    crew.write_text(destino, "\n".join([json.dumps(cabeca, ensure_ascii=False, separators=(",", ":"))] + linhas[1:]) + "\n")
    return novo, destino


def respostas(caminho):
    mensagens = [(evento.get("message") or {}) for evento in sessao().eventos([caminho])]
    return [mensagem for mensagem in mensagens if mensagem.get("role") == "assistant"]


def quebrou_de_novo(mensagem):
    desfecho = dict(type="error", message=mensagem.get("errorMessage"))
    return mensagem.get("stopReason") == "error" and crew.module("crew_causa").do_desfecho(desfecho) == CAUSA_DO_BRIDGE


def veredito_da_copia(caminho, ja):
    prazo = crew.time.time() + ESPERA_DA_RESPOSTA
    while crew.time.time() < prazo:
        novas = respostas(caminho)[ja:]
        if novas:
            return "quebrou" if quebrou_de_novo(novas[-1]) else "funcionou"
        crew.time.sleep(1)
    return "sem confirmação"


def comando_do_pi(conversa, modelo=None):
    comando = 'pi --session-id %s --approve -e "%s"' % (conversa, crew.posix(crew.EXTENSION))
    return comando + (" --model " + modelo if modelo else "")


def abrir_painel(meta, comando):
    aba = crew.herdr("pane", "tab", "create", "--workspace", crew.crew_workspace(), "--cwd", os.path.normpath(meta["worktree"]), "--label", meta["name"], "--no-focus",
                     "--env", "CREW_STATE_FILE=" + meta["state_file"], "--env", "CREW_AGENT_NAME=" + meta["name"], *crew.passthrough())
    pane = crew.find(aba, ("pane_id",))
    if not pane:
        raise Fail("pane", "Herdr did not return a pane id")
    meta["pane"] = pane
    crew.write_meta(meta)
    crew.herdr("agent", "pane", "run", pane, comando)
    return pane


def recomecou(visto, antes):
    chave = "pid" if antes.get("pid") else "at"
    return visto.get("state") == "idle" and visto.get(chave) != antes.get(chave)


def subir(meta, comando, limite):
    antes = crew.file_state(meta["state_file"])
    pane = abrir_painel(meta, comando)
    prazo = crew.time.time() + limite
    while not recomecou(crew.file_state(meta["state_file"]), antes):
        if crew.time.time() > prazo:
            tela = crew.herdr("agent", "pane", "read", pane, "--source", "recent-unwrapped", "--lines", "15")
            ponta = " | ".join(linha.strip() for linha in str(tela).splitlines()[-6:] if linha.strip())
            raise Fail("agent", "Pi did not become ready in %ds; the pane shows: %s" % (limite, ponta))
        crew.time.sleep(1)


def fechar_painel(meta):
    try:
        crew.herdr("pane", "pane", "close", meta["pane"])
    except Fail:
        return


def aviso_de_volta(causa):
    return "[chief] Retomada: você foi reaberto na mesma conversa. Causa da parada: %s. Continue de onde parou; o brief já está na conversa." % (causa or SEM_CAUSA)


def aviso_de_recomeco(meta):
    return ("[chief] Leia o arquivo %s e siga-o. Esta é uma conversa nova: a anterior quebrou no bridge. "
            "O que você já fez está na branch %s; veja `git log` e `git status` antes de refazer qualquer coisa." % (meta["brief"], meta["branch"]))


def entregar(meta, texto, a):
    crew.deliver_brief(meta, meta["pane"], a.prompt_timeout, text=texto)


def recomecar(meta, a):
    meta["conversa"] = proxima_conversa(meta)
    subir(meta, comando_do_pi(meta["conversa"], "%s:%s" % (meta["model"], meta["thinking"])), a.start_timeout)
    entregar(meta, aviso_de_recomeco(meta), a)
    return dict(conversa=meta["conversa"], copia="caiu no recomeço")


def pela_copia(meta, causa, a):
    copia = copiar_conversa(meta)
    if copia:
        meta["conversa"], caminho = copia
        ja = len(respostas(caminho))
        subir(meta, comando_do_pi(meta["conversa"]), a.start_timeout)
        entregar(meta, aviso_de_volta(causa), a)
        veredito = veredito_da_copia(caminho, ja)
        if veredito != "quebrou":
            return dict(conversa=meta["conversa"], copia=veredito)
        fechar_painel(meta)
    return recomecar(meta, a)


def refazer(meta, causa, a):
    fechar_painel(meta)
    if causa == CAUSA_DO_BRIDGE:
        return pela_copia(meta, causa, a)
    subir(meta, comando_do_pi(conversa_de(meta)), a.start_timeout)
    entregar(meta, aviso_de_volta(causa), a)
    return dict(conversa=conversa_de(meta), copia=None)


def recusar(meta):
    if meta.get("closed"):
        raise Fail("retomar", "worker %s is closed" % meta["name"])
    if meta.get("host"):
        raise Fail("retomar", "retomar does not cover a worker on another machine yet (%s runs on %s)" % (meta["name"], meta["host"]))


def retomar(a):
    meta = crew.read_meta(a.name)
    recusar(meta)
    causa = crew.module("crew_causa").da_parada(crew.file_state(meta["state_file"]))
    meta["closing"] = crew.now()
    crew.write_meta(meta)
    try:
        feito = refazer(meta, causa, a)
    finally:
        meta.pop("closing", None)
        crew.write_meta(meta)
    crew.emit("resumed", meta["name"], causa=causa, **feito)
    return dict(ok=True, worker=meta["name"], pane=meta["pane"], causa=causa, **feito)


def registrar(sub):
    s = sub.add_parser("retomar", help="reopen a stopped worker in the same conversation and tell it why it stopped (a copy of the conversation when the bridge broke it)")
    s.add_argument("name")
    s.add_argument("--start-timeout", type=int, default=90, help="seconds to wait for Pi to be ready")
    s.add_argument("--prompt-timeout", type=int, default=20, help="seconds to wait, after each send, for Pi to start on the message")
    s.set_defaults(fn=retomar)
    crew.module("crew_chief").registrar(sub)
    crew.module("crew_drill_sozinha").registrar(sub)
