import json
import os
import signal
import subprocess
import sys
import time

Fail = None
crew = None

ESPERA_DA_VOLTA = 300
ESPERA_DO_RESET = 30
RODADAS_DE_FOLGA = 20
HA_MINUTOS = 180
API = "529 overloaded_error: Overloaded (simulado pelo drill)"
DISCO = "ENOSPC: no space left on device, write (simulado pelo drill)"
REDE = "fetch failed: ECONNRESET (simulado pelo drill)"
LIMITE = "Claude quota exceeded — rate limit (5h) — resets em instantes: You're out of extra usage (simulado pelo drill)"
CREDITO = "400 Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing (simulado pelo drill)"
CREDENCIAL = "401 authentication_error: The API Key appears to be invalid or may have expired (simulado pelo drill)"


def hora(segundos):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(segundos))


class Prova:

    def __init__(self, base):
        self.base = base
        self.vigia = None

    def preparar(self):
        return self.base.preparar()

    def abrir_worker(self):
        return self.base.abrir_worker()

    def guardar_palavra(self):
        return self.base.guardar_palavra()

    def eventos(self):
        linhas = crew.module("crew_drill").ler(os.path.join(self.base.estado, "events.jsonl")).splitlines()
        return [json.loads(linha) for linha in linhas if linha.strip()]

    def voltas(self, causa):
        return sum(1 for e in self.eventos() if e["kind"] == "resumed" and e["worker"] == self.base.nome and e.get("causa") == causa)

    def decisoes_abertas(self):
        achadas = {}
        for linha in crew.module("crew_drill").ler(os.path.join(self.base.estado, "decisions.jsonl")).splitlines():
            if linha.strip():
                entrada = json.loads(linha)
                achadas.setdefault(entrada["id"], {}).update(entrada)
        return [d for d in achadas.values() if d.get("worker") == self.base.nome and d.get("status") == "open"]

    def subir_vigia(self):
        self.base.parar_batida.set()
        registro = open(os.path.join(self.base.pasta, "vigia.log"), "a", encoding="utf-8")
        argv = [sys.executable, os.path.join(crew.ROOT, "scripts", "crew.py"), "watch", "--chief", self.base.env["HERDR_PANE_ID"], "--every", "5"]
        self.vigia = subprocess.Popen(argv, env=self.base.env, stdout=registro, stderr=registro, stdin=subprocess.DEVNULL)
        self.base.esperar(lambda: os.path.exists(os.path.join(self.base.estado, "watch.heartbeat")), 30, "o Vigia do drill bater")
        return "o Vigia do drill roda com o Worker de teste aberto"

    def parar_vigia(self):
        if self.vigia and self.vigia.poll() is None:
            self.vigia.terminate()
            self.vigia.wait(30)

    def cair(self, mensagem, ha_segundos):
        base = self.base
        visto = base.estado_do_worker()
        pid = visto.get("pid")
        if os.path.realpath("/proc/%s/cwd" % pid) != os.path.realpath(base.meta()["worktree"]):
            raise Fail("drill", "o pid %s do estado do Worker não é o Pi dele; não mato" % pid)
        os.kill(pid, signal.SIGKILL)
        base.esperar(lambda: not crew.module("crew_causa").vivo(pid), 30, "o Pi morto sair da lista de processos")
        parou = hora(time.time() - ha_segundos)
        parado = dict(visto, state="idle", at=parou, beat=parou, outcome=dict(type="error", message=mensagem))
        crew.write_text(base.meta()["state_file"], json.dumps(parado))

    def voltou(self, causa, antes):
        base = self.base
        base.esperar(lambda: self.voltas(causa) > antes, ESPERA_DA_VOLTA, "o Vigia retomar o Worker parado por %s" % causa)
        base.esperar(lambda: base.estado_do_worker().get("turns", 0) >= 1 and not base.estado_do_worker().get("outcome")
                     and base.estado_do_worker().get("state") == "idle", ESPERA_DA_VOLTA, "o Worker terminar o turno da volta")
        base.lembra_da_palavra()
        return "o Vigia retomou sozinho o Worker parado por %s e ele lembrou a palavra" % causa

    def parado_por(self, causa, mensagem):
        antes = self.voltas(causa)
        self.cair(mensagem, HA_MINUTOS)
        return self.voltou(causa, antes)

    def api_fora(self):
        return self.parado_por("API fora", API)

    def disco(self):
        return self.parado_por("disco", DISCO)

    def rede(self):
        return self.parado_por("rede", REDE)

    def limite_de_uso(self):
        antes = self.voltas("limite de uso")
        self.cair(LIMITE, 5)
        agora = time.time()
        janela = dict(usado=100, reset=hora(agora + ESPERA_DO_RESET), status="rejected")
        cota = dict(at=hora(agora), status="rejected", limitante="five_hour", janelas={"5h": janela, "7d": None}, extra=dict(status="rejected"))
        crew.write_text(os.path.join(self.base.estado, "_cota.json"), json.dumps(cota))
        time.sleep(ESPERA_DO_RESET / 3)
        if self.voltas("limite de uso") != antes:
            raise Fail("drill", "o Vigia retomou o Worker antes do reset da cota")
        return self.voltou("limite de uso", antes)

    def do_dono(self, causa, mensagem):
        antes = self.voltas(causa)
        self.cair(mensagem, 5)
        self.base.esperar(self.decisoes_abertas, 120, "a Decisão de %s aparecer" % causa)
        time.sleep(RODADAS_DE_FOLGA)
        if self.voltas(causa) != antes:
            raise Fail("drill", "o Vigia retomou o Worker parado por %s sem o Dono responder" % causa)
        self.base.crew_py("answer", self.decisoes_abertas()[0]["id"], "feito")
        return self.voltou(causa, antes)

    def credito(self):
        return self.do_dono("crédito", CREDITO)

    def credencial(self):
        return self.do_dono("credencial", CREDENCIAL)


