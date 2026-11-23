import json
import os
import re
import unittest

from scripts.test_crew import CrewCase, minutes_ago

CINZA = dict(__typename="CheckRun", status="IN_PROGRESS", conclusion=None)


def check(nome, resultado):
    return dict(__typename="CheckRun", name=nome, status="COMPLETED", conclusion=resultado)


def pr(numero=12, head="a" * 40, checks=None, **campos):
    base = dict(number=numero, headRefName="pi/job", headRefOid=head, isDraft=False, state="OPEN", title="Titulo %d" % numero,
                statusCheckRollup=checks if checks is not None else [])
    return dict(base, **campos)


def verde_sem_registro(head="a" * 40):
    return pr(head=head, checks=[check("Freios", "SUCCESS"), check("Registro da PR", "FAILURE")])


def verde_com_registro(head="a" * 40):
    return pr(head=head, checks=[check("Freios", "SUCCESS"), check("Registro da PR", "SUCCESS")])


class VigiaCase(CrewCase):
    def setUp(self):
        super().setUp()
        self.prs = []
        self.gh_quebrado = False
        self.modulo = self.crew.module("crew_prs")
        self.modulo.buscar = self.buscar
        os.makedirs(self.state, exist_ok=True)
        with open(os.path.join(self.state, "notify.cursor"), "w") as f:
            f.write("0")

    def add_events(self, eventos):
        with open(os.path.join(self.state, "events.jsonl"), "a", encoding="utf-8") as f:
            for evento in eventos:
                f.write(json.dumps(dict(dict(at=minutes_ago(1), worker="w"), **evento)) + "\n")

    def avisos(self):
        return [linha for linha in self.told_chief() if not linha.startswith("[resumo]")]

    def buscar(self, caminho):
        if self.gh_quebrado:
            raise self.crew.Fail("gh", "sem rede")
        return self.prs

    def rodada(self, minutos=3):
        self.clock.now += minutos * 60
        self.watch()
        return self.avisos()

    def kinds(self):
        return [e["kind"] for e in self.events()]


class QuemAcorda(VigiaCase):
    def test_um_turno_terminado_nao_acorda(self):
        self.add_worker(turns=1)
        self.assertEqual(self.rodada(), [])
        self.assertIn("turn_ended", self.kinds())

    def test_pedido_de_decisao_traz_numero_e_titulo(self):
        self.add_worker()
        self.add_events([dict(kind="decision_needed", id="D7", question="Qual banco usamos?")])
        avisos = self.rodada()
        self.assertEqual(len(avisos), 1)
        self.assertIn("D7 «Qual banco usamos?»", avisos[0])

    def test_titulo_comprido_e_cortado(self):
        self.add_worker()
        self.add_events([dict(kind="decision_needed", id="D8", question="x" * 300)])
        self.assertLess(len(self.rodada()[0]), 300)

    def test_nenhum_aviso_cita_decisao_sem_titulo(self):
        self.add_worker()
        self.add_events([dict(kind="decision_needed", id="D%d" % n, question="pergunta %d" % n) for n in range(1, 6)])
        for aviso in self.rodada():
            self.assertEqual(re.findall(r"D\d+(?! «)", aviso), [])

    def test_erros_parado_e_mesclada_acordam(self):
        self.add_worker()
        self.add_events([dict(kind=k) for k in ("spawn_failed", "never_started", "stalled", "merged", "gone")])
        aviso = self.rodada()[0]
        for pedaco in ("erro:", "parado:", "branch mesclada:"):
            self.assertIn(pedaco, aviso)

    def test_avisos_do_mesmo_motivo_vao_juntos(self):
        self.add_worker()
        self.add_events([dict(kind="stalled", worker="a"), dict(kind="stalled", worker="b")])
        avisos = self.rodada()
        self.assertEqual(len(avisos), 1)
        self.assertEqual(avisos[0].count("parado:"), 1)

    def test_rotina_nao_acorda(self):
        self.add_worker()
        self.add_events([dict(kind=k) for k in ("spawned", "closed", "told", "turn_ended", "decision_answered")])
        self.assertEqual(self.rodada(), [])

    def test_relatorio_de_quem_nao_tem_pr_acorda(self):
        self.add_worker()
        self.add_events([dict(kind="report_written", worker="t-job")])
        self.assertIn("relatório sem PR: t-job", self.rodada()[0])

    def test_relatorio_de_quem_ja_tem_pr_nao_acorda(self):
        self.add_worker()
        self.prs = [verde_com_registro()]
        self.rodada()
        self.add_events([dict(kind="report_written", worker="t-job")])
        self.assertEqual(self.rodada(), [])


class Resumo(VigiaCase):
    def resumo(self):
        caminho = os.path.join(self.state, "resumo.md")
        if not os.path.exists(caminho):
            return []
        with open(caminho, encoding="utf-8") as f:
            return f.read().splitlines()

    def test_primeira_rodada_nao_despeja_o_historico(self):
        self.add_events([dict(kind="turn_ended") for _ in range(5)])
        self.add_worker()
        self.rodada(31)
        self.assertEqual(self.resumo(), [])

    def test_resumo_sai_a_cada_30_minutos_so_com_novidade(self):
        self.add_worker()
        self.rodada(1)
        self.add_events([dict(kind="turn_ended"), dict(kind="turn_ended"), dict(kind="spawned"), dict(kind="stalled")])
        self.rodada(10)
        self.assertEqual(self.resumo(), [])
        self.rodada(25)
        self.assertEqual(len(self.resumo()), 1)
        self.assertIn("2 turnos", self.resumo()[0])
        self.assertIn("1 worker aberto", self.resumo()[0])
        self.assertNotIn("parado", self.resumo()[0])
        self.rodada(31)
        self.assertEqual(len(self.resumo()), 1)

    def test_resumo_vai_marcado_para_o_chief_entregar_sem_acordar(self):
        self.add_worker()
        self.rodada(1)
        self.add_events([dict(kind="told")])
        self.assertEqual(self.rodada(31), [])
        self.assertEqual(len(self.resumo()), 1)
        self.assertEqual([l[:9] for l in self.told_chief()], ["[resumo] "])


