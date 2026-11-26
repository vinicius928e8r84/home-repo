import contextlib
import io
import unittest

from scripts.freios import reexecutar_registro
from scripts.freios.github_api import ErroDoGitHub
from scripts.freios.test_registro_da_pr import HEAD, OUTRO, REPO


class ClienteFalso:
    def __init__(self, head=HEAD, execucoes=None):
        self.repositorio = REPO
        self.head = head
        self.execucoes = list(execucoes if execucoes is not None else [{"id": 91, "status": "completed"}])
        self.pedidos = []

    def pedir(self, metodo, caminho, corpo=None):
        self.pedidos.append((metodo, caminho))
        if metodo == "POST":
            return None
        if caminho.startswith("pulls/"):
            return {"head": {"sha": self.head}}
        atual = self.execucoes[0] if len(self.execucoes) == 1 else self.execucoes.pop(0)
        return {"workflow_runs": [atual] if atual else []}

    def reexecucoes(self):
        return [pedido for pedido in self.pedidos if pedido[0] == "POST"]


def rodar(cliente, pr="7"):
    esperas = []
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        codigo = reexecutar_registro.reexecutar(cliente, pr, esperas.append)
    return codigo, saida.getvalue(), esperas


class Reexecutar(unittest.TestCase):
    def test_reexecuta_o_run_do_head_atual_da_pr(self):
        cliente = ClienteFalso()
        codigo, saida, esperas = rodar(cliente)
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(cliente.reexecucoes(), [("POST", "actions/runs/91/rerun")])
        self.assertEqual(esperas, [])

    def test_procura_o_run_pelo_head_lido_da_pr_e_so_o_da_pull_request(self):
        cliente = ClienteFalso(head=OUTRO)
        rodar(cliente)
        busca = cliente.pedidos[1][1]
        self.assertIn("actions/workflows/registro-da-pr.yml/runs", busca)
        self.assertIn(f"head_sha={OUTRO}", busca)
        self.assertIn("event=pull_request", busca)

    def test_espera_o_run_em_andamento_terminar_antes_de_reexecutar(self):
        andamento = {"id": 91, "status": "in_progress"}
        cliente = ClienteFalso(execucoes=[andamento, andamento, {"id": 91, "status": "completed"}])
        codigo, saida, esperas = rodar(cliente)
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(len(esperas), 2)
        self.assertEqual(len(cliente.reexecucoes()), 1)

    def test_run_que_nao_termina_nao_e_reexecutado(self):
        cliente = ClienteFalso(execucoes=[{"id": 91, "status": "in_progress"}])
        codigo, saida, esperas = rodar(cliente)
        self.assertEqual(codigo, 1)
        self.assertIn("não terminou", saida)
        self.assertEqual(cliente.reexecucoes(), [])
        self.assertEqual(len(esperas), reexecutar_registro.TENTATIVAS)

    def test_sem_run_para_o_head_nao_ha_o_que_reexecutar(self):
        cliente = ClienteFalso(execucoes=[None])
        codigo, saida, _ = rodar(cliente)
        self.assertEqual(codigo, 0)
        self.assertIn("nenhum run", saida)
        self.assertEqual(cliente.reexecucoes(), [])


class Linha(unittest.TestCase):
    def test_main_sem_pr_ou_repositorio_sai_com_2(self):
        for env in ({}, {"PR": "7"}, {"GITHUB_REPOSITORY": REPO}, {"GITHUB_REPOSITORY": REPO, "PR": "sete"}):
            with self.subTest(env=env), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(reexecutar_registro.main(env), 2)

    def test_erro_do_github_sai_com_2(self):
        class Quebrado:
            repositorio = REPO

            def pedir(self, metodo, caminho, corpo=None):
                raise ErroDoGitHub("o GitHub respondeu 403 a actions/runs/91/rerun")

        saida = io.StringIO()
        original = reexecutar_registro.Cliente
        reexecutar_registro.Cliente = lambda env: Quebrado()
        try:
            with contextlib.redirect_stdout(saida):
                codigo = reexecutar_registro.main({"GITHUB_REPOSITORY": REPO, "PR": "7"})
        finally:
            reexecutar_registro.Cliente = original
        self.assertEqual(codigo, 2)
        self.assertIn("403", saida.getvalue())


if __name__ == "__main__":
    unittest.main()
