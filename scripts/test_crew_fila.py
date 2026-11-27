import contextlib
import io
import json
import os
import types

from scripts.test_crew import CHIEF, minutes_ago, utc_minutes_ago
from scripts.test_crew_vigia import VigiaCase

SEM_MEMORIA = "memória: 1,0 GB livres (mínimo 3)"
SEM_DISCO = "disco: 0,2 GB livres (mínimo 10)"


class FilaCase(VigiaCase):
    def setUp(self):
        super().setUp()
        self.crew.module("crew_recursos").aqui = lambda: "pc"
        self.clonado, self.vps_fora = True, False
        self.crew.module("crew_remote").ssh = self.ssh
        self.recursos()

    def ssh(self, host, comando, step="remote", stdin=None):
        if self.vps_fora:
            raise self.crew.Fail("ssh", "cannot reach %s" % host)
        if comando.startswith("test -d") and not self.clonado:
            raise self.crew.Fail(step, "exit 1")
        return "/home/vps" if comando.startswith("printf") else ""

    def recursos(self, maquina="pc", folga=True, motivo=None, minutos=0):
        os.makedirs(self.state, exist_ok=True)
        leitura = dict(at=utc_minutes_ago(minutos), host=maquina, alcancavel=True, folga=folga, motivo=motivo)
        with open(os.path.join(self.state, "_recursos-%s.json" % maquina), "w", encoding="utf-8") as f:
            json.dump(leitura, f)

    def cota(self, status="allowed", extra="allowed"):
        os.makedirs(self.state, exist_ok=True)
        leitura = dict(at=utc_minutes_ago(0).replace("+00:00", "Z"), status=status, extra=dict(status=extra))
        with open(os.path.join(self.state, "_cota.json"), "w", encoding="utf-8") as f:
            json.dump(leitura, f)

    def spawn(self, task="job", **extra):
        campos = dict(repo="Test", task=task, type=None, model=None, request="do it", request_file=None, done="done", context=None,
                      host="local", frente=None, start_timeout=5, prompt_timeout=10, dry_run=False)
        return self.crew.cmd_spawn(types.SimpleNamespace(**dict(campos, **extra)))

    def fila(self, **extra):
        campos = dict(liberar=None, andar=False)
        with contextlib.redirect_stdout(io.StringIO()):
            return self.crew.module("crew_fila").comando(types.SimpleNamespace(**dict(campos, **extra)))["fila"]

    def nomes_na_fila(self):
        return [t["name"] for t in self.fila()]

    def abertos(self):
        return [m["name"] for m in self.crew.workers()]

    def parado_com_relatorio(self, nome, pane, minutos):
        self.add_worker(name=nome, pane=pane, state="idle", turns=3, at=utc_minutes_ago(minutos))
        with open(os.path.join(self.state, nome, "report.md"), "w", encoding="utf-8") as f:
            f.write("**Resultado**: feito")


class QuandoOSpawnVaiParaAFila(FilaCase):
    def test_sem_folga_a_tarefa_entra_na_fila_em_vez_de_falhar(self):
        self.recursos(folga=False, motivo=SEM_MEMORIA)
        feito = self.spawn()
        self.assertTrue(feito["ok"])
        self.assertTrue(feito["queued"])
        self.assertIn(SEM_MEMORIA, feito["espera"])
        self.assertEqual(self.abertos(), [])
        self.assertEqual(self.herdr.launched, {})
        self.assertEqual(self.nomes_na_fila(), ["t-job"])

    def test_com_folga_o_spawn_abre_na_hora(self):
        feito = self.spawn()
        self.assertNotIn("queued", feito)
        self.assertEqual(self.abertos(), ["t-job"])
        self.assertEqual(self.fila(), [])

    def test_leitura_velha_demais_nao_segura_o_spawn(self):
        self.recursos(folga=False, motivo=SEM_MEMORIA, minutos=30)
        self.assertNotIn("queued", self.spawn())

    def test_no_teto_do_pc_a_tarefa_espera_mesmo_com_folga(self):
        for n in range(10):
            self.add_worker(name="w%d" % n, pane="w4:p%d" % n)
        feito = self.spawn()
        self.assertTrue(feito["queued"])
        self.assertIn("teto", feito["espera"])
        self.assertIn("10", feito["espera"])

    def test_no_teto_da_vps_a_tarefa_espera(self):
        self.recursos("vps")
        for n in range(6):
            self.add_worker(name="w%d" % n, pane="w4:p%d" % n, host="vps")
        feito = self.spawn(host="vps")
        self.assertTrue(feito["queued"])
        self.assertIn("teto", feito["espera"])
        self.assertIn("6", feito["espera"])

    def test_o_teto_de_uma_maquina_nao_segura_a_outra(self):
        for n in range(6):
            self.add_worker(name="w%d" % n, pane="w4:p%d" % n, host="vps")
        self.assertNotIn("queued", self.spawn())

    def test_vps_fora_do_ar_enfileira_em_vez_de_falhar(self):
        self.recursos("vps", folga=False, motivo="VPS fora")
        feito = self.spawn(host="vps")
        self.assertTrue(feito["queued"])
        self.assertIn("VPS fora", feito["espera"])

    def test_o_spawn_diz_de_que_frente_e_a_tarefa(self):
        self.assertEqual(self.spawn(frente="#66")["frente"], "#66")
        self.recursos(folga=False, motivo=SEM_MEMORIA)
        self.assertEqual(self.spawn("outra", frente="#66")["frente"], "#66")
        self.assertEqual(self.fila()[0]["frente"], "#66")

    def test_tarefa_sem_frente_nao_leva_o_campo(self):
        self.assertNotIn("frente", self.spawn())

    def test_o_mesmo_nome_nao_entra_duas_vezes(self):
        self.recursos(folga=False, motivo=SEM_MEMORIA)
        self.spawn()
        with self.assertRaises(self.crew.Fail) as erro:
            self.spawn()
        self.assertEqual(erro.exception.step, "name")

    def test_ensaio_nao_entra_na_fila(self):
        self.recursos(folga=False, motivo=SEM_MEMORIA)
        self.assertTrue(self.spawn(dry_run=True)["dry_run"])
        self.assertEqual(self.fila(), [])


