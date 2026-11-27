import datetime
import json
import os
import unittest

from scripts.test_crew_vigia import VigiaCase, pr, verde_sem_registro

CREDITO = "Your credit balance is too low to access the Anthropic API."
DISCO = "ENOSPC: no space left on device, write"


def agora_utc(minutos=0):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutos)).strftime("%Y-%m-%dT%H:%M:%SZ")


def toon(valor):
    return json.dumps(valor, ensure_ascii=False) if valor == "" or any(c in valor for c in ',"\\\n') else valor


def feedback(*prompts, fim=False):
    cabecalho = "session:\n  file: /x/mesa.html\n  status: feedback\n" + ("  session_ended: true\n  ended_by: user\n" if fim else "")
    linhas = ["  %s,%s,%s,%s,%s" % (toon(""), toon(p["prompt"]), toon(""), toon(p.get("tag", "")), toon(p.get("text", ""))) for p in prompts]
    return cabecalho + "prompts[%d]{uid,prompt,selector,tag,text}:\n" % len(prompts) + "\n".join(linhas) + "\nnext_step: \"x\"\n"


def resposta(texto, id_="D1"):
    return dict(prompt=texto, tag="decisao", text=id_)


ESPERANDO = "session:\n  file: /x/mesa.html\n  status: waiting\n"
ENCERRADA = "session:\n  file: /x/mesa.html\n  status: ended\n  ended_by: user\n"
SEM_SESSAO = "error: \"No active Lavish Editor session for this file\"\ncode: NOT_FOUND\n"


class LavishFalso:
    def __init__(self):
        self.chamadas = []
        self.polls = []
        self.por_arquivo = {}

    def __call__(self, argv, ambiente):
        self.chamadas.append((argv, ambiente))
        if argv[1] == "poll":
            if argv[2] in self.por_arquivo:
                return self.por_arquivo[argv[2]].pop(0) if self.por_arquivo[argv[2]] else ESPERANDO
            return self.polls.pop(0) if self.polls else ESPERANDO
        return ""

    def comandos(self):
        return [argv[1:] for argv, _ in self.chamadas]

    def com(self, palavra):
        return [argv for argv, _ in self.chamadas if palavra in argv]


class MesaCase(VigiaCase):
    def setUp(self):
        super().setUp()
        self.lavish = LavishFalso()
        self.mesa = self.crew.module("crew_mesa")
        self.mesa.executar = self.lavish
        self.pagina = os.path.join(self.state, "_mesa", "mesa.html")

    def html(self):
        with open(self.pagina, encoding="utf-8") as f:
            return f.read()

    def gravar(self, nome, dados):
        os.makedirs(self.state, exist_ok=True)
        with open(os.path.join(self.state, nome), "w", encoding="utf-8") as f:
            json.dump(dados, f)

    def parar(self, meta, mensagem):
        agora = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with open(meta["state_file"], "w", encoding="utf-8") as f:
            json.dump(dict(state="idle", turns=1, pid=os.getpid(), at=agora, beat=agora, outcome=dict(type="error", message=mensagem)), f)

    def decisao(self, pergunta="Qual banco usamos?", worker="t-job"):
        return self.crew.module("crew_conversa").register(worker, "Test", dict(question=pergunta, recommend="o A, é mais simples"), "dono")

    def mensagens_da_mesa(self):
        return [linha for linha in self.told_chief() if linha.startswith("[mesa]")]


