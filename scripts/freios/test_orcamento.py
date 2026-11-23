import unittest

from scripts.freios import orcamento
from scripts.freios.apoio_de_teste import contexto_de_memoria


def skill(descricao):
    return f"---\nname: x\ndescription: {descricao}\n---\n\nCorpo.\n"


LIMITES = {
    "orcamento": {
        "arquivos": ["AGENTS.md", "CLAUDE.md", "wiki/index.md"],
        "tokens_dos_arquivos": 100,
        "tokens_das_descricoes": 50,
    }
}


class TesteDoOrcamento(unittest.TestCase):
    def verificar(self, arquivos):
        return orcamento.verificar(contexto_de_memoria(arquivos, limites=LIMITES))

    def test_tokens_arredonda_para_cima(self):
        self.assertEqual([orcamento.tokens(b"a" * n) for n in (0, 1, 4, 5)], [0, 1, 1, 2])

    def test_arquivos_no_teto_passam(self):
        arquivos = {"AGENTS.md": "a" * 200, "CLAUDE.md": "a" * 100, "wiki/index.md": "a" * 100}
        self.assertEqual(self.verificar(arquivos), [])

    def test_arquivos_acima_do_teto_falham_somados(self):
        arquivos = {"AGENTS.md": "a" * 200, "CLAUDE.md": "a" * 100, "wiki/index.md": "a" * 101}
        achados = self.verificar(arquivos)
        self.assertEqual(len(achados), 1)
        self.assertIn("~101 tokens", achados[0].detalhe)

    def test_arquivo_ausente_conta_zero(self):
        self.assertEqual(self.verificar({"AGENTS.md": "a" * 40}), [])

    def test_descricoes_somadas_no_teto_passam(self):
        arquivos = {
            ".agents/skills/a/SKILL.md": skill("a" * 100),
            ".agents/skills/b/SKILL.md": skill("b" * 100),
        }
        self.assertEqual(self.verificar(arquivos), [])

    def test_descricoes_somadas_acima_do_teto_falham(self):
        arquivos = {
            ".agents/skills/a/SKILL.md": skill("a" * 100),
            ".agents/skills/b/SKILL.md": skill("b" * 104),
        }
        achados = self.verificar(arquivos)
        self.assertEqual(len(achados), 1)
        self.assertIn("~51 tokens", achados[0].detalhe)

    def test_so_a_descricao_conta_e_nao_o_corpo(self):
        arquivos = {".agents/skills/a/SKILL.md": skill("curta") + "corpo " * 1000}
        self.assertEqual(self.verificar(arquivos), [])

    def test_descricao_dobrada_e_entre_aspas(self):
        dobrada = "---\nname: a\ndescription: >-\n  primeira parte\n  segunda parte\nother: x\n---\n"
        self.assertEqual(orcamento.descricao(dobrada), "primeira parte segunda parte")
        self.assertEqual(orcamento.descricao(skill('"entre aspas"')), "entre aspas")
        self.assertEqual(orcamento.descricao("sem frontmatter"), "")


if __name__ == "__main__":
    unittest.main()
