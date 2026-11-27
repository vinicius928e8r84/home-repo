import contextlib
import datetime
import io
import json
import os
import subprocess
import sys
import types
import unittest

from scripts.test_crew import CrewCase
from scripts.test_crew_remote import FAKE_SSH

CREW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crew.py")
LINK_PC = "http://pc.exemplo:4387/session/aaaa111122223333"
LINK_VPS = "http://vps.exemplo:4387/session/bbbb111122223333"
TITULO = "## Precisa do dono"


def horas_atras(n):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=n)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def sessao(arquivo, link, status="open", pendentes=0, horas=1):
    return dict(key=link[-16:], file=arquivo, url=link, status=status, pending_prompts=pendentes, prompts=[], updated_at=horas_atras(horas))


def estado(*sessoes):
    return json.dumps(dict(sessions={s["key"]: s for s in sessoes}))


class DonoCase(CrewCase):
    def setUp(self):
        super().setUp()
        self.lavish = os.path.join(self.tmp, "lavish")
        os.environ["LAVISH_AXI_STATE_DIR"] = self.lavish
        self.add_worker()

    def paginas_no_pc(self, *sessoes):
        os.makedirs(self.lavish, exist_ok=True)
        with open(os.path.join(self.lavish, "state.json"), "w", encoding="utf-8") as f:
            f.write(estado(*sessoes))

    def paginas_na_vps(self, *sessoes):
        os.environ.pop("LAVISH_AXI_STATE_DIR")
        vps = os.path.join(self.tmp, "vps", "home")
        os.makedirs(os.path.join(vps, ".lavish-axi"), exist_ok=True)
        with open(os.path.join(vps, ".lavish-axi", "state.json"), "w", encoding="utf-8") as f:
            f.write(estado(*sessoes))
        with open(os.path.join(self.tmp, "fake_ssh.py"), "w", encoding="utf-8") as f:
            f.write(FAKE_SSH)
        os.environ.update(CREW_LAVISH_HOSTS="vps", FAKE_VPS_HOME=vps, CREW_SSH=json.dumps([sys.executable, "-I", os.path.join(self.tmp, "fake_ssh.py")]))

    def texto(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            self.crew.cmd_board(types.SimpleNamespace(json=False))
        return saida.getvalue()

    def secao(self):
        texto = self.texto()
        inicio = texto.index(TITULO)
        fim = texto.find("\n## ", inicio + 1)
        return texto[inicio:fim if fim >= 0 else len(texto)]

    def decisao(self, pergunta="posso gastar?", para="dono"):
        args = dict(question=pergunta, recommend="sim", para=para, worker="t-job", repo=None)
        return self.crew.module("crew_conversa").ask(types.SimpleNamespace(**args))

    def dono(self, acao, valor):
        return self.crew.module("crew_dono").comando(types.SimpleNamespace(acao=acao, valor=valor))


class SecaoNoTopo(DonoCase):
    def test_vazia_ela_aparece_e_diz_que_nada_precisa_do_dono(self):
        self.assertIn("nada precisa de você agora", self.secao())

    def test_vem_antes_de_todo_o_resto_do_board(self):
        self.decisao()
        self.decisao("e agora?", para="chief")
        texto = self.texto()
        for depois in ("## Perguntas ao chief", "## Decisões esperando", "## Rodando agora"):
            self.assertLess(texto.index(TITULO), texto.index(depois))
        self.assertEqual(texto.splitlines()[0][:7], "# Time:")
        self.assertEqual(texto.splitlines()[2], TITULO)


class DecisoesAbertas(DonoCase):
    def test_a_decisao_do_dono_aparece_com_o_worker_e_o_que_fazer(self):
        self.decisao()
        linha = [x for x in self.secao().splitlines() if "D1" in x][0]
        self.assertIn("t-job", linha)
        self.assertIn("posso gastar?", linha)
        self.assertNotIn("nada precisa de você", self.secao())

    def test_a_pergunta_ao_chief_nao_e_do_dono(self):
        self.decisao("e agora?", para="chief")
        self.assertNotIn("e agora?", self.secao())
        self.assertIn("nada precisa de você agora", self.secao())

    def test_respondida_ela_sai_da_lista(self):
        self.decisao()
        self.crew.cmd_answer(types.SimpleNamespace(id="D1", answer="pode"))
        self.assertNotIn("posso gastar?", self.secao())
        self.assertIn("nada precisa de você agora", self.secao())


class PaginasLavish(DonoCase):
    def test_pagina_aberta_no_pc_aparece_com_o_link_do_estado_local(self):
        self.paginas_no_pc(sessao("C:/x/.lavish/rodada-do-d34.html", LINK_PC))
        linha = [x for x in self.secao().splitlines() if "rodada-do-d34" in x][0]
        self.assertIn(LINK_PC, linha)

    def test_pagina_ja_respondida_ou_encerrada_nao_aparece(self):
        self.paginas_no_pc(sessao("a/ja-respondida.html", LINK_PC[:-1] + "1", status="feedback", pendentes=1),
                           sessao("a/encerrada.html", LINK_PC[:-1] + "2", status="ended"))
        texto = self.secao()
        self.assertNotIn("ja-respondida", texto)
        self.assertNotIn("encerrada", texto)
        self.assertIn("nada precisa de você agora", texto)

    def test_pagina_aberta_ha_mais_de_tres_dias_conta_como_abandonada(self):
        self.paginas_no_pc(sessao("a/velha.html", LINK_PC, horas=73), sessao("a/recente.html", LINK_PC[:-1] + "2", horas=71))
        texto = self.secao()
        self.assertNotIn("velha", texto)
        self.assertIn("recente", texto)

    def test_a_pagina_sai_sozinha_quando_o_dono_responde(self):
        self.paginas_no_pc(sessao("a/rodada.html", LINK_PC))
        self.assertIn("rodada", self.secao())
        self.paginas_no_pc(sessao("a/rodada.html", LINK_PC, status="feedback", pendentes=1))
        self.assertNotIn("rodada", self.secao())

    def test_pagina_aberta_na_vps_aparece_com_o_link_dela(self):
        self.paginas_na_vps(sessao("/home/x/.lavish/rodada-da-vps.html", LINK_VPS))
        linha = [x for x in self.secao().splitlines() if "rodada-da-vps" in x][0]
        self.assertIn(LINK_VPS, linha)

    def test_vps_fora_do_ar_nao_derruba_o_board_e_avisa_na_secao(self):
        self.paginas_na_vps()
        os.environ["CREW_LAVISH_HOSTS"] = "nowhere"
        self.assertIn("nowhere", self.secao())
        self.assertIn("Decisões esperando", self.texto())

    def test_sem_arquivo_de_estado_do_lavish_nao_ha_o_que_mostrar(self):
        self.assertIn("nada precisa de você agora", self.secao())


class ListaLocal(DonoCase):
    def test_add_entra_na_lista_e_aparece_no_board(self):
        achado = self.dono("add", "pôr crédito na chave")
        self.assertEqual(achado["id"], "L1")
        self.assertIn("**L1** pôr crédito na chave", self.secao())

    def test_done_tira_da_lista(self):
        self.dono("add", "pôr crédito na chave")
        self.dono("done", "l1")
        self.assertNotIn("crédito", self.secao())
        self.assertIn("nada precisa de você agora", self.secao())

    def test_os_ids_nao_se_repetem_depois_de_um_done(self):
        self.dono("add", "um")
        self.dono("done", "L1")
        self.assertEqual(self.dono("add", "dois")["id"], "L2")

    def test_done_de_id_que_nao_existe_ou_ja_feito_falha_dizendo_por_que(self):
        with self.assertRaises(self.crew.Fail) as nenhum:
            self.dono("done", "L9")
        self.assertIn("L9", nenhum.exception.error)
        self.dono("add", "um")
        self.dono("done", "L1")
        with self.assertRaises(self.crew.Fail) as repetido:
            self.dono("done", "L1")
        self.assertIn("já", repetido.exception.error)

    def test_add_sem_texto_falha(self):
        with self.assertRaises(self.crew.Fail):
            self.dono("add", "   ")

    def test_a_lista_fica_no_estado_local_e_nao_na_pasta_do_repo(self):
        self.dono("add", "rodar um comando de administrador")
        arquivo = os.path.join(self.state, "dono.jsonl")
        self.assertTrue(os.path.exists(arquivo))
        self.assertTrue(os.path.abspath(arquivo).startswith(os.path.abspath(self.tmp)))

    def test_o_comando_dono_add_e_done_existe_na_linha_de_comando(self):
        env = dict(os.environ, CREW_STATE_DIR=self.state)
        rodar = lambda *args: subprocess.run([sys.executable, "-I", CREW, "dono", *args], env=env, capture_output=True, text=True, encoding="utf-8")
        adicionou = rodar("add", "pôr crédito na chave")
        self.assertEqual(adicionou.returncode, 0, adicionou.stderr)
        self.assertEqual(json.loads(adicionou.stdout)["id"], "L1")
        feito = rodar("done", "L1")
        self.assertEqual(feito.returncode, 0, feito.stderr)
        self.assertEqual(rodar("done", "L1").returncode, 1)


if __name__ == "__main__":
    unittest.main()
