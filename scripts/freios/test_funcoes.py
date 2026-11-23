import unittest

from scripts.freios import funcoes
from scripts.freios.apoio_de_teste import contexto_de_memoria


def funcao(nome, linhas):
    corpo = "".join("    x = 1\n" for _ in range(linhas - 1))
    return f"def {nome}():\n{corpo}"


class TesteDeFuncoes(unittest.TestCase):
    def verificar(self, arquivos, excecoes=None):
        return funcoes.verificar(contexto_de_memoria(arquivos, excecoes=excecoes))

    def test_funcao_com_69_linhas_passa_e_com_70_falha(self):
        self.assertEqual(self.verificar({"a.py": funcao("f", 69)}), [])
        achados = self.verificar({"a.py": funcao("f", 70)})
        self.assertEqual([(a.arquivo, a.linha) for a in achados], [("a.py", 1)])
        self.assertIn("f: 70 linhas", achados[0].detalhe)

    def test_conta_da_linha_do_def_ate_a_ultima_linha(self):
        texto = "x = 1\n\n\n" + funcao("g", 70)
        achados = self.verificar({"a.py": texto})
        self.assertEqual([a.linha for a in achados], [4])

    def test_metodo_e_funcao_assincrona_contam(self):
        texto = "class C:\n    def m(self):\n" + "        x = 1\n" * 69 + "\nasync def h():\n" + "    x = 1\n" * 70
        achados = self.verificar({"a.py": texto})
        self.assertEqual(sorted(a.detalhe.split(":")[0] for a in achados), ["h", "m"])

    def test_funcao_interna_conta_separado_da_externa(self):
        texto = "def f():\n    def g():\n" + "        x = 1\n" * 69 + "    return g\n"
        achados = self.verificar({"a.py": texto})
        self.assertEqual(sorted(a.detalhe.split(":")[0] for a in achados), ["f", "g"])

    def test_varias_funcoes_curtas_no_mesmo_arquivo_passam(self):
        texto = funcao("a", 60) + "\n\n" + funcao("b", 60)
        self.assertEqual(self.verificar({"a.py": texto}), [])

    def test_so_python_e_arquivo_com_erro_de_sintaxe_fica_fora(self):
        arquivos = {"a.js": "function f() {\n" + "x();\n" * 100 + "}\n", "b.py": "def f(:\n"}
        self.assertEqual(self.verificar(arquivos), [])

    def test_excecao_com_motivo_libera_o_arquivo(self):
        excecoes = {"funcoes": [{"glob": "scripts/crew.py", "motivo": "outra tarefa o divide"}]}
        arquivos = {"scripts/crew.py": funcao("f", 100), "scripts/outro.py": funcao("g", 100)}
        achados = self.verificar(arquivos, excecoes)
        self.assertEqual([a.arquivo for a in achados], ["scripts/outro.py"])

    def test_a_excecao_do_crew_esta_na_configuracao_do_repo(self):
        ctx = contexto_de_memoria({})
        self.assertTrue(ctx.excecao("funcoes", "scripts/crew.py"))
        self.assertFalse(ctx.excecao("funcoes", "scripts/freios/freios.py"))


if __name__ == "__main__":
    unittest.main()
