import contextlib
import io
import json
import unittest

from scripts.freios import catraca, principal
from scripts.freios.apoio_de_teste import RepositorioTemporario, contexto_de_memoria
from scripts.freios.contexto import PASTA, Achado, Entrada

NL = chr(10)
COM_COMENTARIOS = NL.join(["x = 1", "# um", "y = 2", "# dois", ""])
COM_UM_COMENTARIO = NL.join(["x = 1", "# um", "y = 2", ""])
SEM_COMENTARIOS = NL.join(["x = 1", "y = 2", ""])


def achados(arquivo, quantidade, verificacao="comentarios"):
    return [Achado(verificacao, arquivo, "ruim", n + 1) for n in range(quantidade)]


def aplicar(achados_da_verificacao, base, teto=None, **modo):
    ctx = contexto_de_memoria({})
    ctx.execucao = modo.get("execucao", "tudo")
    ctx.alvos = [Entrada(c) for c in modo.get("alvos", ())]
    return catraca.aplicar(ctx, "comentarios", achados_da_verificacao, ({"comentarios": base}, teto))


class TesteDaComparacao(unittest.TestCase):
    def test_arquivo_fora_da_linha_de_base_reprova(self):
        falhas, divida = aplicar(achados("novo.py", 2), {})
        self.assertEqual(len(falhas), 2)
        self.assertEqual(divida, 0)

    def test_arquivo_igual_a_linha_de_base_so_conta_como_divida(self):
        falhas, divida = aplicar(achados("a.py", 3), {"a.py": 3})
        self.assertEqual((falhas, divida), ([], 3))

    def test_arquivo_que_piora_reprova(self):
        falhas, _ = aplicar(achados("a.py", 4), {"a.py": 3})
        self.assertEqual(len(falhas), 1)
        self.assertIn("piorou: 4 contra 3", falhas[0].detalhe)

    def test_arquivo_que_melhora_reprova_ate_atualizar_a_linha_de_base(self):
        falhas, _ = aplicar(achados("a.py", 2), {"a.py": 3})
        self.assertIn("melhorou de 3 para 2", falhas[0].detalhe)
        self.assertIn("--atualizar-linha-de-base", falhas[0].detalhe)

    def test_arquivo_limpo_ainda_listado_reprova(self):
        falhas, _ = aplicar([], {"a.py": 3})
        self.assertEqual([(f.arquivo, "não tem mais achados" in f.detalhe) for f in falhas], [("a.py", True)])

    def test_no_commit_so_cobra_o_que_esta_no_commit(self):
        base = {"a.py": 3, "b.py": 2}
        self.assertEqual(aplicar([], base, execucao="commit", alvos=["a.py"])[0][0].arquivo, "a.py")
        self.assertEqual(len(aplicar([], base, execucao="commit", alvos=["a.py"])[0]), 1)
        self.assertEqual(aplicar([], base, execucao="commit", alvos=["c.py"])[0], [])

    def test_achado_sem_arquivo_nunca_entra_na_linha_de_base(self):
        solto = Achado("comentarios", "", "geral")
        self.assertEqual(aplicar([solto], {})[0], [solto])

    def test_medida_de_tamanho_nao_pode_crescer(self):
        grande = Achado("tamanho", "a.md", "x", medida=21000)
        ctx = contexto_de_memoria({})
        ctx.alvos = []
        ok, _ = catraca.aplicar(ctx, "tamanho", [grande], ({"tamanho": {"a.md": 21000}}, None))
        pior, _ = catraca.aplicar(ctx, "tamanho", [grande], ({"tamanho": {"a.md": 20500}}, None))
        self.assertEqual(ok, [])
        self.assertIn("piorou: 21000 contra 20500", pior[0].detalhe)

    def test_teto_de_linhas_e_de_bytes_do_mesmo_arquivo_sao_grupos_separados(self):
        ambos = [
            Achado("tamanho", "a.py", "bytes", medida=30000),
            Achado("tamanho", "a.py", "linhas", medida=1200, grupo="a.py#linhas"),
        ]
        ctx = contexto_de_memoria({})
        ctx.alvos = []
        base = {"tamanho": {"a.py": 30000, "a.py#linhas": 1200}}
        self.assertEqual(catraca.aplicar(ctx, "tamanho", ambos, (base, None)), ([], 2))

    def test_linha_de_base_nao_cresce_em_relacao_a_base(self):
        teto = {"comentarios": {"a.py": 3}}
        self.assertEqual(aplicar(achados("a.py", 3), {"a.py": 3}, teto)[0], [])
        subiu = aplicar(achados("a.py", 4), {"a.py": 4}, teto)[0]
        self.assertIn("subiu de 3 para 4", subiu[0].detalhe)
        entrou = aplicar(achados("b.py", 1), {"a.py": 3, "b.py": 1}, teto)[0]
        self.assertTrue(any("entrou na linha de base" in f.detalhe for f in entrou))

    def test_linha_de_base_pode_encolher_em_relacao_a_base(self):
        teto = {"comentarios": {"a.py": 3, "b.py": 2}}
        self.assertEqual(aplicar(achados("a.py", 2), {"a.py": 2}, teto)[0], [])

    def test_leitura_recusa_formato_errado(self):
        self.assertEqual(catraca.ler_linha_de_base('{"a": {"b.py": 2}}', "x"), {"a": {"b.py": 2}})
        for ruim in ("[]", '{"a": []}', '{"a": {"b.py": 0}}', '{"a": {"b.py": "2"}}', "nao json"):
            with self.subTest(ruim), self.assertRaises(ValueError):
                catraca.ler_linha_de_base(ruim, "x")


