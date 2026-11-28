import datetime
import json
import os
import types
import unittest

from scripts.test_crew_retomar import Base

API = dict(type="error", message="529 overloaded_error: Overloaded")
REDE = dict(type="error", message="fetch failed: ECONNRESET")
DISCO = dict(type="error", message="ENOSPC: no space left on device, write")
LIMITE = dict(type="error", message="Claude quota exceeded — rate limit (5h) — resets 18:00: You're out of extra usage")
CREDITO = dict(type="error", message="400 Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing")
CREDENCIAL = dict(type="error", message="401 authentication_error: The API Key appears to be invalid or may have expired")
DESCONHECIDO = dict(type="error", message="algo que ninguém previu")
TENTATIVAS_DA_API = (2, 5, 15, 30)


def texto_da_hora(segundos):
    return datetime.datetime.fromtimestamp(segundos, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Automatica(Base):

    def setUp(self):
        super().setUp()
        self.auto = self.crew.module("crew_retomada_auto")
        self.rede = True
        self.auto.rede_voltou = lambda: self.rede
        self.meta = self.add_worker()

    def parar(self, desfecho, turns=1):
        momento = datetime.datetime.fromtimestamp(self.clock.now, datetime.timezone.utc).isoformat()
        with open(self.meta["state_file"], "w", encoding="utf-8") as f:
            json.dump(dict(state="idle", turns=turns, at=momento, outcome=desfecho), f)

    def voltar_bem(self):
        with open(self.meta["state_file"], "w", encoding="utf-8") as f:
            json.dump(dict(state="idle", turns=2, at=texto_da_hora(self.clock.now), outcome=None), f)

    def rodar(self, minutos):
        self.clock.now += minutos * 60
        self.watch()

    def retomadas(self):
        return [mensagem for _, mensagem in self.mensagens if "Retomada" in mensagem]

    def disco(self, livre_gb):
        recursos = self.crew.module("crew_recursos")
        leitura = dict(at=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), disco=dict(livre_gb=livre_gb, total_gb=100))
        os.makedirs(self.state, exist_ok=True)
        with open(recursos.arquivo(recursos.aqui()), "w", encoding="utf-8") as f:
            json.dump(leitura, f)

    def cota(self, reset_em_minutos, lida_em_minutos=0):
        leitura = dict(at=texto_da_hora(self.clock.now + lida_em_minutos * 60), status="rejected", limitante="five_hour",
                       janelas={"5h": dict(usado=100, reset=texto_da_hora(self.clock.now + reset_em_minutos * 60), status="rejected"), "7d": None},
                       extra=dict(status="rejected"))
        os.makedirs(self.state, exist_ok=True)
        with open(self.crew.module("crew_cota").arquivo(), "w", encoding="utf-8") as f:
            json.dump(leitura, f)

    def decisoes(self):
        return [d for d in self.crew.decisions().values() if d.get("worker") == "t-job"]


class ApiFora(Automatica):

    def test_volta_depois_de_2_minutos_dizendo_a_causa(self):
        self.parar(API)
        self.rodar(1)
        self.assertEqual(self.retomadas(), [])
        self.rodar(1.1)
        self.assertEqual(len(self.retomadas()), 1)
        self.assertIn("API fora", self.retomadas()[0])

    def test_a_segunda_tentativa_espera_5_minutos_depois_da_nova_parada(self):
        self.parar(API)
        self.rodar(2.1)
        self.parar(API)
        self.rodar(4)
        self.assertEqual(len(self.retomadas()), 1)
        self.rodar(1.1)
        self.assertEqual(len(self.retomadas()), 2)

    def test_depois_da_ultima_tentativa_avisa_o_chief_uma_vez_so(self):
        for atraso in TENTATIVAS_DA_API:
            self.parar(API)
            self.rodar(atraso + 0.1)
        self.assertEqual(len(self.retomadas()), 4)
        self.parar(API)
        self.rodar(1)
        self.rodar(60)
        self.assertEqual(len(self.retomadas()), 4)
        avisos = [linha for linha in self.told_chief() if "4 tentativas" in linha]
        self.assertEqual(len(avisos), 1)
        self.assertIn("t-job", avisos[0])
        self.assertIn("API fora", avisos[0])

    def test_um_turno_bom_zera_a_contagem(self):
        self.parar(API)
        self.rodar(2.1)
        self.voltar_bem()
        self.rodar(1)
        self.parar(API)
        self.rodar(2.1)
        self.assertEqual(len(self.retomadas()), 2)

    def test_nao_acorda_o_chief_a_cada_parada(self):
        self.parar(API)
        self.rodar(1)
        self.assertEqual([linha for linha in self.told_chief() if "parou" in linha], [])


