import hashlib
import json
import os
import unittest

from scripts.test_crew import CrewCase, minutes_ago, utc_minutes_ago

LINHA = chr(0x2500) * 12
FAIXA = "%s %s Working %s" % (chr(0x2500) * 2, chr(0x280b), LINHA)
RODAPE = "\n\n%s\n~\\worktrees\\Test-job (pi/job)\n" % LINHA


def rodando(comando):
    return "\n $ %s (timeout 2000s)\n\n Elapsed 25m 16s\n\n\n%s%s" % (comando, FAIXA, RODAPE)


def terminado(comando):
    return "\n $ %s\n\n Took 4.1s\n\n\n%s%s" % (comando, FAIXA, RODAPE)


OCIOSA = "\n Feito. O relatório está pronto.\n\n%s\n%s%s" % (LINHA, LINHA, RODAPE)


class Parado(CrewCase):
    def parado_com_a_tela(self, tela, relatorio=False):
        meta = self.add_worker(at=utc_minutes_ago(30))
        if relatorio:
            with open(meta["report"], "w") as f:
                f.write("pronto")
        self.herdr.screen = tela
        marca = hashlib.sha1(self.crew.progress_mark(meta).encode()).hexdigest()
        with open(os.path.join(self.state, "t-job", "watch.json"), "w") as f:
            json.dump(dict(progress=dict(mark=marca, at=minutes_ago(25))), f)
        return self.crew.snapshot(meta, False, 20)["stalled"]

    def test_laco_de_espera_do_ci_nao_e_parado(self):
        comando = 'for i in $(seq 1 40); do h=$(gh pr view 844 --json mergeable); [ "$h" = ok ] && break; sleep 45; done'
        self.assertFalse(self.parado_com_a_tela(rodando(comando)))

    def test_gh_pr_checks_watch_nao_e_parado(self):
        self.assertFalse(self.parado_com_a_tela(rodando("gh pr checks 21 --watch")))

    def test_esperar_o_dono_na_pagina_do_lavish_nao_e_parado(self):
        self.assertFalse(self.parado_com_a_tela(rodando("npx -y lavish-axi poll .lavish/plano.html 2>&1 | tail -25")))

    def test_comando_travado_que_nao_e_espera_continua_parado(self):
        self.assertTrue(self.parado_com_a_tela(rodando("python -m unittest discover")))

    def test_espera_que_ja_terminou_continua_parada(self):
        self.assertTrue(self.parado_com_a_tela(terminado("sleep 45")))

    def test_espera_antiga_na_tela_nao_esconde_comando_novo_travado(self):
        tela = terminado("sleep 45") + rodando("python -m unittest discover")
        self.assertTrue(self.parado_com_a_tela(tela))

    def test_ocioso_com_relatorio_pronto_nao_e_parado(self):
        self.assertFalse(self.parado_com_a_tela(OCIOSA, relatorio=True))

    def test_turno_vivo_com_relatorio_continua_parado(self):
        self.assertTrue(self.parado_com_a_tela(rodando("python -m unittest discover"), relatorio=True))

    def test_ocioso_sem_relatorio_continua_parado(self):
        self.assertTrue(self.parado_com_a_tela(OCIOSA))

    def test_tela_ilegivel_com_relatorio_continua_parada(self):
        self.assertTrue(self.parado_com_a_tela("", relatorio=True))


class NuncaComecou(CrewCase):
    def tipos(self):
        return [e["kind"] for e in self.events()]

    def watch_com_turnos_antes(self, turnos):
        with open(os.path.join(self.state, "t-job", "watch.json"), "w") as f:
            json.dump(dict(state="idle", turns=turnos), f)
        self.watch()

    def test_worker_parado_em_zero_turnos_alem_do_prazo_acorda(self):
        self.add_worker(state="idle", turns=0, started=minutes_ago(10), at=utc_minutes_ago(10))
        self.watch()
        self.assertIn("never_started", self.tipos())
        self.assertEqual(len(self.told_chief()), 1)

    def test_worker_novo_tem_tempo_para_comecar(self):
        self.add_worker(state="idle", turns=0, started=minutes_ago(1), at=utc_minutes_ago(1))
        self.watch()
        self.assertNotIn("never_started", self.tipos())

    def test_worker_que_rodou_turno_nao_acorda(self):
        self.add_worker(state="idle", turns=2, started=minutes_ago(10), at=utc_minutes_ago(10))
        self.watch()
        self.assertNotIn("never_started", self.tipos())

    def test_relancado_com_session_volta_a_zero_turnos_e_nao_acorda(self):
        self.add_worker(state="idle", turns=0, started=minutes_ago(600), at=utc_minutes_ago(30))
        self.watch_com_turnos_antes(3)
        self.assertNotIn("never_started", self.tipos())

    def test_o_relancado_segue_sem_acordar_nas_rodadas_seguintes(self):
        self.add_worker(state="idle", turns=0, started=minutes_ago(600), at=utc_minutes_ago(30))
        self.watch_com_turnos_antes(3)
        self.watch(rounds=3)
        self.assertNotIn("never_started", self.tipos())

    def test_relancado_que_o_vigia_nunca_viu_com_turno_conta_do_ultimo_inicio_do_pi(self):
        self.add_worker(state="idle", turns=0, started=minutes_ago(600), at=utc_minutes_ago(1))
        self.watch()
        self.assertNotIn("never_started", self.tipos())


if __name__ == "__main__":
    unittest.main()
