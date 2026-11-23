import unittest

from scripts.freios import binario
from scripts.freios.apoio_de_teste import contexto_de_memoria


class TesteDeBinarioELixo(unittest.TestCase):
    def verificar(self, arquivos, limites=None, excecoes=None):
        return binario.verificar(contexto_de_memoria(arquivos, limites=limites, excecoes=excecoes))

    def test_extensao_de_instalador_falha(self):
        achados = self.verificar({"app.dmg": "x", "pacote.zip": "x", "ok.md": "x"})
        self.assertEqual(sorted(a.arquivo for a in achados), ["app.dmg", "pacote.zip"])

    def test_extensao_em_maiuscula_tambem_falha(self):
        self.assertEqual(len(self.verificar({"APP.EXE": "x"})), 1)

    def test_lixo_de_editor_e_backup_falha(self):
        arquivos = {"a.py.bak": "x", "b.orig": "x", "c~": "x", ".DS_Store": "x", "d.log": "x", "e.py": "x"}
        achados = self.verificar(arquivos)
        self.assertEqual(sorted(a.arquivo for a in achados), [".DS_Store", "a.py.bak", "b.orig", "c~", "d.log"])

    def test_pasta_de_dependencias_falha_em_qualquer_nivel(self):
        achados = self.verificar({"ferramentas/node_modules/x/index.js": "x", "src/index.js": "x"})
        self.assertEqual([a.arquivo for a in achados], ["ferramentas/node_modules/x/index.js"])

    def test_assinatura_de_executavel_com_outro_nome_falha(self):
        self.assertEqual(len(self.verificar({"dados.txt": b"\x7fELF\x02\x01\x01\0" + b"\0" * 20})), 1)

    def test_texto_que_comeca_com_mz_nao_e_executavel(self):
        self.assertEqual(self.verificar({"nota.txt": "MZ e outras letras de um texto comum"}), [])

    def test_arquivo_acima_do_limite_de_megabytes_falha(self):
        limites = {
            "tamanho": {"extensoes_de_codigo": []},
            "binario": {
                "lixo": [], "extensoes_proibidas": [], "assinaturas_proibidas": [], "megabytes_maximos": 1,
            },
        }
        self.assertEqual(len(self.verificar({"a.txt": "a" * (1024 * 1024 + 1)}, limites=limites)), 1)
        self.assertEqual(self.verificar({"b.txt": "a" * 1024}, limites=limites), [])

    def test_codigo_em_utf16_ou_com_byte_nulo_falha(self):
        achados = self.verificar({"a.py": "x = 1\n".encode("utf-16"), "b.sh": b"echo\0oi\n", "c.md": b"a\0b"})
        self.assertEqual(sorted(a.arquivo for a in achados), ["a.py", "b.sh"])

    def test_excecao_com_motivo_libera_o_arquivo(self):
        excecoes = {"binario": [{"glob": "dados/*.zip", "motivo": "amostra de teste"}]}
        self.assertEqual(self.verificar({"dados/a.zip": "x"}, excecoes=excecoes), [])


if __name__ == "__main__":
    unittest.main()
