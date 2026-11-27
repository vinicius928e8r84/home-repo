import json
import os
import shutil
import subprocess
import tempfile
import unittest

from scripts.test_crew_vigia import VigiaCase
from scripts.test_crew import utc_minutes_ago

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPTS)
EXTENSION = os.path.join(ROOT, ".pi", "extensions", "crew-cota.ts")
NODE = shutil.which("node")

HARNESS = '''import { pathToFileURL } from "node:url";

const handlers = {};
const pi = { on: (name, handler) => { handlers[name] = handler; } };
const statuses = [];
const ctx = { cwd: process.env.PI_CWD, ui: { setStatus: (key, text) => statuses.push([key, text]) } };
const module = await import(pathToFileURL(process.env.EXTENSION).href);
module.default(pi);
for (const headers of JSON.parse(process.env.RESPOSTAS)) {
  await handlers.after_provider_response({ status: 200, headers }, ctx);
}
console.log(JSON.stringify(statuses));
'''

PONTE_SO_SEMANA = {
    "anthropic-ratelimit-unified-status": "allowed",
    "anthropic-ratelimit-unified-reset": "1795989600",
    "anthropic-ratelimit-unified-representative-claim": "seven_day",
    "anthropic-ratelimit-unified-overage-status": "rejected",
    "anthropic-ratelimit-unified-7d-utilization": "0.4",
    "anthropic-ratelimit-unified-7d-reset": "1795989600",
}
PONTE_COM_5H = dict(PONTE_SO_SEMANA, **{
    "anthropic-ratelimit-unified-status": "allowed_warning",
    "anthropic-ratelimit-unified-representative-claim": "five_hour",
    "anthropic-ratelimit-unified-7d-utilization": "0.41",
    "anthropic-ratelimit-unified-5h-utilization": "0.87",
    "anthropic-ratelimit-unified-5h-reset": "1795972800",
    "anthropic-ratelimit-unified-overage-status": "allowed",
    "anthropic-ratelimit-unified-overage-reset": "1796000000",
})

QUOTA_AXI = {
    "generatedAt": "2026-11-27T09:07:38.628Z",
    "schemaVersion": 5,
    "providers": [{
        "provider": "claude",
        "plan": "max",
        "windows": [
            {"id": "seven_day", "label": "week", "kind": "weekly", "resetsAt": "2026-11-29T21:59:59.980947+00:00", "percentRemaining": 23},
            {"id": "model:fable", "label": "Fable week", "kind": "model", "resetsAt": "2026-11-29T21:59:59.981094+00:00", "percentRemaining": 91},
        ],
        "state": {"status": "fresh", "stale": False},
    }],
}
QUOTA_AXI_COM_5H_E_EXTRA = {
    "providers": [{
        "provider": "claude",
        "windows": [
            {"id": "five_hour", "kind": "session", "resetsAt": "2026-11-27T12:00:00+00:00", "percentRemaining": 100},
            {"id": "seven_day", "kind": "weekly", "resetsAt": "2026-11-29T22:00:00+00:00", "percentRemaining": 0},
            {"id": "extra_usage", "kind": "credits", "percentRemaining": 75, "spentUsd": 12.5, "limitUsd": 50},
        ],
    }],
}


