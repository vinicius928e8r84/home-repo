import os
import unittest

from scripts.test_crew import git
from scripts.test_crew_vigia import VigiaCase, verde_com_registro


class FechaMesclado(VigiaCase):
    def worker_com_branch(self, mesclada, relatorio):
        caminho = os.path.join(self.home, "worktrees", "Test-job")
        base = git(self.repo, "rev-parse", "origin/main")
        git(self.repo, "worktree", "add", "-q", "-b", "pi/job", caminho, base)
        self.commit(caminho, "mine")
        if mesclada:
            git(caminho, "push", "-q", "origin", "HEAD:main")
        meta = self.add_worker(base_sha=base)
        if relatorio:
            with open(meta["report"], "w", encoding="utf-8") as f:
                f.write("feito")
        return meta

    def test_worker_com_relatorio_e_branch_mesclada_e_fechado(self):
        self.worker_com_branch(mesclada=True, relatorio=True)
        self.rodada()
        self.assertEqual(self.crew.workers(), [])
        self.assertIn("closed", self.kinds())

    def test_o_fechamento_sozinho_vai_para_o_resumo_e_nao_acorda_o_chief(self):
        self.rodada(1)
        self.worker_com_branch(mesclada=True, relatorio=True)
        self.prs = [dict(verde_com_registro(), state="MERGED")]
        self.assertEqual(self.rodada(31), [])
        with open(self.state + "/resumo.md", encoding="utf-8") as f:
            self.assertIn("1 worker fechado", f.read())

    def test_branch_mesclada_sem_relatorio_nao_fecha(self):
        self.worker_com_branch(mesclada=True, relatorio=False)
        self.rodada()
        self.assertEqual(len(self.crew.workers()), 1)
        self.assertNotIn("closed", self.kinds())

    def test_relatorio_com_branch_nao_mesclada_nao_fecha(self):
        self.worker_com_branch(mesclada=False, relatorio=True)
        self.rodada()
        self.assertEqual(len(self.crew.workers()), 1)
        self.assertNotIn("closed", self.kinds())


if __name__ == "__main__":
    unittest.main()
