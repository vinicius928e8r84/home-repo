import contextlib
import io
import os
import subprocess
import sys
import types

from scripts.test_crew import HERE, CrewCase


class TimeNaSaida(CrewCase):

    def board_text(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            self.crew.cmd_board(types.SimpleNamespace(json=False))
        return saida.getvalue()

    def test_o_quadro_se_chama_time(self):
        self.assertTrue(self.board_text().startswith("# Time: "))

    def test_repo_sem_trabalho_fala_do_time(self):
        self.assertIn("nenhum trabalho do Time ainda", self.board_text())

    def test_a_ajuda_fala_do_time_e_nao_da_frota(self):
        ajuda = subprocess.run([sys.executable, os.path.join(HERE, "crew.py"), "--help"], capture_output=True, text=True, encoding="utf-8").stdout
        self.assertIn("the whole Time:", ajuda)
        self.assertIn("the whole Time in one view", ajuda)
        self.assertNotIn("fleet", ajuda.lower())
        self.assertNotIn("frota", ajuda.lower())
