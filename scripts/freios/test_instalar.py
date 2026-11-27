import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.freios import instalar

SLUG = "dono/alvo"


class GhFalso:
    def __init__(self, protecao=None, prs=(), privado=False):
        self.protecao, self.privado = protecao, privado
        self.prs = list(prs)
        self.chamados = []

    def __call__(self, comando, cwd=None, entrada=None):
        self.chamados.append((comando, entrada))
        if comando[0] == "git" and cwd == instalar.RAIZ:
            return instalar.rodar(comando, cwd=cwd)
        if comando[:3] == ["gh", "pr", "list"]:
            return json.dumps(self.prs)
        if comando[:2] == ["git", "init"]:
            Path(comando[-1]).mkdir(parents=True)
            return ""
        if comando[:3] == ["gh", "repo", "clone"]:
            Path(comando[4]).mkdir(parents=True)
            return ""
        if comando[:3] == ["gh", "repo", "view"]:
            return self.ver_repo(comando)
        if comando[:2] == ["gh", "api"] and comando[2].endswith("/protection"):
            if self.protecao is None:
                raise instalar.Falha("gh api: Branch not protected (HTTP 404)")
            return json.dumps(self.protecao)
        return ""

    def ver_repo(self, comando):
        if "isPrivate" in comando:
            return "true\n" if self.privado else "false\n"
        return f"dono/{comando[3]}\n" if "nameWithOwner" in comando else "main\n"

    def escritas(self):
        return [c for c, _ in self.chamados if c[:3] in (["gh", "api", "-X"], ["gh", "pr", "create"]) or c[:2] == ["git", "push"]]


class Argumentos:
    def __init__(self, alvo=None, novo=None, privado=False, simular=True):
        self.alvo, self.novo, self.privado, self.simular = alvo, novo, privado, simular


class Copia(unittest.TestCase):
    def setUp(self):
        self.temporaria = tempfile.TemporaryDirectory()
        self.pasta = Path(self.temporaria.name)
        self.arquivos = instalar.arquivos_do_home()

    def tearDown(self):
        self.temporaria.cleanup()

    def ler(self, caminho):
        return (self.pasta / caminho).read_text(encoding="utf-8")

    def test_repo_vazio_recebe_os_freios_os_ganchos_e_os_workflows(self):
        mudados = instalar.copiar(self.pasta, SLUG, self.arquivos)
        for caminho in ("scripts/freios/freios.py", ".githooks/pre-push", ".github/workflows/freios.yml", ".gitignore"):
            self.assertIn(caminho, mudados)
        self.assertNotIn("scripts/freios/instalar.py", mudados)

    def test_os_ganchos_entram_no_commit_como_executaveis(self):
        subprocess.run(["git", "init", "-q", str(self.pasta)], check=True)
        instalar.copiar(self.pasta, SLUG, self.arquivos)
        instalar.commitar(self.pasta, "teste")
        modo = instalar.rodar(["git", "ls-files", "-s", ".githooks/pre-commit"], cwd=self.pasta)
        self.assertTrue(modo.startswith("100755"), modo)

    def git_do_alvo(self, arquivos):
        subprocess.run(["git", "init", "-q", str(self.pasta)], check=True)
        for caminho, texto in arquivos.items():
            (self.pasta / caminho).parent.mkdir(parents=True, exist_ok=True)
            (self.pasta / caminho).write_bytes(texto.encode("utf-8"))
        instalar.commitar(self.pasta, "alvo")

    def test_arquivo_proprio_do_alvo_fica_e_versao_velha_do_home_e_atualizada(self):
        primeira = instalar.rodar(["git", "log", "--diff-filter=A", "--format=%H", "--", "scripts/freios/principal.py"], cwd=instalar.RAIZ)
        velha = instalar.rodar(["git", "show", f"{primeira.split()[-1]}:scripts/freios/principal.py"], cwd=instalar.RAIZ)
        self.git_do_alvo({"scripts/freios/registro_da_pr.py": "regra do alvo\n", "scripts/freios/principal.py": velha})
        proprios = instalar.proprios_do_alvo(self.pasta, self.arquivos)
        self.assertEqual(proprios, ["scripts/freios/registro_da_pr.py"])
        mudados = instalar.copiar(self.pasta, SLUG, self.arquivos, proprios)
        self.assertEqual(self.ler("scripts/freios/registro_da_pr.py"), "regra do alvo\n")
        self.assertIn("scripts/freios/principal.py", mudados)

    def test_o_modelo_de_pr_aponta_para_as_issues_do_alvo(self):
        instalar.copiar(self.pasta, SLUG, self.arquivos)
        modelo = self.ler(".github/PULL_REQUEST_TEMPLATE.md")
        self.assertIn(f"https://github.com/{SLUG}/issues/", modelo)
        self.assertNotIn("/home-repo/issues/", modelo)

    def test_o_eslint_do_alvo_confere_o_repo_inteiro(self):
        instalar.copiar(self.pasta, SLUG, self.arquivos)
        limites = json.loads(self.ler("scripts/freios/limites.json"))
        eslint = next(f for f in limites["ferramentas"] if f["nome"] == "eslint")
        self.assertEqual(eslint["alvo_tudo"], ["."])

    def test_o_que_e_do_repo_fica_e_so_a_chave_nova_dos_limites_entra(self):
        instalar.copiar(self.pasta, SLUG, self.arquivos)
        limites = json.loads(self.ler("scripts/freios/limites.json"))
        limites["tamanho"]["linhas_maximas"] = 500
        del limites["funcoes"]
        (self.pasta / "scripts/freios/limites.json").write_text(json.dumps(limites), encoding="utf-8")
        (self.pasta / "scripts/freios/ruff.toml").write_text("line-length = 80\n", encoding="utf-8")
        (self.pasta / "scripts/freios/freios.py").write_text("velho\n", encoding="utf-8")
        mudados = instalar.copiar(self.pasta, SLUG, self.arquivos)
        limites = json.loads(self.ler("scripts/freios/limites.json"))
        self.assertEqual(limites["tamanho"]["linhas_maximas"], 500)
        self.assertIn("funcoes", limites)
        self.assertEqual(self.ler("scripts/freios/ruff.toml"), "line-length = 80\n")
        self.assertEqual(sorted(mudados), ["scripts/freios/freios.py", "scripts/freios/limites.json"])

    def test_rodar_de_novo_nao_muda_nada(self):
        instalar.copiar(self.pasta, SLUG, self.arquivos)
        self.assertEqual(instalar.copiar(self.pasta, SLUG, self.arquivos), [])

    def test_gitignore_existente_ganha_so_as_linhas_que_faltam(self):
        (self.pasta / ".gitignore").write_text("dist/\nnode_modules/", encoding="utf-8")
        instalar.copiar(self.pasta, SLUG, self.arquivos)
        linhas = self.ler(".gitignore").splitlines()
        self.assertEqual(linhas[:2], ["dist/", "node_modules/"])
        self.assertEqual(linhas.count("node_modules/"), 1)
        self.assertIn("__pycache__/", linhas)


