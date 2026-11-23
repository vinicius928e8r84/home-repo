import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import registrar_na_pr
from registro_da_pr import conferir
from registrar_na_pr import corpo_com_a_prova, ler_argumentos, secao_da_prova
from test_registro_da_pr import FECHA, HEAD, OUTRO, REPO, prova, revisao

CORPO = f"Atenção: BAIXA\n\n{FECHA}\n"


class ClienteFalso:
    def __init__(self, corpo=CORPO, registros=(), arquivos=("scripts/crew.py",), head=HEAD):
        self.repositorio = REPO
        self.corpo = corpo
        self.registros = list(registros)
        self.arquivos = [{"filename": a} for a in arquivos]
        self.head = head
        self.escritas = []

    def pedir(self, metodo, caminho, corpo=None):
        if metodo != "GET":
            self.escritas.append((metodo, caminho, corpo))
            return None
        return {"body": self.corpo, "head": {"sha": self.head}, "user": {"login": "dono"}}

    def todas(self, caminho):
        if caminho.endswith("/comments"):
            return [{"body": r, "author_association": "OWNER", "created_at": "2026"} for r in self.registros]
        return self.arquivos if caminho.endswith("/files") else []


def rodar(cliente, *argv, nota=None):
    args = ler_argumentos([*argv, "--pr", "7"])
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        codigo = registrar_na_pr.executar(cliente, args, nota or "")
    return codigo, saida.getvalue()


REVISAO_ARGS = ("revisao", "--head", HEAD, "--autor", "agente-a", "--revisor", "agente-b", "--risco", "baixa")


class Revisao(unittest.TestCase):
    def test_ensaio_nao_escreve_e_mostra_o_que_o_check_diria(self):
        cliente = ClienteFalso()
        codigo, saida = rodar(cliente, *REVISAO_ARGS)
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(cliente.escritas, [])
        self.assertIn("ensaio", saida)
        self.assertIn(f"Head: {HEAD}", saida)
        self.assertIn("registro da PR ok", saida)

    def test_publicar_envia_uma_revisao_do_tipo_comentario_no_head(self):
        cliente = ClienteFalso()
        codigo, saida = rodar(cliente, *REVISAO_ARGS, "--publicar")
        self.assertEqual(codigo, 0, saida)
        (metodo, caminho, corpo), = cliente.escritas
        self.assertEqual((metodo, caminho), ("POST", "pulls/7/reviews"))
        self.assertEqual((corpo["event"], corpo["commit_id"]), ("COMMENT", HEAD))
        self.assertIn("Veredito: CLEAN", corpo["body"])

    def test_registro_publicado_passa_no_conferir_do_check(self):
        cliente = ClienteFalso()
        rodar(cliente, *REVISAO_ARGS, "--publicar")
        corpo = cliente.escritas[0][2]["body"]
        ok, mensagem = conferir_com(corpo)
        self.assertTrue(ok, mensagem)

    def test_nota_entra_depois_das_linhas_do_registro(self):
        cliente = ClienteFalso()
        _, saida = rodar(cliente, *REVISAO_ARGS, nota="Achei tudo em ordem.\n")
        self.assertIn("Achei tudo em ordem.", saida)

    def test_recusa_head_que_nao_e_o_da_pr(self):
        cliente = ClienteFalso()
        args = list(REVISAO_ARGS)
        args[2] = OUTRO
        codigo, saida = rodar(cliente, *args, "--publicar")
        self.assertEqual(codigo, 1)
        self.assertIn("o head da PR agora é", saida)
        self.assertEqual(cliente.escritas, [])

    def test_recusa_head_abreviado(self):
        args = list(REVISAO_ARGS)
        args[2] = HEAD[:8]
        codigo, saida = rodar(ClienteFalso(), *args)
        self.assertEqual(codigo, 1)
        self.assertIn("SHA inteiro", saida)

    def test_recusa_revisor_igual_ao_autor(self):
        args = list(REVISAO_ARGS)
        args[6] = "agente-a"
        cliente = ClienteFalso()
        codigo, saida = rodar(cliente, *args, "--publicar")
        self.assertEqual(codigo, 1)
        self.assertIn("próprio autor", saida)
        self.assertEqual(cliente.escritas, [])

    def test_recusa_quem_abriu_a_pr_como_revisor(self):
        args = list(REVISAO_ARGS)
        args[6] = "dono"
        codigo, saida = rodar(ClienteFalso(), *args)
        self.assertEqual(codigo, 1)
        self.assertIn("quem abriu a PR", saida)

    def test_pede_as_opcoes_que_faltam(self):
        codigo, saida = rodar(ClienteFalso(), "revisao", "--head", HEAD)
        self.assertEqual(codigo, 1)
        self.assertIn("--autor, --revisor, --risco", saida)

    def test_risco_invalido(self):
        args = list(REVISAO_ARGS)
        args[-1] = "enorme"
        codigo, saida = rodar(ClienteFalso(), *args)
        self.assertEqual(codigo, 1)
        self.assertIn("baixa, media ou alta", saida)


