import glob
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

Fail = None
crew = None

MODELO = "claude-bridge/claude-haiku-5-5:low"
PEDIDO = ("Isto é um teste do drill da Retomada, não um trabalho. Responda apenas `pronto` e espere as mensagens do chief. "
          "Não crie arquivos, não escreva relatório e não rode comandos que o chief não mandou.")
PRONTO = "Você respondeu `pronto`."
COMANDO_LONGO = "Rode `sleep 90` com a ferramenta bash e só depois responda `feito`."
PERGUNTA = "Qual palavra pedi para você guardar? Responda só com a palavra."
ESPERA_DO_TURNO = 300
ESPERA_DO_SERVIDOR = 30
BATIDA_SEGUNDOS = 10


def texto_da(mensagem):
    blocos = mensagem.get("content") or []
    return " ".join(bloco.get("text", "") for bloco in blocos if isinstance(bloco, dict))


class Drill:

    def __init__(self, modelo):
        self.sessao = "drill-%d-%d" % (os.getpid(), int(time.time()))
        self.pasta = tempfile.mkdtemp(prefix="crew-drill-")
        self.estado = os.path.join(self.pasta, "estado")
        self.modelo = modelo or MODELO
        self.tarefa = "drill-%d" % os.getpid()
        self.nome = "dr-" + self.tarefa
        self.palavra = "girassol-" + uuid.uuid4().hex[:6]
        self.passos = []
        self.servidor = None
        self.copia = None
        self.parar_batida = threading.Event()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("HERDR_", "CREW_"))}
        self.env.update(CREW_STATE_DIR=self.estado, CREW_REPOS=os.path.join(self.pasta, "repos.json"), CREW_HERDR_SESSION=self.sessao)

    def rodar(self, argv):
        feito = subprocess.run(argv, env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=ESPERA_DO_TURNO)
        if feito.returncode != 0:
            raise Fail("drill", "%s: %s" % (" ".join(argv[:4]), (feito.stderr or feito.stdout).strip()[-400:]))
        return feito.stdout

    def herdr(self, *args):
        return self.rodar(["herdr", "--session", self.sessao, *args])

    def crew_py(self, *args):
        return json.loads(self.rodar([sys.executable, os.path.join(crew.ROOT, "scripts", "crew.py"), *args]))

    def esperar(self, condicao, limite, o_que):
        prazo = time.time() + limite
        while time.time() < prazo:
            if condicao():
                return
            time.sleep(2)
        raise Fail("drill", "esperei %ds por %s e não veio" % (limite, o_que))

    def servidor_responde(self):
        try:
            self.herdr("workspace", "list")
        except Fail:
            return False
        return True

    def subir_servidor(self):
        with open(os.path.join(self.pasta, "herdr.log"), "a", encoding="utf-8") as registro:
            self.servidor = subprocess.Popen(["herdr", "--session", self.sessao, "server"], env=self.env, stdout=registro, stderr=registro,
                                             stdin=subprocess.DEVNULL, start_new_session=True)
        self.esperar(self.servidor_responde, ESPERA_DO_SERVIDOR, "o Herdr descartável subir")

    def parar_servidor(self):
        try:
            self.herdr("server", "stop")
        except Fail:
            pass
        try:
            self.servidor.wait(ESPERA_DO_SERVIDOR)
        except subprocess.TimeoutExpired:
            self.servidor.kill()
            self.servidor.wait()

    def preparar_repo(self):
        origem, repo = os.path.join(self.pasta, "origem.git"), os.path.join(self.pasta, "Drill")
        self.rodar(["git", "init", "-q", "--bare", "-b", "main", origem])
        self.rodar(["git", "clone", "-q", origem, repo])
        with open(os.path.join(repo, "LEIAME.txt"), "w", encoding="utf-8") as f:
            f.write("repo de teste do drill\n")
        for comando in (["add", "."], ["-c", "user.name=drill", "-c", "user.email=drill@example.com", "commit", "-q", "-m", "inicio"], ["push", "-q", "origin", "HEAD:main"]):
            self.rodar(["git", "-C", repo, *comando])
        configuracao = dict(Drill=dict(path=repo, remote="none", short="dr", branch="pi/{task}", default_branch="main", host="local"))
        with open(self.env["CREW_REPOS"], "w", encoding="utf-8") as f:
            json.dump(configuracao, f)

    def bater(self):
        os.makedirs(self.estado, exist_ok=True)
        while not self.parar_batida.wait(BATIDA_SEGUNDOS):
            self.tocar_batida()

    def tocar_batida(self):
        with open(os.path.join(self.estado, "watch.heartbeat"), "w", encoding="utf-8") as f:
            json.dump(dict(chief=self.env["HERDR_PANE_ID"]), f)

    def preparar(self):
        self.preparar_repo()
        self.subir_servidor()
        aberta = json.loads(self.herdr("workspace", "create", "--label", "chief", "--cwd", self.pasta, "--no-focus"))
        self.env["HERDR_PANE_ID"] = crew.find(aberta, ("pane_id",))
        os.makedirs(self.estado, exist_ok=True)
        self.tocar_batida()
        threading.Thread(target=self.bater, daemon=True).start()
        return "sessão %s, repo de teste e painel do chief em %s" % (self.sessao, self.pasta)

    def meta(self):
        with open(os.path.join(self.estado, self.nome, "meta.json"), encoding="utf-8") as f:
            return json.load(f)

    def estado_do_worker(self):
        return crew.file_state(self.meta()["state_file"])

    def respostas(self):
        retomada = crew.module("crew_retomada")
        arquivo = retomada.arquivo_da_conversa(self.meta(), retomada.conversa_de(self.meta()))
        return retomada.respostas(arquivo) if arquivo else []

    def abrir_worker(self):
        self.crew_py("spawn", "Drill", self.tarefa, "--model", self.modelo, "--request", PEDIDO, "--done", PRONTO)
        self.esperar(lambda: self.respostas() and self.estado_do_worker().get("state") == "idle", ESPERA_DO_TURNO, "o Worker de teste responder")
        return "Worker %s aberto na conversa %s" % (self.nome, self.nome)

    def perguntar(self, texto):
        antes = len(self.respostas())
        self.crew_py("tell", self.nome, texto)
        self.esperar(lambda: len(self.respostas()) > antes and self.estado_do_worker().get("state") == "idle", ESPERA_DO_TURNO, "a resposta do Worker")
        return texto_da(self.respostas()[-1])

    def lembra_da_palavra(self):
        resposta = self.perguntar(PERGUNTA)
        if self.palavra not in resposta:
            raise Fail("drill", "o Worker voltou sem lembrar a conversa: respondeu %r" % resposta[:120])

    def guardar_palavra(self):
        self.perguntar("Guarde a palavra %s. Responda apenas: ok" % self.palavra)
        return "o Worker guardou %s" % self.palavra

    def retomar_e_conferir(self, esperado=None):
        feito = self.crew_py("retomar", self.nome)
        if esperado and feito["causa"] != esperado:
            raise Fail("drill", "a causa da parada devia ser %r e veio %r" % (esperado, feito["causa"]))
        self.esperar(lambda: self.estado_do_worker().get("state") == "idle", ESPERA_DO_TURNO, "o Worker terminar o turno da volta")
        self.lembra_da_palavra()
        return "voltou na conversa %s (causa: %s) e lembrou a palavra" % (feito["conversa"], feito["causa"] or "nenhuma registrada")

    def filhos_do_pi(self, pid):
        achados = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True, check=False)
        return [int(numero) for numero in achados.stdout.split()]

    def matar_pi(self):
        pid = self.estado_do_worker().get("pid")
        if os.path.realpath("/proc/%s/cwd" % pid) != os.path.realpath(self.meta()["worktree"]):
            raise Fail("drill", "o pid %s do estado do Worker não é o Pi dele; não mato" % pid)
        self.crew_py("tell", self.nome, COMANDO_LONGO)
        self.esperar(lambda: self.filhos_do_pi(pid), ESPERA_DO_TURNO, "o Pi rodar o comando")
        for alvo in self.filhos_do_pi(pid) + [pid]:
            os.kill(alvo, signal.SIGKILL)
        return self.retomar_e_conferir("Pi saiu")

    def fechar_painel(self):
        self.herdr("pane", "close", self.meta()["pane"])
        return self.retomar_e_conferir()

    def reiniciar_herdr(self):
        self.parar_servidor()
        self.subir_servidor()
        return self.retomar_e_conferir()

    def do_bridge(self):
        worktree, achados = self.meta()["worktree"], []
        for caminho in glob.glob(os.path.join(crew.module("crew_retomada").pi_dir(), "claude-bridge", "sessions", "s-*.json")):
            with open(caminho, encoding="utf-8") as f:
                estado = json.load(f)
            projetos = os.path.join(os.path.expanduser("~"), ".claude", "projects", "*", str(estado.get("ccSessionId")) + ".jsonl")
            achados += [(caminho, transcript) for transcript in glob.glob(projetos) if estado.get("cwd") == worktree]
        return achados

    def quebrar_bridge(self):
        achados = self.do_bridge()
        if not achados:
            raise Fail("drill", "não achei o transcript do bridge desta conversa")
        transcript = max(achados, key=lambda par: os.path.getmtime(par[1]))[1]
        with open(transcript, encoding="utf-8") as f:
            linhas = f.read().splitlines()
        with open(transcript, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas[:-2]) + "\n")
        self.crew_py("tell", self.nome, "Responda apenas: ok")
        self.esperar(lambda: self.estado_do_worker().get("outcome"), ESPERA_DO_TURNO, "o bridge falhar")
        feito = self.crew_py("retomar", self.nome)
        if feito["causa"] != "conversa quebrada no bridge":
            raise Fail("drill", "o bridge falhou por %r, não por conversa quebrada" % feito["causa"])
        self.esperar(lambda: self.estado_do_worker().get("state") == "idle", ESPERA_DO_TURNO, "o Worker terminar o turno da volta")
        self.copia = feito["copia"]
        if feito["copia"] == "funcionou":
            self.lembra_da_palavra()
        return "a cópia da conversa %s: %s" % (feito["conversa"], feito["copia"])

    def apagar_conversas(self):
        try:
            caminhos = [caminho for par in self.do_bridge() for caminho in par]
            pasta = crew.module("crew_retomada").pasta_das_conversas(self.meta())
        except (OSError, ValueError, KeyError):
            return
        for caminho in caminhos:
            os.remove(caminho)
        shutil.rmtree(pasta, ignore_errors=True)

    def passo(self, nome, funcao):
        try:
            detalhe, ok = funcao(), True
        except (Fail, OSError, ValueError, KeyError, subprocess.SubprocessError) as erro:
            detalhe, ok = str(getattr(erro, "error", erro)), False
        self.passos.append(dict(nome=nome, ok=ok, detalhe=detalhe))
        return ok

    def limpar(self):
        self.parar_batida.set()
        try:
            self.crew_py("close", self.nome, "--force")
        except (Fail, OSError, ValueError):
            pass
        if self.servidor:
            self.parar_servidor()
        try:
            self.herdr("session", "delete", self.sessao)
        except Fail:
            pass
        self.apagar_conversas()
        shutil.rmtree(self.pasta, ignore_errors=True)


