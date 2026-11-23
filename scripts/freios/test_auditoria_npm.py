import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.freios import auditoria_npm
from scripts.freios.auditoria_npm import ErroDeAuditoria, main, novas_altas, npm_audit

PASTA = "scripts/freios"
LIMPO = {"vulnerabilities": {}}


def achado(severidade, titulo="Prototype pollution"):
    return {"severity": severidade, "range": "<1.2.3", "via": [{"title": titulo}, "outro-pacote"]}


def relatorio(**achados):
    return {"vulnerabilities": achados}


class Repositorio:
    def __init__(self, pasta):
        self.pasta = Path(pasta)
        self.git("init", "-q", "-b", "main")

    def git(self, *args):
        comando = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args]
        subprocess.run(comando, cwd=self.pasta, check=True, capture_output=True)

    def escrever(self, caminho, texto):
        alvo = self.pasta / caminho
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(texto, encoding="utf-8", newline="\n")

    def remover(self, caminho):
        (self.pasta / caminho).unlink()

    def commitar(self, mensagem):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", mensagem)

    def ramo(self, nome):
        self.git("checkout", "-q", "-b", nome)


def auditor_dos_relatorios(por_trava):
    chamadas = []

    def auditor(pasta):
        trava = (Path(pasta) / "package-lock.json").read_text(encoding="utf-8")
        chamadas.append(pasta)
        return por_trava[trava]

    auditor.chamadas = chamadas
    return auditor


def rodar(repo, *argv, auditor=None):
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        codigo = main(["--raiz", str(repo.pasta), *argv], auditor=auditor or auditor_dos_relatorios({}))
    return codigo, saida.getvalue()


class AuditoriaDaMudanca(unittest.TestCase):
    def setUp(self):
        self.temporario = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporario.cleanup)
        self.repo = Repositorio(self.temporario.name)
        self.repo.escrever(f"{PASTA}/package.json", "{}")
        self.repo.escrever(f"{PASTA}/package-lock.json", "v1")
        self.repo.escrever("README.md", "oi")
        self.repo.commitar("base")
        self.repo.ramo("pi/mudanca")

    def test_sem_mudanca_em_trava_nao_audita_nada(self):
        self.repo.escrever("README.md", "outra")
        self.repo.commitar("doc")
        auditor = auditor_dos_relatorios({})
        codigo, saida = rodar(self.repo, "--base", "main", auditor=auditor)
        self.assertEqual(codigo, 0)
        self.assertIn("nenhuma trava de pacotes mudou", saida)
        self.assertEqual(auditor.chamadas, [])

    def test_vulnerabilidade_alta_nova_falha(self):
        self.repo.escrever(f"{PASTA}/package-lock.json", "v2")
        self.repo.commitar("sobe pacote")
        auditor = auditor_dos_relatorios({"v1": LIMPO, "v2": relatorio(lodash=achado("high"))})
        codigo, saida = rodar(self.repo, "--base", "main", auditor=auditor)
        self.assertEqual(codigo, 1, saida)
        self.assertIn(f"✗ {PASTA}/package-lock.json: lodash (high, <1.2.3) Prototype pollution", saida)
        self.assertIn("Conserto:", saida)

    def test_vulnerabilidade_critica_nova_falha(self):
        self.repo.escrever(f"{PASTA}/package-lock.json", "v2")
        self.repo.commitar("sobe pacote")
        auditor = auditor_dos_relatorios({"v1": LIMPO, "v2": relatorio(x=achado("critical"))})
        self.assertEqual(rodar(self.repo, "--base", "main", auditor=auditor)[0], 1)

    def test_vulnerabilidade_que_a_base_ja_tinha_nao_falha(self):
        self.repo.escrever(f"{PASTA}/package-lock.json", "v2")
        self.repo.commitar("sobe pacote")
        velha = relatorio(lodash=achado("high"))
        codigo, saida = rodar(self.repo, "--base", "main", auditor=auditor_dos_relatorios({"v1": velha, "v2": velha}))
        self.assertEqual(codigo, 0, saida)
        self.assertIn("não introduz vulnerabilidade high/critical", saida)

    def test_baixa_e_moderada_novas_nao_falham(self):
        self.repo.escrever(f"{PASTA}/package-lock.json", "v2")
        self.repo.commitar("sobe pacote")
        novas = relatorio(a=achado("low"), b=achado("moderate"))
        codigo, _ = rodar(self.repo, "--base", "main", auditor=auditor_dos_relatorios({"v1": LIMPO, "v2": novas}))
        self.assertEqual(codigo, 0)

    def test_trava_nova_sem_base_conta_tudo_como_novo(self):
        self.repo.escrever("outra/package.json", "{}")
        self.repo.escrever("outra/package-lock.json", "v3")
        self.repo.commitar("pasta nova")
        auditor = auditor_dos_relatorios({"v3": relatorio(y=achado("high"))})
        codigo, saida = rodar(self.repo, "--base", "main", auditor=auditor)
        self.assertEqual(codigo, 1, saida)
        self.assertIn("outra/package-lock.json: y", saida)

    def test_trava_apagada_nao_e_auditada(self):
        self.repo.remover(f"{PASTA}/package-lock.json")
        self.repo.commitar("apaga")
        codigo, saida = rodar(self.repo, "--base", "main")
        self.assertEqual(codigo, 0)
        self.assertIn("nenhuma trava", saida)

    def test_base_toda_de_zeros_nao_audita(self):
        codigo, saida = rodar(self.repo, "--base", "0" * 40)
        self.assertEqual(codigo, 0)
        self.assertIn("sem base de comparação", saida)

    def test_base_que_nao_existe_sai_com_2(self):
        codigo, saida = rodar(self.repo, "--base", "nao-existe")
        self.assertEqual(codigo, 2)
        self.assertIn("não é um commit deste repositório", saida)

    def test_falha_do_npm_sai_com_2(self):
        self.repo.escrever(f"{PASTA}/package-lock.json", "v2")
        self.repo.commitar("sobe pacote")

        def quebrado(pasta):
            raise ErroDeAuditoria("o registro não respondeu")

        codigo, saida = rodar(self.repo, "--base", "main", auditor=quebrado)
        self.assertEqual(codigo, 2)
        self.assertIn("o registro não respondeu", saida)

    def test_trava_sem_package_json_ao_lado_sai_com_2(self):
        self.repo.remover(f"{PASTA}/package.json")
        self.repo.escrever(f"{PASTA}/package-lock.json", "v2")
        self.repo.commitar("sem package.json")
        codigo, saida = rodar(self.repo, "--base", "main")
        self.assertEqual(codigo, 2)
        self.assertIn("package.json ao lado dela", saida)


