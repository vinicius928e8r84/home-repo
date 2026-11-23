import contextlib
import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from scripts.freios import registro_da_pr
from scripts.freios.github_api import Cliente, ErroDoGitHub, corpos_em_ordem, ler_pr

HEAD = "c" * 40
REPO = "dono/repo"
REVISAO = f"Veredito: CLEAN\nHead: {HEAD}\nAutor: agente-a\nRevisor: agente-b\nRisco: BAIXA\n"
CORPO = f"Atenção: BAIXA\nCloses https://github.com/{REPO}/issues/1\n"


class Servidor:
    def __init__(self, rotas):
        self.rotas = rotas
        self.pedidos = []
        servidor = self

        class Atendente(BaseHTTPRequestHandler):
            def responder(self):
                tamanho = int(self.headers.get("Content-Length") or 0)
                corpo = self.rfile.read(tamanho).decode("utf-8") if tamanho else None
                servidor.pedidos.append((self.command, self.path, corpo, self.headers.get("Authorization")))
                chave = self.path.split("?")[0]
                if chave not in servidor.rotas:
                    self.send_response(404)
                    self.end_headers()
                    return
                dados = json.dumps(servidor.rotas[chave]).encode("utf-8")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(dados)

            do_GET = do_POST = do_PATCH = responder

            def log_message(self, *argumentos):
                return None

        self.http = HTTPServer(("127.0.0.1", 0), Atendente)
        self.url = f"http://127.0.0.1:{self.http.server_port}"

    def __enter__(self):
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *erro):
        self.http.shutdown()
        self.http.server_close()


def rotas_da_pr(arquivos):
    return {
        f"/repos/{REPO}/pulls/7": {"body": CORPO, "head": {"sha": HEAD}, "user": {"login": "dono"}},
        f"/repos/{REPO}/issues/7/comments": [
            {"body": REVISAO, "author_association": "OWNER", "created_at": "2026-01-02T00:00:00Z"},
            {"body": "fingi ser revisão", "author_association": "NONE", "created_at": "2026-01-03T00:00:00Z"},
        ],
        f"/repos/{REPO}/pulls/7/reviews": [],
        f"/repos/{REPO}/pulls/7/files": arquivos,
    }


def ambiente(servidor, **extra):
    return {
        "GITHUB_API_URL": servidor.url,
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_TOKEN": "segredo",
        "PR": "7",
        "HEAD": HEAD,
        **extra,
    }


def rodar_main(env):
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        codigo = registro_da_pr.main(env)
    return codigo, saida.getvalue()


class LeituraDoGitHub(unittest.TestCase):
    def test_le_corpo_head_autor_arquivos_e_so_registros_de_quem_pode(self):
        arquivos = [{"filename": "novo.py", "previous_filename": "velho.py"}]
        with Servidor(rotas_da_pr(arquivos)) as servidor:
            pr = ler_pr(Cliente(ambiente(servidor)), "7")
        self.assertEqual(pr["head"], HEAD)
        self.assertEqual(pr["autor"], "dono")
        self.assertEqual(pr["registros"], [REVISAO])
        self.assertEqual(pr["arquivos"], ["novo.py", "velho.py"])

    def test_manda_o_token_como_bearer(self):
        with Servidor(rotas_da_pr([])) as servidor:
            ler_pr(Cliente(ambiente(servidor)), "7")
        self.assertTrue(all(pedido[3] == "Bearer segredo" for pedido in servidor.pedidos))

    def test_erro_http_vira_erro_do_github(self):
        with Servidor({}) as servidor:
            with self.assertRaisesRegex(ErroDoGitHub, "404"):
                Cliente(ambiente(servidor)).pedir("GET", "pulls/7")

    def test_registros_em_ordem_de_data(self):
        registros = [
            {"body": "depois", "author_association": "OWNER", "created_at": "2026-02-01"},
            {"body": "antes", "author_association": "MEMBER", "submitted_at": "2026-01-01"},
        ]
        self.assertEqual(corpos_em_ordem(registros), ["antes", "depois"])

    def test_pagina_ate_o_lote_incompleto(self):
        cheio = [{"n": i} for i in range(100)]
        chamadas = []

        class Falso(Cliente):
            def __init__(self):
                pass

            def pedir(self, metodo, caminho, corpo=None):
                chamadas.append(caminho)
                return cheio if caminho.endswith("&page=1") else [{"n": 100}]

        self.assertEqual(len(Falso().todas("x")), 101)
        self.assertEqual(len(chamadas), 2)


class MainDoRegistro(unittest.TestCase):
    def test_passa_com_a_pr_valida(self):
        with Servidor(rotas_da_pr([{"filename": "wiki/index.md"}])) as servidor:
            codigo, saida = rodar_main(ambiente(servidor))
        self.assertEqual(codigo, 0, saida)
        self.assertIn("registro da PR ok", saida)

    def test_falha_com_caminho_sensivel_e_corpo_baixa(self):
        with Servidor(rotas_da_pr([{"filename": ".github/workflows/freios.yml"}])) as servidor:
            codigo, saida = rodar_main(ambiente(servidor))
        self.assertEqual(codigo, 1, saida)
        self.assertIn("caminho sensível", saida)

    def test_head_que_mudou_durante_a_execucao(self):
        with Servidor(rotas_da_pr([])) as servidor:
            codigo, saida = rodar_main(ambiente(servidor, HEAD="d" * 40))
        self.assertEqual(codigo, 1)
        self.assertIn("um commit novo chegou", saida)

    def test_uso_errado_sai_com_2(self):
        codigo, saida = rodar_main({"PR": "x"})
        self.assertEqual(codigo, 2)
        self.assertIn("uso:", saida)

    def test_github_fora_do_ar_sai_com_2(self):
        with Servidor({}) as servidor:
            codigo, saida = rodar_main(ambiente(servidor))
        self.assertEqual(codigo, 2)
        self.assertIn("Não consegui ler a PR 7", saida)


if __name__ == "__main__":
    unittest.main()
