import os
import unittest
from unittest import mock

from scripts.freios import autoria
from scripts.freios.apoio_de_teste import RepositorioTemporario
from scripts.freios.git import montar_contexto

DONO = "dono@example.com"
LIMITES_DE_TESTE = {
    "autoria": {"emails_do_dono": ["Dono@Example.com"], "emails_de_commit_aceitos": ["noreply@github.com"]},
}


class TesteDeAutoria(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioTemporario()
        self.addCleanup(self.repo.limpar)
        self.repo.adicionar("a.txt", "base\n")
        self.repo.commitar("base", email="outra@pessoa.com")
        self.repo.git("branch", "base")
        self.contador = 0

    def commitar(self, mensagem, email=DONO, extra=()):
        self.contador += 1
        self.repo.adicionar(f"f{self.contador}.txt", "x\n")
        return self.repo.commitar(mensagem, email=email, extra=extra)

    def verificar(self, base="base"):
        ctx = montar_contexto(self.repo.raiz, "tudo", base)
        ctx.limites = {**ctx.limites, **LIMITES_DE_TESTE}
        return autoria.verificar(ctx), ctx

    def test_commits_do_dono_sem_coautor_passam(self):
        self.commitar("um")
        self.commitar("dois")
        self.assertEqual(self.verificar()[0], [])

    def test_o_commit_da_base_nao_e_conferido(self):
        self.assertEqual(self.verificar()[0], [])

    def test_email_do_dono_ignora_maiusculas(self):
        self.commitar("um", email="DONO@example.com")
        self.assertEqual(self.verificar()[0], [])

    def test_autor_de_fora_falha(self):
        sha = self.commitar("de fora", email="intruso@example.com")
        achados, _ = self.verificar()
        self.assertEqual(len(achados), 1)
        self.assertIn(sha[:7], achados[0].detalhe)
        self.assertIn("autor intruso@example.com", achados[0].detalhe)

    def test_coautor_falha_mesmo_que_seja_o_dono(self):
        self.commitar("um\n\nCo-authored-by: Dono <dono@example.com>")
        achados, _ = self.verificar()
        self.assertEqual(len(achados), 1)
        self.assertIn("Co-authored-by", achados[0].detalhe)

    def test_coautor_em_minusculas_tambem_falha(self):
        self.commitar("um\n\nco-authored-by: Alguem <a@b.com>")
        self.assertEqual(len(self.verificar()[0]), 1)

    def test_committer_diferente_do_dono_falha_e_o_do_github_passa(self):
        self.repo.git("config", "user.email", "outro@example.com")
        self.commitar("committer de fora")
        self.assertEqual(len(self.verificar()[0]), 1)
        self.repo.git("reset", "-q", "--hard", "base")
        self.repo.git("config", "user.email", "noreply@github.com")
        self.commitar("pelo github")
        self.assertEqual(self.verificar()[0], [])

    def test_so_aponta_os_commits_ruins(self):
        self.commitar("bom")
        self.commitar("ruim", email="intruso@example.com")
        self.commitar("bom de novo")
        achados, _ = self.verificar()
        self.assertEqual(len(achados), 1)
        self.assertIn("ruim", achados[0].detalhe)

    def test_sem_a_base_avisa_e_nao_falha(self):
        self.commitar("um", email="intruso@example.com")
        achados, ctx = self.verificar(base="origin/main")
        self.assertEqual(achados, [])
        self.assertEqual(len(ctx.avisos), 1)

    def test_no_ci_sem_a_base_falha(self):
        self.commitar("um")
        with mock.patch.dict(os.environ, {"CI": "true"}):
            achados, _ = self.verificar(base="origin/main")
        self.assertEqual(len(achados), 1)
        self.assertIn("fetch-depth", achados[0].detalhe)


if __name__ == "__main__":
    unittest.main()
