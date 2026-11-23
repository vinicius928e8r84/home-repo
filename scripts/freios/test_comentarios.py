import unittest

from scripts.freios import comentarios
from scripts.freios.apoio_de_teste import contexto_de_memoria
from scripts.freios.lexico import achar_comentarios


def linhas(extensao, texto):
    return [linha for linha, _ in achar_comentarios(extensao, texto)]


class TesteDeComentariosEmPython(unittest.TestCase):
    def test_acha_comentario_de_linha_e_de_fim_de_linha(self):
        self.assertEqual(linhas(".py", "# a\nx = 1  # b\n"), [1, 2])

    def test_cerquilha_dentro_de_texto_nao_e_comentario(self):
        self.assertEqual(linhas(".py", 'x = "# nada"\ny = \'#\'\n'), [])

    def test_docstring_de_modulo_funcao_e_classe_conta(self):
        codigo = '"""m"""\n\n\ndef f():\n    """f"""\n\n\nclass C:\n    """c"""\n'
        self.assertEqual(linhas(".py", codigo), [1, 5, 9])

    def test_texto_comum_atribuido_nao_conta(self):
        self.assertEqual(linhas(".py", 'USO = """como usar"""\nx = "a"\n'), [])

    def test_texto_solto_no_meio_do_codigo_conta(self):
        self.assertEqual(linhas(".py", 'x = 1\n"solto"\n'), [2])

    def test_arquivo_com_erro_de_sintaxe_ainda_acha_os_comentarios_do_inicio(self):
        self.assertEqual(linhas(".py", "# a\nx = (\n"), [1])


class TesteDeComentariosEmJs(unittest.TestCase):
    def test_acha_linha_e_bloco(self):
        self.assertEqual(linhas(".ts", "// a\nlet x = 1; /* b\nc */\n"), [1, 2])

    def test_barras_dentro_de_texto_nao_contam(self):
        codigo = "const a = 'http://x';\nconst b = \"// nada\";\n"
        self.assertEqual(linhas(".js", codigo), [])

    def test_barras_dentro_de_regex_nao_contam(self):
        codigo = "const r = /https?:\\/\\/[^/]+\\//;\nconst s = x.replace(/a\\/\\/b/g, '');\n"
        self.assertEqual(linhas(".js", codigo), [])

    def test_divisao_nao_vira_regex_e_o_comentario_depois_dela_aparece(self):
        self.assertEqual(linhas(".js", "const c = a / b / d; // nota\n"), [1])

    def test_comentario_dentro_de_expressao_de_molde_conta(self):
        codigo = "const t = `a ${ x /* c */ } b`;\n"
        self.assertEqual(linhas(".ts", codigo), [1])

    def test_barras_dentro_do_texto_do_molde_nao_contam(self):
        codigo = "const t = `// ${a} // ${ `//` }`;\nconst u = 1;\n"
        self.assertEqual(linhas(".ts", codigo), [])

    def test_chaves_aninhadas_dentro_do_molde(self):
        codigo = "const t = `${ {a: 1}.a } // texto`;\n// fora\n"
        self.assertEqual(linhas(".ts", codigo), [2])

    def test_regex_depois_de_return(self):
        self.assertEqual(linhas(".js", "return /a\\/\\/b/.test(x);\n"), [])


class TesteDeComentariosEmShell(unittest.TestCase):
    def test_acha_comentario_de_linha_inteira_e_de_fim_de_linha(self):
        self.assertEqual(linhas(".sh", "# a\necho oi # b\n"), [1, 2])

    def test_cerquilha_em_texto_e_expansao_nao_conta(self):
        codigo = "echo '# a' \"# b\" ${x#pre} $# ${#x} a#b\n"
        self.assertEqual(linhas(".sh", codigo), [])

    def test_corpo_de_heredoc_nao_conta(self):
        codigo = "cat <<EOF\n# dentro\nEOF\n# fora\n"
        self.assertEqual(linhas(".sh", codigo), [4])

    def test_heredoc_com_aspas_e_traco(self):
        codigo = "cat <<-'FIM'\n\t# dentro\n\tFIM\necho # fora\n"
        self.assertEqual(linhas(".sh", codigo), [4])

    def test_comentario_na_linha_de_abertura_do_heredoc_conta(self):
        self.assertEqual(linhas(".sh", "cat <<EOF # c\ntexto\nEOF\n"), [1])

    def test_escape_antes_da_cerquilha(self):
        self.assertEqual(linhas(".sh", "echo \\# nada\n"), [])


