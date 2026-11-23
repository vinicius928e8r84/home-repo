import unittest

from scripts.freios import segredo
from scripts.freios.apoio_de_teste import contexto_de_memoria

CHAVE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
TOKEN_GITHUB = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
VALOR_ALEATORIO = "Zx9fQ3pLm7" + "Rt2Vb8Nc4Hw6"
SENHA_DA_URL = "Xk29v" + "Lq81"
CABECALHO_PRIVADO = "-----BEGIN RSA PRIVATE" + " KEY-----"


class TesteDeSegredo(unittest.TestCase):
    def verificar(self, arquivos, excecoes=None):
        return segredo.verificar(contexto_de_memoria(arquivos, excecoes=excecoes))

    def test_acha_chave_da_aws_com_arquivo_e_linha(self):
        achados = self.verificar({"a.py": f"x = 1\nchave = '{CHAVE_AWS}'\n"})
        self.assertEqual([(a.arquivo, a.linha) for a in achados], [("a.py", 2)])

    def test_acha_token_do_github_e_chave_privada(self):
        self.assertEqual(len(self.verificar({"a.md": f"use {TOKEN_GITHUB}\n"})), 1)
        self.assertEqual(len(self.verificar({"b.txt": f"{CABECALHO_PRIVADO}\nabc\n"})), 1)

    def test_o_valor_do_segredo_nao_aparece_no_achado(self):
        achado = self.verificar({"a.py": f"k = '{CHAVE_AWS}'\n"})[0]
        self.assertNotIn(CHAVE_AWS, achado.detalhe)

    def test_acha_valor_literal_em_campo_de_segredo(self):
        achados = self.verificar({"a.py": "api_key = '" + VALOR_ALEATORIO + "'\n"})
        self.assertEqual(len(achados), 1)

    def test_placeholder_e_leitura_do_ambiente_passam(self):
        arquivos = {
            "a.py": "token = os.environ['TOKEN_DA_API_DO_SERVICO']\n",
            "b.md": "api_key = 'seu_token_aqui_1234567890'\n",
            "c.md": "senha = 'xxxxxxxxxxxxxxxxxxxx'\n",
            "d.sh": 'PASSWORD_PATH="$CREDENTIALS_DIR/$VPS_ALIAS.password"\n',
        }
        self.assertEqual(self.verificar(arquivos), [])

    def test_url_com_usuario_e_senha_falha_e_a_de_exemplo_passa(self):
        self.assertEqual(len(self.verificar({"a.sh": "curl https://admin:" + SENHA_DA_URL + "@meu-servidor.com.br/x\n"})), 1)
        self.assertEqual(self.verificar({"b.md": "postgres://usuario:senha@exemplo.com/db\n"}), [])
        self.assertEqual(self.verificar({"c.md": "https://user:pass@host.example.com/x\n"}), [])

    def test_arquivo_de_segredo_pelo_nome(self):
        achados = self.verificar({".env": "A=1\n", "pasta/chave.pem": "x", "ok.md": "oi"})
        self.assertEqual(sorted(a.arquivo for a in achados), [".env", "pasta/chave.pem"])

    def test_linha_longa_e_lida_em_janelas(self):
        linha = "a" * 5000 + f" {CHAVE_AWS}"
        self.assertEqual(len(self.verificar({"a.txt": linha})), 1)

    def test_binario_com_texto_de_segredo_falha(self):
        dados = b"\0\0\0" + f"valor {TOKEN_GITHUB} fim".encode() + b"\0\0"
        self.assertEqual(len(self.verificar({"a.dat": dados})), 1)

    def test_binario_sem_segredo_passa(self):
        self.assertEqual(self.verificar({"a.dat": b"\0\1\2\3" * 100}), [])

    def test_excecao_com_motivo_libera_o_arquivo(self):
        excecoes = {"segredo": [{"glob": "docs/exemplos.md", "motivo": "chave de demonstração revogada"}]}
        self.assertEqual(self.verificar({"docs/exemplos.md": f"{CHAVE_AWS}\n"}, excecoes), [])


if __name__ == "__main__":
    unittest.main()
