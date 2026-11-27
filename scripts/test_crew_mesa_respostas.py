import json
import os
import shutil
import socket
import subprocess
import types
import unittest
import urllib.request

from scripts.test_crew_mesa import ENCERRADA, ESPERANDO, SEM_SESSAO, MesaCase, feedback, resposta


class ServidorPropio(MesaCase):
    def test_o_lavish_roda_so_para_a_mesa_e_nunca_dorme(self):
        self.add_worker()
        self.rodada()
        self.assertTrue(self.lavish.chamadas)
        for argv, ambiente in self.lavish.chamadas:
            self.assertEqual(argv[0], "lavish-axi")
            self.assertNotIn(ambiente["LAVISH_AXI_PORT"], ("", "4387"))
            self.assertEqual(os.path.normpath(ambiente["LAVISH_AXI_STATE_DIR"]), os.path.normpath(os.path.join(self.state, "_mesa", "lavish")))
            for chave in ("LAVISH_AXI_IDLE_TIMEOUT_MS", "LAVISH_AXI_DISCONNECT_GRACE_MS"):
                self.assertEqual(ambiente[chave], "off")
            self.assertEqual(ambiente["LAVISH_AXI_NO_OPEN"], "1")

    def test_cada_volta_faz_um_poll_de_1_segundo_sem_assumir_o_ouvinte(self):
        self.add_worker()
        self.rodada()
        polls = self.lavish.com("poll")
        self.assertEqual(len(polls), 1)
        for pedaco in (self.pagina, "--timeout-ms", "1000", "--owner", "vigia"):
            self.assertIn(pedaco, polls[0])
        self.assertNotIn("--takeover", polls[0])

    def test_sem_sessao_a_mesa_abre_sem_abrir_navegador(self):
        self.add_worker()
        self.lavish.polls = [SEM_SESSAO]
        self.rodada()
        self.assertIn([self.pagina, "--no-open"], self.lavish.comandos())

    def test_mesa_viva_nao_e_aberta_de_novo(self):
        self.add_worker()
        self.rodada()
        self.assertNotIn([self.pagina, "--no-open"], self.lavish.comandos())

    def test_lavish_fora_do_ar_nao_derruba_o_vigia(self):
        self.add_worker()

        def quebra(argv, ambiente):
            raise self.crew.Fail("mesa", "o lavish-axi não está instalado")
        self.mesa.executar = quebra
        self.rodada()
        self.assertIn("turn_ended", self.kinds())


class ComandoDoLavish(MesaCase):
    def rodar(self, no_path):
        achados, ambiente = [], dict(LAVISH_AXI_PORT="1")
        self.mesa.shutil = types.SimpleNamespace(which=lambda nome: no_path.get(nome))
        self.mesa.subprocess = types.SimpleNamespace(run=lambda comando, **_: achados.append(comando) or types.SimpleNamespace(stdout="ok"),
                                                     TimeoutExpired=subprocess.TimeoutExpired)
        self.mesa.executar_original(["lavish-axi", "poll", "mesa.html"], ambiente)
        return achados

    def test_sem_lavish_no_path_a_mesa_usa_o_npx_na_versao_fixa(self):
        npx = os.path.join("nodejs", "npx.cmd")
        self.assertEqual(self.rodar({"npx": npx}), [[npx, "-y", "lavish-axi@" + self.mesa.VERSAO_DO_LAVISH, "poll", "mesa.html"]])

    def test_com_lavish_no_path_a_mesa_usa_o_do_path(self):
        self.assertEqual(self.rodar({"lavish-axi": "/usr/bin/lavish-axi", "npx": "/usr/bin/npx"}), [["/usr/bin/lavish-axi", "poll", "mesa.html"]])


