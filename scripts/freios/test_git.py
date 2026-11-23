import unittest

from scripts.freios.apoio_de_teste import RepositorioTemporario
from scripts.freios.git import (
    caminhos_do_commit, commits_entre, entradas_do_indice, montar_contexto, raiz_do_repositorio, ref_existe,
)


class TesteDoGit(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioTemporario()
        self.addCleanup(self.repo.limpar)

    def test_entradas_do_indice_trazem_modo_e_caminho_com_acento(self):
        self.repo.adicionar("pasta/ação.md", "oi\n")
        self.repo.adicionar_link("atalho", "pasta")
        entradas = {e.caminho: e.modo for e in entradas_do_indice(self.repo.raiz)}
        self.assertEqual(entradas, {"pasta/ação.md": "100644", "atalho": "120000"})

    def test_caminhos_do_commit_so_os_preparados(self):
        self.repo.adicionar("a.md", "a\n")
        self.repo.commitar("um")
        self.repo.adicionar("b.md", "b\n")
        self.repo.escrever("c.md", "c\n")
        self.repo.escrever("a.md", "mudou\n")
        self.assertEqual(caminhos_do_commit(self.repo.raiz), {"b.md"})

    def test_raiz_do_repositorio_a_partir_de_uma_subpasta(self):
        self.repo.adicionar("pasta/a.md", "a\n")
        self.assertEqual(raiz_do_repositorio(self.repo.raiz / "pasta").resolve(), self.repo.raiz.resolve())

    def test_ref_existe(self):
        self.repo.adicionar("a.md", "a\n")
        self.repo.commitar("um")
        self.assertTrue(ref_existe(self.repo.raiz, "HEAD"))
        self.assertFalse(ref_existe(self.repo.raiz, "origin/main"))

    def test_commits_entre_traz_autor_committer_assunto_e_mensagem(self):
        self.repo.adicionar("a.md", "a\n")
        self.repo.commitar("base")
        self.repo.git("branch", "base")
        self.repo.adicionar("b.md", "b\n")
        self.repo.commitar("assunto\n\ncorpo da mensagem", email="outra@pessoa.com")
        [commit] = commits_entre(self.repo.raiz, "base", "HEAD")
        self.assertEqual(commit.autor, "outra@pessoa.com")
        self.assertEqual(commit.committer, "dono@example.com")
        self.assertEqual(commit.assunto, "assunto")
        self.assertIn("corpo da mensagem", commit.mensagem)

    def test_no_modo_commit_le_o_conteudo_preparado_e_nao_o_do_disco(self):
        self.repo.adicionar("a.md", "preparado\n")
        self.repo.escrever("a.md", "depois do add\n")
        ctx = montar_contexto(self.repo.raiz, "commit", "origin/main")
        self.assertEqual(ctx.texto(ctx.arquivos["a.md"]), "preparado\n")

    def test_no_modo_tudo_le_o_disco_e_troca_crlf_por_lf(self):
        self.repo.adicionar("a.sh", "echo oi\n")
        self.repo.escrever("a.sh", b"echo oi\r\necho tchau\r\n")
        ctx = montar_contexto(self.repo.raiz, "tudo", "origin/main")
        self.assertEqual(ctx.texto(ctx.arquivos["a.sh"]), "echo oi\necho tchau\n")

    def test_no_modo_tudo_arquivo_novo_ainda_nao_adicionado_entra(self):
        self.repo.adicionar("a.md", "a\n")
        self.repo.escrever("novo.md", "novo\n")
        self.repo.escrever(".gitignore", "ignorado.md\n")
        self.repo.escrever("ignorado.md", "x\n")
        ctx = montar_contexto(self.repo.raiz, "tudo", "origin/main")
        self.assertEqual(sorted(ctx.arquivos), [".gitignore", "a.md", "novo.md"])

    def test_no_modo_commit_os_alvos_sao_so_os_preparados_e_o_universo_e_todo_o_indice(self):
        self.repo.adicionar("a.md", "a\n")
        self.repo.commitar("um")
        self.repo.adicionar("b.md", "b\n")
        ctx = montar_contexto(self.repo.raiz, "commit", "origin/main")
        self.assertEqual([e.caminho for e in ctx.alvos], ["b.md"])
        self.assertEqual(sorted(ctx.arquivos), ["a.md", "b.md"])


if __name__ == "__main__":
    unittest.main()