class PrsProntas(VigiaCase):
    def setUp(self):
        super().setUp()
        self.add_worker()
        self.rodada()

    def test_primeira_leitura_nao_acorda(self):
        self.assertEqual(self.avisos(), [])
        self.assertNotIn("pr_ready_review", self.kinds())

    def test_pr_que_vira_pronta_para_revisao_acorda_uma_vez(self):
        self.prs = [pr(checks=[check("Freios", "SUCCESS"), dict(CINZA, name="Registro da PR")])]
        self.assertEqual(self.rodada(), [])
        self.prs = [verde_sem_registro()]
        avisos = self.rodada()
        self.assertEqual(len(avisos), 1)
        self.assertIn("PR pronta para revisão: Test#12 «Titulo 12» (t-job)", avisos[0])
        self.assertEqual(len(self.rodada()), 1)

    def test_pr_que_oscila_no_mesmo_head_nao_acorda_de_novo(self):
        self.prs = [verde_sem_registro()]
        self.rodada()
        self.prs = [pr(checks=[dict(CINZA, name="Freios")])]
        self.rodada()
        self.prs = [verde_sem_registro()]
        self.assertEqual(len(self.rodada()), 1)

    def test_commit_novo_pede_nova_revisao(self):
        self.prs = [verde_sem_registro()]
        self.rodada()
        self.prs = [verde_sem_registro("b" * 40)]
        self.assertEqual(len(self.rodada()), 2)

    def test_revisao_registrada_vira_pronta_para_merge(self):
        self.prs = [verde_sem_registro()]
        self.rodada()
        self.prs = [verde_com_registro()]
        avisos = self.rodada()
        self.assertEqual(len(avisos), 2)
        self.assertIn("PR pronta para merge: Test#12", avisos[1])

    def test_ci_vermelho_nao_acorda(self):
        self.prs = [pr(checks=[check("Freios", "FAILURE"), check("Registro da PR", "FAILURE")])]
        self.assertEqual(self.rodada(), [])

    def test_gh_fora_do_ar_nao_acorda_nem_despeja_depois(self):
        self.gh_quebrado = True
        self.assertEqual(self.rodada(), [])
        self.gh_quebrado = False
        self.prs = [verde_sem_registro()]
        self.assertEqual(self.rodada(), [])
        self.assertEqual(self.crew.file_state(os.path.join(self.state, "prs.json"))["erros"], {})

    def test_pr_ja_pronta_antes_da_primeira_leitura_nao_acorda(self):
        os.remove(os.path.join(self.state, "prs.json"))
        self.prs = [verde_sem_registro()]
        self.assertEqual(self.rodada(), [])

    def test_pr_sem_worker_leva_o_numero_no_lugar_do_nome(self):
        self.prs = [pr(numero=30, headRefName="pi/de-fora")]
        self.rodada()
        self.prs = [pr(numero=30, headRefName="pi/de-fora", checks=verde_sem_registro()["statusCheckRollup"])]
        self.assertIn("(PR #30)", self.rodada()[0])

    def test_cache_so_atualiza_a_cada_dois_minutos(self):
        chamadas = []
        self.modulo.buscar = lambda caminho: chamadas.append(1) or []
        self.rodada(1)
        self.rodada(1)
        self.assertEqual(len(chamadas), 1)
        self.rodada(2)
        self.assertEqual(len(chamadas), 2)


class EstadoDaPr(unittest.TestCase):
    def estado(self, **campos):
        from scripts.crew_prs import estado
        return estado(pr(**campos))

    def test_cada_caso(self):
        sem = [check("Freios", "SUCCESS"), check("Registro da PR", "FAILURE")]
        com = [check("Freios", "SUCCESS"), check("Registro da PR", "SUCCESS")]
        casos = [
            (dict(state="MERGED"), "mesclada"),
            (dict(state="CLOSED"), "fechada"),
            (dict(isDraft=True, checks=com), "espera CI"),
            (dict(checks=[]), "espera CI"),
            (dict(checks=[dict(CINZA, name="Freios")]), "espera CI"),
            (dict(checks=[check("Freios", "FAILURE"), check("Registro da PR", "FAILURE")]), "espera conserto do CI"),
            (dict(checks=sem), "espera revisão"),
            (dict(checks=[check("Freios", "SKIPPED")]), "espera revisão"),
            (dict(checks=com), "pronta para merge"),
            (dict(checks=[dict(__typename="StatusContext", context="ci", state="PENDING")]), "espera CI"),
            (dict(checks=[dict(__typename="StatusContext", context="ci", state="SUCCESS"), check("Registro da PR", "SUCCESS")]),
             "pronta para merge"),
        ]
        for campos, esperado in casos:
            checks = campos.pop("checks", None)
            with self.subTest(esperado=esperado, campos=campos):
                self.assertEqual(self.estado(checks=checks, **campos), esperado)


if __name__ == "__main__":
    unittest.main()