@unittest.skipUnless(NODE, "node is not installed")
class Rodape(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.state = os.path.join(self.tmp, "state")

    def chamadas(self, respostas):
        harness = os.path.join(self.tmp, "harness.mjs")
        with open(harness, "w", encoding="utf-8") as f:
            f.write(HARNESS)
        env = dict(os.environ, EXTENSION=EXTENSION, PI_CWD=self.tmp, CREW_STATE_DIR=self.state, RESPOSTAS=json.dumps(respostas))
        feito = subprocess.run([NODE, harness], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(feito.returncode, 0, feito.stderr)
        return json.loads(feito.stdout.strip().splitlines()[-1])

    def arquivo(self):
        with open(os.path.join(self.state, "_cota.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_a_chamada_so_com_a_semana_grava_o_arquivo_no_formato_da_pesquisa(self):
        self.chamadas([PONTE_SO_SEMANA])
        gravado = self.arquivo()
        self.assertRegex(gravado.pop("at"), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(gravado.pop("host"), "pc" if os.name == "nt" else "vps")
        self.assertEqual(gravado, {
            "fonte": "bridge",
            "status": "allowed",
            "limitante": "seven_day",
            "janelas": {"5h": None, "7d": {"usado": 40, "reset": "2026-11-29T22:00:00Z", "status": "allowed"}},
            "extra": {"status": "rejected", "reset": None, "ligado": None, "gasto_usd": None, "limite_usd": None},
        })

    def test_com_as_duas_janelas_o_arquivo_traz_porcentagem_de_0_a_100_e_o_aviso(self):
        self.chamadas([PONTE_COM_5H])
        gravado = self.arquivo()
        self.assertEqual(gravado["status"], "allowed_warning")
        self.assertEqual(gravado["limitante"], "five_hour")
        self.assertEqual(gravado["janelas"]["5h"]["usado"], 87)
        self.assertEqual(gravado["janelas"]["7d"]["usado"], 41)
        self.assertEqual(gravado["extra"]["status"], "allowed")
        self.assertEqual(gravado["extra"]["reset"], "2026-11-30T00:53:20Z")
        self.assertEqual(gravado["janelas"]["5h"]["reset"], "2026-11-29T17:20:00Z")

    def test_o_rodape_mostra_a_cota_semanal_e_a_de_5h(self):
        statuses = self.chamadas([PONTE_COM_5H])
        self.assertEqual(statuses[-1], ["cota", "cota sem 41% · 5h 87% · allowed_warning"])

    def test_sem_janela_de_5h_o_rodape_mostra_um_traco(self):
        statuses = self.chamadas([PONTE_SO_SEMANA])
        self.assertEqual(statuses[-1], ["cota", "cota sem 40% · 5h —"])

    def test_cada_chamada_regrava_o_arquivo_e_vale_a_ultima(self):
        self.chamadas([PONTE_COM_5H, PONTE_SO_SEMANA])
        self.assertEqual(self.arquivo()["janelas"]["7d"]["usado"], 40)
        self.assertIsNone(self.arquivo()["janelas"]["5h"])

    def test_resposta_sem_cabecalho_de_cota_nao_grava_nem_mexe_no_rodape(self):
        statuses = self.chamadas([{"content-type": "text/event-stream"}])
        self.assertFalse(os.path.exists(os.path.join(self.state, "_cota.json")))
        self.assertEqual([s for s in statuses if s[1]], [])

    def test_gravacao_que_falha_nao_derruba_o_pi_e_o_rodape_segue(self):
        os.makedirs(os.path.join(self.state, "_cota.json"))
        statuses = self.chamadas([PONTE_COM_5H])
        self.assertEqual(statuses[-1][1], "cota sem 41% · 5h 87% · allowed_warning")


class Vigia(VigiaCase):
    def setUp(self):
        super().setUp()
        self.cota = self.crew.module("crew_cota")
        self.leituras = []
        self.quota_axi = QUOTA_AXI
        self.cota.ler = self.ler
        self.add_worker()

    def ler(self):
        self.leituras.append(1)
        if isinstance(self.quota_axi, Exception):
            raise self.quota_axi
        return self.quota_axi

    def grava(self, minutos, **campos):
        os.makedirs(self.state, exist_ok=True)
        corpo = dict(at=utc_minutes_ago(minutos), fonte="bridge", host="pc", status="allowed", limitante="seven_day",
                     janelas={"5h": None, "7d": {"usado": 1, "reset": "2026-11-29T22:00:00Z", "status": "allowed"}}, extra={})
        with open(os.path.join(self.state, "_cota.json"), "w", encoding="utf-8") as f:
            json.dump(dict(corpo, **campos), f)

    def arquivo(self):
        with open(os.path.join(self.state, "_cota.json"), encoding="utf-8") as f:
            return json.load(f)

    def tentativa(self):
        with open(os.path.join(self.state, "cota-tentativa.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_leitura_de_mais_de_15_min_e_refeita_pelo_quota_axi(self):
        self.grava(16)
        self.rodada()
        self.assertEqual(len(self.leituras), 1)
        self.assertEqual(self.arquivo()["fonte"], "quota-axi")

    def test_leitura_de_menos_de_15_min_fica_como_esta(self):
        self.grava(14)
        self.rodada()
        self.assertEqual(self.leituras, [])
        self.assertEqual(self.arquivo()["fonte"], "bridge")

    def test_sem_arquivo_o_vigia_le_pelo_quota_axi(self):
        self.rodada()
        self.assertEqual(len(self.leituras), 1)

    def test_arquivo_ilegivel_conta_como_velho(self):
        os.makedirs(self.state, exist_ok=True)
        with open(os.path.join(self.state, "_cota.json"), "w", encoding="utf-8") as f:
            f.write("{pela metade")
        self.rodada()
        self.assertEqual(self.arquivo()["fonte"], "quota-axi")

    def test_o_arquivo_bate_com_o_que_o_quota_axi_disse(self):
        self.grava(60)
        self.rodada()
        gravado = self.arquivo()
        self.assertRegex(gravado.pop("at"), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertIn(gravado.pop("host"), ("pc", "vps", "mac"))
        self.assertEqual(gravado, {
            "fonte": "quota-axi",
            "status": "allowed",
            "limitante": "seven_day",
            "janelas": {"5h": None, "7d": {"usado": 77, "reset": "2026-11-29T22:00:00Z", "status": "allowed"}},
            "extra": {"status": "rejected", "reset": None, "ligado": False, "gasto_usd": None, "limite_usd": None},
        })

    def test_com_5h_e_extra_usage_o_arquivo_traz_o_gasto_e_o_limite(self):
        self.quota_axi = QUOTA_AXI_COM_5H_E_EXTRA
        self.rodada()
        gravado = self.arquivo()
        self.assertEqual(gravado["janelas"]["5h"]["usado"], 0)
        self.assertEqual(gravado["janelas"]["7d"]["usado"], 100)
        self.assertEqual(gravado["status"], "rejected")
        self.assertEqual(gravado["limitante"], "seven_day")
        self.assertEqual(gravado["extra"], {"status": "allowed", "reset": None, "ligado": True, "gasto_usd": 12.5, "limite_usd": 50})

    def test_quota_axi_que_falha_nao_derruba_a_volta_nem_apaga_a_leitura_velha(self):
        self.grava(60)
        self.quota_axi = self.crew.Fail("cota", "sem rede")
        self.add_events([dict(kind="decision_needed", id="D7", question="Qual banco usamos?")])
        avisos = self.rodada()
        self.assertEqual(self.arquivo()["fonte"], "bridge")
        self.assertEqual(len(avisos), 1)
        self.assertEqual(self.tentativa()["erro"], "sem rede")

    def test_depois_de_uma_falha_o_vigia_espera_um_minuto_para_tentar_de_novo(self):
        self.quota_axi = self.crew.Fail("cota", "sem rede")
        self.rodada(minutos=0.3)
        self.rodada(minutos=0.3)
        self.assertEqual(len(self.leituras), 1)
        self.rodada(minutos=1)
        self.assertEqual(len(self.leituras), 2)

    def test_resposta_do_quota_axi_sem_a_conta_claude_conta_como_falha(self):
        self.quota_axi = {"providers": [{"provider": "claude", "notSetUp": True, "windows": []}]}
        self.rodada()
        self.assertFalse(os.path.exists(os.path.join(self.state, "_cota.json")))
        self.assertIn("conta Claude", self.tentativa()["erro"])


if __name__ == "__main__":
    unittest.main()
