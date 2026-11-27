import datetime
import json
import os
import re

Fail = None
crew = None

CONVERSA = "chief"
COMANDO = "pi --session-id %s --approve" % CONVERSA
TRAVA_SEGUNDOS = 300
ESPERA_DO_PI = 90


def arquivo(sufixo):
    return os.path.join(crew.STATE, "_chief", "chief." + sufixo)


def visto():
    return crew.file_state(arquivo("json"))


def conversa_aberta():
    estado = visto()
    return bool(estado) and estado.get("state") != "gone"


def avisar(painel, linha):
    pasta = os.path.join(crew.STATE, "_chief")
    os.makedirs(pasta, exist_ok=True)
    caixas = ["chief.inbox"]
    if painel and not conversa_aberta():
        caixas.append(re.sub(r"[^A-Za-z0-9_-]", "_", painel) + ".inbox")
    for caixa in caixas:
        with open(os.path.join(pasta, caixa), "a", encoding="utf-8") as f:
            f.write(linha + "\n")


def caiu(estado):
    causa = crew.module("crew_causa")
    pid = causa.pid_do(estado)
    return estado.get("state") != "gone" and pid is not None and not causa.vivo(pid)


def trava_ativa():
    dados = crew.file_state(arquivo("trava"))
    if not dados:
        return os.path.exists(arquivo("trava"))
    velha = crew.time.time() - dados.get("at", 0) > TRAVA_SEGUNDOS
    return not (velha or not crew.module("crew_causa").vivo(dados.get("pid", 0)))


def tomar_trava():
    caminho = arquivo("trava")
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    for _ in range(2):
        try:
            aberta = os.open(caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if trava_ativa():
                raise Fail("chief", "a retomada do Chief já está em andamento") from None
            os.remove(caminho)
            continue
        with os.fdopen(aberta, "w", encoding="utf-8") as f:
            json.dump(dict(pid=os.getpid(), at=crew.time.time()), f)
        return
    raise Fail("chief", "a retomada do Chief já está em andamento")


def soltar_trava():
    try:
        os.remove(arquivo("trava"))
    except OSError:
        return


def hora(instante):
    return instante.astimezone().strftime("%H:%M")


def resumo_do_vigia(desde):
    vigia = crew.module("crew_vigia")
    todos = crew.read_events()
    novos = [e for e in todos if e and (crew.module("crew_causa").instante(e.get("at")) or desde) >= desde]
    ciclo, sem_pr = vigia.ciclo_de_vida(todos), vigia.sem_pr_esperada()
    partes = [vigia.contar(novos, sem_pr, ciclo)] + vigia.agrupar(novos, sem_pr, ciclo)
    return "; ".join(parte for parte in partes if parte) or "nada de novo"


def mensagem_de_volta(antes, causa):
    queda = crew.module("crew_causa").instante(antes.get("beat") or antes.get("at")) or datetime.datetime.now(datetime.timezone.utc)
    return ("[crew] Retomada: você caiu e foi reaberto na mesma conversa. Causa da queda: %s. Caiu às %s e voltou às %s. "
            "Resumo do Vigia enquanto você esteve fora: %s. Os avisos dessa fase estão na sua caixa de entrada, logo abaixo. "
            "Continue de onde parou." % (causa or "não registrada", hora(queda), hora(datetime.datetime.now()), resumo_do_vigia(queda)))


def workspace_do(painel):
    info = crew.pane_info(painel) or {}
    return crew.find(info, ("workspace_id",)) or crew.crew_workspace()


def abrir_painel(antes):
    workspace = workspace_do(antes.get("pane"))
    try:
        crew.herdr("pane", "pane", "close", antes["pane"])
    except (Fail, KeyError):
        pass
    aba = crew.herdr("pane", "tab", "create", "--workspace", workspace, "--cwd", os.path.normpath(os.environ.get("CREW_CHIEF_DIR") or crew.ROOT), "--label", CONVERSA, "--no-focus",
                     *crew.passthrough())
    painel = crew.find(aba, ("pane_id",))
    if not painel:
        raise Fail("chief", "Herdr did not return a pane id")
    crew.herdr("agent", "pane", "run", painel, COMANDO)
    return painel


def esperar_o_pi(painel, antes):
    prazo = crew.time.time() + ESPERA_DO_PI
    while not crew.module("crew_retomada").recomecou(visto(), antes):
        if crew.time.time() > prazo:
            tela = crew.herdr("agent", "pane", "read", painel, "--source", "recent-unwrapped", "--lines", "15")
            ponta = " | ".join(linha.strip() for linha in str(tela).splitlines()[-6:] if linha.strip())
            raise Fail("chief", "Pi did not become ready in %ds; the pane shows: %s" % (ESPERA_DO_PI, ponta))
        crew.time.sleep(1)


def reabrir(_a=None):
    if not caiu(visto()):
        raise Fail("chief", "o Chief está de pé ou nunca abriu; não reabro")
    tomar_trava()
    antes = visto()
    if not caiu(antes):
        soltar_trava()
        raise Fail("chief", "outra retomada já trouxe o Chief de volta")
    causa = crew.module("crew_causa").da_parada(antes)
    crew.write_text(arquivo("volta"), mensagem_de_volta(antes, causa) + "\n")
    painel = abrir_painel(antes)
    esperar_o_pi(painel, antes)
    soltar_trava()
    crew.emit("chief_resumed", CONVERSA, causa=causa, pane=painel)
    return dict(ok=True, pane=painel, causa=causa, conversa=CONVERSA)


def seguir(painel):
    estado = visto()
    if not estado:
        return painel if crew.pane_alive(painel) else None
    if estado.get("state") == "gone":
        return None
    if caiu(estado) and not trava_ativa():
        try:
            return reabrir()["pane"]
        except Fail as e:
            crew.emit("chief_resume_failed", CONVERSA, error=e.error)
    return estado.get("pane") or painel


def registrar(sub):
    s = sub.add_parser("chief-reabrir", help="reopen the Chief in the `chief` conversation when only its Pi fell (the Vigia does this by itself)")
    s.set_defaults(fn=reabrir)
    crew.module("crew_drill_chief").registrar(sub)