class QuandoOVigiaAbreAFila(FilaCase):
    def enfileirar(self, task, **extra):
        self.recursos(folga=False, motivo=SEM_MEMORIA)
        self.spawn(task, **extra)
        self.clock.now += 60

    def test_a_fila_anda_sozinha_quando_a_folga_volta(self):
        self.enfileirar("job")
        self.watch()
        self.assertEqual(self.abertos(), [])
        self.recursos()
        self.watch()
        self.assertEqual(self.abertos(), ["t-job"])
        self.assertEqual(self.fila(), [])
        self.assertIn("spawned", self.kinds())

    def test_abre_uma_por_volta(self):
        self.enfileirar("um")
        self.spawn("dois")
        self.recursos()
        self.watch()
        self.assertEqual(self.abertos(), ["t-um"])
        self.watch()
        self.assertEqual(self.abertos(), ["t-dois", "t-um"])

    def test_merge_e_revisao_vao_a_frente(self):
        self.enfileirar("antiga", type="implement")
        self.spawn("revisao", type="review")
        self.spawn("juntar", type="merge")
        self.recursos()
        self.watch()
        self.assertEqual(self.abertos(), ["t-revisao"])
        self.watch()
        self.assertEqual(sorted(self.abertos()), ["t-juntar", "t-revisao"])
        self.watch()
        self.assertEqual(sorted(self.abertos()), ["t-antiga", "t-juntar", "t-revisao"])

    def test_tarefa_presa_a_vps_espera_por_ela_mesmo_com_o_pc_livre(self):
        self.recursos("vps", folga=False, motivo=SEM_MEMORIA)
        self.spawn(host="vps")
        self.watch()
        self.assertEqual(self.nomes_na_fila(), ["t-job"])
        self.assertEqual(self.abertos(), [])

    def test_tarefa_sem_maquina_fixa_abre_no_pc_quando_so_o_pc_tem_folga(self):
        self.recursos("vps", folga=False, motivo="VPS fora")
        self.recursos("pc", folga=False, motivo=SEM_MEMORIA)
        self.assertIn("VPS: ", self.spawn(host=None)["espera"])
        self.recursos("pc")
        self.watch()
        self.assertEqual(self.abertos(), ["t-job"])

    def test_o_teto_segura_a_fila_ate_alguem_fechar(self):
        for n in range(10):
            self.add_worker(name="w%d" % n, pane="w4:p%d" % n)
        self.spawn()
        self.watch()
        self.assertEqual(self.nomes_na_fila(), ["t-job"])

    def test_pedido_que_nao_abre_vira_aviso_de_erro_e_sai_da_fila(self):
        self.enfileirar("job")
        with open(os.environ["CREW_REPOS"], "w", encoding="utf-8") as f:
            json.dump({}, f)
        self.recursos()
        self.watch()
        self.assertEqual(self.fila(), [])
        self.assertIn("spawn_failed", self.kinds())
        self.assertIn("erro:", self.avisos()[0])

    def test_a_fila_mantem_o_vigia_vivo_sem_worker_aberto(self):
        self.enfileirar("job")
        args = types.SimpleNamespace(chief=CHIEF, every=700, stall=20, unstarted=4, rounds=2)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.crew.cmd_watch(args), dict(ok=True, rounds=2))
        self.assertEqual(self.nomes_na_fila(), ["t-job"])

    def test_sem_fila_e_sem_worker_o_vigia_para_como_antes(self):
        args = types.SimpleNamespace(chief=CHIEF, every=700, stall=20, unstarted=4, rounds=2)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.crew.cmd_watch(args)["stopped"], "no open workers for 10 minutes")


