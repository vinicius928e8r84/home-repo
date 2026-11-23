import re
import unittest
from pathlib import Path

from scripts.freios.registro_da_pr import Pr, conferir
from scripts.freios.test_registro_da_pr import HEAD, REPO, revisao

RAIZ = Path(__file__).resolve().parents[2]
WORKFLOWS = RAIZ / ".github" / "workflows"
MODELO = RAIZ / ".github" / "PULL_REQUEST_TEMPLATE.md"
USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)\s*$", re.M)


def ler(nome):
    return (WORKFLOWS / nome).read_text(encoding="utf-8")


class AsActionsEstaoFixadasPorSha(unittest.TestCase):
    def test_toda_action_de_todo_workflow_usa_sha_inteiro(self):
        arquivos = sorted(WORKFLOWS.glob("*.yml"))
        self.assertTrue(arquivos)
        for arquivo in arquivos:
            usadas = USES.findall(arquivo.read_text(encoding="utf-8"))
            for usada in usadas:
                with self.subTest(arquivo=arquivo.name, action=usada):
                    self.assertRegex(usada, r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")

    def test_todo_checkout_busca_o_historico_e_nao_deixa_o_token_no_git(self):
        for arquivo in sorted(WORKFLOWS.glob("*.yml")):
            texto = arquivo.read_text(encoding="utf-8")
            with self.subTest(arquivo=arquivo.name):
                self.assertEqual(texto.count("persist-credentials: false"), texto.count("actions/checkout@"))
                self.assertEqual(texto.count("fetch-depth: 0"), texto.count("actions/checkout@"))
                self.assertNotIn("git fetch", texto)

    def test_workflows_nao_tem_comentario(self):
        for arquivo in sorted(WORKFLOWS.glob("*.yml")):
            with self.subTest(arquivo=arquivo.name):
                self.assertNotRegex(arquivo.read_text(encoding="utf-8"), r"(?m)^\s*#")


class WorkflowFreios(unittest.TestCase):
    def setUp(self):
        self.texto = ler("freios.yml")

    def test_nome_e_gatilhos(self):
        self.assertRegex(self.texto, r"(?m)^name: Freios$")
        self.assertRegex(self.texto, r"(?m)^  pull_request:$")
        self.assertRegex(self.texto, r"(?m)^  push:\n    branches: \[main\]$")

    def test_roda_o_comando_unico_dos_freios_e_os_testes(self):
        self.assertIn("python scripts/freios/freios.py --tudo 2>&1 | tee", self.texto)
        self.assertIn("run: python -m unittest discover\n", self.texto)

    def test_instala_ruff_e_as_dependencias_do_eslint_antes_dos_freios(self):
        antes = self.texto[: self.texto.index("- name: Freios\n")]
        self.assertIn("python -m pip install --disable-pip-version-check -r scripts/freios/requirements.txt", antes)
        self.assertIn("npm ci --ignore-scripts --no-audit --no-fund --prefix scripts/freios", antes)
        self.assertNotIn("if [ -f scripts/freios/package-lock.json ]", self.texto)

    def test_falha_se_alguma_ferramenta_for_pulada_e_olha_as_duas_saidas(self):
        self.assertIn('python -m scripts.freios.sem_pulo "$RUNNER_TEMP"/freios*.txt', self.texto)
        self.assertIn('tee "$RUNNER_TEMP/freios.txt"', self.texto)
        self.assertIn('tee "$RUNNER_TEMP/freios-da-pr.txt"', self.texto)
        self.assertEqual(self.texto.count("set -o pipefail"), 2)

    def test_a_pr_tambem_roda_os_freios_nos_arquivos_dela_com_as_dependencias_dela(self):
        trecho = self.texto[self.texto.index("Voltar aos freios da PR"): self.texto.index("Nenhuma ferramenta pulada")]
        self.assertIn("npm ci --ignore-scripts --no-audit --no-fund --prefix scripts/freios", trecho)
        self.assertIn("python scripts/freios/freios.py --tudo --sem-testes", trecho)
        self.assertEqual(trecho.count("env.FREIOS_DA_BASE == '1'"), 3)

    def test_a_pr_roda_os_freios_da_base_e_depois_volta_aos_da_pr(self):
        self.assertIn('git cat-file -e "origin/$BASE:scripts/freios/freios.py"', self.texto)
        self.assertIn('git archive "origin/$BASE" scripts/freios | tar -x', self.texto)
        self.assertIn("git checkout -- scripts/freios", self.texto)

    def test_a_ordem_e_base_depois_ferramentas_depois_freios_depois_testes(self):
        passos = [
            "Usar os freios da base",
            "Instalar ruff e ESLint\n",
            "- name: Freios\n",
            "Voltar aos freios da PR",
            "Instalar ruff e ESLint da PR",
            "Freios nos arquivos da PR",
            "Nenhuma ferramenta pulada",
            "- name: Testes",
        ]
        posicoes = []
        for passo in passos:
            posicoes.append(self.texto.index(passo, posicoes[-1] + 1 if posicoes else 0))
        self.assertEqual(posicoes, sorted(posicoes))

    def test_permissao_minima(self):
        self.assertRegex(self.texto, r"(?m)^permissions:\n  contents: read$")
        self.assertNotIn("write", self.texto)

    def test_job_da_auditoria_roda_a_auditoria_da_base_contra_a_base_da_mudanca(self):
        self.assertIn("name: Auditoria de dependências", self.texto)
        self.assertIn('python -m scripts.freios.auditoria_npm --raiz "$GITHUB_WORKSPACE" --base "$BASE_SHA"', self.texto)
        self.assertIn('cd "$FREIOS_RAIZ"', self.texto)
        self.assertIn("github.event.pull_request.base.sha || github.event.before", self.texto)

    def test_o_checkout_traz_o_historico_inteiro(self):
        self.assertEqual(self.texto.count("fetch-depth: 0"), self.texto.count("actions/checkout@"))


class WorkflowRegistroDaPr(unittest.TestCase):
    def setUp(self):
        self.texto = ler("registro-da-pr.yml")

    def test_nome_do_job_e_gatilhos(self):
        self.assertRegex(self.texto, r"(?m)^name: Registro da PR$")
        self.assertIn("    name: Registro da PR\n", self.texto)
        self.assertRegex(self.texto, r"(?m)^  pull_request:$")
        self.assertRegex(self.texto, r"(?m)^  pull_request_review:$")

    def test_roda_o_check_da_base_com_o_head_do_evento(self):
        self.assertIn('git cat-file -e "origin/$BASE:scripts/freios/registro_da_pr.py"', self.texto)
        self.assertIn('cd "$FREIOS_RAIZ"\n          python -m scripts.freios.registro_da_pr', self.texto)
        self.assertIn("HEAD: ${{ github.event.pull_request.head.sha }}", self.texto)
        self.assertIn("PR: ${{ github.event.pull_request.number }}", self.texto)

    def test_so_le_a_pr(self):
        self.assertRegex(self.texto, r"(?m)^permissions:\n  contents: read\n  pull-requests: read$")


class ModeloDaPr(unittest.TestCase):
    def conferir(self, corpo):
        pr = Pr(corpo=corpo, head=HEAD, registros=[revisao(HEAD)], arquivos=["wiki/index.md"], autor="dono", repositorio=REPO)
        return conferir(pr)

    def test_o_modelo_cru_nao_passa_e_o_que_esta_em_comentario_nao_conta(self):
        ok, mensagem = self.conferir(MODELO.read_text(encoding="utf-8"))
        self.assertFalse(ok)
        self.assertIn("não tem a linha de atenção", mensagem)
        self.assertIn("não tem a URL completa da issue", mensagem)

    def test_o_modelo_preenchido_passa(self):
        texto = MODELO.read_text(encoding="utf-8")
        texto = texto.replace("**Atenção:**", "**Atenção:** BAIXA", 1)
        texto = texto.replace("issues/N", "issues/3", 1)
        ok, mensagem = self.conferir(texto)
        self.assertTrue(ok, mensagem)

    def test_o_modelo_com_sem_issue_passa(self):
        texto = MODELO.read_text(encoding="utf-8")
        texto = texto.replace("**Atenção:**", "**Atenção:** MÉDIA", 1)
        texto = texto.replace("Closes https://github.com/vinicius928e8r84/home-repo/issues/N", "Sem issue", 1)
        ok, mensagem = self.conferir(texto)
        self.assertTrue(ok, mensagem)

    def test_o_modelo_cita_os_dois_modulos_que_existem(self):
        texto = MODELO.read_text(encoding="utf-8")
        for modulo in ("registro_da_pr", "registrar_na_pr"):
            self.assertIn(modulo, texto)
            self.assertTrue((RAIZ / "scripts" / "freios" / f"{modulo}.py").is_file(), modulo)
        self.assertIn("python -m scripts.freios.registrar_na_pr", texto)


if __name__ == "__main__":
    unittest.main()
