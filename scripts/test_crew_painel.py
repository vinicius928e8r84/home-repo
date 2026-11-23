import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS)
import crew_painel
import crew_remote
import crew_sessao
import test_crew_remote as remoto

AGORA = None
CATALOGO = {"anthropic": {"models": [{"id": "claude-opus-5-5", "name": "Claude Opus 5.5", "contextWindow": 1000000}]}}
AJUSTES = {"compaction": {"modelOverrides": {"claude-bridge/claude-opus-5-5": {"reserveTokens": 850000}}}}


def iso(minutos_atras=0):
    return (AGORA - datetime.timedelta(minutes=minutos_atras)).isoformat(timespec="seconds")


def utc(minutos_atras=0):
    return (AGORA - datetime.timedelta(minutes=minutos_atras)).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def linha(**campos):
    return json.dumps(campos, separators=(",", ":"))


def cabeca(minutos_atras):
    return linha(type="session", version=3, timestamp=utc(minutos_atras))


def resposta(minutos_atras, entrada=2, saida=100, **extra):
    uso = dict(input=entrada, output=saida, cacheRead=extra.pop("lido", 0), cacheWrite=extra.pop("escrito", 0))
    mensagem = dict(role="assistant", provider="claude-bridge", model="claude-opus-5-5", thinkingLevel="medium",
                    stopReason=extra.pop("parou", "toolUse"), usage=uso, **extra)
    return linha(type="message", timestamp=utc(minutos_atras), message=mensagem)


def compactacao(minutos_atras, antes):
    return linha(type="compaction", timestamp=utc(minutos_atras), tokensBefore=antes, summary="x")


def gravar(caminho, texto):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)


