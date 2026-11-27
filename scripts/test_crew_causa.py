import contextlib
import datetime
import io
import json
import os
import subprocess
import sys
import types
import unittest
from unittest import mock

from scripts import crew_causa
from scripts.test_crew import CrewCase

CAUSAS = [
    ("disco", "error", "ENOSPC: no space left on device, write"),
    ("conversa quebrada no bridge", "error", "Cut boundary 9847936c-1111-2222-3333-444455556666 is not on the primary parent chain"),
    ("conversa quebrada no bridge", "error", "Session boundary 9f6fcd05-1111-2222-3333-444455556666 is absent from the transcript"),
    ("crédito", "error", '400 {"type":"error","error":{"type":"invalid_request_error","message":"Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits."}}'),
    ("crédito", "error", '{"type":"error","error":{"details":null,"type":"invalid_request_error","message":"Your credit balance is too low to access the Anthropic API."}}'),
    ("recusa", "error", "API Error: Opus 5's safeguards flagged this message (https://www.anthropic.com/legal/aup). Claude Code can't respond to this message with Opus 5."),
    ("interrompido", "aborted", "Operation aborted"),
    ("credencial", "error", '401 {"error":{"type":"authentication_error","message":"The API Key appears to be invalid or may have expired. Please verify your credentials and try again."}}'),
    ("limite de uso", "error", "Claude quota exceeded — rate limit (five_hour) — resets 3pm: You're out of extra usage · resets 3pm"),
    ("API fora", "error", '529 {"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}'),
    ("API fora", "error", "503 Service Unavailable"),
    ("rede", "error", "fetch failed"),
    ("rede", "error", "read ECONNRESET"),
    ("rede", "error", "getaddrinfo ENOTFOUND api.anthropic.com"),
    ("erro desconhecido", "error", "Claude Code process exited with code 3"),
]
AGORA = datetime.datetime(2026, 11, 27, 12, 0, tzinfo=datetime.timezone.utc)


def estado(**campos):
    return dict(dict(state="idle", turns=1, pid=os.getpid(), outcome=None, beat=iso(0)), **campos)


def iso(segundos_atras):
    return (AGORA - datetime.timedelta(seconds=segundos_atras)).isoformat().replace("+00:00", "Z")


def pid_morto():
    filho = subprocess.Popen([sys.executable, "-c", "pass"])
    filho.wait()
    return filho.pid


class UmaCausaPorTexto(unittest.TestCase):
    def test_cada_texto_real_de_erro_da_a_sua_causa(self):
        for causa, tipo, texto in CAUSAS:
            with self.subTest(texto=texto[:50]):
                visto = estado(outcome=dict(type=tipo, message=texto))
                self.assertEqual(crew_causa.da_parada(visto, AGORA), causa)

    def test_turno_bom_nao_e_parada(self):
        self.assertIsNone(crew_causa.da_parada(estado(), AGORA))

    def test_erro_de_um_turno_que_ainda_trabalha_nao_e_parada(self):
        visto = estado(state="working", outcome=dict(type="error", message="fetch failed"))
        self.assertIsNone(crew_causa.da_parada(visto, AGORA))

    def test_estado_sem_pid_nem_batida_nao_diz_nada(self):
        self.assertIsNone(crew_causa.da_parada(dict(state="starting"), AGORA))


class PiVivoOuNao(unittest.TestCase):
    def test_pid_morto_diz_pi_saiu(self):
        self.assertEqual(crew_causa.da_parada(estado(pid=pid_morto()), AGORA), "Pi saiu")

    def test_pid_morto_diz_pi_saiu_mesmo_trabalhando(self):
        self.assertEqual(crew_causa.da_parada(estado(state="working", pid=pid_morto()), AGORA), "Pi saiu")

    def test_pid_vivo_com_batida_velha_diz_congelado(self):
        visto = estado(beat=iso(crew_causa.BATIDA_VELHA_SEGUNDOS + 5))
        self.assertEqual(crew_causa.da_parada(visto, AGORA), "congelado")

    def test_pid_vivo_com_batida_recente_nao_parou(self):
        visto = estado(beat=iso(crew_causa.BATIDA_VELHA_SEGUNDOS - 5))
        self.assertIsNone(crew_causa.da_parada(visto, AGORA))

    def test_pid_morto_com_batida_velha_diz_pi_saiu(self):
        visto = estado(pid=pid_morto(), beat=iso(3600))
        self.assertEqual(crew_causa.da_parada(visto, AGORA), "Pi saiu")

    def test_pi_que_saiu_depois_de_um_erro_guarda_a_causa_do_erro(self):
        visto = estado(pid=pid_morto(), outcome=dict(type="error", message="ENOSPC: no space left on device, write"))
        self.assertEqual(crew_causa.da_parada(visto, AGORA), "disco")

    def test_estado_gone_nao_e_causa(self):
        self.assertIsNone(crew_causa.da_parada(estado(state="gone", pid=pid_morto()), AGORA))

    def test_pid_estranho_nao_derruba_a_leitura(self):
        for pid in ("abc", 0, -4, None, True):
            with self.subTest(pid=pid):
                self.assertIsNone(crew_causa.da_parada(estado(pid=pid), AGORA))