class RespostaDoDono(MesaCase):
    def test_a_resposta_responde_a_decisao_chega_ao_worker_e_a_caixa_do_chief(self):
        self.add_worker()
        self.decisao()
        self.lavish.polls = [feedback(resposta("usa o A"))]
        self.rodada()
        entrada = self.crew.decisions()["D1"]
        self.assertEqual((entrada["status"], entrada["answer"]), ("answered", "usa o A"))
        self.assertIn("decision_answered", self.kinds())
        self.assertTrue(any("D1" in t and "usa o A" in t for t in self.herdr.sent["w4:p1"]))
        mensagens = self.mensagens_da_mesa()
        self.assertEqual(len(mensagens), 1)
        self.assertIn("D1", mensagens[0])
        self.assertIn("usa o A", mensagens[0])
        self.assertIn("t-job", mensagens[0])

    def test_a_pagina_da_mesma_volta_ja_nao_traz_a_decisao_respondida(self):
        self.add_worker()
        self.decisao()
        self.rodada()
        self.assertIn("Qual banco usamos?", self.html())
        self.lavish.polls = [feedback(resposta("usa o A"), fim=True)]
        self.rodada()
        self.assertNotIn("Qual banco usamos?", self.html())

    def test_o_dono_ve_o_recebido(self):
        self.add_worker()
        self.decisao()
        self.lavish.polls = [feedback(resposta("usa o A"))]
        self.rodada()
        self.assertEqual(self.lavish.com("reply"), [["lavish-axi", "reply", self.pagina, "--agent-reply", "Recebido."]])

    def test_sem_resposta_nao_ha_recibo_nem_aviso(self):
        self.add_worker()
        self.rodada()
        self.assertEqual(self.lavish.com("reply"), [])
        self.assertEqual(self.mensagens_da_mesa(), [])

    def test_resposta_com_virgula_aspas_e_quebra_de_linha_chega_inteira(self):
        self.add_worker()
        self.decisao()
        texto = 'sim, "talvez"\nlinha 2 \\ barra'
        self.lavish.polls = [feedback(resposta(texto))]
        self.rodada()
        self.assertEqual(self.crew.decisions()["D1"]["answer"], texto)

    def test_duas_respostas_na_mesma_volta(self):
        self.add_worker()
        self.decisao("primeira")
        self.decisao("segunda")
        self.lavish.polls = [feedback(resposta("um", "D1"), resposta("dois", "D2"))]
        self.rodada()
        self.assertEqual([self.crew.decisions()[i]["answer"] for i in ("D1", "D2")], ["um", "dois"])
        self.assertEqual(len(self.mensagens_da_mesa()), 2)
        self.assertEqual(len(self.lavish.com("reply")), 1)

    def test_resposta_livre_da_pagina_vai_so_a_caixa_do_chief(self):
        self.add_worker()
        self.lavish.polls = [feedback(dict(prompt="e a cota?", tag="", text=""))]
        self.rodada()
        self.assertEqual(len(self.mensagens_da_mesa()), 1)
        self.assertIn("e a cota?", self.mensagens_da_mesa()[0])

    def test_decisao_que_nao_existe_vai_ao_chief_com_o_motivo(self):
        self.add_worker()
        self.lavish.polls = [feedback(resposta("oi", "D99"))]
        self.rodada()
        self.assertEqual(len(self.mensagens_da_mesa()), 1)
        self.assertIn("D99", self.mensagens_da_mesa()[0])
        self.assertIn("oi", self.mensagens_da_mesa()[0])
        self.assertIn("não", self.mensagens_da_mesa()[0])

    def test_worker_fechado_a_resposta_fica_registrada_e_o_chief_sabe(self):
        self.add_worker()
        self.decisao()
        self.herdr.panes["w4:p1"]["alive"] = False
        self.lavish.polls = [feedback(resposta("usa o A"))]
        self.rodada()
        self.assertEqual(self.crew.decisions()["D1"]["status"], "answered")
        self.assertIn("usa o A", self.mensagens_da_mesa()[0])


