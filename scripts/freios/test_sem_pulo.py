import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from scripts.freios.sem_pulo import main, pulos

ESLINT = "aviso: eslint: dependências não instaladas, pulado (rode npm ci --prefix scripts/freios)"
RUFF = "aviso: ruff: ainda sem configuração no repositório, pulado"
BASH = "aviso: sintaxe: bash não encontrado, os .sh não foram conferidos"
INFORMATIVO = "aviso: origin/main não existe aqui: sem teto da main, todo achado reprova"


def rodar(*textos):
    with tempfile.TemporaryDirectory() as pasta:
        caminhos = []
        for indice, texto in enumerate(textos):
            caminho = Path(pasta) / f"saida{indice}.txt"
            caminho.write_text(texto, encoding="utf-8")
            caminhos.append(str(caminho))
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = main(caminhos)
    return codigo, saida.getvalue()


class Pulos(unittest.TestCase):
    def test_reconhece_eslint_ruff_e_bash_pulados(self):
        self.assertEqual(pulos("\n".join([ESLINT, RUFF, BASH])), [ESLINT, RUFF, BASH])

    def test_aviso_informativo_e_linha_comum_nao_contam(self):
        self.assertEqual(pulos(f"✓ tamanho\n{INFORMATIVO}\ntudo certo\n"), [])

    def test_a_palavra_pulado_fora_de_um_aviso_nao_conta(self):
        self.assertEqual(pulos("    eslint.config.mjs: arquivo pulado do lint\n"), [])


class Principal(unittest.TestCase):
    def test_saida_sem_pulo_passa(self):
        codigo, saida = rodar("✓ externos\n\ntudo certo\n")
        self.assertEqual(codigo, 0)
        self.assertIn("nenhuma ferramenta foi pulada", saida)

    def test_eslint_pulado_reprova_e_diz_o_conserto(self):
        codigo, saida = rodar(f"✓ externos\naviso: x\n{ESLINT}\n\ntudo certo\n")
        self.assertEqual(codigo, 1)
        self.assertIn("os freios pularam uma verificação", saida)
        self.assertIn("eslint: dependências não instaladas", saida)
        self.assertIn("npm ci --prefix scripts/freios", saida)

    def test_junta_os_achados_de_todos_os_arquivos(self):
        codigo, saida = rodar("tudo certo\n", RUFF + "\n")
        self.assertEqual(codigo, 1)
        self.assertIn("saida1.txt: " + RUFF, saida)

    def test_arquivo_que_nao_existe_sai_com_2(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = main(["/nao/existe/saida.txt"])
        self.assertEqual(codigo, 2)
        self.assertIn("não consegui ler", saida.getvalue())

    def test_sem_argumento_sai_com_2(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            self.assertEqual(main([]), 2)
        self.assertIn("uso:", saida.getvalue())


if __name__ == "__main__":
    unittest.main()
