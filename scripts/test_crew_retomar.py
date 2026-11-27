import contextlib
import io
import json
import os
import re
import types
import unittest

from scripts.crew_sessao import pasta_da_sessao
from scripts.test_crew import CrewCase

DISCO = dict(type="error", message="ENOSPC: no space left on device, write")
BRIDGE = dict(type="error", message="Cut boundary 9847936c-1111-2222-3333-444455556666 is not on the primary parent chain")
DATA = "2026-11-27T10-00-00-000Z"


def resposta(parou, erro=None):
    mensagem = dict(role="assistant", stopReason=parou, content=[dict(type="text", text="ok")])
    if erro:
        mensagem["errorMessage"] = erro
    return json.dumps(dict(type="message", timestamp="2026-11-27T10:00:00.000Z", message=mensagem), separators=(",", ":"))


class Base(CrewCase):

    def setUp(self):
        super().setUp()
        self.pi = os.path.join(self.tmp, "pi")
        os.environ["PI_CODING_AGENT_DIR"] = self.pi
        self.mensagens = []
        self.responder = None
        enviar = self.herdr.handlers[("pane", "send-keys")]

        def pane_send_keys(step, *args):
            texto = self.herdr.typed.get(args[2], "")
            resultado = enviar(step, *args)
            if texto:
                self.mensagens.append((args[2], texto))
                self.quando_receber(args[2])
            return resultado

        self.herdr.handlers[("pane", "send-keys")] = pane_send_keys

    def quando_receber(self, pane):
        if self.responder:
            conversa = re.search(r"--session-id (\S+)", self.herdr.launched[pane]).group(1)
            self.escrever(conversa, [self.responder(conversa)])

    def pasta_das_conversas(self, meta):
        return os.path.join(self.pi, "sessions", pasta_da_sessao(meta["worktree"]))

    def arquivo(self, conversa):
        pasta = self.pasta_das_conversas(self.meta)
        return os.path.join(pasta, "%s_%s.jsonl" % (DATA, conversa))

    def escrever(self, conversa, linhas):
        os.makedirs(os.path.dirname(self.arquivo(conversa)), exist_ok=True)
        with open(self.arquivo(conversa), "a", encoding="utf-8") as f:
            f.write("".join(linha + "\n" for linha in linhas))

    def linhas(self, conversa):
        with open(self.arquivo(conversa), encoding="utf-8") as f:
            return f.read().splitlines()

    def parado(self, desfecho=DISCO, **campos):
        self.meta = self.add_worker(state="idle", **campos)
        self.gravar_estado(desfecho)
        return self.meta

    def gravar_estado(self, desfecho):
        with open(self.meta["state_file"], "w", encoding="utf-8") as f:
            json.dump(dict(state="idle", turns=1, at="2026-11-27T11:00:00+00:00", outcome=desfecho), f)

    def conversa_do_worker(self, nome="t-job"):
        cabeca = json.dumps(dict(type="session", version=3, id=nome, timestamp="2026-11-27T10:00:00.000Z", cwd=self.meta["worktree"]))
        self.escrever(nome, [cabeca, resposta("stop")])

    def retomar(self, nome="t-job"):
        args = types.SimpleNamespace(name=nome, start_timeout=5, prompt_timeout=10)
        with contextlib.redirect_stdout(io.StringIO()):
            return self.crew.module("crew_retomada").retomar(args)


