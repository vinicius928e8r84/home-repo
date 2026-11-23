import sys
import tempfile
import unittest
from pathlib import Path

from scripts.freios import externos
from scripts.freios.apoio_de_teste import contexto_de_memoria
from scripts.freios.contexto import Entrada


def ferramenta(codigo, quando_existe=("ferramenta.toml",), comando=None):
    return {
        "nome": "falsa",
        "quando_existe": list(quando_existe),
        "comando": comando or [sys.executable, "-c", codigo],
        "alvo_tudo": ["pasta"],
        "extensoes": [".py"],
    }


class TesteDeFerramentasExternas(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)

    def contexto(self, ferramentas, execucao="tudo", arquivos=None):
        ctx = contexto_de_memoria(arquivos or {}, raiz=self.raiz)
        ctx.limites = {**ctx.limites, "ferramentas": ferramentas}
        ctx.execucao = execucao
        return ctx

    def configurar(self):
        (self.raiz / "ferramenta.toml").write_text("x", encoding="utf-8")

    def test_sem_configuracao_pula_e_avisa(self):
        ctx = self.contexto([ferramenta("import sys; sys.exit(1)")])
        self.assertEqual(externos.verificar(ctx), [])
        self.assertEqual(len(ctx.avisos), 1)
        self.assertIn("pulado", ctx.avisos[0])

    def test_configurada_e_passando_nao_tem_achado(self):
        self.configurar()
        self.assertEqual(externos.verificar(self.contexto([ferramenta("pass")])), [])

    def test_configurada_e_falhando_mostra_a_saida(self):
        self.configurar()
        codigo = "import sys; print('erro na linha 3'); sys.exit(1)"
        achados = externos.verificar(self.contexto([ferramenta(codigo)]))
        self.assertEqual(len(achados), 1)
        self.assertIn("erro na linha 3", achados[0].detalhe)

    def test_configurada_com_comando_ausente_falha(self):
        self.configurar()
        achados = externos.verificar(self.contexto([ferramenta("", comando=["comando-que-nao-existe-aqui"])]))
        self.assertEqual(len(achados), 1)
        self.assertIn("não foi encontrado", achados[0].detalhe)

    def test_sem_dependencias_instaladas_pula_e_diz_como_instalar(self):
        self.configurar()
        item = {**ferramenta("import sys; sys.exit(1)"), "instalado_em": "node_modules", "instalar": "npm ci"}
        ctx = self.contexto([item])
        self.assertEqual(externos.verificar(ctx), [])
        self.assertIn("npm ci", ctx.avisos[0])
        (self.raiz / "node_modules").mkdir()
        self.assertEqual(len(externos.verificar(self.contexto([item]))), 1)

    def test_no_commit_recebe_so_os_arquivos_da_extensao(self):
        self.configurar()
        codigo = "import sys; print(sys.argv[1:]); sys.exit(1)"
        ctx = self.contexto([ferramenta(codigo)], execucao="commit")
        ctx.alvos = [Entrada("a.py"), Entrada("b.md"), Entrada("c.py")]
        achados = externos.verificar(ctx)
        self.assertIn("['a.py', 'c.py']", achados[0].detalhe)

    def test_no_commit_sem_arquivos_da_extensao_nao_roda(self):
        self.configurar()
        ctx = self.contexto([ferramenta("import sys; sys.exit(1)")], execucao="commit")
        ctx.alvos = [Entrada("b.md")]
        self.assertEqual(externos.verificar(ctx), [])

    def test_a_configuracao_do_repo_lista_ruff_e_eslint(self):
        ctx = contexto_de_memoria({})
        self.assertEqual([f["nome"] for f in ctx.limites["ferramentas"]], ["ruff", "eslint"])


if __name__ == "__main__":
    unittest.main()
