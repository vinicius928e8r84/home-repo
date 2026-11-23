import contextlib
import io
import unittest

from scripts.freios import principal
from scripts.freios.apoio_de_teste import RepositorioTemporario

NL = chr(10)
DOIS = NL.join(["x = 1", "# um", "y = 2", "# dois", ""])
UM = NL.join(["x = 1", "# um", "y = 2", ""])
TRES = NL.join(["x = 1", "# um", "y = 2", "# dois", "# tres", ""])
LIMPO = NL.join(["x = 1", "y = 2", ""])


def bytes_de(quantidade):
    return "a" * (quantidade - 1) + NL


def linhas_de(quantidade):
    return NL.join(f"x{n} = {n}" for n in range(quantidade)) + NL


class BaseDosTestes(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioTemporario()
        self.addCleanup(self.repo.limpar)

    def na_main(self, arquivos):
        for caminho, conteudo in arquivos.items():
            self.repo.adicionar(caminho, conteudo)
        self.repo.commitar("main")
        self.repo.git("checkout", "-q", "-b", "feature")

    def rodar(self, modo="--tudo", base="main"):
        saida = io.StringIO()
        argumentos = [modo, "--base", base, "--raiz", str(self.repo.raiz), "--sem-testes"]
        argumentos += ["--so", "tamanho", "--so", "comentarios"]
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
            codigo = principal.main(argumentos)
        return codigo, saida.getvalue()


class TesteDosComentarios(BaseDosTestes):
    def test_encolher_passa_sem_editar_nada(self):
        self.na_main({"a.py": DOIS})
        self.repo.adicionar("a.py", UM)
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 0, saida)
        self.assertIn("✓ comentarios (1 no teto da main)", saida)

    def test_limpar_de_vez_passa(self):
        self.na_main({"a.py": DOIS})
        self.repo.adicionar("a.py", LIMPO)
        self.assertEqual(self.rodar()[0], 0)

    def test_ficar_igual_passa(self):
        self.na_main({"a.py": DOIS})
        self.repo.adicionar("b.py", LIMPO)
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 0, saida)
        self.assertIn("(2 no teto da main)", saida)

    def test_crescer_reprova(self):
        self.na_main({"a.py": DOIS})
        self.repo.adicionar("a.py", TRES)
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertIn("a.py: piorou: 3 contra 2 na main", saida)

    def test_arquivo_novo_com_comentario_reprova(self):
        self.na_main({"a.py": DOIS})
        self.repo.adicionar("novo.py", UM)
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertIn("novo.py:2", saida)

    def test_arquivo_novo_sem_comentario_passa(self):
        self.na_main({"a.py": DOIS})
        self.repo.adicionar("novo.py", LIMPO)
        self.assertEqual(self.rodar()[0], 0)

    def test_arquivo_que_nao_tinha_comentario_na_main_nao_pode_ganhar(self):
        self.na_main({"a.py": LIMPO})
        self.repo.adicionar("a.py", UM)
        self.assertEqual(self.rodar()[0], 1)

    def test_arquivo_movido_com_comentario_conta_como_novo(self):
        self.na_main({"a.py": DOIS})
        self.repo.git("mv", "a.py", "b.py")
        self.assertEqual(self.rodar()[0], 1)

    def test_o_teto_e_o_do_ponto_em_que_a_branch_saiu_da_main(self):
        self.na_main({"a.py": DOIS})
        self.repo.git("checkout", "-q", "main")
        self.repo.adicionar("a.py", UM)
        self.repo.commitar("main encolheu")
        self.repo.git("checkout", "-q", "feature")
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 0, saida)

    def test_arquivo_na_excecao_cresce_sem_barrar(self):
        self.na_main({"scripts/crew.py": DOIS})
        self.repo.adicionar("scripts/crew.py", TRES + "# quatro" + NL)
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 0, saida)

    def test_sem_main_todo_achado_reprova_e_avisa(self):
        self.na_main({"a.py": DOIS})
        codigo, saida = self.rodar(base="origin/main")
        self.assertEqual(codigo, 1)
        self.assertIn("origin/main não existe aqui", saida)


class TesteDoTamanho(BaseDosTestes):
    def test_arquivo_grande_encolhendo_passa(self):
        self.na_main({"grande.md": bytes_de(30000)})
        self.repo.adicionar("grande.md", bytes_de(25000))
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 0, saida)
        self.assertIn("✓ tamanho (1 no teto da main)", saida)

    def test_arquivo_grande_crescendo_reprova(self):
        self.na_main({"grande.md": bytes_de(30000)})
        self.repo.adicionar("grande.md", bytes_de(30001))
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertIn("piorou: 30001 contra 30000", saida)

    def test_arquivo_novo_gordo_reprova(self):
        self.na_main({"grande.md": bytes_de(30000)})
        self.repo.adicionar("novo.md", bytes_de(20001))
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertIn("novo.md: 20001 bytes", saida)

    def test_arquivo_novo_dentro_do_teto_passa(self):
        self.na_main({"grande.md": bytes_de(30000)})
        self.repo.adicionar("novo.md", bytes_de(20000))
        self.assertEqual(self.rodar()[0], 0)

    def test_teto_de_linhas_tem_a_propria_medida(self):
        self.na_main({"grande.py": linhas_de(1200)})
        self.repo.adicionar("grande.py", linhas_de(1100))
        self.assertEqual(self.rodar()[0], 0)
        self.repo.adicionar("grande.py", linhas_de(1201))
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertIn("piorou: 1201 contra 1200", saida)

    def test_encolher_em_bytes_nao_libera_crescer_em_linhas(self):
        self.na_main({"grande.py": linhas_de(1200)})
        mais_linhas_menos_bytes = NL.join("x" for _ in range(1300)) + NL
        self.repo.adicionar("grande.py", mais_linhas_menos_bytes)
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertIn("1300 contra 1200", saida)

    def test_arquivo_na_excecao_cresce_sem_barrar(self):
        self.na_main({"scripts/crew.py": linhas_de(1100)})
        self.repo.adicionar("scripts/crew.py", linhas_de(1500))
        self.assertEqual(self.rodar()[0], 0)


class TesteDoPreCommit(BaseDosTestes):
    def test_commit_que_encolhe_passa(self):
        self.na_main({"a.py": DOIS})
        self.repo.adicionar("a.py", UM)
        self.assertEqual(self.rodar("--commit")[0], 0)

    def test_commit_que_cresce_e_barrado(self):
        self.na_main({"a.py": DOIS})
        self.repo.adicionar("a.py", TRES)
        self.assertEqual(self.rodar("--commit")[0], 1)

    def test_commit_com_arquivo_novo_gordo_e_barrado(self):
        self.na_main({"a.py": DOIS})
        self.repo.adicionar("novo.md", bytes_de(20001))
        self.assertEqual(self.rodar("--commit")[0], 1)

    def test_commit_so_cobra_o_que_esta_nele(self):
        self.na_main({"a.py": DOIS, "b.py": DOIS})
        self.repo.adicionar("b.py", UM)
        self.assertEqual(self.rodar("--commit")[0], 0)


if __name__ == "__main__":
    unittest.main()