class NovasAltas(unittest.TestCase):
    def test_so_o_que_a_base_nao_tinha_e_so_alta_ou_critica(self):
        base = relatorio(velho=achado("high"))
        ramo = relatorio(velho=achado("high"), novo=achado("critical"), leve=achado("low"))
        self.assertEqual([a["nome"] for a in novas_altas(base, ramo)], ["novo"])

    def test_sem_base_tudo_e_novo(self):
        self.assertEqual(len(novas_altas(None, relatorio(a=achado("high"), b=achado("critical")))), 2)

    def test_titulos_ignoram_vias_que_sao_so_o_nome_de_outro_pacote(self):
        achados = novas_altas(None, relatorio(a=achado("high", "Titulo")))
        self.assertEqual(achados[0]["titulos"], ["Titulo"])


class ChamadaDoNpm(unittest.TestCase):
    def rodar_com(self, stdout, stderr=""):
        feito = subprocess.CompletedProcess([], 1, stdout=stdout, stderr=stderr)
        with mock.patch.object(auditoria_npm.subprocess, "run", return_value=feito):
            with mock.patch.object(auditoria_npm.shutil, "which", return_value="npm"):
                return npm_audit("pasta")

    def test_le_o_json_mesmo_com_codigo_de_saida_diferente_de_zero(self):
        self.assertEqual(self.rodar_com(json.dumps(relatorio(a=achado("high")))), relatorio(a=achado("high")))

    def test_saida_que_nao_e_json(self):
        with self.assertRaisesRegex(ErroDeAuditoria, "não produziu JSON"):
            self.rodar_com("", "npm ERR! network")

    def test_erro_do_npm(self):
        with self.assertRaisesRegex(ErroDeAuditoria, "ENOLOCK"):
            self.rodar_com(json.dumps({"error": {"code": "ENOLOCK", "summary": "ENOLOCK sem trava"}}))

    def test_sem_npm_instalado(self):
        with mock.patch.object(auditoria_npm.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ErroDeAuditoria, "npm não está instalado"):
                npm_audit("pasta")


if __name__ == "__main__":
    unittest.main()
