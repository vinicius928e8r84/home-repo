import contextlib
import json
import os
import shlex
import time
import types

try:
    import fcntl
except ImportError:
    import msvcrt
    fcntl = None

Fail = None
crew = None

TETOS = {"pc": 10, "vps": 6}
COM_PRIORIDADE = ("merge", "review")
LEITURA_VELHA_MINUTOS = 10
ACORDA_APOS_MINUTOS = 60
OCIOSO_MINUTOS = 60
ESPERA_DA_TRAVA_SEGUNDOS = 30


def arquivo():
    return os.path.join(crew.STATE, "_fila.json")


def tentar_travar(arquivo_da_trava):
    arquivo_da_trava.seek(0)
    try:
        if fcntl:
            fcntl.flock(arquivo_da_trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            msvcrt.locking(arquivo_da_trava.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return False
    return True


@contextlib.contextmanager
def trava():
    os.makedirs(crew.STATE, exist_ok=True)
    limite = time.monotonic() + ESPERA_DA_TRAVA_SEGUNDOS
    with open(arquivo() + ".lock", "a+b") as arquivo_da_trava:
        while not tentar_travar(arquivo_da_trava):
            if time.monotonic() > limite:
                raise Fail("fila", "a Fila está trancada há mais de %ds por outro processo; tente de novo" % ESPERA_DA_TRAVA_SEGUNDOS)
            time.sleep(0.05)
        try:
            yield
        finally:
            arquivo_da_trava.seek(0)
            if not fcntl:
                msvcrt.locking(arquivo_da_trava.fileno(), msvcrt.LK_UNLCK, 1)


def ler():
    lida = crew.file_state(arquivo())
    return lida.get("tarefas", []) if isinstance(lida, dict) else []


def gravar(tarefas):
    os.makedirs(crew.STATE, exist_ok=True)
    crew.write_text(arquivo(), json.dumps(dict(tarefas=tarefas), ensure_ascii=False))


def pendentes():
    return bool(ler())


def recursos():
    return crew.module("crew_recursos")


def maquina_de(host):
    if not host or host == "local":
        return recursos().aqui()
    return {hospedeiro: maquina for maquina, hospedeiro in recursos().HOSPEDEIRO.items()}.get(host)


def nome_de(host):
    return recursos().NOMES.get(maquina_de(host), host)


def abertos(maquina):
    return sum(1 for meta in crew.workers() if maquina_de(meta.get("host")) == maquina)


def leitura_de(maquina):
    leitura = crew.file_state(recursos().arquivo(maquina))
    if not leitura.get("at") or crew.minutes_since(leitura["at"]) > LEITURA_VELHA_MINUTOS:
        return {}
    return leitura


def motivo_da_cota(tipo, liberada):
    cota = crew.module("crew_cota")
    leitura = cota.ler_arquivo()
    if not leitura or cota.velha(leitura):
        return None
    if leitura.get("status") == "rejected" and (leitura.get("extra") or {}).get("status") != "allowed":
        return "cota no limite: tudo espera o reset"
    if leitura.get("status") == "allowed_warning" and tipo not in COM_PRIORIDADE and not liberada:
        return "cota perto do limite: só merge e revisão abrem"
    return None


def motivo_da_maquina(host):
    maquina = maquina_de(host)
    teto = TETOS.get(maquina)
    if teto and abertos(maquina) >= teto:
        return "teto: %d Workers abertos no %s (máximo %d)" % (abertos(maquina), nome_de(host), teto)
    leitura = leitura_de(maquina)
    if leitura and not leitura.get("folga", True):
        return "sem Folga no %s: %s" % (nome_de(host), leitura.get("motivo"))
    return None


def sem_clone_na_vps(repo):
    caminho = repo.get("path", "")
    verificar = 'test -d "$HOME"/%s/.git' % shlex.quote(caminho[2:]) if caminho.startswith("~/") else "test -d %s/.git" % shlex.quote(caminho)
    try:
        crew.module("crew_remote").ssh("vps", verificar, "clone")
    except Fail as e:
        return "a VPS não respondeu: %s" % e.error if e.step == "ssh" else "o repo não está clonado na VPS"
    return None


def escolher(a, repo, tipo, liberada=False):
    if getattr(a, "da_fila", False):
        return a.host or repo.get("host"), None
    fixa = a.host or repo.get("host")
    motivo = motivo_da_cota(tipo, liberada)
    if motivo:
        return fixa, motivo
    if fixa:
        return fixa, motivo_da_maquina(fixa)
    na_vps = motivo_da_maquina("vps") or sem_clone_na_vps(repo)
    if not na_vps:
        return "vps", None
    no_pc = motivo_da_maquina("local")
    if not no_pc:
        return "local", None
    return None, "VPS: %s; PC: %s" % (na_vps, no_pc)


def prioridade(tarefa):
    return (tarefa["tipo"] not in COM_PRIORIDADE, tarefa["t"])


def entrar(a, name, request, espera):
    resposta = dict(ok=True, queued=True, name=name, espera=espera, frente=getattr(a, "frente", None))
    if a.dry_run:
        return dict(resposta, dry_run=True)
    pedido = dict(repo=a.repo, task=a.task, type=a.type, model=a.model, request=request, done=a.done, context=a.context, host=a.host,
                  frente=getattr(a, "frente", None), start_timeout=a.start_timeout, prompt_timeout=a.prompt_timeout)
    tipo = a.type or crew.load("model_routing.json").get("default")
    with trava():
        tarefas = ler()
        if any(tarefa["name"] == name for tarefa in tarefas):
            raise Fail("name", "worker %r já espera na Fila" % name)
        tarefas.append(dict(name=name, tipo=tipo, t=crew.time.time(), desde=crew.now(), espera=espera, pedido=pedido))
        gravar(tarefas)
    if not crew.watcher_alive() and os.environ.get("HERDR_PANE_ID"):
        crew.start_watcher(crew.my_pane("watch"))
    return dict(resposta, lugar=len(tarefas))


def avisar_se_demorou(tarefa):
    minutos = int((crew.time.time() - tarefa["t"]) / 60)
    if tarefa.get("avisada") or not ("disco:" in tarefa["espera"] or minutos >= ACORDA_APOS_MINUTOS):
        return
    crew.emit("fila_espera", tarefa["name"], motivo=tarefa["espera"], minutos=minutos)
    tarefa["avisada"] = True


def abrir(tarefa, host):
    pedido = types.SimpleNamespace(**dict(tarefa["pedido"], host=host, dry_run=False, request_file=None, da_fila=True))
    try:
        crew.cmd_spawn(pedido)
    except Exception as e:
        if not crew.file_state(crew.meta_path(tarefa["name"])).get("error"):
            crew.emit("spawn_failed", tarefa["name"], step=getattr(e, "step", "fila"), error=getattr(e, "error", repr(e)))


def decidir(tarefa):
    pedido = tarefa["pedido"]
    repo = crew.load("repos.json").get(pedido["repo"])
    if repo is None:
        return None, None
    return escolher(types.SimpleNamespace(**pedido), repo, tarefa["tipo"], tarefa.get("liberada"))


def ocioso_ha_muito(meta, com_decisao):
    visto = crew.file_state(meta["state_file"])
    parado = visto.get("state") == "idle" and crew.minutes_since(visto.get("at")) >= OCIOSO_MINUTOS
    return parado and os.path.exists(meta["report"]) and meta["name"] not in com_decisao


def fechar_o_mais_antigo():
    com_decisao = {d["worker"] for d in crew.decisions().values() if d.get("status") == "open"}
    ociosos = [meta for meta in crew.workers() if ocioso_ha_muito(meta, com_decisao)]
    if ociosos:
        antigo = max(ociosos, key=lambda meta: crew.minutes_since(crew.file_state(meta["state_file"])["at"]))
        crew.module("crew_vigia").fechar(antigo["name"], force=True)


def anotar_a_rodada(vistas, aberta):
    por_nome = {tarefa["name"]: tarefa for tarefa in vistas}
    with trava():
        tarefas = [tarefa for tarefa in ler() if tarefa["name"] != aberta]
        for tarefa in tarefas:
            vista = por_nome.get(tarefa["name"], {})
            tarefa["espera"] = vista.get("espera", tarefa.get("espera"))
            tarefa["avisada"] = vista.get("avisada", tarefa.get("avisada", False))
        gravar(tarefas)


def rodada():
    tarefas = sorted(ler(), key=prioridade)
    proxima, espera_por_vaga = None, False
    for tarefa in tarefas:
        host, motivo = decidir(tarefa)
        tarefa["espera"] = motivo
        if motivo is None and proxima is None:
            proxima = (tarefa, host)
        elif motivo:
            avisar_se_demorou(tarefa)
            espera_por_vaga = espera_por_vaga or not motivo.startswith("cota")
    anotar_a_rodada(tarefas, proxima[0]["name"] if proxima else None)
    if proxima:
        abrir(*proxima)
    elif espera_por_vaga:
        fechar_o_mais_antigo()


def quadro(tarefa):
    fixa = tarefa["pedido"].get("host")
    return dict(name=tarefa["name"], tipo=tarefa["tipo"], maquina=maquina_de(fixa) if fixa else None, frente=tarefa["pedido"].get("frente"),
                espera=tarefa.get("espera"), desde=tarefa["desde"], liberada=bool(tarefa.get("liberada")))


def comando(a):
    if a.liberar:
        with trava():
            tarefas = ler()
            achada = next((tarefa for tarefa in tarefas if tarefa["name"] == a.liberar), None)
            if not achada:
                raise Fail("fila", "nenhuma Tarefa %r na Fila (veja `fila`)" % a.liberar)
            achada["liberada"] = True
            gravar(tarefas)
    if a.andar:
        rodada()
    return dict(ok=True, fila=[quadro(tarefa) for tarefa in sorted(ler(), key=prioridade)])


def registrar(sub):
    s = sub.add_parser("fila", help="the Tarefas waiting for Folga, with the reason and since when; --liberar lets one open despite the quota warning, --andar runs one round of the Fila now")
    s.add_argument("--liberar", metavar="NAME", help="open this Tarefa even with the quota near the limit (it still waits for Folga)")
    s.add_argument("--andar", action="store_true", help="run one round of the Fila now, as the watcher does")
    s.set_defaults(fn=comando)
