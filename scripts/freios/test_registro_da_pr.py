import unittest

from registro_da_pr import (
    CAMINHOS_SENSIVEIS,
    Pr,
    caminhos_sensiveis,
    conferir,
    falta_da_issue,
    marca_de_prova_parcial,
    risco_do_revisor,
)
from registro_texto import linhas_que_valem

HEAD = "a" * 40
OUTRO = "b" * 40
REPO = "vinicius928e8r84/home-repo"
ISSUE = f"https://github.com/{REPO}/issues/12"
FECHA = f"Closes {ISSUE}"
CAMINHOS_DE_TESTE = (
    "scripts/freios/freios.py",
    ".github/workflows/freios.yml",
    "scripts/crew.py",
    ".pi/extensions/fm-calm.ts",
    "model_routing.json",
    "repos.json",
    "AGENTS.md",
    "CLAUDE.md",
    ".agents/skills/pr/SKILL.md",
)


def revisao(head, **campos):
    dados = {"risco": "BAIXA", "veredito": "CLEAN", "autor": "agente-a", "revisor": "agente-b", **campos}
    linhas = [
        "Registro de revisão independente",
        "",
        f"Veredito: {dados['veredito']}",
        f"Head: {head}",
        f"Autor: {dados['autor']}",
        f"Revisor: {dados['revisor']}",
        f"Risco: {dados['risco']}",
    ]
    return "\n".join(linhas) + "\n"


def prova(head):
    return (
        f"## Prova real\n\nPROVADO 100% REAL\nHead: {head}\n\n"
        "Rodei o workflow numa PR de teste e o check apareceu verde no head.\n"
    )


def pr(corpo, **mudancas):
    base = {
        "corpo": corpo,
        "head": HEAD,
        "registros": [revisao(HEAD)],
        "arquivos": ["wiki/index.md"],
        "autor": "dono",
        "repositorio": REPO,
    }
    return Pr(**{**base, **mudancas})


class RegistroPassa(unittest.TestCase):
    def test_baixa_com_closes_e_revisao_limpa(self):
        ok, mensagem = conferir(pr(f"Atenção: BAIXA\n\n{FECHA}\n"))
        self.assertTrue(ok, mensagem)
        self.assertIn("atenção BAIXA", mensagem)

    def test_sem_issue_vale(self):
        ok, mensagem = conferir(pr("Atenção: MÉDIA\n\nSem issue\n"))
        self.assertTrue(ok, mensagem)

    def test_alta_com_prova_no_head_exato(self):
        ok, mensagem = conferir(pr(f"**Atenção:** ALTA\n\n{FECHA}\n\n{prova(HEAD)}"))
        self.assertTrue(ok, mensagem)
        self.assertIn("PROVADO 100% REAL", mensagem)

    def test_cada_caminho_sensivel_com_alta_e_prova_passa(self):
        corpo = f"Atenção: ALTA\n\n{FECHA}\n\n{prova(HEAD)}"
        for caminho in CAMINHOS_DE_TESTE:
            with self.subTest(caminho=caminho):
                ok, mensagem = conferir(pr(corpo, arquivos=[caminho]))
                self.assertTrue(ok, mensagem)

    def test_cada_caminho_sensivel_com_alta_sem_prova_reprova(self):
        for caminho in CAMINHOS_DE_TESTE:
            with self.subTest(caminho=caminho):
                ok, mensagem = conferir(pr(f"Atenção: ALTA\n\n{FECHA}", arquivos=[caminho]))
                self.assertFalse(ok, mensagem)
                self.assertIn("não tem a seção", mensagem)

    def test_caminhos_parecidos_mas_fora_da_lista_nao_sao_sensiveis(self):
        parecidos = [
            "scripts/crew.pyc", "scripts/crew.py.bak", "wiki/AGENTS.md", "docs/CLAUDE.md",
            "model_routing.json.bak", "repos.jsonl", ".pit/x", ".github-old/x", ".agents/other/x",
            "scripts/freios-old/x.py", ".agents/skills",
        ]
        self.assertEqual(caminhos_sensiveis(parecidos), [])

    def test_a_lista_de_teste_cobre_toda_a_lista_do_check(self):
        self.assertEqual(len(CAMINHOS_DE_TESTE), len(CAMINHOS_SENSIVEIS))
        for sensivel, exemplo in zip(CAMINHOS_SENSIVEIS, CAMINHOS_DE_TESTE, strict=True):
            self.assertTrue(exemplo.startswith(sensivel), (sensivel, exemplo))

    def test_vale_a_revisao_do_head_mesmo_com_uma_antiga_antes(self):
        ok, mensagem = conferir(pr(f"Atenção: BAIXA\n{FECHA}", registros=[revisao(OUTRO), revisao(HEAD)]))
        self.assertTrue(ok, mensagem)


