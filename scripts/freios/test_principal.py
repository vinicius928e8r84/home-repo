import contextlib
import io
import unittest

from scripts.freios import principal
from scripts.freios.apoio_de_teste import RepositorioTemporario


class TesteDoPrincipal(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioTemporario()
        self.addCleanup(self.repo.limpar)

    def rodar(self, *argumentos):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = principal.main([*argumentos, "--raiz", str(self.repo.raiz), "--sem-testes"])
        return codigo, saida.getvalue()

    def test_repositorio_limpo_sai_com_zero(self):
        self.repo.adicionar("a.md", "oi\n")
        codigo, saida = self.rodar("--commit")
        self.assertEqual(codigo, 0)
        self.assertIn("tudo certo", saida)

    def test_arquivo_grande_no_commit_sai_com_um_e_mostra_o_conserto(self):
        self.repo.adicionar("a.md", "x" * 20001)
        codigo, saida = self.rodar("--commit")
        self.assertEqual(codigo, 1)
        self.assertIn("a.md: 20001 bytes", saida)
        self.assertIn("Conserto:", saida)

    def test_no_commit_so_confere_o_que_esta_preparado(self):
        self.repo.adicionar("a.md", "oi\n")
        self.repo.commitar("um")
        self.repo.escrever("grande.md", "x" * 20001)
        self.assertEqual(self.rodar("--commit")[0], 0)

    def test_tudo_confere_o_indice_e_ignora_arquivo_nao_rastreado(self):
        self.repo.adicionar("a.md", "oi" + chr(10))
        self.repo.commitar("um")
        self.repo.escrever("grande.md", "x" * 20001)
        self.assertEqual(self.rodar("--tudo")[0], 0)
        self.repo.adicionar("grande.md", "x" * 20001)
        codigo, saida = self.rodar("--tudo")
        self.assertEqual(codigo, 1)
        self.assertIn("grande.md", saida)

    def test_commit_roda_so_tamanho_e_comentarios(self):
        _, saida = self.rodar("--commit")
        self.assertEqual(
            [linha[2:] for linha in saida.splitlines() if linha.startswith(("✓", "✗"))], ["tamanho", "comentarios"]
        )

    def test_tudo_roda_todas_as_verificacoes(self):
        self.repo.adicionar("a.md", "oi" + chr(10))
        _, saida = self.rodar("--tudo")
        rodadas = [linha[2:].split(":")[0].split(" ")[0] for linha in saida.splitlines() if linha.startswith(("✓", "✗"))]
        esperadas = [v.ID for v in principal.POR_ARQUIVO + principal.DO_REPOSITORIO if v is not principal.testes]
        self.assertEqual(rodadas, esperadas)

    def test_so_roda_a_verificacao_pedida(self):
        self.repo.adicionar("a.md", "x" * 20001)
        _, saida = self.rodar("--commit", "--so", "binario")
        self.assertIn("✓ binario", saida)
        self.assertNotIn("tamanho", saida)

    def test_verificacao_desconhecida_sai_com_dois(self):
        self.repo.adicionar("a.md", "oi\n")
        self.assertEqual(self.rodar("--commit", "--so", "nao-existe")[0], 2)

    def test_lista_corta_os_achados_sem_completo(self):
        for numero in range(20):
            self.repo.adicionar(f"g{numero}.md", "x" * 20001)
        _, saida = self.rodar("--commit")
        self.assertIn("e mais 5", saida)
        _, completa = self.rodar("--commit", "--completo")
        self.assertNotIn("e mais", completa)

    def test_sem_modo_e_erro(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            principal.ler_argumentos([])

    def test_descrever_acha_com_arquivo_e_linha(self):
        from scripts.freios.contexto import Achado

        self.assertEqual(principal.descrever(Achado("x", "a.py", "ruim", 3)), "a.py:3: ruim")
        self.assertEqual(principal.descrever(Achado("x", "", "ruim")), "ruim")


if __name__ == "__main__":
    unittest.main()
