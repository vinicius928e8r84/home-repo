import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.freios import dados_pessoais, principal, sem_pulo
from scripts.freios.apoio_de_teste import RepositorioTemporario, contexto_de_memoria

NL = chr(10)
BARRA = chr(92)
EMAIL_PESSOAL = "fulana" + "@" + "provedor.com"
IP_PRIVADO = ".".join(["10", "9", "8", "7"])
IP_DO_TAILNET = ".".join(["100", "64", "1", "2"])
IP_PUBLICO = ".".join(["198", "18", "0", "9"])
NOME_NO_WINDOWS = "C:" + BARRA + "Users" + BARRA + "fulano"
NOME_NO_MAC = "/" + "Users" + "/" + "fulano"
LISTA_DE_NOMES = "# nomes que não podem aparecer" + NL + NL + "Beltrano" + NL + "Fulana da Silva" + NL + "João" + NL


class BaseDosTestes(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.casa = Path(self.pasta.name)

    def ambiente(self, **variaveis):
        base = {"HOME": str(self.casa), "USERPROFILE": str(self.casa), **variaveis}
        return mock.patch.dict(os.environ, base, clear=True)

    def verificar(self, arquivos, excecoes=None, ambiente=None):
        ctx = contexto_de_memoria(arquivos, excecoes=excecoes)
        with self.ambiente(**(ambiente or {})):
            return dados_pessoais.verificar(ctx), ctx

    def achados(self, texto, nome="a.md"):
        return self.verificar({nome: texto})[0]


class TesteDeEmail(BaseDosTestes):
    def test_email_pessoal_falha_com_arquivo_e_linha(self):
        achados = self.achados("oi" + NL + "fale com " + EMAIL_PESSOAL + NL)
        self.assertEqual([(a.arquivo, a.linha) for a in achados], [("a.md", 2)])

    def test_o_valor_nao_aparece_no_achado(self):
        achado = self.achados(EMAIL_PESSOAL + NL)[0]
        self.assertNotIn("fulana", achado.detalhe)
        self.assertIn("e-mail", achado.detalhe)

    def test_noreply_passa(self):
        linhas = [
            "12345+fulano@users.noreply.github.com",
            "noreply@github.com",
            "Co-Authored-By: Alguem <noreply@anthropic.com>",
            "no-reply@servico.com.br",
        ]
        self.assertEqual(self.achados(NL.join(linhas)), [])

    def test_enderecos_de_exemplo_passam(self):
        linhas = [
            "a@example.com", "b@sub.example.org", "c@exemplo.com", "d@exemplo.com.br", "e@host.test", "f@x.example",
            "git@github.com:dono/repo.git",
        ]
        self.assertEqual(self.achados(NL.join(linhas)), [])

    def test_o_que_so_parece_email_passa(self):
        linhas = ["npm i pacote@1.2.3", "import '@escopo/pacote'", "foo@latest", "imagem@sha256:abc", "a @ b.com"]
        self.assertEqual(self.achados(NL.join(linhas)), [])

    def test_dominio_em_maiuscula_de_exemplo_passa_e_pessoal_falha(self):
        self.assertEqual(self.achados("A@EXAMPLE.COM"), [])
        self.assertEqual(len(self.achados(EMAIL_PESSOAL.upper())), 1)


class TesteDeIp(BaseDosTestes):
    def test_ip_fora_das_faixas_de_exemplo_falha(self):
        for ip in (IP_PRIVADO, IP_PUBLICO):
            with self.subTest(ip=ip):
                self.assertEqual(len(self.achados("servidor em " + ip + NL)), 1)

    def test_ip_do_tailnet_falha(self):
        achado = self.achados("ssh " + IP_DO_TAILNET + NL)[0]
        self.assertIn("IP", achado.detalhe)
        self.assertNotIn(IP_DO_TAILNET, achado.detalhe)

    def test_ip_dentro_de_url_com_porta_falha(self):
        self.assertEqual(len(self.achados("http://" + IP_PRIVADO + ":8080/x")), 1)

    def test_loopback_zero_e_documentacao_passam(self):
        ips = ["127.0.0.1", "127.1.2.3", "0.0.0.0", "192.0.2.7", "198.51.100.7", "203.0.113.250", "255.255.255.0"]
        for ip in ips:
            with self.subTest(ip=ip):
                self.assertEqual(self.achados("host " + ip + NL), [])

    def test_o_que_so_parece_ip_passa(self):
        linhas = ["versao 1.2.3", "v" + IP_PRIVADO, IP_PRIVADO + ".4", "300.1.1.1", "1.2.3.999", "2025.11.27.1"]
        self.assertEqual(self.achados(NL.join(linhas)), [])

    def test_ip_no_fim_da_frase_falha(self):
        self.assertEqual(len(self.achados("o servidor é " + IP_PRIVADO + ".")), 1)


class TesteDeCaminhoPessoal(BaseDosTestes):
    def test_caminho_de_usuario_no_windows_e_no_mac_falha(self):
        for caminho in (NOME_NO_WINDOWS, NOME_NO_MAC + "/pasta", NOME_NO_WINDOWS.replace(BARRA, "/")):
            with self.subTest(caminho=caminho):
                self.assertEqual(len(self.achados("abra " + caminho + NL)), 1)

    def test_barra_dobrada_de_json_e_de_string_falha(self):
        self.assertEqual(len(self.achados(NOME_NO_WINDOWS.replace(BARRA, BARRA * 2))), 1)

    def test_o_nome_nao_aparece_no_achado(self):
        achado = self.achados(NOME_NO_WINDOWS)[0]
        self.assertNotIn("fulano", achado.detalhe)

    def test_marcadores_no_lugar_do_nome_passam(self):
        nomes = ["<usuário>", "<nome>", "$USER", "${USER}", "%USERNAME%", "$env:USERNAME", "*", "...", "[nome]"]
        for nome in nomes:
            with self.subTest(nome=nome):
                texto = "C:" + BARRA + "Users" + BARRA + nome + " e /Users/" + nome + "/x"
                self.assertEqual(self.achados(texto), [])

    def test_pastas_genericas_do_sistema_passam(self):
        texto = "C:" + BARRA + "Users" + BARRA + "Public e /Users/Shared e C:/Users/Default"
        self.assertEqual(self.achados(texto), [])

    def test_til_e_variavel_do_perfil_passam(self):
        self.assertEqual(self.achados("cd ~/worktrees e %USERPROFILE%" + BARRA + "worktrees"), [])

    def test_o_que_so_parece_caminho_passa(self):
        linhas = ["src/Users/Lista.tsx", "fetch(`/users/${id}`)", "import x from './Users/lista'"]
        self.assertEqual(self.achados(NL.join(linhas)), [])


class TesteDaListaDeNomes(BaseDosTestes):
    def escrever_lista(self, caminho, texto=LISTA_DE_NOMES):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")
        return str(caminho)

    def com_lista(self, texto):
        lista = self.escrever_lista(self.casa / "fora" / "lista.txt")
        return self.verificar({"a.md": texto}, ambiente={"FREIOS_NOMES": lista})[0]

    def test_nome_da_lista_falha_sem_mostrar_o_nome(self):
        achados = self.com_lista("obrigado, Beltrano!" + NL)
        self.assertEqual([(a.arquivo, a.linha) for a in achados], [("a.md", 1)])
        self.assertNotIn("Beltrano", achados[0].detalhe)

    def test_ignora_maiuscula_e_acento(self):
        self.assertEqual(len(self.com_lista("fala do JOAO")), 1)
        self.assertEqual(len(self.com_lista("fala da fulana da silva")), 1)

    def test_so_a_palavra_inteira_conta(self):
        self.assertEqual(self.com_lista("Beltranopolis e Joaozinho"), [])

    def test_comentario_e_linha_vazia_da_lista_nao_viram_nome(self):
        self.assertEqual(self.com_lista("nomes que não podem aparecer, texto qualquer"), [])

    def test_lista_padrao_fica_em_config_freios_nomes_txt(self):
        self.escrever_lista(self.casa / ".config" / "freios" / "nomes.txt")
        achados, ctx = self.verificar({"a.md": "oi Beltrano"})
        self.assertEqual(len(achados), 1)
        self.assertEqual(ctx.avisos, [])

    def test_a_variavel_de_ambiente_vence_a_lista_padrao(self):
        self.escrever_lista(self.casa / ".config" / "freios" / "nomes.txt")
        outra = self.escrever_lista(self.casa / "outra.txt", "Cicrano" + NL)
        arquivos = {"a.md": "oi Beltrano e Cicrano"}
        achados, _ = self.verificar(arquivos, ambiente={"FREIOS_NOMES": outra})
        self.assertEqual(len(achados), 1)

    def test_sem_lista_avisa_e_pula_so_os_nomes(self):
        achados, ctx = self.verificar({"a.md": "oi Beltrano e " + EMAIL_PESSOAL})
        self.assertEqual(len(achados), 1)
        self.assertEqual(len(ctx.avisos), 1)
        self.assertIn("FREIOS_NOMES", ctx.avisos[0])
        self.assertIn("nomes.txt", ctx.avisos[0])

    def test_lista_apontada_que_nao_existe_tambem_avisa(self):
        achados, ctx = self.verificar({"a.md": "oi"}, ambiente={"FREIOS_NOMES": str(self.casa / "nada.txt")})
        self.assertEqual((achados, len(ctx.avisos)), ([], 1))

    def test_o_aviso_nao_derruba_o_ci(self):
        _, ctx = self.verificar({"a.md": "oi"})
        self.assertEqual(sem_pulo.pulos("aviso: " + ctx.avisos[0]), [])


class TesteDoFreio(BaseDosTestes):
    def test_arquivo_binario_fica_fora(self):
        dados = b"\0\0" + EMAIL_PESSOAL.encode() + b"\0"
        self.assertEqual(self.verificar({"a.dat": dados})[0], [])

    def test_varios_tipos_na_mesma_linha_sao_achados_separados(self):
        achados = self.achados(EMAIL_PESSOAL + " " + IP_PRIVADO + " " + NOME_NO_MAC)
        self.assertEqual(len(achados), 3)

    def test_excecao_com_motivo_libera_o_arquivo(self):
        excecoes = {"dados_pessoais": [{"glob": "docs/exemplo.md", "motivo": "exemplo de saída de uma ferramenta"}]}
        achados, _ = self.verificar({"docs/exemplo.md": EMAIL_PESSOAL}, excecoes=excecoes)
        self.assertEqual(achados, [])

    def test_o_conserto_diz_como_resolver(self):
        for trecho in ("excecoes.json", "nomes.txt", "FREIOS_NOMES", "<usuário>", "example.com"):
            self.assertIn(trecho, dados_pessoais.CONSERTO)

    def test_o_modulo_so_depende_do_contexto_dos_freios(self):
        fonte = Path(dados_pessoais.__file__).read_text(encoding="utf-8")
        importados = [linha for linha in fonte.splitlines() if linha.startswith(("import ", "from "))]
        proprios = [linha for linha in importados if "scripts" in linha]
        self.assertEqual(proprios, ["from scripts.freios.contexto import Achado"])


class TesteDosDadosPessoaisNaCatraca(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioTemporario()
        self.addCleanup(self.repo.limpar)

    def rodar(self):
        saida = io.StringIO()
        argumentos = ["--tudo", "--base", "main", "--raiz", str(self.repo.raiz), "--sem-testes", "--so", "dados_pessoais"]
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
            with mock.patch.dict(os.environ, {"HOME": str(self.repo.raiz)}):
                codigo = principal.main(argumentos)
        return codigo, saida.getvalue()

    def na_main(self, arquivos):
        for caminho, conteudo in arquivos.items():
            self.repo.adicionar(caminho, conteudo)
        self.repo.commitar("main")
        self.repo.git("checkout", "-q", "-b", "feature")

    def test_dado_que_ja_estava_na_main_passa(self):
        self.na_main({"a.md": EMAIL_PESSOAL + NL})
        self.repo.adicionar("b.md", "oi" + NL)
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 0, saida)
        self.assertIn("✓ dados_pessoais (1 no teto da main)", saida)

    def test_dado_novo_reprova_com_o_conserto_e_sem_mostrar_o_valor(self):
        self.na_main({"a.md": "oi" + NL})
        self.repo.adicionar("a.md", "oi" + NL + EMAIL_PESSOAL + NL)
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertIn("a.md:2", saida)
        self.assertIn("Conserto:", saida)
        self.assertNotIn("fulana", saida)

    def test_trocar_o_dado_da_main_por_outro_reprova(self):
        self.na_main({"a.md": EMAIL_PESSOAL + NL})
        self.repo.adicionar("a.md", "outra" + "@" + "provedor.com" + NL)
        codigo, saida = self.rodar()
        self.assertEqual(codigo, 1, saida)
        self.assertIn("a.md:1", saida)

    def test_mudar_de_linha_o_dado_da_main_passa(self):
        self.na_main({"a.md": EMAIL_PESSOAL + NL})
        self.repo.adicionar("a.md", "oi" + NL + "fale com " + EMAIL_PESSOAL + NL)
        self.assertEqual(self.rodar()[0], 0)

    def test_tirar_o_dado_passa(self):
        self.na_main({"a.md": EMAIL_PESSOAL + NL})
        self.repo.adicionar("a.md", "oi" + NL)
        self.assertEqual(self.rodar()[0], 0)


if __name__ == "__main__":
    unittest.main()