class VigiaParadoNoMeio(MesaCase):
    def cair_ao_avisar_o_chief(self):
        original = self.crew.tell_chief

        def cai(pane, texto):
            if texto.startswith("[mesa]"):
                raise RuntimeError("o Vigia caiu")
            return original(pane, texto)
        self.crew.tell_chief = cai
        self.addCleanup(setattr, self.crew, "tell_chief", original)
        return original

    def test_queda_depois_de_gravar_a_resposta_entrega_na_volta_seguinte(self):
        self.add_worker()
        self.decisao()
        self.lavish.polls = [feedback(resposta("usa o A"))]
        original = self.cair_ao_avisar_o_chief()
        with self.assertRaises(RuntimeError):
            self.rodada()
        self.assertEqual(self.mensagens_da_mesa(), [])
        self.crew.tell_chief = original
        self.rodada()
        mensagens = self.mensagens_da_mesa()
        self.assertEqual(len(mensagens), 1)
        self.assertIn("usa o A", mensagens[0])
        self.assertNotIn("não entrou", mensagens[0])
        self.assertEqual(len(self.herdr.sent["w4:p1"]), 1)
        self.rodada()
        self.assertEqual(len(self.mensagens_da_mesa()), 1)

    def test_o_dono_ve_o_recebido_mesmo_com_a_queda_antes_da_entrega(self):
        self.add_worker()
        self.decisao()
        self.lavish.polls = [feedback(resposta("usa o A"))]
        original = self.cair_ao_avisar_o_chief()
        with self.assertRaises(RuntimeError):
            self.rodada()
        self.assertEqual(self.lavish.com("reply"), [])
        self.crew.tell_chief = original
        self.rodada()
        self.rodada()
        self.assertEqual(self.lavish.com("reply"), [["lavish-axi", "reply", self.pagina, "--agent-reply", "Recebido."]])

    def test_a_entrega_pendente_nao_espera_o_lavish_voltar(self):
        self.add_worker()
        self.decisao()
        self.lavish.polls = [feedback(resposta("usa o A"))]
        original = self.cair_ao_avisar_o_chief()
        with self.assertRaises(RuntimeError):
            self.rodada()
        self.crew.tell_chief = original

        def fora(argv, ambiente):
            raise self.crew.Fail("mesa", "o lavish-axi não está instalado")
        self.mesa.executar = fora
        self.rodada()
        self.assertEqual(len(self.mensagens_da_mesa()), 1)

    def test_resposta_dada_com_o_vigia_parado_chega_quando_ele_volta(self):
        self.add_worker()
        self.decisao()
        self.lavish.polls = [ESPERANDO, ESPERANDO, feedback(resposta("usa o A"))]
        self.rodada()
        self.rodada()
        self.assertEqual(self.mensagens_da_mesa(), [])
        self.rodada()
        self.assertIn("usa o A", self.mensagens_da_mesa()[0])


class EncerrarAMesa(MesaCase):
    def test_encerrada_a_mesa_reabre_na_volta_seguinte_sem_avisar_o_chief(self):
        self.add_worker()
        antes = self.told_chief()
        self.lavish.polls = [ENCERRADA]
        self.rodada()
        self.assertIn([self.pagina, "--reopen", "--no-open"], self.lavish.comandos())
        self.assertEqual(self.told_chief(), antes)
        self.assertEqual(self.lavish.com("reply"), [])

    def test_a_ultima_resposta_de_quem_encerra_e_entregue_e_a_mesa_reabre(self):
        self.add_worker()
        self.decisao()
        self.lavish.polls = [feedback(resposta("usa o A"), fim=True)]
        self.rodada()
        self.assertEqual(self.crew.decisions()["D1"]["answer"], "usa o A")
        self.assertEqual(len(self.mensagens_da_mesa()), 1)
        self.assertIn([self.pagina, "--reopen", "--no-open"], self.lavish.comandos())

    def test_mesa_aberta_nao_e_reaberta(self):
        self.add_worker()
        self.rodada()
        self.assertNotIn("--reopen", sum(self.lavish.comandos(), []))