class TesteDeComentariosEmYamlToml(unittest.TestCase):
    def test_yaml_acha_comentario_e_ignora_texto_e_bloco(self):
        codigo = "a: 1  # c\nb: 'x # y'\nc: |\n  # dentro\n  texto\nd: 2\n# f\n"
        self.assertEqual(linhas(".yaml", codigo), [1, 7])

    def test_yaml_sem_espaco_antes_da_cerquilha_nao_e_comentario(self):
        self.assertEqual(linhas(".yml", "url: http://x/#y\n"), [])

    def test_yaml_valor_terminado_em_maior_nao_abre_bloco(self):
        self.assertEqual(linhas(".yml", "a: <b>\n  # c\n"), [2])

    def test_toml_acha_comentario_e_ignora_texto(self):
        codigo = "a = \"# x\"\nb = '''\n# y\n'''\n# z\n"
        self.assertEqual(linhas(".toml", codigo), [5])


class TesteDeComentariosEmPowershell(unittest.TestCase):
    def test_acha_linha_e_bloco(self):
        self.assertEqual(linhas(".ps1", "# a\nWrite-Host 'oi # nada'\n<# b\nc #>\n"), [1, 3])


class TesteDaVerificacao(unittest.TestCase):
    def verificar(self, arquivos, excecoes=None):
        return comentarios.verificar(contexto_de_memoria(arquivos, excecoes=excecoes))

    def test_shebang_da_linha_um_passa_e_o_da_linha_dois_nao(self):
        self.assertEqual(self.verificar({"a.py": "#!/usr/bin/env python3\nx = 1\n"}), [])
        achados = self.verificar({"b.py": "x = 1\n#!/usr/bin/env python3\n"})
        self.assertEqual([a.linha for a in achados], [2])

    def test_diretiva_com_codigo_de_regra_passa(self):
        self.assertEqual(self.verificar({"a.py": "import os  # noqa: F401\n"}), [])
        self.assertEqual(self.verificar({"b.py": "import os  # noqa: F401, E402\n"}), [])
        self.assertEqual(self.verificar({"c.ts": "// @ts-expect-error\nx();\n"}), [])

    def test_noqa_sem_codigo_e_eslint_disable_nao_passam(self):
        self.assertEqual(len(self.verificar({"a.py": "import os  # noqa\n"})), 1)
        self.assertEqual(len(self.verificar({"b.js": "// eslint-disable-next-line no-console\n"})), 1)
        self.assertEqual(len(self.verificar({"c.ts": "// @ts-expect-error porque sim\n"})), 1)

    def test_markdown_e_json_ficam_fora(self):
        arquivos = {"a.md": "<!-- nota -->\n# titulo\n", "b.json": "{}\n"}
        self.assertEqual(self.verificar(arquivos), [])

    def test_extensao_em_maiuscula_tambem_conta(self):
        self.assertEqual(len(self.verificar({"A.PY": "# a\n"})), 1)

    def test_excecao_com_motivo_libera_o_arquivo(self):
        excecoes = {"comentarios": [{"glob": "vendor/", "motivo": "terceiro"}]}
        arquivos = {"vendor/a.py": "# a\n", "b.py": "# b\n"}
        achados = self.verificar(arquivos, excecoes)
        self.assertEqual([a.arquivo for a in achados], ["b.py"])

    def test_achado_traz_arquivo_linha_e_resumo(self):
        achado = self.verificar({"a.sh": "echo\n# explica o que faz\n"})[0]
        self.assertEqual((achado.arquivo, achado.linha), ("a.sh", 2))
        self.assertEqual(achado.detalhe, "# explica o que faz")


if __name__ == "__main__":
    unittest.main()
