import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time

Fail = None
crew = None

ESPERA_DA_VOLTA = 300
RODADAS_DE_FOLGA = 20
PERGUNTA = "Pergunta do drill do Chief: a caixa guarda isto?"
EXTENSOES = ("crew-state.ts", "crew-aviso.ts", os.path.join("lib", "crew-chief.ts"))
CONFIGURACAO = dict(defaultProvider="claude-bridge", defaultModel="claude-haiku-5-5", defaultThinkingLevel="low")


def ler(caminho):
    try:
        with open(caminho, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


class Prova:

    def __init__(self, base):
        self.base = base
        self.casa = os.path.join(base.pasta, "casa")
        self.vigia = None

    def estado(self):
        return crew.file_state(os.path.join(self.base.estado, "_chief", "chief.json"))

    def pid(self):
        return self.estado().get("pid")

    def reaberturas(self):
        return sum(1 for evento in crew.read_events() if evento and evento["kind"] == "chief_resumed")

    def conversa(self):
        retomada = crew.module("crew_retomada")
        return ler(retomada.arquivo_da_conversa(dict(worktree=self.casa, name="chief"), "chief") or "")

    def preparar(self):
        detalhe = self.base.preparar()
        for extensao in EXTENSOES:
            destino = os.path.join(self.casa, ".pi", "extensions", extensao)
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.copy(os.path.join(crew.ROOT, ".pi", "extensions", extensao), destino)
        os.makedirs(os.path.join(self.casa, "scripts"), exist_ok=True)
        open(os.path.join(self.casa, "scripts", "crew.py"), "w").close()
        crew.write_text(os.path.join(self.casa, ".pi", "settings.json"), json.dumps(CONFIGURACAO))
        self.base.env["CREW_CHIEF_DIR"] = self.casa
        return detalhe

    def abrir_chief(self):
        painel = self.base.env["HERDR_PANE_ID"]
        self.base.herdr("pane", "run", painel, "cd %s && pi --session-id chief" % shlex.quote(self.casa))
        self.esperar_o_chief(None)
        return "o Chief de teste abriu na conversa chief (pid %s)" % self.pid()

    def esperar_o_chief(self, antigo):
        vivo = crew.module("crew_causa").vivo
        self.base.esperar(lambda: self.pid() not in (None, antigo) and vivo(self.pid()) and self.estado().get("state") == "idle", ESPERA_DA_VOLTA,
                          "o Chief de teste ficar de pé")

    def subir_vigia(self):
        self.base.parar_batida.set()
        painel = self.estado()["pane"]
        registro = open(os.path.join(self.base.pasta, "vigia.log"), "a", encoding="utf-8")
        self.vigia = subprocess.Popen([sys.executable, os.path.join(crew.ROOT, "scripts", "crew.py"), "watch", "--chief", painel, "--every", "5"],
                                      env=self.base.env, stdout=registro, stderr=registro, stdin=subprocess.DEVNULL)
        self.base.esperar(lambda: os.path.exists(os.path.join(self.base.estado, "watch.heartbeat")), 30, "o Vigia do drill bater")
        return "o Vigia do drill roda com o Worker de teste aberto"

    def parar_vigia(self):
        if self.vigia and self.vigia.poll() is None:
            self.vigia.terminate()
            self.vigia.wait(30)

    def matar_o_pi(self):
        pid = self.pid()
        if os.path.realpath("/proc/%s/cwd" % pid) != os.path.realpath(self.casa):
            raise Fail("drill", "o pid %s do estado do Chief não é o Pi dele; não mato" % pid)
        os.kill(pid, signal.SIGKILL)
        self.base.esperar(lambda: not crew.module("crew_causa").vivo(pid), 30, "o Pi do Chief morrer")
        return pid

    def worker_parou(self):
        return any(e and e["kind"] == "stopped" and e["worker"] == self.base.nome for e in crew.read_events())

    def worker_caido_nao_reabre_o_chief(self):
        chief, antes = self.pid(), self.reaberturas()
        pid, worktree = self.base.estado_do_worker().get("pid"), self.base.meta()["worktree"]
        if os.path.realpath("/proc/%s/cwd" % pid) != os.path.realpath(worktree):
            raise Fail("drill", "o pid %s do estado do Worker não é o Pi dele; não mato" % pid)
        os.kill(pid, signal.SIGKILL)
        self.base.esperar(self.worker_parou, ESPERA_DA_VOLTA, "o Vigia ver o Worker de teste parado")
        time.sleep(RODADAS_DE_FOLGA)
        if self.reaberturas() != antes or self.pid() != chief:
            raise Fail("drill", "com só o Worker caído o Vigia mexeu no Chief (pid %s -> %s)" % (chief, self.pid()))
        return "o Worker caiu (pid %s), o Vigia o viu parado e deixou o Chief (pid %s) como estava" % (pid, chief)

    def reabre_uma_vez_so(self):
        antes = self.reaberturas()
        morto = self.matar_o_pi()
        self.esperar_o_chief(morto)
        time.sleep(RODADAS_DE_FOLGA)
        if self.reaberturas() != antes + 1:
            raise Fail("drill", "o Vigia reabriu o Chief %d vezes; devia ser 1" % (self.reaberturas() - antes))
        return "o Chief caiu (pid %s) e o Vigia o reabriu uma vez só (pid %s)" % (morto, self.pid())

    def avisos_de_quando_esteve_fora(self):
        morto = self.matar_o_pi()
        self.base.crew_py("ask", PERGUNTA, "--worker", self.base.nome, "--para", "dono", "--recommend", "sim")
        self.esperar_o_chief(morto)
        self.base.esperar(lambda: self.conversa().count(PERGUNTA) >= 2, ESPERA_DA_VOLTA, "o aviso e o resumo chegarem ao Chief")
        if "Causa da queda" not in self.conversa():
            raise Fail("drill", "o Chief voltou sem a mensagem com a causa da queda")
        return "o aviso da caixa e o resumo de volta chegaram ao Chief"

    def duas_reaberturas_ao_mesmo_tempo(self):
        self.parar_vigia()
        antes, morto = self.reaberturas(), self.matar_o_pi()
        comando = [sys.executable, os.path.join(crew.ROOT, "scripts", "crew.py"), "chief-reabrir"]
        provas = [subprocess.Popen(comando, env=self.base.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        saidas = [(prova.communicate(timeout=ESPERA_DA_VOLTA), prova.returncode) for prova in provas]
        passaram = [saida for saida, codigo in saidas if codigo == 0]
        if len(passaram) != 1 or self.reaberturas() != antes + 1:
            raise Fail("drill", "de duas reaberturas ao mesmo tempo devia passar uma; passaram %d: %s" % (len(passaram), saidas))
        self.esperar_o_chief(morto)
        return "de duas reaberturas ao mesmo tempo, só uma passou"

    def limpar(self):
        self.parar_vigia()
        try:
            pasta = crew.module("crew_retomada").pasta_das_conversas(dict(worktree=self.casa))
        except (OSError, KeyError):
            pasta = None
        self.base.limpar()
        if pasta and "crew-drill-" in os.path.basename(pasta):
            shutil.rmtree(pasta, ignore_errors=True)


SEQUENCIA = (
    ("preparar a sessão descartável", "preparar"),
    ("abrir o Worker de teste", "abrir_worker"),
    ("abrir o Chief de teste", "abrir_chief"),
    ("ligar o Vigia do drill", "subir_vigia"),
    ("com o Chief vivo e só o Worker caído, o Vigia não reabre o Chief", "worker_caido_nao_reabre_o_chief"),
    ("matar o Pi do Chief: o Vigia o reabre uma vez só", "reabre_uma_vez_so"),
    ("os avisos de enquanto o Chief esteve fora chegam a ele", "avisos_de_quando_esteve_fora"),
    ("duas reaberturas ao mesmo tempo: só uma passa", "duas_reaberturas_ao_mesmo_tempo"),
)


def drill(a):
    prova = Prova(crew.module("crew_drill").Drill(a.model))
    try:
        for nome, metodo in SEQUENCIA:
            alvo = prova.base if metodo == "abrir_worker" else prova
            if not prova.base.passo(nome, getattr(alvo, metodo)):
                break
    finally:
        prova.limpar()
    passos = prova.base.passos
    return dict(ok=len(passos) == len(SEQUENCIA) and all(p["ok"] for p in passos), sessao=prova.base.sessao, passos=passos)


def comando(a):
    relatorio = drill(a)
    if not relatorio["ok"]:
        raise Fail("drill", "; ".join("%s: %s" % (p["nome"], p["detalhe"] if not p["ok"] else "ok") for p in relatorio["passos"]))
    return relatorio


def registrar(sub):
    s = sub.add_parser("drill-chief", help="prove the Chief's return with real Herdr and Pi, in a disposable Herdr session: kill the test Chief's Pi and check the Vigia reopens it once, with the notices that came while it was out; run it on the VPS")
    s.add_argument("--model", help="provider/id:thinking of the test worker")
    s.set_defaults(fn=comando)
