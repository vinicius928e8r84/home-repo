import shutil
import unittest

from scripts.freios import sintaxe
from scripts.freios.apoio_de_teste import contexto_de_memoria


class TesteDeSintaxe(unittest.TestCase):
    def verificar(self, arquivos):
        return sintaxe.verificar(contexto_de_memoria(arquivos))

    def test_python_valido_passa(self):
        self.assertEqual(self.verificar({"a.py": "x = 1\n"}), [])

    def test_python_com_erro_falha_com_a_linha(self):
        achados = self.verificar({"a.py": "x = 1\ndef f(:\n"})
        self.assertEqual(len(achados), 1)
        self.assertTrue(achados[0].detalhe.startswith("linha 2"))

    def test_python_com_bom_passa(self):
        self.assertEqual(self.verificar({"a.py": "﻿x = 1\n"}), [])

    def test_json_valido_passa_e_invalido_falha(self):
        self.assertEqual(self.verificar({"repos.json": '{"a": 1}'}), [])
        achados = self.verificar({".pi/settings.json": '{"a": 1,}'})
        self.assertEqual([a.arquivo for a in achados], [".pi/settings.json"])

    def test_json_com_bom_passa(self):
        self.assertEqual(self.verificar({"a.json": "﻿{}"}), [])

    def test_arquivo_binario_e_texto_de_outro_tipo_ficam_fora(self):
        self.assertEqual(self.verificar({"a.bin": b"\0\0", "b.md": "def f(:"}), [])

    @unittest.skipUnless(shutil.which("bash"), "sem bash")
    def test_shell_com_erro_falha_e_valido_passa(self):
        self.assertEqual(self.verificar({"a.sh": "echo oi\n"}), [])
        achados = self.verificar({"b.sh": "if true; then\necho oi\n"})
        self.assertEqual([a.arquivo for a in achados], ["b.sh"])

    def test_excecao_libera_o_arquivo(self):
        excecoes = {"sintaxe": [{"glob": "modelos/", "motivo": "modelo com lacunas"}]}
        ctx = contexto_de_memoria({"modelos/a.py": "def f(:"}, excecoes=excecoes)
        self.assertEqual(sintaxe.verificar(ctx), [])


if __name__ == "__main__":
    unittest.main()
