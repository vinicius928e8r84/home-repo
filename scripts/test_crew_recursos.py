import json
import os
import types
import unittest

from scripts.test_crew import CrewCase
from scripts.test_crew_vigia import VigiaCase

E2E_VPS = "1379046 WRITE  /home/factory/crew-state/e2e.lock\n1403209 WRITE* 1379046 /home/factory/crew-state/e2e.lock"
E2E_PROCS = "1379046|/home/factory/worktrees/PerpetualMiner-rev-t3/e2e|57\n1403209|/tmp/rev920/pr|5"
MAC_NA_VPS = "1500100 WRITE  /home/factory/crew-state/mac.lock"
MAC_PROCS_NA_VPS = "1500100|/home/factory/worktrees/Nova-AI-prova|3725"
LOCKF_NO_MAC = "93607|/Users/usuario/prova|1-02:03:04"


def pc(livre_mb=2473, cpu=65, fila=37, disco=4.7):
    return json.dumps(dict(livre_mb=livre_mb, total_mb=16103, cpu_pct=cpu, fila=fila, nucleos=16, disco_livre_gb=disco, disco_total_gb=455.3))


def vps(livre_kb=8000000, carga5="0.50", pressao="1.00", disco_gb=56, **travas):
    return "\n".join([
        "##meminfo", "MemTotal:       16376004 kB", "MemAvailable:   %d kB" % livre_kb, "SwapFree:            152 kB",
        "##loadavg", "0.60 %s 0.40 1/200 12345" % carga5,
        "##pressure", "some avg10=1.00 avg60=%s avg300=1.00 total=374460855308" % pressao, "full avg10=0.00 avg60=0.00 avg300=0.00 total=0",
        "##nproc", "4",
        "##df", "      Avail    1B-blocks", "%d 206900281344" % (disco_gb * 2 ** 30),
        "##travas", travas.get("travas", ""), "##procs", travas.get("procs", ""), ""])


def mac(livre_pct=67, carga5="3.88", disco_kb=90525064, procs=""):
    return "\n".join([
        "##ncpu", "8", "##memsize", "8589934592", "##loadavg", "{ 4.10 %s 3.87 }" % carga5,
        "##pressure", "The system has 8589934592 (524288 pages with a page size of 16384).", "System-wide memory free percentage: %d%%" % livre_pct,
        "##df", "Filesystem     1024-blocks      Used Available Capacity iused     ifree %iused  Mounted on",
        "/dev/disk3s1s1   239362496  19827648  %d  18%%  425955 905250640    0%%   /" % disco_kb,
        "##procs", procs, ""])


PC_DA_PESQUISA = pc()
VPS_DA_PESQUISA = vps(livre_kb=4509715, carga5="15.90", pressao="91.00")
MAC_DA_PESQUISA = mac(livre_pct=41, carga5="2.09", disco_kb=20 * 1024 * 1024)
MEMORIA_DO_PC_NA_PESQUISA_MB = [1190, 260, 2750, 2990, 2470, 2390]


class RecursosCase(CrewCase):
    def setUp(self):
        super().setUp()
        self.modulo = self.crew.module("crew_recursos")
        self.leituras = dict(pc=pc(5000, 10, 1, 100), vps=vps(), mac=mac())
        self.modulo.ler = self.ler

    def ler(self, maquina):
        leitura = self.leituras[maquina]
        if isinstance(leitura, Exception):
            raise leitura
        return leitura

    def rodar(self):
        return self.modulo.comando(types.SimpleNamespace())

    def arquivo(self, maquina):
        with open(os.path.join(self.state, "_recursos-%s.json" % maquina), encoding="utf-8") as f:
            return json.load(f)


