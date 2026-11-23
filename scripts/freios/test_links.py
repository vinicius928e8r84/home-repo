import unittest

from scripts.freios import links
from scripts.freios.apoio_de_teste import contexto_de_memoria


class TesteDosLinks(unittest.TestCase):
    def verificar(self, arquivos, link_simbolico=None, excecoes=None):
        return links.verificar(contexto_de_memoria(arquivos, links=link_simbolico, excecoes=excecoes))

    def test_link_para_arquivo_existente_passa(self):
        arquivos = {"README.md": "[guia](docs/guia.md)\n", "docs/guia.md": "oi\n"}
        self.assertEqual(self.verificar(arquivos), [])

    def test_link_quebrado_falha_com_arquivo_e_linha(self):
        achados = self.verificar({"README.md": "oi\n\n[guia](docs/guia.md)\n"})
        self.assertEqual([(a.arquivo, a.linha) for a in achados], [("README.md", 3)])

    def test_caminho_e_relativo_a_pasta_do_arquivo(self):
        arquivos = {"wiki/a.md": "[b](b.md) [c](../c.md) [d](../d.md)\n", "wiki/b.md": "", "c.md": ""}
        achados = self.verificar(arquivos)
        self.assertEqual([a.detalhe.split()[2] for a in achados], ["../d.md"])

    def test_ancora_consulta_e_destino_com_ancora_so_contam_o_arquivo(self):
        arquivos = {"a.md": "[x](b.md#secao) [y](b.md?v=1) [z](#aqui)\n", "b.md": ""}
        self.assertEqual(self.verificar(arquivos), [])

    def test_endereco_externo_e_email_ficam_fora(self):
        texto = "[a](https://x.com/a) [b](mailto:a@b.com) [c](C:/nada) [d](/absoluto)\n"
        self.assertEqual(self.verificar({"a.md": texto}), [])

    def test_link_dentro_de_codigo_fica_fora(self):
        texto = "`[a](nada.md)`\n\n```\n[b](nada.md)\n```\n\n~~~md\n[c](nada.md)\n~~~\n"
        self.assertEqual(self.verificar({"a.md": texto}), [])

    def test_texto_depois_do_bloco_de_codigo_volta_a_valer(self):
        texto = "```\n[b](nada.md)\n```\n[c](falta.md)\n"
        achados = self.verificar({"a.md": texto})
        self.assertEqual([a.linha for a in achados], [4])

    def test_link_para_pasta_existente_passa(self):
        arquivos = {"a.md": "[p](pasta/)\n", "pasta/x.md": ""}
        self.assertEqual(self.verificar(arquivos), [])

    def test_link_de_referencia_e_imagem(self):
        texto = "![img](fig.png)\n\n[ref]: outro.md\n[ext]: https://x.com\n"
        achados = self.verificar({"a.md": texto})
        self.assertEqual(sorted(a.detalhe.split()[2] for a in achados), ["fig.png", "outro.md"])

    def test_link_com_espaco_codificado(self):
        arquivos = {"a.md": "[x](meu%20arquivo.md)\n", "meu arquivo.md": ""}
        self.assertEqual(self.verificar(arquivos), [])

    def test_caminho_que_passa_por_link_simbolico_vale(self):
        arquivos = {"a.md": "[x](.claude/skills/ola/SKILL.md)\n", ".agents/skills/ola/SKILL.md": ""}
        self.assertEqual(self.verificar(arquivos, {".claude/skills/ola": "../../.agents/skills/ola"}), [])

    def test_arquivos_que_nao_sao_md_ficam_fora(self):
        self.assertEqual(self.verificar({"a.txt": "[x](nada.md)\n"}), [])

    def test_excecao_com_motivo_libera_o_arquivo(self):
        excecoes = {"links": [{"glob": "modelos/", "motivo": "modelo com links de exemplo"}]}
        self.assertEqual(self.verificar({"modelos/a.md": "[x](nada.md)\n"}, excecoes=excecoes), [])


if __name__ == "__main__":
    unittest.main()
