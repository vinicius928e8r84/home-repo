import contextlib
import io
import unittest

from scripts.freios import depuracao, principal
from scripts.freios.apoio_de_teste import RepositorioTemporario, contexto_de_memoria

NL = chr(10)
BIBLIOTECA = "def f():" + NL + "    print('x')" + NL
SCRIPT = "def f():" + NL + "    print('x')" + NL + NL + "if __name__ == '__main__':" + NL + "    f()" + NL
SCRIPT_INVERTIDO = "print('x')" + NL + "if \"__main__\" == __name__:" + NL + "    pass" + NL


class TesteDaDepuracao(unittest.TestCase):
    def verificar(self, arquivos, excecoes=None):
        return depuracao.verificar(contexto_de_memoria(arquivos, excecoes=excecoes))

    def test_print_em_arquivo_que_nao_e_script_falha_com_arquivo_e_linha(self):
        achados = self.verificar({"lib.py": "x = 1" + NL + BIBLIOTECA})
        self.assertEqual([(a.arquivo, a.linha) for a in achados], [("lib.py", 3)])

    def test_cada_print_e_um_achado(self):
        achados = self.verificar({"lib.py": "print(1)" + NL + "print(2)" + NL})
        self.assertEqual([a.linha for a in achados], [1, 2])

    def test_script_com_guarda_de_execucao_pode_imprimir(self):
        self.assertEqual(self.verificar({"cli.py": SCRIPT}), [])

    def test_a_guarda_vale_escrita_ao_contrario_e_com_aspas_duplas(self):
        self.assertEqual(self.verificar({"cli.py": SCRIPT_INVERTIDO}), [])

    def test_guarda_dentro_de_funcao_nao_vale(self):
        corpo = "def f():" + NL + "    if __name__ == '__main__':" + NL + "        pass" + NL + "    print(1)" + NL
        self.assertEqual(len(self.verificar({"lib.py": corpo})), 1)

    def test_print_em_texto_ou_comentario_nao_conta(self):
        corpo = "x = 'print(1)'" + NL + "y = [1]  # print(2)" + NL
        self.assertEqual(self.verificar({"lib.py": corpo}), [])

    def test_print_como_metodo_nao_conta(self):
        self.assertEqual(self.verificar({"lib.py": "impressora.print(1)" + NL}), [])

    def test_so_olha_arquivos_python(self):
        self.assertEqual(self.verificar({"a.md": "print(1)" + NL, "a.js": "print(1)" + NL}), [])

    def test_arquivo_com_erro_de_sintaxe_fica_para_o_freio_de_sintaxe(self):
        self.assertEqual(self.verificar({"lib.py": "print(" + NL}), [])

    def test_excecao_com_motivo_libera_o_arquivo(self):
        excecoes = {"depuracao": [{"glob": "lib.py", "motivo": "o trabalho dele é imprimir"}]}
        self.assertEqual(self.verificar({"lib.py": BIBLIOTECA}, excecoes), [])

    def test_o_conserto_aponta_a_saida_certa_e_a_excecao(self):
        self.assertIn("excecoes.json", depuracao.CONSERTO)
        self.assertIn("__main__", depuracao.CONSERTO)


class TesteDaDepuracaoNaCatraca(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioTemporario()
        self.addCleanup(self.repo.limpar)

    def rodar(self):
        saida = io.StringIO()
        argumentos = ["--tudo", "--base", "main", "--raiz", str(self.repo.raiz), "--sem-testes", "--so", "depuracao"]
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
            codigo = principal.main(argumentos)
        return codigo, saida.getvalue()

    def na_main(self, arquivos):
        for caminho, conteudo in arquivos.items():
            self.repo.adicionar(caminho, conteudo)
        self.repo.commitar("main")
        self.repo.git("checkout", "-q", "-b", "feature")

    def test_print_que_ja_estava_na_main_passa(self):
        self.na_main({"lib.py": BIBLIOTECA})
        self.repo.adicionar("outro.md", "oi" + NL)
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 0, saida)
        self.assertIn("✓ depuracao (1 no teto da main)", saida)

    def test_print_novo_em_arquivo_que_ja_tinha_reprova(self):
        self.na_main({"lib.py": BIBLIOTECA})
        self.repo.adicionar("lib.py", BIBLIOTECA + "print(2)" + NL)
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertIn("lib.py: piorou: 2 contra 1 na main", saida)

    def test_print_em_arquivo_novo_reprova_e_mostra_o_conserto(self):
        self.na_main({"lib.py": "x = 1" + NL})
        self.repo.adicionar("novo.py", BIBLIOTECA)
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertIn("novo.py:2", saida)
        self.assertIn("Conserto:", saida)

    def test_tirar_o_print_passa(self):
        self.na_main({"lib.py": BIBLIOTECA})
        self.repo.adicionar("lib.py", "x = 1" + NL)
        self.assertEqual(self.rodar()[0], 0)


if __name__ == "__main__":
    unittest.main()
