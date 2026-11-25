import unittest

from scripts.test_crew import minutes_ago
from scripts.test_crew_vigia import VigiaCase, verde_com_registro


def pr_pronta(numero=12, head="a" * 40, worker="t-job"):
    return dict(kind="pr_ready_merge", worker=worker, repo="Test", number=numero, head=head, title="Titulo %d" % numero)


class RevisaoNaoTemPr(VigiaCase):
    def test_relatorio_de_revisao_nao_acorda(self):
        self.add_worker(type="review")
        self.add_events([dict(kind="report_written", worker="t-job")])
        self.assertEqual(self.rodada(), [])

    def test_relatorio_de_revisao_vai_para_o_resumo(self):
        self.add_worker(type="review")
        self.rodada(1)
        self.add_events([dict(kind="report_written", worker="t-job")])
        self.rodada(31)
        with open(self.state + "/resumo.md", encoding="utf-8") as f:
            self.assertIn("1 relatório de worker com PR ou de revisão", f.read())

    def test_relatorio_de_implementacao_sem_pr_continua_acordando(self):
        self.add_worker(type="implement")
        self.add_events([dict(kind="report_written", worker="t-job")])
        self.assertIn("relatório sem PR: t-job", self.rodada()[0])


class PedidoRespondido(VigiaCase):
    def pedido(self, numero, respondido):
        self.crew.log_decision(dict(id=numero, at=minutes_ago(9), worker="t-job", repo="Test", question="q", recommend="r", status="open", para="chief"))
        if respondido:
            self.crew.log_decision(dict(id=numero, status="answered", answered_at=minutes_ago(1), answer="a"))
        self.add_events([dict(kind="question_for_chief", worker="t-job", id=numero, question="q")])

    def test_pedido_ja_respondido_nao_acorda(self):
        self.add_worker()
        self.pedido("P4", respondido=True)
        self.assertEqual(self.rodada(), [])

    def test_pedido_em_aberto_acorda(self):
        self.add_worker()
        self.pedido("P4", respondido=False)
        self.assertIn("pergunta ao chief: P4", self.rodada()[0])

    def test_decisao_do_dono_respondida_nao_acorda(self):
        self.add_worker()
        self.crew.log_decision(dict(id="D9", at=minutes_ago(9), worker="t-job", repo="Test", question="q", status="open", para="dono"))
        self.crew.log_decision(dict(id="D9", status="answered", answered_at=minutes_ago(1), answer="a"))
        self.add_events([dict(kind="decision_needed", worker="t-job", id="D9", question="q")])
        self.assertEqual(self.rodada(), [])


class WorkerJaFechado(VigiaCase):
    def eventos(self, *extras):
        self.add_worker()
        self.add_events([dict(kind="spawned", worker="t-job")] + list(extras))

    def test_merge_depois_de_o_chief_fechar_o_worker_nao_acorda(self):
        self.eventos(dict(kind="closed", worker="t-job", merged=True), dict(kind="merged", worker="t-job"))
        self.assertEqual(self.rodada(), [])

    def test_merge_com_o_worker_aberto_acorda(self):
        self.eventos(dict(kind="merged", worker="t-job"))
        self.assertIn("branch mesclada: t-job", self.rodada()[0])

    def test_merge_de_worker_reaberto_com_o_mesmo_nome_acorda(self):
        self.eventos(dict(kind="closed", worker="t-job", merged=True), dict(kind="spawned", worker="t-job"), dict(kind="merged", worker="t-job"))
        self.assertIn("branch mesclada: t-job", self.rodada()[0])

    def test_pr_pronta_de_worker_fechado_e_mesclado_nao_acorda(self):
        self.eventos(pr_pronta(), dict(kind="closed", worker="t-job", merged=True))
        self.assertEqual(self.rodada(), [])

    def test_pr_pronta_de_worker_fechado_sem_merge_acorda(self):
        self.eventos(pr_pronta(), dict(kind="closed", worker="t-job", merged=False))
        self.assertIn("PR pronta para merge: Test#12", self.rodada()[0])


class PrJaEncerrada(VigiaCase):
    def test_pr_mesclada_no_github_nao_acorda_como_pronta(self):
        self.add_worker()
        self.prs = [dict(verde_com_registro(), state="MERGED")]
        self.add_events([pr_pronta()])
        self.assertEqual(self.rodada(), [])

    def test_pr_com_head_novo_nao_acorda_pelo_head_velho(self):
        self.add_worker()
        self.prs = [verde_com_registro("b" * 40)]
        self.add_events([pr_pronta()])
        self.assertEqual(self.rodada(), [])

    def test_pr_ainda_aberta_no_mesmo_head_acorda(self):
        self.add_worker()
        self.prs = [verde_com_registro()]
        self.add_events([pr_pronta()])
        self.assertIn("PR pronta para merge: Test#12", self.rodada()[0])


if __name__ == "__main__":
    unittest.main()