class RegraDaFolga(RecursosCase):
    def test_o_pc_da_pesquisa_fica_sem_folga_por_memoria_disco_e_processador(self):
        self.leituras["pc"] = PC_DA_PESQUISA
        self.rodar()
        gravado = self.arquivo("pc")
        self.assertFalse(gravado["folga"])
        for motivo in ("memória: 2,4 GB livres", "disco: 4,7 GB livres", "processador: fila 37"):
            self.assertIn(motivo, gravado["motivo"])
        self.assertEqual(gravado["memoria"], dict(livre_mb=2473, total_mb=16103, mediana_mb=2473))
        self.assertEqual(gravado["cpu"], dict(uso_pct=65, fila=37, carga_5m=None, pressao_60s=None))
        self.assertEqual(gravado["nucleos"], 16)

    def test_a_vps_da_pesquisa_fica_sem_folga_so_por_processador(self):
        self.leituras["vps"] = VPS_DA_PESQUISA
        self.rodar()
        gravado = self.arquivo("vps")
        self.assertFalse(gravado["folga"])
        self.assertEqual(gravado["motivo"], "processador: carga de 5 min 15,9 em 4 núcleos (máximo 8,0) e pressão 91% (máximo 80)")
        self.assertEqual(gravado["cpu"]["carga_5m"], 15.9)
        self.assertEqual(gravado["cpu"]["pressao_60s"], 91.0)
        self.assertEqual(gravado["disco"]["livre_gb"], 56.0)

    def test_o_mac_da_pesquisa_tem_folga(self):
        self.leituras["mac"] = MAC_DA_PESQUISA
        self.rodar()
        gravado = self.arquivo("mac")
        self.assertTrue(gravado["folga"])
        self.assertIsNone(gravado["motivo"])
        self.assertEqual(gravado["nucleos"], 8)
        self.assertEqual(gravado["disco"]["livre_gb"], 20.0)

    def test_cada_maquina_grava_o_seu_arquivo(self):
        resultado = self.rodar()
        self.assertTrue(resultado["ok"])
        for maquina in ("pc", "vps", "mac"):
            gravado = self.arquivo(maquina)
            self.assertEqual(gravado["host"], maquina)
            self.assertRegex(gravado["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
            self.assertTrue(gravado["folga"], maquina)

    def test_disco_abaixo_de_10_gb_tira_a_folga(self):
        self.leituras["pc"] = pc(5000, 10, 1, 9.9)
        self.rodar()
        self.assertEqual(self.arquivo("pc")["motivo"], "disco: 9,9 GB livres (mínimo 10)")

    def test_disco_com_exatos_10_gb_ainda_tem_folga(self):
        self.leituras["pc"] = pc(5000, 10, 1, 10.0)
        self.rodar()
        self.assertTrue(self.arquivo("pc")["folga"])

    def test_windows_com_processador_acima_de_90_por_cento_fica_sem_folga(self):
        self.leituras["pc"] = pc(5000, 95, 1, 100)
        self.rodar()
        self.assertEqual(self.arquivo("pc")["motivo"], "processador: uso 95% (máximo 90)")

    def test_a_mediana_das_tres_ultimas_leituras_ignora_um_pico_isolado(self):
        for livre_mb in (5000, 800, 5200):
            self.leituras["pc"] = pc(livre_mb, 10, 1, 100)
            self.rodar()
        gravado = self.arquivo("pc")
        self.assertTrue(gravado["folga"])
        self.assertEqual(gravado["memoria"]["mediana_mb"], 5000)
        self.assertEqual(gravado["memoria"]["livre_mb"], 5200)

    def test_duas_leituras_baixas_em_tres_tiram_a_folga(self):
        for livre_mb in (800, 900, 5200):
            self.leituras["pc"] = pc(livre_mb, 10, 1, 100)
            self.rodar()
        self.assertFalse(self.arquivo("pc")["folga"])

    def test_so_as_tres_ultimas_leituras_valem(self):
        for livre_mb in (800, 800, 5000, 5000, 5000):
            self.leituras["pc"] = pc(livre_mb, 10, 1, 100)
            self.rodar()
        self.assertEqual(len(self.arquivo("pc")["historico"]), 3)
        self.assertTrue(self.arquivo("pc")["folga"])

    def test_a_serie_de_memoria_do_pc_da_pesquisa_nunca_da_folga(self):
        for livre_mb in MEMORIA_DO_PC_NA_PESQUISA_MB:
            self.leituras["pc"] = pc(livre_mb, 10, 1, 100)
            self.rodar()
            self.assertFalse(self.arquivo("pc")["folga"], livre_mb)

    def test_sem_folga_a_maquina_so_volta_com_4_gb_de_memoria(self):
        self.leituras["pc"] = pc(2000, 10, 1, 100)
        self.rodar()
        self.leituras["pc"] = pc(3500, 10, 1, 100)
        for _ in range(3):
            self.rodar()
        gravado = self.arquivo("pc")
        self.assertFalse(gravado["folga"])
        self.assertEqual(gravado["motivo"], "memória: 3,4 GB livres (para voltar, mínimo 4)")
        self.leituras["pc"] = pc(4200, 10, 1, 100)
        for _ in range(3):
            self.rodar()
        self.assertTrue(self.arquivo("pc")["folga"])

    def test_com_folga_a_maquina_aguenta_3_gb_sem_perder_a_folga(self):
        self.leituras["pc"] = pc(3500, 10, 1, 100)
        self.rodar()
        self.assertTrue(self.arquivo("pc")["folga"])

    def test_sem_folga_o_disco_so_volta_com_15_gb(self):
        self.leituras["pc"] = pc(5000, 10, 1, 5)
        self.rodar()
        self.leituras["pc"] = pc(5000, 10, 1, 12)
        for _ in range(3):
            self.rodar()
        self.assertEqual(self.arquivo("pc")["motivo"], "disco: 12,0 GB livres (para voltar, mínimo 15)")
        self.leituras["pc"] = pc(5000, 10, 1, 15)
        for _ in range(3):
            self.rodar()
        self.assertTrue(self.arquivo("pc")["folga"])

    def test_sem_folga_o_processador_so_volta_abaixo_de_1_5_vezes_os_nucleos(self):
        self.leituras["pc"] = pc(5000, 10, 40, 100)
        self.rodar()
        self.leituras["pc"] = pc(5000, 10, 28, 100)
        for _ in range(3):
            self.rodar()
        self.assertFalse(self.arquivo("pc")["folga"])
        self.leituras["pc"] = pc(5000, 10, 23, 100)
        for _ in range(3):
            self.rodar()
        self.assertTrue(self.arquivo("pc")["folga"])

    def test_com_folga_a_fila_entre_1_5_e_2_vezes_os_nucleos_nao_tira_a_folga(self):
        self.leituras["pc"] = pc(5000, 10, 30, 100)
        self.rodar()
        self.assertTrue(self.arquivo("pc")["folga"])
        self.leituras["pc"] = pc(5000, 10, 33, 100)
        for _ in range(3):
            self.rodar()
        self.assertFalse(self.arquivo("pc")["folga"])

    def test_na_vps_a_carga_de_5_min_acima_de_2_vezes_os_nucleos_tira_a_folga(self):
        self.leituras["vps"] = vps(carga5="8.10")
        self.rodar()
        self.assertFalse(self.arquivo("vps")["folga"])
        self.leituras["vps"] = vps(carga5="7.90")
        for _ in range(3):
            self.rodar()
        self.assertFalse(self.arquivo("vps")["folga"])
        self.leituras["vps"] = vps(carga5="5.90")
        for _ in range(3):
            self.rodar()
        self.assertTrue(self.arquivo("vps")["folga"])

    def test_na_vps_a_pressao_acima_de_80_tira_a_folga_mesmo_com_carga_baixa(self):
        self.leituras["vps"] = vps(pressao="81.2")
        self.rodar()
        self.assertEqual(self.arquivo("vps")["motivo"], "processador: pressão 81% (máximo 80)")

    def test_arquivo_anterior_ilegivel_recomeca_o_historico(self):
        os.makedirs(self.state, exist_ok=True)
        with open(os.path.join(self.state, "_recursos-pc.json"), "w", encoding="utf-8") as f:
            f.write("{pela metade")
        self.rodar()
        self.assertEqual(len(self.arquivo("pc")["historico"]), 1)


class QuemTemAsTravas(RecursosCase):
    def setUp(self):
        super().setUp()
        self.add_worker(name="pm-rev-t3", host="vps", worktree="/home/factory/worktrees/PerpetualMiner-rev-t3")

    def test_o_arquivo_da_vps_diz_quem_tem_a_trava_do_e2e_e_quem_espera(self):
        self.leituras["vps"] = vps(travas=E2E_VPS, procs=E2E_PROCS)
        self.rodar()
        self.assertEqual(self.arquivo("vps")["travas"], [dict(
            nome="e2e", lugar="vps", caminho="~/crew-state/e2e.lock",
            com=dict(pid=1379046, onde="PerpetualMiner-rev-t3", worker="pm-rev-t3", ha_s=57),
            esperando=[dict(pid=1403209, onde="/tmp/rev920/pr", worker=None, ha_s=5)])])

    def test_trava_livre_aparece_com_ninguem(self):
        self.rodar()
        self.assertEqual(self.arquivo("vps")["travas"], [dict(nome="e2e", lugar="vps", caminho="~/crew-state/e2e.lock", com=None, esperando=[])])

    def test_o_arquivo_do_mac_diz_quem_tem_a_trava_na_vps_e_a_do_proprio_mac(self):
        self.leituras["vps"] = vps(travas=MAC_NA_VPS, procs=MAC_PROCS_NA_VPS)
        self.leituras["mac"] = mac(procs=LOCKF_NO_MAC)
        self.rodar()
        self.assertEqual(self.arquivo("mac")["travas"], [
            dict(nome="mac", lugar="vps", caminho="~/crew-state/mac.lock",
                 com=dict(pid=1500100, onde="Nova-AI-prova", worker=None, ha_s=3725), esperando=[]),
            dict(nome="mac", lugar="mac", caminho="/tmp/fm-mac.lock",
                 com=dict(pid=93607, onde="/Users/usuario/prova", worker=None, ha_s=93784), esperando=[])])

    def test_o_pc_nao_tem_trava(self):
        self.rodar()
        self.assertEqual(self.arquivo("pc")["travas"], [])

    def test_trava_de_outro_arquivo_na_vps_nao_conta(self):
        self.leituras["vps"] = vps(travas="42 WRITE  /home/factory/crew-state/e2e.lock.velho", procs="42|/tmp|9")
        self.rodar()
        self.assertIsNone(self.arquivo("vps")["travas"][0]["com"])


class MaquinaFora(RecursosCase):
    def test_mac_que_nao_responde_vira_mac_fora_sem_derrubar_o_comando(self):
        self.leituras["mac"] = self.crew.Fail("ssh", "cannot reach vps: Connection timed out")
        resultado = self.rodar()
        self.assertTrue(resultado["ok"])
        gravado = self.arquivo("mac")
        self.assertFalse(gravado["alcancavel"])
        self.assertFalse(gravado["folga"])
        self.assertEqual(gravado["motivo"], "Mac fora")
        self.assertIn("Connection timed out", gravado["erro"])
        self.assertEqual(resultado["maquinas"]["mac"]["motivo"], "Mac fora")
        self.assertTrue(self.arquivo("pc")["folga"])
        self.assertTrue(self.arquivo("vps")["folga"])

    def test_leitura_em_formato_estranho_conta_como_maquina_fora(self):
        self.leituras["vps"] = "isto não é a leitura"
        self.rodar()
        self.assertEqual(self.arquivo("vps")["motivo"], "VPS fora")

    def test_vps_fora_deixa_o_mac_com_so_a_trava_dele(self):
        self.leituras["vps"] = self.crew.Fail("ssh", "sem rede")
        self.leituras["mac"] = mac(procs=LOCKF_NO_MAC)
        self.rodar()
        self.assertEqual([t["lugar"] for t in self.arquivo("mac")["travas"]], ["mac"])

    def test_mac_que_volta_so_recupera_a_folga_com_os_numeros_de_volta(self):
        self.leituras["mac"] = self.crew.Fail("ssh", "sem rede")
        self.rodar()
        self.leituras["mac"] = mac(livre_pct=45)
        self.rodar()
        self.assertFalse(self.arquivo("mac")["folga"])
        self.assertTrue(self.arquivo("mac")["alcancavel"])
        self.leituras["mac"] = mac(livre_pct=70)
        for _ in range(3):
            self.rodar()
        self.assertTrue(self.arquivo("mac")["folga"])


class Leitura:
    def __init__(self, terminou):
        self.terminou = terminou

    def poll(self):
        return 0 if self.terminou else None


class NoVigia(VigiaCase):
    def setUp(self):
        super().setUp()
        self.modulo = self.crew.module("crew_recursos")
        self.disparar_real = self.modulo.disparar_original
        self.disparos = []
        self.terminou = True
        self.erro = None
        self.modulo.disparar = self.disparar
        self.add_worker()

    def disparar(self):
        if self.erro:
            raise self.erro
        self.disparos.append(self.clock.now)
        return Leitura(self.terminou)

    def test_a_primeira_volta_dispara_a_leitura_dos_recursos(self):
        self.rodada()
        self.assertEqual(len(self.disparos), 1)

    def test_o_vigia_dispara_a_leitura_a_cada_minuto_e_nao_a_cada_volta_de_20_s(self):
        for _ in range(3):
            self.rodada(minutos=20 / 60)
        self.assertEqual(len(self.disparos), 1)
        self.rodada(minutos=1)
        self.assertEqual(len(self.disparos), 2)

    def test_enquanto_a_leitura_anterior_roda_o_vigia_nao_abre_outra(self):
        self.terminou = False
        self.rodada()
        self.rodada(minutos=5)
        self.assertEqual(len(self.disparos), 1)

    def test_nao_conseguir_abrir_a_leitura_nao_derruba_a_volta(self):
        self.erro = OSError("sem processos")
        self.add_events([dict(kind="decision_needed", id="D7", question="Qual banco usamos?")])
        self.assertEqual(len(self.rodada()), 1)

    def test_a_leitura_roda_num_processo_a_parte_que_o_vigia_nao_espera(self):
        abertos = []
        self.modulo.subprocess = types.SimpleNamespace(Popen=lambda argv, **kw: abertos.append(argv) or Leitura(False), DEVNULL=-3)
        self.disparar_real()
        self.assertEqual(len(abertos), 1)
        self.assertEqual(os.path.basename(abertos[0][1]), "crew.py")
        self.assertEqual(abertos[0][-1], "recursos")

if __name__ == "__main__":
    unittest.main()
