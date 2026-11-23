import unittest

from scripts.freios import tamanho
from scripts.freios.apoio_de_teste import contexto_de_memoria


class TesteDeTamanho(unittest.TestCase):
    def test_conta_a_ultima_linha_sem_quebra(self):
        self.assertEqual(tamanho.contar_linhas(b"a\nb"), 2)
        self.assertEqual(tamanho.contar_linhas(b"a\nb\n"), 2)
        self.assertEqual(tamanho.contar_linhas(b""), 0)

    def test_arquivo_no_teto_de_bytes_passa(self):
        ctx = contexto_de_memoria({"nota.md": "a" * 20000})
        self.assertEqual(tamanho.verificar(ctx), [])

    def test_arquivo_acima_do_teto_de_bytes_falha(self):
        ctx = contexto_de_memoria({"nota.md": "a" * 20001})
        achados = tamanho.verificar(ctx)
        self.assertEqual([a.arquivo for a in achados], ["nota.md"])
        self.assertIn("20001 bytes", achados[0].detalhe)

    def test_codigo_com_mil_linhas_passa_e_com_mil_e_uma_falha(self):
        ctx = contexto_de_memoria({"ok.py": "x\n" * 1000, "grande.py": "x\n" * 1001})
        achados = tamanho.verificar(ctx)
        self.assertEqual([a.arquivo for a in achados], ["grande.py"])
        self.assertIn("1001 linhas", achados[0].detalhe)

    def test_markdown_e_json_nao_tem_teto_de_linhas(self):
        ctx = contexto_de_memoria({"a.md": "x\n" * 1500, "b.json": "1\n" * 1500})
        self.assertEqual(tamanho.verificar(ctx), [])

    def test_arquivo_binario_fica_fora(self):
        ctx = contexto_de_memoria({"imagem.png": b"\0" * 30000})
        self.assertEqual(tamanho.verificar(ctx), [])

    def test_codigo_grande_em_bytes_e_em_linhas_gera_dois_achados(self):
        ctx = contexto_de_memoria({"grande.py": "x" * 19 + "\n" + "yyyyyyyyyyyyyyyyyyyy\n" * 1000})
        self.assertEqual(len(tamanho.verificar(ctx)), 2)

    def test_excecao_com_motivo_libera_o_arquivo(self):
        excecoes = {"tamanho": [{"glob": "package-lock.json", "motivo": "trava"}]}
        ctx = contexto_de_memoria({"ferramentas/package-lock.json": "a" * 50000}, excecoes=excecoes)
        self.assertEqual(tamanho.verificar(ctx), [])

    def test_excecao_por_pasta(self):
        excecoes = {"tamanho": [{"glob": "dados/", "motivo": "gerado"}]}
        ctx = contexto_de_memoria({"dados/a.json": "a" * 50000, "b.md": "a" * 50000}, excecoes=excecoes)
        self.assertEqual([a.arquivo for a in tamanho.verificar(ctx)], ["b.md"])


if __name__ == "__main__":
    unittest.main()