class AtencaoFalha(unittest.TestCase):
    def falha(self, corpo, trecho, **mudancas):
        ok, mensagem = conferir(pr(corpo, **mudancas))
        self.assertFalse(ok, mensagem)
        self.assertIn(trecho, mensagem)

    def test_sem_a_linha_de_atencao(self):
        self.falha(FECHA, "não tem a linha de atenção")

    def test_valor_invalido(self):
        self.falha(f"Atenção: média-alta\n{FECHA}", "não é BAIXA nem MÉDIA nem ALTA")

    def test_duas_atencoes(self):
        self.falha(f"Atenção: BAIXA\nAtenção: ALTA\n{FECHA}", "mais de uma atenção")

    def test_atencao_dentro_de_comentario_html_ou_bloco_de_codigo_nao_conta(self):
        self.falha(f"<!-- Atenção: BAIXA -->\n{FECHA}", "não tem a linha de atenção")
        self.falha(f"```\nAtenção: BAIXA\n```\n{FECHA}", "não tem a linha de atenção")

    def test_caminho_sensivel_com_atencao_menor_que_alta(self):
        for caminho in ("scripts/freios/freios.py", ".github/workflows/freios.yml"):
            with self.subTest(caminho=caminho):
                self.falha(f"Atenção: BAIXA\n{FECHA}", "mexe em caminho sensível", arquivos=[caminho])

    def test_cada_caminho_sensivel_reprova_com_baixa_e_com_media(self):
        for caminho in CAMINHOS_DE_TESTE:
            for atencao in ("BAIXA", "MÉDIA"):
                with self.subTest(caminho=caminho, atencao=atencao):
                    trecho = f"conta como ALTA, mas o corpo diz {atencao}: {caminho}"
                    self.falha(f"Atenção: {atencao}\n{FECHA}", trecho, arquivos=[caminho])

    def test_caminho_movido_para_fora_da_pasta_sensivel_conta(self):
        self.falha(f"Atenção: MÉDIA\n{FECHA}", "conta como ALTA", arquivos=["scripts/freios/antigo.py"])


class IssueFalha(unittest.TestCase):
    def falha(self, corpo, trecho):
        ok, mensagem = conferir(pr(f"Atenção: BAIXA\n\n{corpo}\n"))
        self.assertFalse(ok, mensagem)
        self.assertIn(trecho, mensagem)

    def test_corpo_sem_issue_nem_sem_issue(self):
        self.falha("Só descrevo a mudança.", "o corpo não diz a issue")

    def test_numero_solto_nao_vale(self):
        self.falha("Closes #12", "não tem a URL completa da issue")

    def test_issue_de_outro_repositorio_nao_vale(self):
        self.falha("Closes https://github.com/outro/repo/issues/3", "não tem a URL completa da issue")

    def test_closes_em_bloco_de_codigo_ou_citacao_nao_conta(self):
        self.falha(f"```\n{FECHA}\n```", "o corpo não diz a issue")
        self.falha(f"> {FECHA}", "o corpo não diz a issue")

    def test_sem_issue_no_meio_de_frase_nao_conta(self):
        self.falha("Esta PR é Sem issue por enquanto.", "o corpo não diz a issue")

    def test_varias_issues_por_linha_sozinha(self):
        linhas = linhas_que_valem(f"{FECHA}\nCloses https://github.com/{REPO}/issues/13\n")
        self.assertIsNone(falta_da_issue(linhas, REPO))

    def test_sem_repositorio_conhecido_aceita_qualquer_dono(self):
        linhas = linhas_que_valem("Closes https://github.com/outro/repo/issues/3")
        self.assertIsNone(falta_da_issue(linhas, None))


