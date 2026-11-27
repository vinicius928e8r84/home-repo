import contextlib
import datetime
import io
import json
import os
import types

from scripts.test_crew import CHIEF, FakeHerdr, minutes_ago, utc_minutes_ago
from scripts.test_crew_vigia import VigiaCase

MORTO, NOVO = 111, 222


class HerdrDoChief(FakeHerdr):
    def __init__(self, crew, ao_subir):
        super().__init__(crew)
        self.abertas = []
        self.ao_subir = ao_subir
        self.ao_rodar = None
        self.painel_novo = None

    def pane_get(self, step, *args):
        achado = super().pane_get(step, *args)
        achado["result"]["pane"]["workspace_id"] = "w4"
        return achado

    def tab_create(self, step, *args):
        self.next_pane += 1
        self.painel_novo = "w9:p%d" % self.next_pane
        self.panes[self.painel_novo] = dict(alive=True, agent=None)
        self.abertas.append(args)
        return {"result": {"pane": {"pane_id": self.painel_novo}}}

    def pane_run(self, step, *args):
        self.launched[args[2]] = args[3]
        self.panes[args[2]]["agent"] = "pi"
        if self.ao_rodar:
            self.ao_rodar()
        self.ao_subir(args[2])
        return {}


class ChiefCase(VigiaCase):
    def setUp(self):
        super().setUp()
        self.sobe = True
        self.herdr = HerdrDoChief(self.crew, self.subir)
        self.herdr.panes[CHIEF] = dict(alive=True, agent="pi")
        self.crew.herdr = self.herdr
        self.vivos = {NOVO, os.getpid()}
        self.crew.module("crew_causa").vivo = lambda pid: pid in self.vivos
        self.chief = self.crew.module("crew_chief")

    def watch(self, rounds=1):
        painel = self.herdr.painel_novo or CHIEF
        args = types.SimpleNamespace(chief=painel, every=0, stall=20, unstarted=4, rounds=rounds)
        with contextlib.redirect_stdout(io.StringIO()):
            self.crew.cmd_watch(args)

    def subir(self, painel):
        if self.sobe:
            self.escrever_chief(pid=NOVO, painel=painel, beat=utc_minutes_ago(0))

    def escrever_chief(self, pid=MORTO, state="idle", beat=None, painel=CHIEF):
        os.makedirs(os.path.join(self.state, "_chief"), exist_ok=True)
        corpo = dict(state=state, turns=1, at=beat or utc_minutes_ago(7), beat=beat or utc_minutes_ago(7), pane=painel, pid=pid, outcome=None)
        with open(os.path.join(self.state, "_chief", "chief.json"), "w", encoding="utf-8") as f:
            json.dump(corpo, f)

    def volta(self):
        with open(os.path.join(self.state, "_chief", "chief.volta"), encoding="utf-8") as f:
            return f.read().splitlines()

    def trava(self):
        return os.path.join(self.state, "_chief", "chief.trava")

    def travar(self, pid, idade=0):
        os.makedirs(os.path.dirname(self.trava()), exist_ok=True)
        with open(self.trava(), "w", encoding="utf-8") as f:
            json.dump(dict(pid=pid, at=self.clock.time() - idade), f)

    def reabrir(self):
        return self.chief.reabrir()


class VigiaComOChiefFora(ChiefCase):
    def test_pi_do_chief_morto_o_vigia_reabre_uma_vez_so(self):
        self.escrever_chief()
        self.add_worker()
        for _ in range(3):
            self.rodada()
        self.assertEqual(len(self.herdr.abertas), 1)
        self.assertEqual(self.herdr.launched[self.herdr.painel_novo], "pi --session-id chief")

    def test_o_vigia_segue_sem_o_chief_e_guarda_os_avisos_na_caixa(self):
        self.escrever_chief()
        self.sobe = False
        self.add_worker()
        self.add_events([dict(kind="decision_needed", id="D7", question="Qual banco?")])
        self.assertIn("D7", self.rodada()[0])
        self.assertEqual(self.kinds().count("chief_resumed"), 0)

    def test_chief_de_pe_nao_e_reaberto(self):
        self.vivos.add(MORTO)
        self.escrever_chief(beat=utc_minutes_ago(0))
        self.add_worker()
        self.rodada()
        self.assertEqual(self.herdr.abertas, [])

    def test_sem_estado_do_chief_o_vigia_so_confere_o_painel(self):
        self.add_worker()
        self.rodada()
        self.assertEqual(self.herdr.abertas, [])

    def test_com_a_retomada_em_andamento_o_vigia_nao_abre_outra(self):
        self.escrever_chief()
        self.travar(os.getpid())
        self.add_worker()
        self.rodada()
        self.assertEqual(self.herdr.abertas, [])

    def test_chief_que_saiu_limpo_nao_e_reaberto(self):
        self.escrever_chief(state="gone")
        self.add_worker()
        self.rodada()
        self.assertEqual(self.herdr.abertas, [])