class TesteDoFluxoCompleto(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioTemporario()
        self.addCleanup(self.repo.limpar)
        self.repo.adicionar("a.py", COM_COMENTARIOS)

    def rodar(self, *argumentos):
        saida = io.StringIO()
        erro = io.StringIO()
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
            codigo = principal.main([*argumentos, "--raiz", str(self.repo.raiz), "--sem-testes", "--tudo"])
        return codigo, saida.getvalue() + erro.getvalue()

    def linha_de_base(self):
        return json.loads((self.repo.raiz / catraca.ARQUIVO).read_text(encoding="utf-8"))

    def versionar(self):
        self.repo.git("add", "-A")

    def criar(self):
        self.assertEqual(self.rodar("--criar-linha-de-base")[0], 0)
        self.versionar()

    def test_sem_linha_de_base_a_divida_existente_reprova(self):
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertIn("a.py:2", saida)

    def test_criar_registra_a_divida_e_passa_a_so_avisar(self):
        self.criar()
        self.assertEqual(self.linha_de_base()["comentarios"], {"a.py": 2})
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 0)
        self.assertIn("✓ comentarios (2 na linha de base)", saida)

    def test_criar_de_novo_nao_sobrescreve(self):
        self.criar()
        self.assertEqual(self.rodar("--criar-linha-de-base")[0], 1)

    def test_arquivo_novo_com_comentario_reprova(self):
        self.criar()
        self.repo.adicionar("novo.py", COM_UM_COMENTARIO)
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertIn("novo.py:2", saida)

    def test_arquivo_que_piora_reprova(self):
        self.criar()
        self.repo.adicionar("a.py", COM_COMENTARIOS + "# tres" + NL)
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertIn("piorou: 3 contra 2", saida)

    def test_limpeza_exige_atualizar_e_depois_passa(self):
        self.criar()
        self.repo.adicionar("a.py", COM_UM_COMENTARIO)
        self.assertEqual(self.rodar()[0], 1)
        self.assertEqual(self.rodar("--atualizar-linha-de-base")[0], 0)
        self.assertEqual(self.linha_de_base()["comentarios"], {"a.py": 1})
        self.versionar()
        self.assertEqual(self.rodar()[0], 0)

    def test_limpeza_total_tira_o_arquivo_da_linha_de_base(self):
        self.criar()
        self.repo.adicionar("a.py", SEM_COMENTARIOS)
        self.assertEqual(self.rodar("--atualizar-linha-de-base")[0], 0)
        self.assertEqual(self.linha_de_base()["comentarios"], {})
        self.versionar()
        self.assertEqual(self.rodar()[0], 0)

    def test_atualizar_recusa_subir_e_nao_grava_nada(self):
        self.criar()
        antes = (self.repo.raiz / catraca.ARQUIVO).read_text(encoding="utf-8")
        self.repo.adicionar("a.py", COM_COMENTARIOS + "# tres" + NL)
        self.repo.adicionar("novo.py", COM_UM_COMENTARIO)
        codigo, saida = self.rodar("--atualizar-linha-de-base")
        self.assertEqual(codigo, 1)
        self.assertIn("nada foi atualizado", saida)
        self.assertEqual((self.repo.raiz / catraca.ARQUIVO).read_text(encoding="utf-8"), antes)

    def test_sem_linha_de_base_lista_toda_a_divida(self):
        self.criar()
        codigo, saida = self.rodar("--sem-linha-de-base")
        self.assertEqual(codigo, 1)
        self.assertIn("a.py:2", saida)

    def test_criar_e_atualizar_pedem_tudo(self):
        argumentos = ["--commit", "--criar-linha-de-base", "--raiz", str(self.repo.raiz)]
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(principal.main(argumentos), 2)

    def test_pre_commit_deixa_passar_a_divida_e_barra_o_arquivo_novo(self):
        self.criar()
        self.repo.commitar("base")
        self.repo.adicionar("a.py", COM_COMENTARIOS + NL)
        argumentos = ["--commit", "--raiz", str(self.repo.raiz)]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(principal.main(argumentos), 0)
            self.repo.adicionar("novo.py", COM_UM_COMENTARIO)
            self.assertEqual(principal.main(argumentos), 1)

    def test_linha_de_base_nao_cresce_em_relacao_a_base_da_branch(self):
        self.criar()
        self.repo.commitar("base")
        self.repo.git("branch", "base-falsa")
        self.repo.adicionar("b.py", COM_UM_COMENTARIO)
        dados = self.linha_de_base()
        dados["comentarios"]["b.py"] = 1
        (self.repo.raiz / catraca.ARQUIVO).write_text(json.dumps(dados), encoding="utf-8")
        self.versionar()
        codigo, saida = self.rodar("--base", "base-falsa")
        self.assertEqual(codigo, 1)
        self.assertIn("b.py: entrou na linha de base", saida)


class TesteDaConfiguracao(unittest.TestCase):
    def test_as_verificacoes_com_linha_de_base_sao_as_aprovadas(self):
        ctx = contexto_de_memoria({})
        self.assertEqual(ctx.limites["linha_de_base"]["verificacoes"], ["tamanho", "comentarios", "skills", "links"])

    def test_o_repo_tem_a_linha_de_base_versionada_e_valida(self):
        texto = (PASTA / "linha-de-base.json").read_text(encoding="utf-8")
        self.assertTrue(set(catraca.ler_linha_de_base(texto, "x")) <= {"tamanho", "comentarios", "skills", "links"})


if __name__ == "__main__":
    unittest.main()
  