class QuandoACotaEstaPertoDoLimite(FilaCase):
    def fila_com(self, **tarefas):
        self.recursos(folga=False, motivo=SEM_MEMORIA)
        for task, tipo in tarefas.items():
            self.spawn(task, type=tipo)
        self.recursos()

    def test_perto_do_limite_so_merge_e_revisao_abrem(self):
        self.fila_com(feature="implement", juntar="merge")
        self.cota("allowed_warning")
        self.watch()
        self.assertEqual(self.abertos(), ["t-juntar"])
        self.watch()
        self.assertEqual(self.abertos(), ["t-juntar"])
        self.assertIn("cota perto do limite", self.fila()[0]["espera"])

    def test_plan_e_implement_esperam_mas_revisao_abre(self):
        self.fila_com(planejar="plan", construir="implement", revisar="review")
        self.cota("allowed_warning")
        self.watch(3)
        self.assertEqual(self.abertos(), ["t-revisar"])

    def test_o_dono_libera_o_resto(self):
        self.fila_com(feature="implement")
        self.cota("allowed_warning")
        self.watch()
        self.assertEqual(self.abertos(), [])
        self.fila(liberar="t-feature")
        self.watch()
        self.assertEqual(self.abertos(), ["t-feature"])

    def test_liberar_um_nome_que_nao_esta_na_fila_diz_o_erro(self):
        with self.assertRaises(self.crew.Fail) as erro:
            self.fila(liberar="nao-existe")
        self.assertEqual(erro.exception.step, "fila")

    def test_no_limite_tudo_espera_o_reset(self):
        self.fila_com(feature="implement", juntar="merge")
        self.cota("rejected", extra="rejected")
        self.watch(2)
        self.assertEqual(self.abertos(), [])
        self.assertIn("cota no limite", self.fila()[0]["espera"])

    def test_no_limite_com_extra_usage_a_fila_anda(self):
        self.fila_com(feature="implement")
        self.cota("rejected", extra="allowed")
        self.watch()
        self.assertEqual(self.abertos(), ["t-feature"])

    def test_cota_velha_nao_segura_ninguem(self):
        self.fila_com(feature="implement")
        self.cota("rejected", extra="rejected")
        caminho = os.path.join(self.state, "_cota.json")
        with open(caminho, encoding="utf-8") as f:
            leitura = json.load(f)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dict(leitura, at="2020-01-01T00:00:00Z"), f)
        self.watch()
        self.assertEqual(self.abertos(), ["t-feature"])

    def test_o_spawn_com_a_cota_perto_do_limite_entra_na_fila(self):
        self.cota("allowed_warning")
        self.assertTrue(self.spawn(type="implement")["queued"])
        self.assertNotIn("queued", self.spawn("juntar", type="merge"))


class QuandoHaFilaOVigiaFechaOOcioso(FilaCase):
    def fila_sem_folga(self):
        self.recursos(folga=False, motivo=SEM_MEMORIA)
        self.spawn("espera")

    def fechados(self):
        return [e["worker"] for e in self.events() if e["kind"] == "closed"]

    def test_fecha_o_mais_antigo_um_por_vez(self):
        self.parado_com_relatorio("novo", "w4:p1", 90)
        self.parado_com_relatorio("velho", "w4:p2", 300)
        self.parado_com_relatorio("meio", "w4:p3", 120)
        self.fila_sem_folga()
        self.watch()
        self.assertEqual(self.fechados(), ["velho"])
        self.watch()
        self.assertEqual(self.fechados(), ["velho", "meio"])

    def test_sem_fila_ninguem_e_fechado(self):
        self.parado_com_relatorio("velho", "w4:p2", 300)
        self.watch()
        self.assertEqual(self.fechados(), [])

    def test_ocioso_ha_menos_de_60_min_fica(self):
        self.parado_com_relatorio("recente", "w4:p1", 59)
        self.fila_sem_folga()
        self.watch()
        self.assertEqual(self.fechados(), [])

    def test_sem_relatorio_fica(self):
        self.add_worker(name="sem", pane="w4:p1", state="idle", turns=3, at=utc_minutes_ago(300))
        self.fila_sem_folga()
        self.watch()
        self.assertEqual(self.fechados(), [])

    def test_quem_esta_trabalhando_fica(self):
        self.add_worker(name="ocupado", pane="w4:p1", state="working", turns=3)
        with open(os.path.join(self.state, "ocupado", "report.md"), "w", encoding="utf-8") as f:
            f.write("**Resultado**: feito")
        self.fila_sem_folga()
        self.watch()
        self.assertEqual(self.fechados(), [])

    def test_a_cota_no_limite_nao_fecha_ninguem_porque_vaga_nao_ajuda(self):
        self.parado_com_relatorio("velho", "w4:p2", 300)
        self.cota("rejected", extra="rejected")
        self.spawn("espera")
        self.watch()
        self.assertEqual(self.fechados(), [])

    def test_a_vaga_aberta_deixa_a_fila_andar_na_volta_seguinte(self):
        self.parado_com_relatorio("velho", "w4:p2", 300)
        self.fila_sem_folga()
        self.watch()
        self.recursos()
        self.watch()
        self.assertIn("t-espera", self.abertos())