class RevisaoFalha(unittest.TestCase):
    CORPO = f"Atenção: BAIXA\n{FECHA}\n"

    def falha(self, trecho, **mudancas):
        ok, mensagem = conferir(pr(self.CORPO, **mudancas))
        self.assertFalse(ok, mensagem)
        self.assertIn(trecho, mensagem)

    def test_sem_nenhum_registro(self):
        self.falha("nenhum comentário ou revisão", registros=[])

    def test_registro_de_outro_head_diz_que_o_head_mudou(self):
        self.falha("o head mudou", registros=[revisao(OUTRO)])

    def test_head_abreviado(self):
        self.falha("abreviado", registros=[revisao(HEAD[:8])])

    def test_veredito_que_nao_e_clean(self):
        self.falha("não CLEAN", registros=[revisao(HEAD, veredito="MUDANÇAS")])

    def test_veredito_ruim_no_head_nao_se_desfaz_com_outro_comentario(self):
        self.falha("não CLEAN", registros=[revisao(HEAD, veredito="MUDANÇAS"), revisao(HEAD)])

    def test_revisor_igual_ao_autor_do_registro(self):
        self.falha("próprio autor", registros=[revisao(HEAD, revisor="agente-a")])

    def test_revisor_e_quem_abriu_a_pr(self):
        self.falha("é quem abriu a PR", registros=[revisao(HEAD, revisor="Dono")])

    def test_sem_risco(self):
        texto = revisao(HEAD).replace("Risco: BAIXA\n", "")
        self.falha("não diz o risco", registros=[texto])

    def test_registro_citado_em_resposta_nao_conta(self):
        citado = "> " + revisao(HEAD).replace("\n", "\n> ")
        self.falha("nenhum comentário ou revisão", registros=[citado])

    def test_registro_sem_veredito_nao_conta(self):
        texto = revisao(HEAD).replace("Veredito: CLEAN\n", "")
        self.falha("nenhum comentário ou revisão", registros=[texto])


class ProvaFalha(unittest.TestCase):
    def falha(self, trecho_do_corpo, trecho, **mudancas):
        ok, mensagem = conferir(pr(f"Atenção: ALTA\n{FECHA}\n\n{trecho_do_corpo}", **mudancas))
        self.assertFalse(ok, mensagem)
        self.assertIn(trecho, mensagem)

    def test_sem_a_secao(self):
        self.falha("", "não tem a seção \"Prova real\"")

    def test_head_abreviado_ou_de_outro_commit(self):
        self.falha(prova(HEAD[:8]), "abreviado")
        self.falha(prova(OUTRO), "o head mudou")

    def test_sem_a_frase(self):
        self.falha(f"## Prova real\n\nHead: {HEAD}\n", "não tem a linha PROVADO 100% REAL")

    def test_explicacao_curta(self):
        self.falha(f"## Prova real\n\nPROVADO 100% REAL\nHead: {HEAD}\nok\n", "não explica o que foi provado")

    def test_prova_parcial_nao_vale(self):
        texto = prova(HEAD) + "\nNÃO COBERTO: o gancho de pre-push.\n"
        self.falha(texto, "prova parcial não vale")
        self.falha(prova(HEAD).replace("PROVADO 100% REAL", "BLOQUEADA-parcial"), "prova parcial não vale")

    def test_secao_so_em_comentario_html_nao_conta(self):
        self.falha(f"<!--\n{prova(HEAD)}-->", "não tem a seção")

    def test_revisor_com_risco_alta_pede_prova_mesmo_com_corpo_media(self):
        ok, mensagem = conferir(pr(f"Atenção: MÉDIA\n{FECHA}\n", registros=[revisao(HEAD, risco="ALTA")]))
        self.assertFalse(ok, mensagem)
        self.assertIn("o revisor disse Risco: ALTA, o corpo diz MÉDIA", mensagem)

    def test_prova_de_secao_posterior_nao_vaza_para_a_anterior(self):
        corpo = f"## Prova real\n\n## Outra\n\nPROVADO 100% REAL\nHead: {HEAD}\n"
        self.falha(corpo, "não tem a linha PROVADO 100% REAL")


class Ajudantes(unittest.TestCase):
    def test_risco_do_revisor_so_conta_registro_do_head(self):
        registros = [revisao(OUTRO, risco="ALTA"), revisao(HEAD, risco="MÉDIA")]
        self.assertEqual(risco_do_revisor(registros, HEAD), "MÉDIA")
        self.assertIsNone(risco_do_revisor([revisao(OUTRO)], HEAD))

    def test_marca_de_prova_parcial(self):
        self.assertEqual(marca_de_prova_parcial("**NÃO COBERTO**: x"), "NAO COBERTO")
        self.assertEqual(marca_de_prova_parcial("bloqueadas"), "BLOQUEADAS")
        self.assertIsNone(marca_de_prova_parcial("cobertura total"))


if __name__ == "__main__":
    unittest.main()
