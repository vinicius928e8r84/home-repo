import json
import re
import unittest

from scripts.freios.apoio_de_teste import contexto_de_memoria
from scripts.freios.contexto import PASTA

CATEGORIAS = {
    "tamanho", "funcoes", "comentarios", "sintaxe", "segredo", "binario", "depuracao", "ruff", "eslint",
}


def excecoes():
    return json.loads((PASTA / "excecoes.json").read_text(encoding="utf-8"))


def globs(categoria):
    return [item["glob"] for item in excecoes()[categoria]]


def exclusoes_do_ruff():
    texto = (PASTA / "ruff.toml").read_text(encoding="utf-8")
    bloco = re.search(r"^extend-exclude\s*=\s*\[(.*?)\]", texto, re.MULTILINE | re.DOTALL)
    return re.findall(r'"([^"]+)"', bloco.group(1)) if bloco else []


class TesteDoArquivoUnicoDeExcecoes(unittest.TestCase):
    def test_so_existe_este_arquivo_de_excecoes(self):
        nomes = {p.name for p in PASTA.glob("*.json")}
        self.assertIn("excecoes.json", nomes)
        self.assertNotIn("ignorar.json", nomes)

    def test_o_extend_exclude_do_ruff_e_o_que_o_arquivo_diz(self):
        self.assertEqual(sorted(exclusoes_do_ruff()), sorted(globs("ruff")))

    def test_o_eslint_le_as_exclusoes_do_mesmo_arquivo(self):
        config = (PASTA / "eslint.config.mjs").read_text(encoding="utf-8")
        self.assertIn("excecoes.json", config)
        self.assertNotIn("ignorar.json", config)
        self.assertIn(".eslint.map(", config)

    def test_toda_excecao_tem_motivo_e_categoria_conhecida(self):
        dados = excecoes()
        self.assertLessEqual(set(dados), CATEGORIAS)
        for categoria, itens in dados.items():
            for item in itens:
                with self.subTest(categoria=categoria, glob=item["glob"]):
                    self.assertTrue(item["motivo"].strip())

    def test_crew_py_e_a_excecao_do_dono_em_tamanho_comentarios_funcoes_e_ruff(self):
        for categoria in ("tamanho", "comentarios", "funcoes", "ruff"):
            self.assertIn("scripts/crew.py", globs(categoria))

    def test_o_contexto_usa_o_mesmo_arquivo(self):
        self.assertTrue(contexto_de_memoria({}).excecao("ruff", "scripts/crew.py"))


if __name__ == "__main__":
    unittest.main()