class Protecao(unittest.TestCase):
    def test_so_exige_os_checks_que_os_workflows_do_alvo_rodam(self):
        with tempfile.TemporaryDirectory() as temporaria:
            workflows = Path(temporaria) / ".github/workflows"
            workflows.mkdir(parents=True)
            (workflows / "freios.yml").write_text("jobs:\n  freios:\n    name: Freios\n", encoding="utf-8")
            self.assertEqual(instalar.checks_do_alvo(Path(temporaria)), ["Freios"])

    def test_protecao_completa_nao_e_mudada_de_novo(self):
        atual = {"required_status_checks": {"checks": [{"context": c, "app_id": 15368} for c in instalar.CHECKS]},
                 "enforce_admins": {"enabled": True}}
        self.assertEqual([c[0] for c in instalar.chamadas_de_protecao(SLUG, "main", atual)], ["PATCH"])

    def test_sem_protecao_liga_tudo_de_uma_vez(self):
        chamadas = instalar.chamadas_de_protecao(SLUG, "main", None)
        self.assertEqual([c[:2] for c in chamadas], [("PATCH", f"repos/{SLUG}"), ("PUT", f"repos/{SLUG}/branches/main/protection")])
        corpo = chamadas[1][2]
        self.assertTrue(corpo["enforce_admins"])
        self.assertFalse(corpo["allow_force_pushes"])
        self.assertFalse(corpo["allow_deletions"])
        self.assertEqual([c["context"] for c in corpo["required_status_checks"]["checks"]], instalar.CHECKS)
        seguranca = chamadas[0][2]["security_and_analysis"]
        self.assertEqual(seguranca["secret_scanning_push_protection"], {"status": "enabled"})

    def test_protecao_existente_ganha_os_checks_sem_perder_os_dela(self):
        atual = {"required_status_checks": {"checks": [{"context": "Testes", "app_id": 1}, {"context": "Freios", "app_id": 15368}]},
                 "enforce_admins": {"enabled": False}}
        chamadas = instalar.chamadas_de_protecao(SLUG, "main", atual)
        checks = chamadas[1][2]["checks"]
        self.assertEqual([c["context"] for c in checks], ["Testes", "Freios", "Registro da PR", "Auditoria de dependências"])
        self.assertEqual(chamadas[2][:2], ("POST", f"repos/{SLUG}/branches/main/protection/enforce_admins"))

    def test_admin_ja_travado_nao_e_chamado_de_novo(self):
        atual = {"required_status_checks": {"checks": [{"context": "Testes", "app_id": 1}]}, "enforce_admins": {"enabled": True}}
        self.assertEqual(len(instalar.chamadas_de_protecao(SLUG, "main", atual)), 2)

    def test_protecao_sem_checks_exigidos_recusa_em_vez_de_sobrescrever(self):
        with self.assertRaises(instalar.Falha):
            instalar.chamadas_de_protecao(SLUG, "main", {"required_status_checks": None})