SEQUENCIA = (
    ("preparar a sessão descartável", "preparar"),
    ("abrir o Worker de teste", "abrir_worker"),
    ("o Worker guarda uma palavra", "guardar_palavra"),
    ("ligar o Vigia do drill", "subir_vigia"),
    ("API fora: volta sozinho depois do atraso", "api_fora"),
    ("disco: volta sozinho com espaço livre", "disco"),
    ("rede: volta sozinho quando a rede responde", "rede"),
    ("limite de uso: volta sozinho no reset da cota", "limite_de_uso"),
    ("crédito: vira Decisão do Dono e volta quando ele responde", "credito"),
    ("credencial: vira Decisão do Dono e volta quando ele responde", "credencial"),
)


def drill(a):
    prova = Prova(crew.module("crew_drill").Drill(a.model))
    try:
        for nome, metodo in SEQUENCIA:
            if not prova.base.passo(nome, getattr(prova, metodo)):
                break
    finally:
        prova.parar_vigia()
        prova.base.limpar()
    passos = prova.base.passos
    return dict(ok=len(passos) == len(SEQUENCIA) and all(p["ok"] for p in passos), sessao=prova.base.sessao, passos=passos)


def comando(a):
    relatorio = drill(a)
    if not relatorio["ok"]:
        raise Fail("drill", "; ".join("%s: %s" % (p["nome"], p["detalhe"] if not p["ok"] else "ok") for p in relatorio["passos"]))
    return relatorio


def registrar(sub):
    s = sub.add_parser("drill-sozinha", help="prove the automatic Retomada with real Herdr and Pi, in a disposable Herdr session: stop a test worker with each simulated cause and check the Vigia brings it back; run it on the VPS")
    s.add_argument("--model", help="provider/id:thinking of the test worker")
    s.set_defaults(fn=comando)