class Retomada(Base):

    def test_closes_the_old_pane_and_opens_pi_again_in_the_same_conversation_without_a_model(self):
        self.parado()
        resultado = self.retomar()
        self.assertFalse(self.herdr.panes["w4:p1"]["alive"])
        comando = self.herdr.launched[resultado["pane"]]
        self.assertRegex(comando, r'^pi --session-id t-job --approve -e "[^"]+crew-state\.ts"$')
        self.assertNotIn("--model", comando)
        self.assertEqual(self.crew.read_meta("t-job")["pane"], resultado["pane"])

    def test_the_message_back_carries_the_cause_and_not_the_brief_again(self):
        self.parado()
        resultado = self.retomar()
        (pane, texto), = self.mensagens
        self.assertEqual(pane, resultado["pane"])
        self.assertIn("disco", texto)
        self.assertNotIn("Leia o arquivo", texto)
        self.assertEqual(resultado["causa"], "disco")

    def test_a_stop_without_a_recorded_cause_still_resumes(self):
        self.parado(desfecho=None)
        resultado = self.retomar()
        self.assertIsNone(resultado["causa"])
        self.assertIn("não registrada", self.mensagens[0][1])

    def test_the_watcher_does_not_call_the_swap_a_gone_pane(self):
        self.parado()
        self.herdr.on_close = self.watch
        self.retomar()
        self.assertNotIn("gone", [e["kind"] for e in self.events()])
        self.assertIn("resumed", [e["kind"] for e in self.events()])
        self.assertNotIn("closing", self.crew.read_meta("t-job"))

    def test_a_worker_on_another_machine_gets_a_clear_error(self):
        self.parado(host="vps")
        with self.assertRaises(self.crew.Fail) as caught:
            self.retomar()
        self.assertEqual(caught.exception.step, "retomar")
        self.assertIn("another machine", caught.exception.error)
        self.assertTrue(self.herdr.panes["w4:p1"]["alive"])

    def test_a_closed_worker_is_not_resumed(self):
        self.parado(closed="2026-11-27T10:00:00-03:00")
        with self.assertRaises(self.crew.Fail) as caught:
            self.retomar()
        self.assertEqual(caught.exception.step, "retomar")

    def test_gives_up_loudly_when_pi_never_gets_ready(self):
        self.parado()
        self.herdr.handlers[("pane", "run")] = lambda step, *args: {}
        with self.assertRaises(self.crew.Fail) as caught:
            self.retomar()
        self.assertEqual(caught.exception.step, "agent")


class ConversaQuebrada(Base):

    def setUp(self):
        super().setUp()
        self.parado(desfecho=BRIDGE)
        self.conversa_do_worker()

    def test_opens_a_copy_of_the_conversation_under_another_name(self):
        self.responder = lambda conversa: resposta("stop")
        resultado = self.retomar()
        self.assertIn("--session-id t-job-2 ", self.herdr.launched[resultado["pane"]] + " ")
        original, copia = self.linhas("t-job"), self.linhas("t-job-2")
        self.assertEqual(json.loads(copia[0])["id"], "t-job-2")
        self.assertEqual(copia[1:len(original)], original[1:])
        self.assertEqual((resultado["conversa"], resultado["copia"]), ("t-job-2", "funcionou"))
        self.assertEqual(self.crew.read_meta("t-job")["conversa"], "t-job-2")
        self.assertIn("conversa quebrada no bridge", self.mensagens[0][1])

    def test_the_next_resume_follows_the_copy(self):
        self.responder = lambda conversa: resposta("stop")
        self.retomar()
        self.gravar_estado(DISCO)
        resultado = self.retomar()
        self.assertIn("--session-id t-job-2 ", self.herdr.launched[resultado["pane"]] + " ")

    def test_falls_back_to_a_new_conversation_with_the_brief_when_the_copy_breaks_again(self):
        self.responder = lambda conversa: resposta("error", BRIDGE["message"]) if conversa == "t-job-2" else resposta("stop")
        resultado = self.retomar()
        self.assertEqual((resultado["conversa"], resultado["copia"]), ("t-job-3", "caiu no recomeço"))
        comando = self.herdr.launched[resultado["pane"]]
        self.assertIn("--session-id t-job-3 ", comando + " ")
        self.assertIn("--model x/y:high", comando)
        texto = self.mensagens[-1][1]
        self.assertIn("Leia o arquivo %s" % self.meta["brief"], texto)
        self.assertIn(self.meta["branch"], texto)
        self.assertFalse(self.herdr.panes["w9:p1"]["alive"])

    def test_without_a_conversation_file_it_starts_over_with_the_brief(self):
        os.remove(self.arquivo("t-job"))
        resultado = self.retomar()
        self.assertEqual((resultado["conversa"], resultado["copia"]), ("t-job-2", "caiu no recomeço"))
        self.assertIn("Leia o arquivo", self.mensagens[-1][1])

    def test_says_so_when_the_copy_does_not_answer_in_time(self):
        resultado = self.retomar()
        self.assertEqual(resultado["copia"], "sem confirmação")


if __name__ == "__main__":
    unittest.main()
