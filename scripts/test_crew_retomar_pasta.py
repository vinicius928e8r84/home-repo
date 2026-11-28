import json
import os
import unittest

from scripts.crew_sessao import pasta_da_sessao
from scripts.test_crew import CrewCase

DAS_SESSOES = "/router/sessions"
DO_PROCESSO = "/processo/sessions"


class PastaDasConversas(CrewCase):

    def setUp(self):
        super().setUp()
        self.retomada = self.crew.module("crew_retomada")
        self.meta = self.add_worker()
        self.ambiente_do_pi = {}
        self.retomada.ambiente_do_pi = lambda pid: self.ambiente_do_pi
        os.environ["PI_CODING_AGENT_DIR"] = "/agent"
        self.addCleanup(os.environ.pop, "PI_CODING_AGENT_DIR", None)
        os.environ.pop("PI_CODING_AGENT_SESSION_DIR", None)
        self.addCleanup(os.environ.pop, "PI_CODING_AGENT_SESSION_DIR", None)

    def estado(self, **campos):
        with open(self.meta["state_file"], "w", encoding="utf-8") as f:
            json.dump(dict(state="idle", turns=1, pid=4242, **campos), f)

    def pasta(self):
        return self.retomada.pasta_das_conversas(self.meta)

    def test_sem_nada_usa_a_pasta_do_pi_por_diretorio(self):
        self.estado()
        self.assertEqual(self.pasta(), os.path.join("/agent", "sessions", pasta_da_sessao(self.meta["worktree"])))

    def test_a_variavel_do_processo_manda_sobre_a_pasta_padrao(self):
        os.environ["PI_CODING_AGENT_SESSION_DIR"] = DO_PROCESSO
        self.estado()
        self.assertEqual(self.pasta(), DO_PROCESSO)

    def test_o_ambiente_do_pi_vivo_manda_sobre_a_variavel_do_processo(self):
        os.environ["PI_CODING_AGENT_SESSION_DIR"] = DO_PROCESSO
        self.ambiente_do_pi = {"PI_CODING_AGENT_SESSION_DIR": DAS_SESSOES}
        self.estado()
        self.assertEqual(self.pasta(), DAS_SESSOES)

    def test_o_que_o_pi_gravou_vale_depois_que_ele_morre(self):
        os.environ["PI_CODING_AGENT_SESSION_DIR"] = DO_PROCESSO
        self.estado(sessoes=DAS_SESSOES)
        self.assertEqual(self.pasta(), DAS_SESSOES)

    def test_sem_arquivo_de_estado_nao_quebra(self):
        os.remove(self.meta["state_file"])
        self.assertEqual(self.pasta(), os.path.join("/agent", "sessions", pasta_da_sessao(self.meta["worktree"])))

    def test_a_pasta_do_pi_segue_o_ambiente_dele_e_depois_a_variavel_do_processo(self):
        self.estado()
        self.assertEqual(self.retomada.pi_dir(self.meta), "/agent")
        self.ambiente_do_pi = {"PI_CODING_AGENT_DIR": "/do-pi"}
        self.assertEqual(self.retomada.pi_dir(self.meta), "/do-pi")
        self.estado(agente="/gravada")
        self.assertEqual(self.retomada.pi_dir(self.meta), "/gravada")
        self.ambiente_do_pi = {}
        self.assertEqual(self.retomada.pi_dir(), "/agent")

    def test_so_as_conversas_do_worker_e_das_copias_dele(self):
        pasta = os.path.join(self.tmp, "sessoes")
        os.makedirs(pasta)
        nomes = ["D_t-job.jsonl", "D_t-job-2.jsonl", "D_t-job-10.jsonl", "D_t-jobs.jsonl", "D_outro-t-job.jsonl", "D_t-job-x.jsonl"]
        for nome in nomes:
            open(os.path.join(pasta, nome), "w").close()
        self.estado(sessoes=pasta)
        achadas = sorted(os.path.basename(c) for c in self.retomada.conversas_do_worker(self.meta))
        self.assertEqual(achadas, ["D_t-job-10.jsonl", "D_t-job-2.jsonl", "D_t-job.jsonl"])

    def test_le_o_ambiente_de_um_processo(self):
        leitor = self.crew.module("crew_retomada")
        self.assertEqual(leitor.ler_ambiente("A=1\0PI_CODING_AGENT_SESSION_DIR=/x=y\0\0"), {"A": "1", "PI_CODING_AGENT_SESSION_DIR": "/x=y"})


if __name__ == "__main__":
    unittest.main()
