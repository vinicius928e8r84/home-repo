import threading

from scripts.test_crew_fila import SEM_MEMORIA, FilaCase


class QuandoOSpawnEOVigiaGravamJuntos(FilaCase):
    def fila_modulo(self):
        return self.crew.module("crew_fila")

    def entrar_no_meio_da_rodada(self, nova, folga_depois):
        fila = self.fila_modulo()
        decidir = fila.decidir

        def decidir_e_entrar(tarefa):
            fila.decidir = decidir
            self.recursos(folga=False, motivo=SEM_MEMORIA)
            self.spawn(nova)
            self.recursos(folga=folga_depois, motivo=SEM_MEMORIA)
            return decidir(tarefa)

        fila.decidir = decidir_e_entrar

    def test_tarefa_que_entra_no_meio_da_rodada_continua_na_fila(self):
        self.recursos(folga=False, motivo=SEM_MEMORIA)
        self.spawn("velha")
        self.entrar_no_meio_da_rodada("nova", False)
        self.fila_modulo().rodada()
        self.assertEqual(sorted(self.nomes_na_fila()), ["t-nova", "t-velha"])

    def test_a_rodada_que_abre_uma_tarefa_nao_apaga_a_que_entrou_no_meio(self):
        self.recursos(folga=False, motivo=SEM_MEMORIA)
        self.spawn("velha")
        self.recursos()
        self.entrar_no_meio_da_rodada("nova", True)
        self.fila_modulo().rodada()
        self.assertEqual(self.abertos(), ["t-velha"])
        self.assertEqual(self.nomes_na_fila(), ["t-nova"])

    def segurar_a_trava(self):
        fila = self.fila_modulo()
        fila.ESPERA_DA_TRAVA_SEGUNDOS = 0.3
        pronta, solta = threading.Event(), threading.Event()

        def segurar():
            with fila.trava():
                pronta.set()
                solta.wait(5)

        dono = threading.Thread(target=segurar)
        dono.start()
        self.addCleanup(dono.join)
        self.addCleanup(solta.set)
        self.assertTrue(pronta.wait(5))
        return solta, dono

    def test_quem_chega_com_a_trava_ocupada_espera_e_depois_desiste_com_erro(self):
        fila = self.fila_modulo()
        solta, dono = self.segurar_a_trava()
        with self.assertRaises(self.crew.Fail) as erro:
            with fila.trava():
                pass
        self.assertEqual(erro.exception.step, "fila")
        solta.set()
        dono.join()
        with fila.trava():
            pass

    def test_quem_so_le_a_fila_tambem_espera_a_trava(self):
        self.recursos(folga=False, motivo=SEM_MEMORIA)
        self.spawn()
        self.segurar_a_trava()
        with self.assertRaises(self.crew.Fail) as erro:
            self.fila()
        self.assertEqual(erro.exception.step, "fila")

    def test_com_a_trava_presa_o_vigia_segue_como_se_houvesse_fila(self):
        self.segurar_a_trava()
        self.assertTrue(self.fila_modulo().pendentes())


class QuandoUmaTarefaSaiDaFila(FilaCase):
    def test_pedido_que_quebra_sem_ser_falha_do_spawn_deixa_o_evento(self):
        self.recursos(folga=False, motivo=SEM_MEMORIA)
        self.spawn()
        self.recursos()

        def quebrar(pedido):
            raise OSError("disco cheio")

        self.crew.cmd_spawn = quebrar
        self.watch()
        self.assertEqual(self.fila(), [])
        [evento] = [e for e in self.events() if e["kind"] == "spawn_failed"]
        self.assertEqual(evento["worker"], "t-job")
        self.assertIn("disco cheio", evento["error"])
