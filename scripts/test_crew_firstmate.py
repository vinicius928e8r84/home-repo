import json
import os
import unittest

from scripts.test_crew_vigia import VigiaCase

ETIQUETA = "[home-repo] "


def recibos(*itens):
    handled, replies = [], []
    for numero, (corpo, resposta) in enumerate(itens, 1):
        ident = "n%d" % abs(hash(corpo))
        handled.append(dict(id=ident, body=corpo))
        if resposta:
            replies.append(dict(id=ident, body=resposta, cursor="%012d" % numero))
    return dict(handled=handled, pending=[], replies=replies)


class RespostasDoFirstmate(VigiaCase):
    def setUp(self):
        super().setUp()
        self.dados = recibos((ETIQUETA + "ja respondida", "antiga"))
        self.chamadas = 0
        self.crew.module("crew_firstmate").ler_recibos = self.ler

    def ler(self):
        self.chamadas += 1
        if isinstance(self.dados, Exception):
            raise self.dados
        return self.dados

    def respostas(self):
        return [a for a in self.avisos() if "firstmate" in a]

    def test_resposta_antiga_do_primeiro_olhar_nao_acorda(self):
        self.rodada(3)
        self.assertNotIn("firstmate_reply", self.kinds())

    def test_nota_respondida_chega_uma_vez_so(self):
        self.rodada(3)
        self.dados = recibos((ETIQUETA + "ja respondida", "antiga"), (ETIQUETA + "pergunta sobre o CodeScene", "A resposta e sim."))
        for _ in range(4):
            self.rodada(3)
        achados = self.respostas()
        self.assertEqual(len(achados), 1)
        self.assertIn("pergunta sobre o CodeScene", achados[0])
        self.assertIn("A resposta e sim.", achados[0])
        self.assertEqual(self.kinds().count("firstmate_reply"), 1)

    def test_resposta_a_nota_de_outro_nao_acorda(self):
        self.rodada(3)
        self.dados = recibos((ETIQUETA + "nossa", ""), ("de outro agente", "resposta alheia"))
        self.rodada(3)
        self.assertEqual(self.respostas(), [])
        self.assertNotIn("firstmate_reply", self.kinds())

    def test_nao_olha_o_vps_a_cada_volta(self):
        self.rodada(3)
        self.rodada(0)
        self.assertEqual(self.chamadas, 1)

    def test_vps_fora_do_ar_nao_derruba_o_vigia(self):
        self.dados = self.crew.Fail("firstmate", "ssh caiu")
        for _ in range(3):
            self.rodada(3)
        self.assertEqual(self.chamadas, 3)
        self.assertEqual(self.respostas(), [])

    def test_apos_a_queda_a_resposta_nova_chega(self):
        self.rodada(3)
        self.dados = self.crew.Fail("firstmate", "ssh caiu")
        self.rodada(3)
        self.dados = recibos((ETIQUETA + "ja respondida", "antiga"), (ETIQUETA + "nova", "chegou"))
        self.rodada(3)
        self.assertEqual(len(self.respostas()), 1)

    def test_resposta_gigante_e_cortada(self):
        self.rodada(3)
        self.dados = recibos((ETIQUETA + "x", "palavra " * 1000))
        self.rodada(3)
        self.assertLess(len(self.respostas()[0]), 1900)


if __name__ == "__main__":
    unittest.main()