class ConferirOPid(unittest.TestCase):
    def test_o_pid_deste_processo_esta_vivo(self):
        self.assertTrue(crew_causa.vivo(os.getpid()))

    def test_o_pid_de_um_filho_que_saiu_esta_morto(self):
        self.assertFalse(crew_causa.vivo(pid_morto()))

    def test_no_windows_a_lista_de_processos_decide_e_o_kill_nunca_roda(self):
        achado = '"python.exe","4242","Console","1","20.000 K"'
        vazio = "INFO: No tasks are running which match the specified criteria."
        with mock.patch("os.kill", side_effect=AssertionError("os.kill no Windows mata o processo")):
            self.assertTrue(crew_causa.vivo(4242, "win32", lambda pid: achado))
            self.assertFalse(crew_causa.vivo(4242, "win32", lambda pid: vazio))
            self.assertFalse(crew_causa.vivo(4242, "win32", lambda pid: '"python.exe","4243","Console","1","20.000 K"'))

    @unittest.skipUnless(sys.platform == "win32", "só no Windows")
    def test_no_windows_de_verdade_o_pid_deste_processo_vive_e_o_de_um_filho_morto_nao(self):
        with mock.patch("os.kill", side_effect=AssertionError("os.kill no Windows mata o processo")):
            self.assertTrue(crew_causa.vivo(os.getpid()))
            self.assertFalse(crew_causa.vivo(pid_morto()))

    @unittest.skipIf(sys.platform == "win32", "só no Linux e no Mac")
    def test_no_linux_o_kill_zero_so_confere(self):
        with mock.patch("os.kill") as kill:
            self.assertTrue(crew_causa.vivo(4242, "linux"))
        kill.assert_called_once_with(4242, 0)


class VigiaEPainel(CrewCase):
    def gravar(self, meta, **campos):
        with open(meta["state_file"], "w", encoding="utf-8") as f:
            json.dump(dict(dict(state="idle", turns=1, pid=os.getpid(), outcome=None,
                                beat=datetime.datetime.now(datetime.timezone.utc).isoformat(), at=datetime.datetime.now(datetime.timezone.utc).isoformat()), **campos), f)

    def paradas(self):
        return [e for e in self.events() if e["kind"] == "stopped"]

    def time(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            self.crew.cmd_time(types.SimpleNamespace(fechados=False))
        return saida.getvalue()

    def test_o_vigia_avisa_parou_com_a_causa(self):
        meta = self.add_worker()
        self.gravar(meta, outcome=dict(type="error", message="ENOSPC: no space left on device, write"))
        self.watch()
        self.assertEqual([e["cause"] for e in self.paradas()], ["disco"])
        avisos = self.told_chief()
        self.assertEqual(len(avisos), 1)
        self.assertIn("t-job: parou, causa: disco", avisos[0])

    def test_a_mesma_causa_avisa_uma_vez_so(self):
        meta = self.add_worker()
        self.gravar(meta, outcome=dict(type="error", message="fetch failed"))
        self.watch(rounds=3)
        self.assertEqual(len(self.paradas()), 1)
        self.assertEqual(len(self.told_chief()), 1)

    def test_pi_que_saiu_acorda_o_chief(self):
        meta = self.add_worker()
        self.gravar(meta, state="working", pid=pid_morto())
        self.watch()
        self.assertEqual([e["cause"] for e in self.paradas()], ["Pi saiu"])
        self.assertIn("parou, causa: Pi saiu", self.told_chief()[0])

    def test_worker_saudavel_nao_avisa(self):
        self.gravar(self.add_worker())
        self.watch()
        self.assertEqual(self.paradas(), [])
        self.assertEqual(self.told_chief(), [])

    def test_painel_fechado_so_diz_que_o_painel_fechou(self):
        meta = self.add_worker()
        self.gravar(meta, state="working", pid=pid_morto())
        self.herdr.panes["w4:p1"]["alive"] = False
        self.watch()
        self.assertEqual(self.paradas(), [])
        self.assertIn("gone", [e["kind"] for e in self.events()])

    def test_worker_de_outra_maquina_nao_tem_o_pid_conferido_aqui(self):
        meta = self.add_worker(host="vps")
        self.gravar(meta, state="working", pid=pid_morto())
        self.assertIsNone(self.crew.snapshot(meta, False)["cause"])
        self.assertNotIn("parou:", self.time())

    def test_o_time_mostra_a_causa(self):
        meta = self.add_worker()
        self.gravar(meta, outcome=dict(type="error", message="Your credit balance is too low to access the Anthropic API."))
        linha = [x for x in self.time().splitlines() if "t-job" in x][0]
        self.assertTrue(linha.startswith("! t-job"))
        self.assertIn("parou: crédito", linha)

    def test_o_time_mostra_pi_saiu(self):
        meta = self.add_worker()
        self.gravar(meta, state="working", pid=pid_morto())
        self.assertIn("parou: Pi saiu", self.time())

    def test_o_time_de_um_worker_saudavel_nao_fala_de_parada(self):
        self.gravar(self.add_worker())
        self.assertNotIn("parou:", self.time())


if __name__ == "__main__":
    unittest.main()
