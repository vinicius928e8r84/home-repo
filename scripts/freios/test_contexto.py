import unittest

from scripts.freios.apoio_de_teste import contexto_de_memoria
from scripts.freios.contexto import casa, parece_binario


class TesteDeGlobs(unittest.TestCase):
    def test_nome_sem_barra_casa_em_qualquer_pasta(self):
        self.assertTrue(casa("package-lock.json", "package-lock.json"))
        self.assertTrue(casa("package-lock.json", "a/b/package-lock.json"))
        self.assertFalse(casa("package-lock.json", "a/package-lock.json.bak"))

    def test_asterisco_nao_atravessa_pastas(self):
        self.assertTrue(casa("scripts/*.py", "scripts/a.py"))
        self.assertFalse(casa("scripts/*.py", "scripts/sub/a.py"))

    def test_dois_asteriscos_atravessam_pastas(self):
        self.assertTrue(casa("scripts/**/*.py", "scripts/a.py"))
        self.assertTrue(casa("scripts/**/*.py", "scripts/sub/fundo/a.py"))
        self.assertFalse(casa("scripts/**/*.py", "outro/a.py"))

    def test_pasta_sem_barra_no_meio_casa_em_qualquer_nivel(self):
        self.assertTrue(casa("node_modules/", "node_modules/x.js"))
        self.assertTrue(casa("node_modules/", "a/node_modules/x.js"))
        self.assertFalse(casa("node_modules/", "a/meu_node_modules/x.js"))

    def test_pasta_com_barra_no_meio_so_casa_a_partir_da_raiz(self):
        self.assertTrue(casa("dados/brutos/", "dados/brutos/a.csv"))
        self.assertFalse(casa("dados/brutos/", "x/dados/brutos/a.csv"))

    def test_ponto_e_interrogacao_sao_literais_ou_um_caractere(self):
        self.assertTrue(casa("a?.md", "ab.md"))
        self.assertFalse(casa("a.md", "ab.md"))

    def test_extensao_composta(self):
        self.assertTrue(casa("*.bak-*", "x.bak-1"))
        self.assertTrue(casa(".env.*", ".env.local"))


class TesteDoContexto(unittest.TestCase):
    def test_binario_e_texto(self):
        self.assertTrue(parece_binario(b"ab\0cd"))
        self.assertFalse(parece_binario("açúcar".encode("utf-8")))

    def test_texto_devolve_none_para_binario(self):
        ctx = contexto_de_memoria({"a.bin": b"\0\1", "b.txt": "oi"})
        self.assertIsNone(ctx.texto(ctx.arquivos["a.bin"]))
        self.assertEqual(ctx.texto(ctx.arquivos["b.txt"]), "oi")

    def test_links_ficam_fora_dos_alvos_e_dentro_dos_links(self):
        ctx = contexto_de_memoria({"a.md": "x"}, links={"b": "a.md"})
        self.assertEqual([e.caminho for e in ctx.alvos], ["a.md"])
        self.assertEqual(ctx.links, {"b": "a.md"})

    def test_existe_arquivo_pasta_e_inexistente(self):
        ctx = contexto_de_memoria({"a/b/c.md": "x"})
        self.assertTrue(ctx.existe("a/b/c.md"))
        self.assertTrue(ctx.existe("a/b"))
        self.assertTrue(ctx.existe("a/b/../b/c.md"))
        self.assertFalse(ctx.existe("a/b/d.md"))
        self.assertFalse(ctx.existe("../fora.md"))

    def test_existe_atravessa_link_simbolico_de_pasta(self):
        ctx = contexto_de_memoria({"x/y/z.md": "oi"}, links={"atalho": "x/y"})
        self.assertTrue(ctx.existe("atalho/z.md"))
        self.assertFalse(ctx.existe("atalho/w.md"))

    def test_link_circular_nao_trava(self):
        ctx = contexto_de_memoria({}, links={"a": "b", "b": "a"})
        self.assertFalse(ctx.existe("a/x"))


if __name__ == "__main__":
    unittest.main()