class Base(unittest.TestCase):
    def setUp(self):
        global AGORA
        AGORA = datetime.datetime.now().astimezone()
        self.tmp = tempfile.mkdtemp(prefix="crew-painel-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.estado = os.path.join(self.tmp, "estado")
        self.pi = os.path.join(self.tmp, "pi")
        gravar(os.path.join(self.pi, "models-store.json"), json.dumps(CATALOGO))
        gravar(os.path.join(self.pi, "settings.json"), json.dumps(AJUSTES))

    def worktree(self, nome):
        return os.path.join(self.tmp, "worktrees", nome)

    def sessao(self, nome, arquivo, *linhas):
        pasta = crew_sessao.pasta_da_sessao(self.worktree(nome))
        gravar(os.path.join(self.pi, "sessions", pasta, arquivo + ".jsonl"), "\n".join(linhas) + "\n")

    def worker(self, nome, estado="idle", minutos=5, **campos):
        meta = dict(name=nome, repo="home-repo", type="implement", model="claude-bridge/claude-opus-5-5", thinking="medium",
                    worktree=self.worktree(nome), branch="pi/" + nome, started=iso(60), state_file=os.path.join(self.estado, nome, "state.json"))
        meta.update(campos)
        gravar(meta["state_file"], json.dumps(dict(state=estado, turns=1, at=utc(minutos))))
        return meta

    def painel(self, metas, decisoes=None, fechados=False):
        os.environ["PI_CODING_AGENT_DIR"] = self.pi
        self.addCleanup(os.environ.pop, "PI_CODING_AGENT_DIR", None)
        return crew_painel.painel(metas, decisoes or {}, self.estado, fechados).splitlines()


class SessaoTest(Base):
    def test_contexto_e_modelo_da_ultima_resposta(self):
        self.sessao("a", "1", cabeca(50), resposta(40, 2, 100, lido=1000, escrito=500), resposta(30, 2, 300, lido=50000, escrito=1000))
        achado = crew_sessao.resumo(self.pi, self.worktree("a"), iso(60))
        self.assertEqual((achado["modelo"], achado["nome"], achado["esforco"]), ("claude-opus-5-5", "Claude Opus 5.5", "medium"))
        self.assertEqual(achado["contexto"], 2 + 300 + 50000 + 1000)
        self.assertEqual(achado["compacta_em"], 150000)

    def test_o_ajuste_do_worktree_vence_o_global(self):
        gravar(os.path.join(self.worktree("a"), ".pi", "settings.json"), json.dumps({"compaction": {"modelOverrides": {"claude-bridge/claude-opus-5-5": {"reserveTokens": 900000}}}}))
        self.sessao("a", "1", cabeca(50), resposta(40))
        self.assertEqual(crew_sessao.resumo(self.pi, self.worktree("a"), iso(60))["compacta_em"], 100000)

    def test_sem_ajuste_vale_a_reserva_padrao_do_pi(self):
        os.remove(os.path.join(self.pi, "settings.json"))
        self.sessao("a", "1", cabeca(50), resposta(40))
        self.assertEqual(crew_sessao.resumo(self.pi, self.worktree("a"), iso(60))["compacta_em"], 1000000 - crew_sessao.RESERVA_PADRAO)

    def test_new_abre_outro_arquivo_e_compactacoes_somam(self):
        self.sessao("a", "1", cabeca(50), resposta(45, lido=140000), compactacao(44, 150000), resposta(43, lido=20000))
        self.sessao("a", "2", cabeca(30), resposta(25, lido=90000), compactacao(20, 151000))
        achado = crew_sessao.resumo(self.pi, self.worktree("a"), iso(60))
        self.assertEqual(achado["sessoes"], 2)
        self.assertEqual([c["antes"] for c in achado["compactacoes"]], [150000, 151000])
        self.assertTrue(achado["depois_de_compactar"])
        self.assertEqual(achado["contexto"], 90102)

    def test_sessao_anterior_a_abertura_do_worker_nao_conta(self):
        self.sessao("a", "velha", cabeca(500), resposta(499, lido=900), compactacao(498, 1))
        self.sessao("a", "nova", cabeca(50), resposta(40, lido=10))
        achado = crew_sessao.resumo(self.pi, self.worktree("a"), iso(60))
        self.assertEqual((achado["sessoes"], achado["compactacoes"], achado["contexto"]), (1, [], 112))

    def test_resposta_com_erro_guarda_a_mensagem_e_o_contexto_anterior(self):
        self.sessao("a", "1", cabeca(50), resposta(40, lido=7000), resposta(30, 0, 0, parou="error", errorMessage="401 authentication_error"))
        achado = crew_sessao.resumo(self.pi, self.worktree("a"), iso(60))
        self.assertEqual((achado["erro"], achado["contexto"]), ("401 authentication_error", 7102))

    def test_sem_sessao_nao_quebra(self):
        achado = crew_sessao.resumo(self.pi, self.worktree("a"), iso(60))
        self.assertEqual((achado["sessoes"], achado["modelo"], achado["contexto"]), (0, None, None))


class PainelTest(Base):
    def test_uma_linha_com_modelo_completo_esforco_contexto_e_hora(self):
        self.sessao("home-x", "1", cabeca(50), resposta(40, lido=88000))
        linhas = self.painel([self.worker("home-x", "working", 12)])
        self.assertEqual(linhas[0], "Time: 1 workers · 0 precisam de atenção")
        self.assertIn("home-x  home-repo · implement  Opus 5.5 medium  trabalhando · turno 12 min  aberto %s  faltam 62k até compactar" % crew_painel.hora(iso(60)), linhas[1])

    def test_compactacoes_aparecem_com_a_hora(self):
        self.sessao("home-x", "1", cabeca(50), resposta(40, lido=140000), compactacao(30, 150000), resposta(20, lido=30000), compactacao(10, 151000), resposta(5, lido=20000))
        texto = self.painel([self.worker("home-x", "working")])[1]
        self.assertIn("faltam 130k até compactar · 2 compactações (%s, %s)" % (crew_painel.hora(utc(30)), crew_painel.hora(utc(10))), texto)

    def test_logo_apos_compactar_diz_a_hora_em_vez_do_resto(self):
        self.sessao("home-x", "1", cabeca(50), resposta(40, lido=140000), compactacao(3, 150000))
        texto = self.painel([self.worker("home-x", "working")])[1]
        self.assertIn("compactou às %s · 1 compactação (%s)" % (crew_painel.hora(utc(3)), crew_painel.hora(utc(3))), texto)

    def test_sem_resposta_ainda_usa_o_meta_e_modelo_fora_do_catalogo_leva_o_id(self):
        self.assertIn("Opus 5.5 medium", self.painel([self.worker("home-x")])[1])
        meta = self.worker("home-y", model="claude-bridge/modelo-novo-9", thinking="low")
        self.assertIn("modelo-novo-9 low", self.painel([meta])[1])

    def test_erro_da_ultima_resposta_vai_para_o_topo_com_sessenta_caracteres(self):
        longo = "401 authentication_error " + "x" * 80
        self.sessao("home-e", "1", cabeca(50), resposta(40, lido=5), resposta(30, 0, 0, parou="error", errorMessage=longo))
        linhas = self.painel([self.worker("home-ok", "working"), self.worker("home-e", "idle")])
        self.assertTrue(linhas[1].startswith("! home-e"))
        self.assertIn("ERRO: 401 authentication_error " + "x" * 34 + "…", linhas[1])
        self.assertTrue(linhas[0].endswith("1 precisam de atenção"))

    def test_erro_antigo_nao_vale_enquanto_o_worker_trabalha(self):
        self.sessao("home-e", "1", cabeca(50), resposta(30, 0, 0, parou="error", errorMessage="429"))
        self.assertNotIn("ERRO", self.painel([self.worker("home-e", "working")])[1])

    def test_erro_ao_abrir_vem_do_meta(self):
        meta = self.worker("home-e", error=dict(step="agent", error="Pi did not become ready"))
        self.assertIn("ERRO: Pi did not become ready", self.painel([meta])[1])

    def test_parado_vem_do_vigia(self):
        meta = self.worker("home-p", "working")
        gravar(os.path.join(self.estado, "home-p", "watch.json"), json.dumps(dict(stalled=True, progress=dict(mark="m", at=iso(34)))))
        linhas = self.painel([meta])
        self.assertTrue(linhas[1].startswith("! home-p"))
        self.assertIn("parado há 34 min", linhas[1])

    def test_parado_sem_marca_de_progresso_conta_do_ultimo_turno(self):
        gravar(os.path.join(self.estado, "home-p", "watch.json"), json.dumps(dict(stalled=True)))
        self.assertIn("parado há 25 min", self.painel([self.worker("home-p", "working", 25)])[1])

    def test_espera_dono_mostra_a_pergunta(self):
        decisoes = {"D1": dict(worker="home-d", status="open", question="Mesclar a #11 antes da #5?"), "D2": dict(worker="home-d", status="answered", question="velha")}
        linhas = self.painel([self.worker("home-d", "working")], decisoes)
        self.assertTrue(linhas[1].startswith("? home-d"))
        self.assertIn("espera dono: Mesclar a #11 antes da #5?", linhas[1])

    def test_ordem_atencao_dono_rodando_ociosos_e_mais_antigo_primeiro(self):
        metas = [self.worker("a-ocioso", "idle", started=iso(10)), self.worker("b-rodando-novo", "working", started=iso(20)),
                 self.worker("c-rodando-velho", "working", started=iso(90)), self.worker("d-dono", "working"),
                 self.worker("e-erro", "idle", error=dict(step="x", error="falhou"))]
        decisoes = {"D1": dict(worker="d-dono", status="open", question="q")}
        nomes = [texto[2:].split()[0] for texto in self.painel(metas, decisoes)[1:]]
        self.assertEqual(nomes, ["e-erro", "d-dono", "c-rodando-velho", "b-rodando-novo", "a-ocioso"])

    def test_fechado_so_nas_ultimas_doze_horas_ou_com_a_opcao(self):
        recente = self.worker("home-r", closed=iso(60))
        antigo = self.worker("home-a", closed=iso(60 * 20))
        self.assertEqual([x[2:].split()[0] for x in self.painel([recente, antigo])[1:]], ["home-r"])
        self.assertTrue(self.painel([recente])[1].startswith("- home-r"))
        self.assertEqual(len(self.painel([recente, antigo], fechados=True)), 3)

    def test_fechado_e_painel_fechou_nao_dizem_quanto_falta_mas_contam_compactacoes(self):
        self.sessao("home-f", "1", cabeca(50), resposta(40, lido=5000), compactacao(30, 150000), resposta(20, lido=5000))
        fechado = self.painel([self.worker("home-f", "idle", closed=iso(5))])[1]
        sumiu = self.painel([self.worker("home-f", "gone")])[1]
        for texto in (fechado, sumiu):
            self.assertNotIn("faltam", texto)
            self.assertIn("1 compactação", texto)

    def test_pr_e_head_vem_do_cache_do_vigia(self):
        meta = self.worker("home-x", "working")
        self.assertIn("PR sem leitura", self.painel([meta])[1])
        prs = dict(prs={"home-repo": [dict(number=11, branch="pi/home-x", head="13438c9" + "0" * 33, state="OPEN", estado="espera revisão"),
                                      dict(number=9, branch="pi/outro", head="f" * 40, state="OPEN", estado="espera CI")]})
        gravar(os.path.join(self.estado, "prs.json"), json.dumps(prs))
        self.assertTrue(self.painel([meta])[1].endswith("PR #11 13438c9 espera revisão"))
        self.assertTrue(self.painel([self.worker("home-z", "working")])[1].endswith("sem PR"))

    def test_worker_da_vps_le_a_sessao_espelhada(self):
        self.sessao("home-v", "1", cabeca(50), resposta(40, lido=100000))
        gravar(os.path.join(self.estado, "home-v", "session.json"), json.dumps(crew_sessao.resumo(self.pi, self.worktree("home-v"), iso(60))))
        os.rename(os.path.join(self.pi, "sessions"), os.path.join(self.pi, "sessoes-da-vps"))
        meta = self.worker("home-v", "working", host="vps")
        self.assertIn("faltam 50k até compactar", self.painel([meta])[1])

    def test_quarenta_e_cinco_workers_em_menos_de_um_segundo(self):
        metas = []
        for numero in range(45):
            nome = "home-w%02d" % numero
            self.sessao(nome, "1", cabeca(50), *[resposta(40 - n, lido=1000 * n) for n in range(30)], compactacao(5, 150000))
            metas.append(self.worker(nome, "working"))
        inicio = time.time()
        linhas = self.painel(metas)
        self.assertEqual(len(linhas), 46)
        self.assertLess(time.time() - inicio, 1)


class ComandoTest(Base):
    def test_crew_time_imprime_o_painel(self):
        self.sessao("home-x", "1", cabeca(50), resposta(40, lido=88000))
        meta = self.worker("home-x", "working")
        gravar(os.path.join(self.estado, "home-x", "meta.json"), json.dumps(meta))
        env = dict(os.environ, CREW_STATE_DIR=self.estado, PI_CODING_AGENT_DIR=self.pi)
        saida = subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "crew.py"), "time"], env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(saida.returncode, 0, saida.stderr)
        self.assertIn("home-x  home-repo · implement  Opus 5.5 medium  trabalhando", saida.stdout)
        self.assertIn("faltam 62k até compactar", saida.stdout)