class ReaberturaDoChief(ChiefCase):
    def test_abre_na_conversa_chief_no_workspace_do_painel_velho(self):
        self.escrever_chief()
        feito = self.reabrir()
        argumentos = self.herdr.abertas[0]
        self.assertEqual(argumentos[argumentos.index("--workspace") + 1], "w4")
        self.assertFalse(self.herdr.panes[CHIEF]["alive"])
        self.assertEqual((feito["causa"], feito["conversa"], feito["pane"]), ("Pi saiu", "chief", self.herdr.painel_novo))

    def test_abre_na_pasta_do_chief_quando_o_drill_a_indica(self):
        os.environ["CREW_CHIEF_DIR"] = os.path.join(self.tmp, "casa")
        self.escrever_chief()
        self.reabrir()
        argumentos = self.herdr.abertas[0]
        self.assertEqual(argumentos[argumentos.index("--cwd") + 1], os.path.normpath(os.path.join(self.tmp, "casa")))

    def test_a_mensagem_de_volta_traz_causa_hora_da_queda_hora_da_volta_e_resumo(self):
        beat = utc_minutes_ago(7)
        self.escrever_chief(beat=beat)
        self.add_events([dict(kind="decision_needed", id="D7", question="Qual banco?"), dict(kind="turn_ended"), dict(kind="turn_ended"),
                         dict(kind="decision_needed", id="D1", question="antiga", at=minutes_ago(30))])
        self.reabrir()
        (mensagem,) = self.volta()
        queda = datetime.datetime.fromisoformat(beat).astimezone().strftime("%H:%M")
        self.assertIn("Causa da queda: Pi saiu", mensagem)
        self.assertIn("Caiu às %s e voltou às " % queda, mensagem)
        self.assertIn("D7 «Qual banco?»", mensagem)
        self.assertIn("2 turnos", mensagem)
        self.assertNotIn("D1", mensagem)

    def test_os_avisos_de_enquanto_esteve_fora_estao_na_caixa_e_no_resumo(self):
        self.escrever_chief()
        self.travar(os.getpid())
        self.add_worker()
        self.add_events([dict(kind="decision_needed", id="D7", question="Qual banco?")])
        self.assertIn("D7", self.rodada()[0])
        os.remove(self.trava())
        self.reabrir()
        self.assertIn("D7", self.told_chief()[0])
        self.assertIn("D7", self.volta()[0])

    def test_com_o_chief_de_pe_recusa_e_nao_cria_trava(self):
        self.vivos.add(MORTO)
        self.escrever_chief(beat=utc_minutes_ago(0))
        with self.assertRaises(self.crew.Fail):
            self.reabrir()
        self.assertEqual(self.herdr.abertas, [])
        self.assertFalse(os.path.exists(self.trava()))

    def test_duas_reaberturas_ao_mesmo_tempo_so_uma_passa(self):
        self.escrever_chief()
        recusadas = []

        def segunda():
            try:
                self.reabrir()
            except self.crew.Fail as erro:
                recusadas.append(erro.error)

        self.herdr.ao_rodar = segunda
        self.reabrir()
        self.assertEqual(len(self.herdr.abertas), 1)
        self.assertEqual(len(recusadas), 1)
        self.assertIn("em andamento", recusadas[0])

    def test_depois_da_volta_a_trava_solta_e_outra_reabertura_ve_o_chief_de_pe(self):
        self.escrever_chief()
        self.reabrir()
        self.assertFalse(os.path.exists(self.trava()))
        with self.assertRaises(self.crew.Fail):
            self.reabrir()
        self.assertEqual(len(self.herdr.abertas), 1)

    def test_pi_que_nao_sobe_segura_a_trava_ate_ela_vencer(self):
        self.escrever_chief()
        self.sobe = False
        with self.assertRaises(self.crew.Fail):
            self.reabrir()
        self.add_worker()
        self.rodada()
        self.assertEqual(len(self.herdr.abertas), 1)
        self.clock.now += 400
        self.rodada()
        self.assertEqual(len(self.herdr.abertas), 2)

    def test_trava_de_quem_morreu_e_tomada(self):
        self.escrever_chief()
        self.travar(MORTO)
        self.reabrir()
        self.assertEqual(len(self.herdr.abertas), 1)