class PaginaDaMesa(MesaCase):
    def estado_gravado(self):
        janela = lambda usado, reset: dict(usado=usado, reset=reset, status="allowed_warning")
        self.gravar("_cota.json", dict(at=agora_utc(), fonte="quota-axi", host="vps", status="allowed_warning", limitante="seven_day",
                                       janelas={"5h": janela(37, "2026-11-27T20:00:00Z"), "7d": janela(82, "2026-11-29T22:00:00Z")},
                                       extra=dict(status="rejected", ligado=False)))
        memoria = lambda livre: dict(livre_mb=livre, total_mb=16384, mediana_mb=livre)
        base = dict(at=agora_utc(), alcancavel=True, nucleos=8, cpu=dict(), travas=[], folga=True, motivo=None)
        self.gravar("_recursos-pc.json", dict(base, host="pc", memoria=memoria(2560), disco=dict(livre_gb=4.7, total_gb=455.3),
                                              folga=False, motivo="disco: 4,7 GB livres (mínimo 10)"))
        self.gravar("_recursos-vps.json", dict(base, host="vps", memoria=memoria(8192), disco=dict(livre_gb=56.0, total_gb=190.0)))
        trava = dict(nome="mac", lugar="mac", caminho="/tmp/fm-mac.lock", com=dict(pid=9, onde="Nova-AI-prova", worker="nova-prova", ha_s=60),
                     esperando=[dict(pid=10, onde="PerpetualMiner-prova", worker="pm-prova", ha_s=5)])
        self.gravar("_recursos-mac.json", dict(base, host="mac", memoria=memoria(4096), disco=dict(livre_gb=20.0, total_gb=229.0), travas=[trava]))

    def test_a_pagina_sai_do_estado_gravado(self):
        self.estado_gravado()
        disco = self.add_worker(name="t-disco", pane="w4:p1")
        self.parar(disco, DISCO)
        self.add_worker(name="t-vivo", pane="w4:p2", branch="pi/vivo")
        self.decisao("Qual banco usamos?", worker="t-vivo")
        self.prs = [verde_sem_registro()]
        self.rodada()
        pagina = self.html()
        for pedaco in ("Qual banco usamos?", "D1", "82%", "37%", "disco: 4,7 GB livres", "PC", "VPS", "Mac", "nova-prova", "pm-prova",
                       "t-disco", "parou: disco", "t-vivo", "PR #12", "Titulo 12", "espera revisão"):
            self.assertIn(pedaco, pagina)

    def test_o_topo_traz_o_que_precisa_do_dono_e_os_parados_antes_da_cota(self):
        self.estado_gravado()
        self.parar(self.add_worker(name="t-disco"), DISCO)
        self.decisao(worker="t-disco")
        self.rodada()
        pagina = self.html()
        self.assertLess(pagina.index("Decisões para você"), pagina.index("Parados"))
        self.assertLess(pagina.index("Parados"), pagina.index("Cota"))
        self.assertLess(pagina.index("Cota"), pagina.index("Máquinas"))
        topo = pagina[:pagina.index("Cota")]
        self.assertIn("t-disco", topo)
        self.assertIn("parou: disco", topo)

    def test_credito_e_credencial_aparecem_como_decisao_do_dono(self):
        self.parar(self.add_worker(name="t-credito", pane="w4:p1"), CREDITO)
        self.parar(self.add_worker(name="t-chave", pane="w4:p2", branch="pi/chave"), "401 authentication_error: invalid x-api-key")
        self.parar(self.add_worker(name="t-disco", pane="w4:p3", branch="pi/disco"), DISCO)
        self.rodada()
        pagina = self.html()
        decisoes = pagina[pagina.index("Decisões para você"):pagina.index("Parados")]
        parados = pagina[pagina.index("Parados"):pagina.index("Cota")]
        for nome, causa in (("t-credito", "crédito"), ("t-chave", "credencial")):
            self.assertIn(nome, decisoes)
            self.assertIn(causa, decisoes)
            self.assertNotIn(nome, parados)
        self.assertIn("t-disco", parados)
        self.assertNotIn("t-disco", decisoes)

    def test_decisao_aberta_traz_o_campo_de_resposta_e_a_recomendacao(self):
        self.add_worker()
        self.decisao()
        self.rodada()
        pagina = self.html()
        self.assertIn('data-lavish-question="D1"', pagina)
        self.assertIn("queuePrompt", pagina)
        self.assertIn("o A, é mais simples", pagina)

    def test_decisao_respondida_some_da_pagina(self):
        self.add_worker()
        self.decisao()
        self.rodada()
        self.crew.cmd_answer(type("A", (), dict(id="D1", answer="usa o A"))())
        self.rodada()
        self.assertNotIn("Qual banco usamos?", self.html())

    def test_texto_do_estado_nao_vira_html(self):
        self.add_worker()
        self.decisao("<script>alert(1)</script> & <b>")
        self.rodada()
        self.assertNotIn("<script>alert", self.html())
        self.assertIn("&lt;script&gt;", self.html())

    def test_sem_nenhum_estado_a_pagina_ainda_sai(self):
        self.rodada()
        self.assertIn("Mesa", self.html())

    def test_pagina_igual_nao_e_regravada(self):
        self.add_worker()
        self.rodada()
        antes = os.stat(self.pagina).st_mtime_ns
        self.rodada()
        self.assertEqual(os.stat(self.pagina).st_mtime_ns, antes)

    def test_pr_fechada_nao_entra_na_esteira(self):
        self.add_worker()
        self.prs = [pr(numero=7, state="MERGED", title="Velha"), verde_sem_registro()]
        self.rodada()
        self.assertNotIn("Velha", self.html())


if __name__ == "__main__":
    unittest.main()
