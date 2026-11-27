import contextlib
import io
import os
import stat
import tempfile
import types
import unittest

from scripts.test_crew import CHIEF, CrewCase

HERDR_DE_MENTIRA = """#!/bin/bash
echo "$*" >> "$DRILL_LOG"
echo "$CREW_STATE_DIR|$CREW_REPOS|$CREW_HERDR_SESSION|$HERDR_PANE_ID|$HERDR_ENV" >> "$DRILL_LOG.env"
shift 2
case "$1 $2" in
  "server ") touch "$DRILL_RODANDO"; while [ -e "$DRILL_RODANDO" ]; do sleep 0.2; done ;;
  "server stop") rm -f "$DRILL_RODANDO" ;;
  "workspace list") echo '{"result":{"workspaces":[]}}' ;;
  "workspace create") echo '{"result":{"root_pane":{"pane_id":"w1:p1"}}}' ;;
  "pane get") echo '{"result":{"pane":{"pane_id":"w1:p1"}}}' ;;
  "session delete") ;;
  *) echo "herdr de mentira: $*" >&2; exit 1 ;;
esac
"""


class Drill(CrewCase):

    def setUp(self):
        super().setUp()
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        self.log = os.path.join(self.tmp, "herdr.log")
        herdr = os.path.join(self.bin, "herdr")
        with open(herdr, "w", encoding="utf-8") as f:
            f.write(HERDR_DE_MENTIRA)
        os.chmod(herdr, os.stat(herdr).st_mode | stat.S_IEXEC)
        os.environ.update(PATH=self.bin + os.pathsep + os.environ["PATH"], DRILL_LOG=self.log, DRILL_RODANDO=os.path.join(self.tmp, "rodando"),
                          HERDR_ENV="1", HERDR_PANE_ID=CHIEF)

    def rodar(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.crew.module("crew_drill").drill(types.SimpleNamespace(model="x/y:low"))

    def linhas(self, sufixo=""):
        with open(self.log + sufixo, encoding="utf-8") as f:
            return f.read().splitlines()

    def test_a_drill_that_cannot_open_the_test_worker_says_which_step_failed(self):
        relatorio = self.rodar()
        self.assertFalse(relatorio["ok"])
        self.assertEqual([p["nome"] for p in relatorio["passos"] if not p["ok"]], ["abrir o Worker de teste"])

    def test_it_only_talks_to_its_own_disposable_herdr_session(self):
        relatorio = self.rodar()
        sessoes = {linha.split()[1] for linha in self.linhas()}
        self.assertEqual(sessoes, {relatorio["sessao"]})
        self.assertNotIn(relatorio["sessao"], {"default", "crew", "vps"})
        self.assertTrue(relatorio["sessao"].startswith("drill-"))

    def test_it_never_reuses_the_real_state_repos_or_chief_pane(self):
        self.rodar()
        for estado, repos, sessao, pane, _ in (linha.split("|") for linha in self.linhas(".env")):
            self.assertNotEqual(estado, self.state)
            self.assertTrue(estado.startswith(tempfile.gettempdir()))
            self.assertNotEqual(repos, os.environ["CREW_REPOS"])
            self.assertTrue(sessao.startswith("drill-"))
            self.assertNotEqual(pane, CHIEF)

    def test_it_leaves_nothing_behind(self):
        self.rodar()
        estado = self.linhas(".env")[0].split("|")[0]
        self.assertFalse(os.path.exists(estado))
        self.assertFalse(os.path.exists(os.environ["DRILL_RODANDO"]))
        self.assertEqual(os.listdir(os.path.join(self.home, "worktrees")) if os.path.isdir(os.path.join(self.home, "worktrees")) else [], [])
        self.assertTrue(any(" server stop" in " " + linha for linha in self.linhas()))
        self.assertTrue(any(" session delete " in linha for linha in self.linhas()))


if __name__ == "__main__":
    unittest.main()