class Comando(unittest.TestCase):
    def test_simular_num_repo_existente_nao_escreve_nada(self):
        gh, saida = GhFalso(), io.StringIO()
        self.assertEqual(instalar.instalar(Argumentos(alvo=SLUG), gh, saida), 0)
        self.assertEqual(gh.escritas(), [])
        self.assertIn("Simulação", saida.getvalue())
        self.assertIn("espera a PR entrar", saida.getvalue())
        self.assertNotIn("/protection", saida.getvalue())

    def test_simular_o_novo_mostra_a_protecao(self):
        saida = io.StringIO()
        instalar.instalar(Argumentos(novo="alvo"), GhFalso(), saida)
        self.assertIn("PUT repos/alvo/branches/main/protection", saida.getvalue())

    def test_simular_o_novo_nao_cria_o_repo(self):
        gh = GhFalso()
        instalar.instalar(Argumentos(novo="alvo"), gh, io.StringIO())
        self.assertFalse(any(c[:3] == ["gh", "repo", "create"] for c, _ in gh.chamados))

    def test_repo_existente_vai_por_pr_e_a_protecao_espera_a_pr(self):
        gh = GhFalso()
        instalar.instalar(Argumentos(alvo=SLUG, simular=False), gh, io.StringIO())
        escritas = gh.escritas()
        self.assertEqual(escritas[0][:2], ["git", "push"])
        self.assertEqual(escritas[1][:3], ["gh", "pr", "create"])
        self.assertEqual(escritas[2:], [["gh", "api", "-X", "PATCH", f"repos/{SLUG}", "--input", "-"]])

    def test_com_a_pr_dos_freios_aberta_nao_abre_outra(self):
        gh = GhFalso(prs=[{"headRefName": "freios/instalar-2026-01-01", "url": "https://x/pull/1"}])
        saida = io.StringIO()
        instalar.instalar(Argumentos(alvo=SLUG, simular=False), gh, saida)
        self.assertFalse(any(c[:3] == ["gh", "pr", "create"] or c[:2] == ["git", "push"] for c in gh.escritas()))
        self.assertIn("https://x/pull/1", saida.getvalue())

    def test_novo_cria_empurra_a_main_e_protege(self):
        gh = GhFalso()
        instalar.instalar(Argumentos(novo="alvo", simular=False), gh, io.StringIO())
        comandos = [c for c, _ in gh.chamados]
        self.assertEqual(comandos[0], ["gh", "repo", "create", "alvo", "--public"])
        self.assertIn(["git", "push", "-q", "origin", "main"], comandos)
        self.assertFalse(any(c[:2] == ["gh", "pr"] for c in comandos))

    def test_novo_privado_e_recusado_antes_de_criar(self):
        erro = io.StringIO()
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(erro):
            instalar.ler_argumentos(["--novo", "alvo", "--privado"])
        self.assertIn("conta Free", erro.getvalue())

    def test_repo_privado_existente_recebe_os_freios_sem_a_protecao_e_avisa(self):
        gh, saida = GhFalso(privado=True), io.StringIO()
        self.assertEqual(instalar.instalar(Argumentos(alvo=SLUG, simular=False), gh, saida), 0)
        self.assertTrue(any(c[:3] == ["gh", "pr", "create"] for c in gh.escritas()))
        self.assertFalse(any(c[:3] == ["gh", "api", "-X"] for c in gh.escritas()))
        self.assertIn("ficaram de fora", saida.getvalue())

    def test_alvo_e_novo_juntos_sao_recusados(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            instalar.ler_argumentos(["dono/x", "--novo", "y"])


if __name__ == "__main__":
    unittest.main()
