import tempfile
import unittest
from pathlib import Path

from scripts.freios import testes
from scripts.freios.apoio_de_teste import contexto_de_memoria


class TesteDosLimitesAprovados(unittest.TestCase):
    def setUp(self):
        self.limites = contexto_de_memoria({}).limites

    def test_tetos_de_tamanho(self):
        self.assertEqual(self.limites["tamanho"]["bytes_maximos"], 20000)
        self.assertEqual(self.limites["tamanho"]["linhas_maximas"], 1000)
        self.assertEqual(self.limites["funcoes"]["linhas_maximas"], 69)

    def test_orcamento_de_contexto(self):
        orcamento = self.limites["orcamento"]
        self.assertEqual((orcamento["tokens_dos_arquivos"], orcamento["tokens_das_descricoes"]), (800, 1500))

    def test_extensoes_do_sem_comentario(self):
        esperadas = {".py", ".ts", ".mts", ".js", ".mjs", ".cjs", ".sh", ".ps1", ".yml", ".yaml", ".toml"}
        self.assertEqual(set(self.limites["comentarios"]["extensoes"]), esperadas)

    def test_comando_do_eslint_usa_o_prefixo_onde_a_pr_dos_lints_o_instala(self):
        eslint = next(f for f in self.limites["ferramentas"] if f["nome"] == "eslint")
        comando = " ".join(eslint["comando"])
        self.assertIn("--prefix scripts/freios eslint", comando)
        self.assertIn("--config scripts/freios/eslint.config.mjs", comando)

    def test_comando_do_ruff_usa_a_configuracao_do_repo(self):
        ruff = next(f for f in self.limites["ferramentas"] if f["nome"] == "ruff")
        self.assertIn("scripts/freios/ruff.toml", ruff["comando"])


class TesteDoPassoDeTestes(unittest.TestCase):
    def rodar(self, corpo):
        with tempfile.TemporaryDirectory() as pasta:
            (Path(pasta) / "test_a.py").write_text(corpo, encoding="utf-8")
            return testes.verificar(contexto_de_memoria({}, raiz=pasta))

    def test_teste_que_passa_nao_gera_achado(self):
        corpo = "import unittest" + chr(10) + "class T(unittest.TestCase):" + chr(10) + "    def test_a(self):" + chr(10) + "        pass" + chr(10)
        self.assertEqual(self.rodar(corpo), [])

    def test_teste_que_falha_gera_achado_com_a_saida(self):
        corpo = "import unittest" + chr(10) + "class T(unittest.TestCase):" + chr(10) + "    def test_a(self):" + chr(10) + "        self.fail('quebrou')" + chr(10)
        achados = self.rodar(corpo)
        self.assertEqual(len(achados), 1)
        self.assertIn("quebrou", achados[0].detalhe)


if __name__ == "__main__":
    unittest.main()
