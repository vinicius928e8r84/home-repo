import json
import os
import unittest

from scripts.test_crew import git
from scripts.test_crew_dono import estado, sessao
from scripts.test_crew_vigia import VigiaCase, verde_com_registro


LINK = "http://pc.exemplo:4387/session/aaaa111122223333"


class FechaMesclado(VigiaCase):
    def worker_com_branch(self, mesclada, relatorio, commit=True):
        caminho = os.path.join(self.home, "worktrees", "Test-job")
        base = git(self.repo, "rev-parse", "origin/main")
        git(self.repo, "worktree", "add", "-q", "-b", "pi/job", caminho, base)
        if commit:
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

    def test_branch_sem_commit_proprio_com_relatorio_nao_fecha(self):
        self.worker_com_branch(mesclada=False, relatorio=True, commit=False)
        self.rodada()
        self.assertEqual(len(self.crew.workers()), 1)

    def test_branch_que_so_trouxe_a_base_nova_nao_fecha(self):
        outra = os.path.join(self.tmp, "outra")
        git(self.repo, "worktree", "add", "-q", "--detach", outra, "origin/main")
        self.worker_com_branch(mesclada=False, relatorio=True, commit=False)
        self.commit(outra, "alheio")
        git(outra, "push", "-q", "origin", "HEAD:main")
        caminho = os.path.join(self.home, "worktrees", "Test-job")
        git(caminho, "fetch", "-q", "origin")
        git(caminho, "merge", "-q", "--ff-only", "origin/main")
        self.rodada()
        self.assertEqual(len(self.crew.workers()), 1)

    def pagina(self, arquivo, **opcoes):
        pasta = os.path.join(self.tmp, "lavish")
        os.makedirs(pasta, exist_ok=True)
        os.environ["LAVISH_AXI_STATE_DIR"] = pasta
        with open(os.path.join(pasta, "state.json"), "w", encoding="utf-8") as f:
            f.write(estado(sessao(arquivo, LINK, **opcoes)))

    def test_pagina_lavish_esperando_o_dono_nao_fecha(self):
        meta = self.worker_com_branch(mesclada=True, relatorio=True)
        self.pagina(meta["worktree"] + "/.lavish/rodada.html")
        self.rodada()
        self.assertEqual(len(self.crew.workers()), 1)
        self.assertNotIn("closed", self.kinds())

    def test_pagina_que_o_dono_respondeu_nao_segura(self):
        meta = self.worker_com_branch(mesclada=True, relatorio=True)
        self.pagina(meta["worktree"] + "/.lavish/rodada.html", chat=["assistant", "user"])
        self.rodada()
        self.assertEqual(self.crew.workers(), [])

    def test_pagina_de_outra_pasta_nao_segura(self):
        meta = self.worker_com_branch(mesclada=True, relatorio=True)
        self.pagina(meta["worktree"] + "-outro/.lavish/rodada.html")
        self.rodada()
        self.assertEqual(self.crew.workers(), [])

    def test_sem_conseguir_ler_as_paginas_nao_fecha(self):
        self.worker_com_branch(mesclada=True, relatorio=True)
        pasta = os.path.join(self.tmp, "lavish")
        os.makedirs(pasta, exist_ok=True)
        os.environ["LAVISH_AXI_STATE_DIR"] = pasta
        with open(os.path.join(pasta, "state.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(dict(sessions=dict(x=dict(status="open")))))
        self.rodada()
        self.assertEqual(len(self.crew.workers()), 1)


if __name__ == "__main__":
    unittest.main()
