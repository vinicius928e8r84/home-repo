import contextlib
import io
import os
import stat
import tempfile
import types

from scripts.test_crew import CHIEF, CrewCase
from scripts.test_crew_drill import HERDR_DE_MENTIRA


class DrillDoChief(CrewCase):

    def setUp(self):
        super().setUp()
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        self.log = os.path.join(self.tmp, "herdr.log")
        for nome, corpo in (("herdr", HERDR_DE_MENTIRA), ("pi", "#!/bin/sh\nexit 1\n")):
            caminho = os.path.join(self.bin, nome)
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(corpo)
            os.chmod(caminho, os.stat(caminho).st_mode | stat.S_IEXEC)
        os.environ.update(PATH=self.bin + os.pathsep + os.environ["PATH"], DRILL_LOG=self.log, DRILL_RODANDO=os.path.join(self.tmp, "rodando"),
                          HERDR_ENV="1", HERDR_PANE_ID=CHIEF)

    def rodar(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.crew.module("crew_drill_chief").drill(types.SimpleNamespace(model="x/y:low"))

    def linhas(self, sufixo=""):
        with open(self.log + sufixo, encoding="utf-8") as f:
            return f.read().splitlines()

    def test_um_drill_que_nao_abre_o_worker_de_teste_diz_qual_passo_falhou(self):
        relatorio = self.rodar()
        self.assertFalse(relatorio["ok"])
        self.assertEqual([p["nome"] for p in relatorio["passos"] if not p["ok"]], ["abrir o Worker de teste"])

    def test_so_fala_com_a_sessao_descartavel_e_nunca_com_o_estado_ou_o_chief_reais(self):
        relatorio = self.rodar()
        self.assertEqual({linha.split()[1] for linha in self.linhas()}, {relatorio["sessao"]})
        for estado, _, sessao, pane, _, _ in (linha.split("|") for linha in self.linhas(".env")):
            self.assertNotEqual(estado, self.state)
            self.assertTrue(estado.startswith(tempfile.gettempdir()))
            self.assertTrue(sessao.startswith("drill-"))
            self.assertNotEqual(pane, CHIEF)

    def test_nao_deixa_nada_para_tras(self):
        self.rodar()
        self.assertFalse(os.path.exists(self.linhas(".env")[0].split("|")[0]))
        self.assertFalse(os.path.exists(os.environ["DRILL_RODANDO"]))

    def test_o_comando_falha_com_o_passo_que_falhou_no_erro(self):
        with self.assertRaises(self.crew.Fail) as caught:
            with contextlib.redirect_stdout(io.StringIO()):
                self.crew.module("crew_drill_chief").comando(types.SimpleNamespace(model="x/y:low"))
        self.assertEqual(caught.exception.step, "drill")
        self.assertIn("abrir o Worker de teste:", caught.exception.error)