class QuandoAEsperaPassaDeUmaHora(FilaCase):
    def test_depois_de_uma_hora_o_chief_e_acordado_uma_vez_so(self):
        self.recursos(folga=False, motivo=SEM_MEMORIA)
        self.spawn()
        self.assertEqual(self.rodada(30), [])
        avisos = self.rodada(31)
        self.assertEqual(len(avisos), 1)
        self.assertIn("t-job", avisos[0])
        self.assertIn("esperando Folga", avisos[0])
        self.assertIn(SEM_MEMORIA, avisos[0])
        self.assertEqual(len(self.rodada(5)), 1)

    def test_motivo_de_disco_acorda_na_hora(self):
        self.recursos(folga=False, motivo=SEM_DISCO)
        self.spawn()
        avisos = self.rodada(1)
        self.assertEqual(len(avisos), 1)
        self.assertIn(SEM_DISCO, avisos[0])

    def test_tarefa_que_abriu_a_tempo_nao_acorda_ninguem(self):
        self.recursos(folga=False, motivo=SEM_MEMORIA)
        self.spawn()
        self.rodada(30)
        self.recursos()
        self.assertEqual(self.rodada(40), [])
        self.assertEqual(self.abertos(), ["t-job"])


class QuadroDaFila(FilaCase):
    def test_o_comando_lista_motivo_maquina_e_ha_quanto_tempo(self):
        self.recursos(folga=False, motivo=SEM_MEMORIA)
        self.spawn(frente="#66", type="merge")
        self.watch()
        [tarefa] = self.fila()
        self.assertEqual((tarefa["name"], tarefa["tipo"], tarefa["maquina"], tarefa["frente"]), ("t-job", "merge", "pc", "#66"))
        self.assertIn(SEM_MEMORIA, tarefa["espera"])
        self.assertTrue(tarefa["desde"] <= minutes_ago(0))


class QuandoOSpawnNaoFixaAMaquina(FilaCase):
    def onde(self, **extra):
        return self.spawn(dry_run=True, **dict(dict(host=None), **extra))

    def test_tenta_a_vps_primeiro(self):
        self.assertEqual(self.onde()["host"], "vps")

    def test_vps_sem_folga_cai_no_pc(self):
        self.recursos("vps", folga=False, motivo=SEM_MEMORIA)
        self.assertNotIn("host", self.onde())

    def test_repo_que_nao_esta_clonado_na_vps_cai_no_pc(self):
        self.clonado = False
        self.assertNotIn("host", self.onde())

    def test_vps_que_nao_responde_cai_no_pc(self):
        self.vps_fora = True
        self.assertNotIn("host", self.onde())

    def test_nenhuma_com_folga_entra_na_fila_com_os_dois_motivos(self):
        self.recursos("vps", folga=False, motivo=SEM_MEMORIA)
        self.recursos("pc", folga=False, motivo=SEM_DISCO)
        feito = self.onde()
        self.assertTrue(feito["queued"])
        self.assertIn("VPS: sem Folga no VPS: " + SEM_MEMORIA, feito["espera"])
        self.assertIn("PC: sem Folga no PC: " + SEM_DISCO, feito["espera"])

    def test_host_local_prende_ao_pc_mesmo_com_a_vps_livre(self):
        self.assertNotIn("host", self.onde(host="local"))

    def test_host_local_espera_pelo_pc(self):
        self.recursos("pc", folga=False, motivo=SEM_MEMORIA)
        self.assertTrue(self.onde(host="local")["queued"])

    def test_host_do_repo_prende_a_tarefa(self):
        with open(os.environ["CREW_REPOS"], "w", encoding="utf-8") as f:
            json.dump({"Test": dict(path=self.repo, remote="none", short="t", branch="pi/{task}", default_branch="main", host="vps")}, f)
        self.recursos("vps", folga=False, motivo=SEM_MEMORIA)
        self.assertTrue(self.onde()["queued"])
