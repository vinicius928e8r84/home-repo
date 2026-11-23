import shutil
import unittest
from pathlib import Path

from scripts.freios import skills
from scripts.freios.apoio_de_teste import RepositorioTemporario, contexto_de_memoria
from scripts.freios.git import montar_contexto

VALIDADOR_REAL = Path(__file__).resolve().parents[2] / skills.VALIDADOR
SKILL_VALIDA = "---\nname: ola\ndescription: Diz ola. Use quando o usuario cumprimentar.\n---\n\nCorpo.\n"
LINK = "../../.agents/skills/"


def memoria(arquivos=(), links=None):
    conteudo = {f".agents/skills/{nome}/SKILL.md": SKILL_VALIDA for nome in arquivos}
    return contexto_de_memoria(conteudo, links=links)


class TesteDosLinksDosSkills(unittest.TestCase):
    def test_skill_com_link_certo_passa(self):
        ctx = memoria(["ola"], {".claude/skills/ola": LINK + "ola"})
        self.assertEqual(skills.verificar(ctx), [])

    def test_skill_sem_link_falha(self):
        achados = skills.verificar(memoria(["ola"]))
        self.assertEqual([a.arquivo for a in achados], [".claude/skills/ola"])

    def test_link_sem_skill_falha(self):
        achados = skills.verificar(memoria([], {".claude/skills/fantasma": LINK + "fantasma"}))
        self.assertEqual([a.arquivo for a in achados], [".claude/skills/fantasma"])
        self.assertIn("não existe", achados[0].detalhe)

    def test_link_que_aponta_para_outro_skill_falha(self):
        ctx = memoria(["ola", "tchau"], {".claude/skills/ola": LINK + "tchau", ".claude/skills/tchau": LINK + "tchau"})
        achados = skills.verificar(ctx)
        self.assertEqual([a.arquivo for a in achados], [".claude/skills/ola"])

    def test_arquivo_comum_dentro_de_claude_skills_falha(self):
        ctx = contexto_de_memoria({".claude/skills/x/SKILL.md": SKILL_VALIDA})
        self.assertEqual(len(skills.verificar(ctx)), 1)

    def test_pasta_sem_skill_md_nao_conta_como_skill(self):
        ctx = contexto_de_memoria({".agents/skills/ola/notas.md": "x"})
        self.assertEqual(skills.verificar(ctx), [])


@unittest.skipUnless(VALIDADOR_REAL.exists(), "sem validate.py")
class TesteDoValidador(unittest.TestCase):
    def montar(self, conteudo_do_skill):
        repo = RepositorioTemporario()
        self.addCleanup(repo.limpar)
        validador = repo.raiz / skills.VALIDADOR
        validador.parent.mkdir(parents=True)
        shutil.copy(VALIDADOR_REAL, validador)
        repo.git("add", skills.VALIDADOR)
        repo.adicionar(".agents/skills/ola/SKILL.md", conteudo_do_skill)
        repo.adicionar_link(".claude/skills/ola", LINK + "ola")
        repo.adicionar_link(".claude/skills/writing-for-agents", LINK + "writing-for-agents")
        repo.adicionar(".agents/skills/writing-for-agents/SKILL.md", SKILL_VALIDA.replace("ola", "writing-for-agents"))
        return montar_contexto(repo.raiz, "tudo", "origin/main")

    def test_skill_valido_passa(self):
        self.assertEqual(skills.verificar(self.montar(SKILL_VALIDA)), [])

    def test_skill_invalido_falha_com_a_mensagem_do_validador(self):
        achados = skills.verificar(self.montar("sem frontmatter\n"))
        self.assertEqual([a.arquivo for a in achados], [".agents/skills/ola/SKILL.md"])
        self.assertIn("frontmatter", achados[0].detalhe)

    def test_sem_o_validador_no_repositorio_falha(self):
        ctx = memoria(["ola"], {".claude/skills/ola": LINK + "ola"})
        ctx.raiz = Path(".")
        achados = skills.verificar(ctx)
        self.assertEqual([a.arquivo for a in achados], [skills.VALIDADOR])


if __name__ == "__main__":
    unittest.main()