class DiscoERede(Automatica):

    def test_disco_volta_quando_ha_espaco(self):
        self.parar(DISCO)
        self.disco(3)
        self.rodar(5)
        self.assertEqual(self.retomadas(), [])
        self.disco(30)
        self.rodar(1)
        self.assertEqual(len(self.retomadas()), 1)
        self.assertIn("disco", self.retomadas()[0])

    def test_disco_acorda_o_chief_na_hora(self):
        self.parar(DISCO)
        self.disco(3)
        self.rodar(1)
        self.assertTrue([linha for linha in self.told_chief() if "parou, causa: disco" in linha])

    def test_rede_volta_quando_a_rede_responde(self):
        self.parar(REDE)
        self.rede = False
        self.rodar(5)
        self.assertEqual(self.retomadas(), [])
        self.rede = True
        self.rodar(1)
        self.assertEqual(len(self.retomadas()), 1)
        self.assertIn("rede", self.retomadas()[0])


class LimiteDeUso(Automatica):

    def test_volta_no_reset_da_janela_que_manda(self):
        self.parar(LIMITE)
        self.cota(reset_em_minutos=90)
        self.rodar(60)
        self.assertEqual(self.retomadas(), [])
        self.rodar(31)
        self.assertEqual(len(self.retomadas()), 1)
        self.assertIn("limite de uso", self.retomadas()[0])

    def test_uma_leitura_de_antes_da_parada_nao_vale(self):
        self.cota(reset_em_minutos=-10)
        self.rodar(1)
        self.parar(LIMITE)
        self.rodar(1)
        self.assertEqual(self.retomadas(), [])


class CreditoECredencial(Automatica):

    def dono_responde(self, texto):
        return self.crew.cmd_answer(types.SimpleNamespace(id=self.decisoes()[0]["id"], answer=texto))

    def confere(self, desfecho, causa):
        self.parar(desfecho)
        self.rodar(1)
        self.assertEqual(len(self.decisoes()), 1)
        self.assertEqual(self.decisoes()[0]["status"], "open")
        self.assertIn(causa, self.decisoes()[0]["question"])
        self.rodar(30)
        self.assertEqual((len(self.decisoes()), self.retomadas()), (1, []))
        self.dono_responde("resolvido")
        self.parar(desfecho)
        self.rodar(1)
        self.assertEqual(len(self.retomadas()), 1)
        self.assertIn(causa, self.retomadas()[0])

    def test_credito_vira_decisao_do_dono_e_volta_quando_ele_responde(self):
        self.confere(CREDITO, "crédito")

    def test_credencial_vira_decisao_do_dono_e_volta_quando_ele_responde(self):
        self.confere(CREDENCIAL, "credencial")

    def parar_com_o_pi(self, desfecho):
        self.parar(desfecho)
        with open(self.meta["state_file"], encoding="utf-8") as f:
            visto = json.load(f)
        with open(self.meta["state_file"], "w", encoding="utf-8") as f:
            json.dump(dict(visto, pid=4242), f)

    def responder_com_o_pi(self, desfecho, vivo):
        self.crew.module("crew_causa").vivo = lambda pid: vivo
        self.parar_com_o_pi(desfecho)
        self.rodar(1)
        abertos = dict(self.herdr.launched)
        resposta = self.dono_responde("resolvido")
        self.parar_com_o_pi(desfecho)
        self.rodar(1)
        return resposta, abertos

    def test_com_o_pi_vivo_a_resposta_entregue_basta_e_o_vigia_nao_o_derruba(self):
        resposta, abertos = self.responder_com_o_pi(CREDITO, vivo=True)
        self.assertTrue(resposta["delivered"])
        self.assertEqual((self.herdr.launched, self.retomadas()), (abertos, []))

    def test_com_o_pi_morto_a_resposta_nao_vai_ao_painel_e_o_vigia_o_reabre(self):
        resposta, abertos = self.responder_com_o_pi(CREDENCIAL, vivo=False)
        self.assertFalse(resposta["delivered"])
        self.assertEqual(len(self.retomadas()), 1)
        self.assertNotIn("resolvido", " ".join(m for _, m in self.mensagens))

    def test_nao_acorda_o_chief_com_a_parada_alem_da_decisao(self):
        self.parar(CREDITO)
        self.rodar(1)
        self.assertEqual([linha for linha in self.told_chief() if "parou, causa" in linha], [])
        self.assertTrue([linha for linha in self.told_chief() if "precisa de uma decisão" in linha])


class SemRetomada(Automatica):

    def test_causa_desconhecida_fica_para_o_chief(self):
        self.parar(DESCONHECIDO)
        self.rodar(120)
        self.assertEqual(self.retomadas(), [])
        self.assertTrue([linha for linha in self.told_chief() if "parou, causa: erro desconhecido" in linha])

    def test_retomada_que_falha_volta_como_erro_sem_derrubar_o_ciclo(self):
        def falha(pedido):
            raise self.crew.Fail("retomada", "sem painel")
        self.crew.module("crew_retomada").retomar = falha
        self.parar(API)
        self.clock.now += 200
        self.assertIn("sem painel", self.auto.rodada())

    def test_worker_fechado_nao_volta(self):
        self.parar(API)
        meta = self.crew.read_meta("t-job")
        meta["closed"] = "2026-11-27T10:00:00-03:00"
        self.crew.write_meta(meta)
        self.rodar(5)
        self.assertEqual(self.retomadas(), [])


if __name__ == "__main__":
    unittest.main()
