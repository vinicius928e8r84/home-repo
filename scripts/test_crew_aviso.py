import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PANE = "w3:p3"
HARNESS = """
const [file, inbox, lines, throwing, wait] = process.argv.slice(1);
const fs = await import("node:fs");
const handlers = {};
const sent = [];
const users = [];
const pi = {
  on: (name, fn) => { handlers[name] = fn; },
  sendMessage: async (message, options) => { if (throwing === "1") throw new Error("busy"); sent.push([message, options]); },
  sendUserMessage: async (text, options) => { users.push([text, options]); },
};
const { default: extension } = await import(new URL("file:///" + file.replace(/\\\\/g, "/")).href);
extension(pi);
await handlers.session_start?.({}, { cwd: process.argv[6] });
fs.mkdirSync(inbox.replace(/[^\\\\/]+$/, ""), { recursive: true });
fs.writeFileSync(inbox, JSON.parse(lines).join("\\n") + "\\n");
await new Promise((resolve) => setTimeout(resolve, Number(wait)));
await handlers.session_shutdown?.();
const left = fs.existsSync(inbox) ? fs.readFileSync(inbox, "utf8") : null;
console.log(JSON.stringify({ sent, users, left }));
"""


@unittest.skipUnless(shutil.which("node"), "node não está instalado")
class ExtensaoDeAviso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crew-aviso-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.inbox = os.path.join(self.tmp, "state", "_chief", "w3_p3.inbox")

    def entregar(self, extensao, linhas, falha=False, worker=False):
        env = {k: v for k, v in os.environ.items() if k not in ("CREW_STATE_FILE", "HERDR_ENV", "HERDR_PANE_ID")}
        env.update(HERDR_ENV="1", HERDR_PANE_ID=PANE, CREW_STATE_DIR=os.path.join(self.tmp, "state"), CREW_AVISO_MS="30")
        if worker:
            env["CREW_STATE_FILE"] = os.path.join(self.tmp, "state.json")
        arquivo = str(ROOT / ".pi" / "extensions" / extensao)
        args = [arquivo, self.inbox, json.dumps(linhas), "1" if falha else "0", "600", str(ROOT)]
        feito = subprocess.run(["node", "--input-type=module", "-e", HARNESS, *args], capture_output=True, text=True, env=env,
                               encoding="utf-8", timeout=60, cwd=self.tmp)
        self.assertEqual(feito.returncode, 0, feito.stderr)
        return json.loads(feito.stdout.strip().splitlines()[-1])

    def test_avisos_viram_uma_mensagem_invisivel_que_acorda(self):
        saida = self.entregar("crew-aviso.ts", ["[crew] erro: a", "[crew] parado: b"])
        self.assertEqual(len(saida["sent"]), 1)
        mensagem, opcoes = saida["sent"][0]
        self.assertEqual(mensagem, dict(customType="crew", display=False, content="[crew] erro: a\n[crew] parado: b"))
        self.assertEqual(opcoes, dict(deliverAs="followUp", triggerTurn=True))
        self.assertEqual(saida["users"], [])
        self.assertIsNone(saida["left"])

    def test_resumo_entra_invisivel_sem_acordar(self):
        saida = self.entregar("crew-aviso.ts", ["[resumo] Resumo 14:00–14:30: 3 turnos"])
        self.assertEqual(len(saida["sent"]), 1)
        self.assertEqual(saida["sent"][0][1], dict(deliverAs="followUp", triggerTurn=False))
        self.assertFalse(saida["sent"][0][0]["display"])

    def test_resumo_e_avisos_vao_em_envios_separados(self):
        saida = self.entregar("crew-aviso.ts", ["[resumo] r", "[crew] erro: a"])
        self.assertEqual([envio[1]["triggerTurn"] for envio in saida["sent"]], [False, True])

    def test_falha_no_envio_devolve_as_linhas_para_a_caixa(self):
        saida = self.entregar("crew-aviso.ts", ["[crew] erro: a"], falha=True)
        self.assertEqual(saida["sent"], [])
        self.assertIn("[crew] erro: a", saida["left"])

    def test_painel_de_worker_nao_recebe_nada(self):
        saida = self.entregar("crew-aviso.ts", ["[crew] erro: a"], worker=True)
        self.assertEqual(saida["sent"], [])
        self.assertIn("[crew] erro: a", saida["left"])

    def test_o_guarda_do_fim_de_turno_nao_digita_mais_na_caixa(self):
        saida = self.entregar("crew-turnend-guard.ts", ["[crew] erro: a"])
        self.assertEqual(saida["users"], [])
        self.assertEqual(saida["sent"], [])
        self.assertIn("[crew] erro: a", saida["left"])


if __name__ == "__main__":
    unittest.main()
