import glob
import json
import os
import re
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
MARCA = "DRILL_CHIEF_ANTIGO"
PERGUNTA_ANTIGA = "Pergunta do drill ao Chief aberto à moda antiga: chegou?"
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
        return sum(1 for evento in self.eventos() if evento["kind"] == "chief_resumed")

    def eventos(self):
        linhas = ler(os.path.join(self.base.estado, "events.jsonl")).splitlines()
        return [json.loads(linha) for linha in linhas if linha.strip()]

    def conversa(self):
        retomada = crew.module("crew_retomada")
        return ler(retomada.arquivo_da_conversa(dict(worktree=self.casa, name="chief"), "chief") or "")

    def chegou(self, marca):
        mensagens = []
        for linha in self.conversa().splitlines():
            entrada = json.loads(linha)
            texto = str(entrada.get("content", ""))
            if entrada.get("type") == "custom_message" and entrada.get("customType") == "crew" and marca in texto and PERGUNTA in texto:
                mensagens.append(texto[:400])
        return mensagens

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

    def antigo(self):
        return os.path.join(self.base.pasta, "antigo.jsonl")

    def pids_do_antigo(self):
        achados = []
        for pasta in glob.glob("/proc/[0-9]*"):
            ambiente = ler(os.path.join(pasta, "environ")).split("\0")
            if MARCA + "=" + self.antigo() in ambiente and os.path.realpath(os.path.join(pasta, "cwd")) == os.path.realpath(self.casa):
                achados.append(int(os.path.basename(pasta)))
        return achados

    def chief_a_moda_antiga_recebe_o_aviso(self):
        painel = self.base.env["HERDR_PANE_ID"]
        self.base.herdr("pane", "run", painel, "cd %s && %s=%s pi --approve --session %s" % (shlex.quote(self.casa), MARCA, shlex.quote(self.antigo()), shlex.quote(self.antigo())))
        self.base.esperar(self.pids_do_antigo, ESPERA_DA_VOLTA, "o Chief antigo abrir")
        time.sleep(5)
        self.base.crew_py("tell", "chief", PERGUNTA_ANTIGA)
        self.base.esperar(lambda: PERGUNTA_ANTIGA in ler(self.antigo()), ESPERA_DA_VOLTA, "o aviso chegar ao Chief antigo")
        if PERGUNTA_ANTIGA not in ler(os.path.join(self.base.estado, "_chief", "chief.inbox")):
            raise Fail("drill", "a caixa chief.inbox não guardou o aviso dado ao Chief antigo")
        if self.estado():
            raise Fail("drill", "o Chief antigo gravou o estado da conversa chief: %s" % self.estado())
        conversa = json.loads(ler(self.antigo()).splitlines()[0]).get("id")
        pids = self.pids_do_antigo()
        for pid in pids:
            os.kill(pid, signal.SIGTERM)
        self.base.esperar(lambda: not self.pids_do_antigo(), 30, "o Chief antigo sair")
        return "o Chief aberto com --session %s (conversa %s, pids %s) recebeu o aviso pelo painel %s, e a caixa chief.inbox o guardou" % (
            self.antigo(), conversa, pids, painel)

    def abrir_chief(self):
        painel = self.base.env["HERDR_PANE_ID"]
        self.base.herdr("pane", "run", painel, "cd %s && %s" % (shlex.quote(self.casa), crew.module("crew_chief").COMANDO))
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
        return any(e["kind"] == "stopped" and e["worker"] == self.base.nome for e in self.eventos())

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
        self.base.esperar(lambda: self.chegou("Causa da queda") and self.chegou("aviso automático"), ESPERA_DA_VOLTA,
                          "a mensagem de volta, com a pergunta no resumo, e o aviso da caixa chegarem ao Chief")
        antigas = [nome for nome in os.listdir(os.path.join(self.base.estado, "_chief")) if nome.endswith(".inbox") and nome != "chief.inbox"]
        if antigas:
            raise Fail("drill", "com a conversa chief aberta o aviso ainda foi para a caixa do painel: %s" % antigas)
        return "chegaram ao Chief reaberto, como mensagens do crew: %s" % " || ".join(self.chegou("Causa da queda") + self.chegou("aviso automático"))

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
        recusa = [saida[0][0] or saida[0][1] for saida in saidas if saida[1] != 0]
        return "de duas reaberturas ao mesmo tempo, só uma passou; a outra respondeu: %s" % " ".join(str(recusa[0]).split())[:300]

    def limpar(self):
        self.parar_vigia()
        try:
            pasta = crew.module("crew_retomada").pasta_das_conversas(dict(worktree=self.casa))
        except (OSError, KeyError):
            pasta = None
        self.base.limpar()
        if pasta and "crew-drill-" in os.path.basename(pasta):
            shutil.rmtree(pasta, ignore_errors=True)
        self.apagar_rastros_da_casa()

    def apagar_rastros_da_casa(self):
        cwd_do = crew.module("crew_drill").cwd_do
        pontes = glob.glob(os.path.join(crew.module("crew_retomada").pi_dir(), "claude-bridge", "sessions", "s-*.json"))
        processos = glob.glob(os.path.join(os.path.expanduser("~"), ".claude", "sessions", "*.json"))
        for caminho in [c for c in pontes if cwd_do(c) == self.casa] + [c for c in processos if cwd_do(c) == self.casa]:
            for achado in [caminho] + glob.glob(caminho[:-len(".json")] + ".*.key"):
                os.remove(achado)
        shutil.rmtree(os.path.join(os.path.expanduser("~"), ".claude", "projects", re.sub(r"[^A-Za-z0-9]", "-", self.casa)), ignore_errors=True)


SEQUENCIA = (
    ("preparar a sessão descartável", "preparar"),
    ("abrir o Worker de teste", "abrir_worker"),
    ("um Chief aberto à moda antiga (--session <arquivo>) recebe o aviso", "chief_a_moda_antiga_recebe_o_aviso"),
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
