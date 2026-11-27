import json
import os
import shutil
import subprocess
import tempfile
import unittest

from scripts.test_crew_sinais import HARNESS, NODE, START, EXTENSION


@unittest.skipUnless(NODE, "node is not installed")
class EstadoDoChief(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crew-chief-estado-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.casa = os.path.join(self.tmp, "casa")
        os.makedirs(os.path.join(self.casa, "scripts"))
        open(os.path.join(self.casa, "scripts", "crew.py"), "w").close()
        self.estado = os.path.join(self.tmp, "estado")

    def abrir(self, conversa, painel="w1:p2"):
        harness = os.path.join(self.tmp, "harness.mjs")
        with open(harness, "w", encoding="utf-8") as f:
            f.write(HARNESS)
        env = {k: v for k, v in os.environ.items() if k != "CREW_STATE_FILE"}
        env.update(HERDR_ENV="1", HERDR_PANE_ID=painel, CREW_STATE_DIR=self.estado, CREW_HERDR_BIN="herdr-de-mentira", EXTENSION=EXTENSION,
                   PI_CWD=self.casa, PI_MODE="tui", PI_SESSION_ID=conversa, STEPS=json.dumps(START))
        feito = subprocess.run([NODE, harness], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(feito.returncode, 0, feito.stderr)
        return json.loads(feito.stdout.strip().splitlines()[-1])

    def arquivos(self):
        pasta = os.path.join(self.estado, "_chief")
        return sorted(os.listdir(pasta)) if os.path.isdir(pasta) else []

    def test_o_chief_grava_sempre_no_mesmo_arquivo_qualquer_que_seja_o_painel(self):
        self.abrir("chief", "w1:p2")
        self.abrir("chief", "w7:p9")
        self.assertEqual(self.arquivos(), ["chief.json"])

    def test_o_arquivo_do_chief_traz_o_painel_e_o_pid(self):
        saida = self.abrir("chief", "w7:p9")
        with open(os.path.join(self.estado, "_chief", "chief.json"), encoding="utf-8") as f:
            gravado = json.load(f)
        self.assertEqual((gravado["pane"], gravado["pid"], gravado["state"]), ("w7:p9", saida["pid"], "working"))

    def test_um_pi_de_outra_conversa_na_mesma_pasta_nao_grava_estado(self):
        self.abrir("teste-solto")
        self.assertEqual(self.arquivos(), [])


if __name__ == "__main__":
    unittest.main()