SEQUENCIA = (
    ("preparar a sessão descartável", "preparar"),
    ("abrir o Worker de teste", "abrir_worker"),
    ("o Worker guarda uma palavra", "guardar_palavra"),
    ("matar o Pi no meio de um comando", "matar_pi"),
    ("fechar o painel", "fechar_painel"),
    ("reiniciar o Herdr", "reiniciar_herdr"),
    ("cópia da conversa depois do bridge quebrado", "quebrar_bridge"),
)


def drill(a):
    prova = Drill(a.model)
    try:
        for nome, metodo in SEQUENCIA:
            if not prova.passo(nome, getattr(prova, metodo)):
                break
    finally:
        prova.limpar()
    return dict(ok=len(prova.passos) == len(SEQUENCIA) and all(p["ok"] for p in prova.passos), sessao=prova.sessao, copia=prova.copia, passos=prova.passos)


def comando(a):
    relatorio = drill(a)
    if not relatorio["ok"]:
        raise Fail("drill", "; ".join("%s: %s" % (p["nome"], p["detalhe"] if not p["ok"] else "ok") for p in relatorio["passos"]))
    return relatorio


def registrar(sub):
    s = sub.add_parser("drill", help="prove the Retomada with real Herdr and Pi: in a disposable Herdr session, open a test worker, drop it every way and check it comes back")
    s.add_argument("--model", help="provider/id:thinking of the test worker (default: %s)" % MODELO)
    s.set_defaults(fn=comando)