class PuxarSessaoDaVpsTest(Base):
    def test_o_script_remoto_devolve_o_resumo_da_sessao_do_worker(self):
        vps = os.path.join(self.tmp, "vps", "home")
        pi = os.path.join(vps, ".local", "share", "crew", "pi-agent")
        gravar(os.path.join(pi, "models-store.json"), json.dumps(CATALOGO))
        trabalho = os.path.join(vps, "worktrees", "home-repo-v")
        gravar(os.path.join(pi, "sessions", crew_sessao.pasta_da_sessao(trabalho), "1.jsonl"), "\n".join([cabeca(50), resposta(40, lido=120000)]) + "\n")
        gravar(os.path.join(self.tmp, "fake_ssh.py"), remoto.FAKE_SSH)
        os.environ.update(FAKE_VPS_HOME=vps, CREW_SSH=json.dumps([sys.executable, "-I", os.path.join(self.tmp, "fake_ssh.py")]))
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in ("FAKE_VPS_HOME", "CREW_SSH")])
        gravar(os.path.join(vps, "crew-state", "home-v", "state.json"), "{}")
        meta = dict(remote_dir=os.path.join(vps, "crew-state", "home-v"), worktree=trabalho, started=iso(60))
        achado = json.loads(crew_remote.pull("vps", [meta])[meta["remote_dir"]]["session"])
        self.assertEqual((achado["nome"], achado["contexto"], achado["compacta_em"]), ("Claude Opus 5.5", 120102, 983616))


if __name__ == "__main__":
    unittest.main()