class RespostasAntigas(MesaCase):
    def setUp(self):
        super().setUp()
        self.antigo = os.path.join(self.home, ".lavish-axi")
        os.makedirs(self.antigo)
        self.arquivos = {nome: "/c/worktrees/x/.lavish/%s" % nome for nome in ("mesa.html", "geral.html", "d34-limite-de-linhas.html", "outra.html")}

    def sessoes(self, pendentes=True):
        sessoes = {nome: dict(file=arquivo, status="ended", prompts=[dict(prompt="x")] if pendentes else []) for nome, arquivo in self.arquivos.items()}
        with open(os.path.join(self.antigo, "state.json"), "w", encoding="utf-8") as f:
            json.dump(dict(sessions=sessoes), f)

    def test_as_respostas_nunca_entregues_das_paginas_antigas_vao_ao_chief(self):
        self.add_worker()
        self.sessoes()
        for nome in ("mesa.html", "geral.html", "d34-limite-de-linhas.html"):
            self.lavish.por_arquivo[self.arquivos[nome]] = [feedback(dict(prompt="resposta de %s" % nome, tag="", text=""), fim=True)]
        self.rodada()
        mensagens = self.mensagens_da_mesa()
        self.assertEqual(len(mensagens), 3)
        for nome in ("mesa.html", "geral.html", "d34-limite-de-linhas.html"):
            self.assertTrue(any("resposta de %s" % nome in m for m in mensagens))
        antigas = [argv for argv in self.lavish.com("poll") if self.pagina not in argv]
        self.assertEqual(len(antigas), 3)
        for argv, ambiente in self.lavish.chamadas:
            if self.pagina not in argv:
                self.assertNotIn("4388", ambiente.get("LAVISH_AXI_PORT", ""))
                self.assertNotIn("--takeover", argv)

    def test_pagina_antiga_sem_resposta_pendente_nao_e_lida(self):
        self.add_worker()
        self.sessoes(pendentes=False)
        self.rodada()
        self.assertEqual([a for a in self.lavish.com("poll") if self.pagina not in a], [])

    def test_so_as_tres_paginas_da_mesa_antiga_sao_lidas(self):
        self.add_worker()
        self.sessoes()
        self.rodada()
        lidas = [a[2] for a in self.lavish.com("poll")]
        self.assertNotIn(self.arquivos["outra.html"], lidas)

    def test_a_resposta_antiga_chega_uma_vez_so(self):
        self.add_worker()
        self.sessoes()
        self.lavish.por_arquivo[self.arquivos["mesa.html"]] = [feedback(dict(prompt="oi antigo", tag="", text=""), fim=True)]
        self.rodada()
        self.rodada()
        self.assertEqual(len([m for m in self.mensagens_da_mesa() if "oi antigo" in m]), 1)


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return str(s.getsockname()[1])


@unittest.skipUnless(shutil.which("lavish-axi"), "o lavish-axi não está instalado")
class MesaDeVerdade(MesaCase):
    def setUp(self):
        super().setUp()
        self.mesa.executar = self.executar_real
        self.mesa.PORTA = porta_livre()
        self.addCleanup(self.parar_servidor)

    def executar_real(self, argv, ambiente):
        feito = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", env=ambiente, timeout=90)
        return feito.stdout

    def parar_servidor(self):
        subprocess.run(["lavish-axi", "stop"], capture_output=True, env=self.mesa.ambiente(), timeout=60)

    def sessao(self):
        with open(os.path.join(self.state, "_mesa", "lavish", "state.json"), encoding="utf-8") as f:
            return list(json.load(f)["sessions"].values())[0]

    def enviar(self, prompts, fim=False):
        corpo = json.dumps(dict(prompts=prompts, endSession=fim)).encode()
        pedido = urllib.request.Request("http://127.0.0.1:%s/api/%s/prompts" % (self.mesa.PORTA, self.sessao()["key"]), data=corpo,
                                        headers={"content-type": "application/json", "Origin": "http://127.0.0.1:%s" % self.mesa.PORTA})
        urllib.request.urlopen(pedido, timeout=30).read()

    def test_resposta_dada_com_o_vigia_parado_chega_a_caixa_do_chief_e_encerrar_reabre(self):
        self.add_worker()
        self.decisao()
        self.rodada()
        self.assertEqual(self.sessao()["status"], "open")
        self.enviar([dict(prompt="usa o A", tag="decisao", text="D1")])
        self.rodada()
        self.assertEqual(self.crew.decisions()["D1"]["answer"], "usa o A")
        self.assertEqual(len(self.mensagens_da_mesa()), 1)
        self.enviar([dict(prompt="tchau", tag="", text="")], fim=True)
        self.rodada()
        self.assertEqual(len(self.mensagens_da_mesa()), 2)
        self.assertEqual(self.sessao()["status"], "open")


if __name__ == "__main__":
    unittest.main()