def conferir_com(registro):
    from registro_da_pr import Pr

    return conferir(Pr(corpo=CORPO, head=HEAD, registros=[registro], autor="dono", repositorio=REPO))


class Prova(unittest.TestCase):
    ALTA = f"Atenção: ALTA\n\n{FECHA}\n"
    NOTA = "Rodei o workflow numa PR de teste e o check apareceu verde no head.\n"

    def test_publicar_troca_o_corpo_com_a_secao_e_o_head(self):
        cliente = ClienteFalso(corpo=self.ALTA, registros=[revisao(HEAD)])
        codigo, saida = rodar(cliente, "prova", "--head", HEAD, "--cobertura", "total", "--publicar", nota=self.NOTA)
        self.assertEqual(codigo, 0, saida)
        (metodo, caminho, corpo), = cliente.escritas
        self.assertEqual((metodo, caminho), ("PATCH", "pulls/7"))
        self.assertIn(f"PROVADO 100% REAL\nHead: {HEAD}", corpo["body"])
        self.assertTrue(corpo["body"].startswith(self.ALTA.rstrip()))

    def test_total_sem_nota_e_recusada(self):
        cliente = ClienteFalso(corpo=self.ALTA, registros=[revisao(HEAD)])
        codigo, saida = rodar(cliente, "prova", "--head", HEAD, "--cobertura", "total", "--publicar")
        self.assertEqual(codigo, 1)
        self.assertIn("não explica o que foi provado", saida)
        self.assertEqual(cliente.escritas, [])

    def test_parcial_e_publicada_mas_o_check_nao_passa(self):
        cliente = ClienteFalso(corpo=self.ALTA, registros=[revisao(HEAD)])
        codigo, saida = rodar(cliente, "prova", "--head", HEAD, "--cobertura", "parcial", "--publicar", nota=self.NOTA)
        self.assertEqual(codigo, 1)
        self.assertIn("prova parcial não vale", saida)
        self.assertEqual(len(cliente.escritas), 1)

    def test_head_de_outro_commit_e_recusado(self):
        cliente = ClienteFalso(corpo=self.ALTA)
        codigo, _ = rodar(cliente, "prova", "--head", OUTRO, "--cobertura", "total", "--publicar", nota=self.NOTA)
        self.assertEqual(codigo, 1)
        self.assertEqual(cliente.escritas, [])


class CorpoComAProva(unittest.TestCase):
    SECAO = secao_da_prova(HEAD, "total", "nota")

    def test_acrescenta_no_fim_quando_nao_ha_secao(self):
        corpo = corpo_com_a_prova("Atenção: ALTA\n", self.SECAO)
        self.assertEqual(corpo, f"Atenção: ALTA\n\n{self.SECAO}\n")

    def test_troca_a_secao_antiga_e_preserva_a_seguinte(self):
        antigo = f"Atenção: ALTA\n\n{prova(OUTRO)}\n## Depois\n\nfica\n"
        corpo = corpo_com_a_prova(antigo, self.SECAO)
        self.assertNotIn(OUTRO, corpo)
        self.assertIn(f"Head: {HEAD}", corpo)
        self.assertIn("## Depois\n\nfica", corpo)
        self.assertEqual(corpo.count("## Prova real"), 1)

    def test_secao_de_exemplo_em_comentario_html_nao_e_trocada(self):
        modelo = "<!--\n## Prova real\n\nexemplo\n-->\nAtenção: ALTA\n"
        corpo = corpo_com_a_prova(modelo, self.SECAO)
        self.assertTrue(corpo.startswith(modelo.rstrip()))
        self.assertEqual(corpo.count("## Prova real"), 2)

    def test_secao_parcial_usa_a_marca_de_bloqueada(self):
        self.assertIn("BLOQUEADA-parcial", secao_da_prova(HEAD, "parcial", ""))


class Linha(unittest.TestCase):
    def test_main_sem_repositorio_sai_com_2(self):
        saida = io.StringIO()
        original = registrar_na_pr.repositorio_do_origin
        registrar_na_pr.repositorio_do_origin = lambda: None
        try:
            with contextlib.redirect_stdout(saida):
                codigo = registrar_na_pr.main(["conferir", "--pr", "7"], {})
        finally:
            registrar_na_pr.repositorio_do_origin = original
        self.assertEqual(codigo, 2)

    def test_nota_inexistente_sai_com_2(self):
        saida = io.StringIO()
        with tempfile.TemporaryDirectory() as pasta, contextlib.redirect_stdout(saida):
            falta = str(Path(pasta) / "nao-existe.md")
            codigo = registrar_na_pr.main(["revisao", "--pr", "7", "--nota", falta], {"GITHUB_REPOSITORY": REPO})
        self.assertEqual(codigo, 2)


if __name__ == "__main__":
    unittest.main()
