import contextlib
import io
import json
import os
import subprocess
import sys
import types
import unittest

from scripts.test_crew import CHIEF
from scripts.test_crew_vigia import VigiaCase


class ConversaCase(VigiaCase):
    def setUp(self):
        super().setUp()
        os.environ.pop("CREW_AGENT_NAME", None)
        self.add_worker()
        self.beat(CHIEF)

    def beat(self, chief):
        os.makedirs(self.state, exist_ok=True)
        with open(os.path.join(self.state, "watch.heartbeat"), "w", encoding="utf-8") as f:
            json.dump(dict(chief=chief), f)

    def ask(self, question="qual abordagem?", para=None, **extra):
        args = dict(question=question, recommend="a primeira", para=para, worker="t-job", repo=None)
        return self.crew.module("crew_conversa").ask(types.SimpleNamespace(**dict(args, **extra)))

    def board(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.crew.cmd_board(types.SimpleNamespace(json=True))

    def board_text(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.crew.cmd_board(types.SimpleNamespace(json=False))
        return out.getvalue()


class QuestionToTheChief(ConversaCase):
    def test_the_watcher_puts_it_in_the_chief_inbox_as_a_question_with_its_title(self):
        result = self.ask()
        self.assertEqual((result["id"], result["para"]), ("P1", "chief"))
        told = self.rodada()
        self.assertEqual(len(told), 1)
        self.assertIn("t-job pergunta ao chief: P1 «qual abordagem?»", told[0])
        self.assertNotIn("decisão", told[0])

    def test_without_para_it_goes_to_the_chief(self):
        self.assertEqual(self.ask()["para"], "chief")

    def test_it_never_reaches_the_owner(self):
        self.ask()
        self.assertNotIn("decision_needed", self.kinds())
        self.assertIn("question_for_chief", self.kinds())
        board = self.board()
        self.assertEqual(board["decisions"], [])
        self.assertEqual([q["id"] for q in board["questions"]], ["P1"])
        text = self.board_text()
        owner_part = text[text.index("## Cole no fim"):]
        self.assertNotIn("qual abordagem?", owner_part)
        self.assertIn("Suas decisões**: nenhuma", owner_part)
        chief_part = text[:text.index("## Decisões esperando")]
        self.assertIn("## Perguntas ao chief (1)", chief_part)
        self.assertIn("qual abordagem?", chief_part)

    def test_it_is_announced_once_and_never_twice(self):
        self.ask()
        self.rodada()
        self.rodada()
        self.assertEqual(len(self.told_chief()), 1)

    def test_a_worker_waiting_on_the_chief_is_not_a_worker_in_trouble(self):
        self.add_worker(state="idle", turns=2)
        self.ask()
        board = self.board()
        self.assertEqual([m["name"] for m in board["running"]], ["t-job"])
        self.assertEqual(board["trouble"], [])

    def test_it_stays_on_the_board_until_answered(self):
        self.ask()
        self.assertEqual([q["id"] for q in self.board()["questions"]], ["P1"])

    def test_the_answer_reaches_the_worker_as_a_question_answer(self):
        self.ask()
        self.crew.cmd_answer(types.SimpleNamespace(id="p1", answer="a segunda"))
        self.assertEqual(self.herdr.sent["w4:p1"], ["[chief] Pergunta P1 (qual abordagem?): a segunda"])
        self.assertEqual(self.board()["questions"], [])


class DecisionForTheOwner(ConversaCase):
    def test_it_goes_to_the_owner_board_as_before(self):
        result = self.ask("posso gastar?", para="dono")
        self.assertEqual((result["id"], result["para"]), ("D1", "dono"))
        self.assertIn("decision_needed", self.kinds())
        self.assertNotIn("question_for_chief", self.kinds())
        board = self.board()
        self.assertEqual([d["id"] for d in board["decisions"]], ["D1"])
        self.assertEqual(board["questions"], [])

    def test_the_answer_says_decision(self):
        self.ask("posso gastar?", para="dono")
        self.crew.cmd_answer(types.SimpleNamespace(id="D1", answer="pode"))
        self.assertEqual(self.herdr.sent["w4:p1"], ["[chief] Decisão D1 (posso gastar?): pode"])

    def test_questions_and_decisions_count_apart(self):
        ids = [self.ask(para=para)["id"] for para in ("chief", "dono", "chief", "dono")]
        self.assertEqual(ids, ["P1", "D1", "P2", "D2"])

    def test_a_decision_in_the_old_format_still_counts_as_the_owners(self):
        self.crew.log_decision(dict(id="D1", at=self.crew.now(), worker="t-job", repo="Test", question="velha", recommend="r", status="open"))
        self.assertEqual([d["id"] for d in self.board()["decisions"]], ["D1"])
        self.assertEqual(self.ask(para="dono")["id"], "D2")

    def test_the_chiefs_own_ask_is_always_the_owners(self):
        result = self.ask(worker=None, repo="Test")
        self.assertEqual((result["id"], result["para"]), ("D1", "dono"))
        with self.assertRaises(self.crew.Fail) as caught:
            self.ask(worker=None, repo="Test", para="chief")
        self.assertIn("--para dono", caught.exception.error)


class TellTheChief(ConversaCase):
    def tell(self):
        return self.crew.cmd_tell(types.SimpleNamespace(name="chief", message="terminei a leitura"))

    def test_goes_to_the_chief_inbox_as_a_notice(self):
        os.environ["CREW_AGENT_NAME"] = "t-job"
        self.assertTrue(self.tell()["delivered"])
        told = self.told_chief()
        self.assertEqual(len(told), 1)
        self.assertIn("t-job avisa o chief: terminei a leitura", told[0])
        self.assertIn("told_chief", self.kinds())
        self.assertEqual(self.board()["questions"], [])

    def test_says_clearly_when_the_chief_cannot_be_reached(self):
        os.remove(os.path.join(self.state, "watch.heartbeat"))
        with self.assertRaises(self.crew.Fail) as caught:
            self.tell()
        self.assertIn("watcher is not running", caught.exception.error)

    def test_a_real_worker_name_still_goes_to_the_worker(self):
        self.crew.cmd_tell(types.SimpleNamespace(name="t-job", message="oi"))
        self.assertEqual(self.herdr.sent["w4:p1"], ["[chief] oi"])


class AskFromTheCommandLine(ConversaCase):
    def test_an_unknown_para_is_refused_by_the_parser(self):
        here = os.path.dirname(os.path.abspath(__file__))
        out = subprocess.run([sys.executable, "-I", os.path.join(here, "crew.py"), "ask", "q", "--recommend", "r", "--para", "ninguem"],
                             capture_output=True, text=True)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("invalid choice", out.stderr)

    def test_a_para_outside_the_two_is_not_registered(self):
        with self.assertRaises(ValueError):
            self.crew.module("crew_conversa").register("t-job", "Test", dict(question="q", recommend="r"), "ninguem")


if __name__ == "__main__":
    unittest.main()
