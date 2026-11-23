import os
import unittest
from unittest import mock

from scripts.freios import testes


class TesteDoAmbiente(unittest.TestCase):
    def test_tira_as_variaveis_do_git_e_guarda_o_resto(self):
        with mock.patch.dict(os.environ, {"GIT_DIR": "x", "GIT_INDEX_FILE": "y", "MINHA_VARIAVEL": "z"}):
            ambiente = testes.ambiente_sem_git()
        self.assertNotIn("GIT_DIR", ambiente)
        self.assertNotIn("GIT_INDEX_FILE", ambiente)
        self.assertEqual(ambiente["MINHA_VARIAVEL"], "z")


if __name__ == "__main__":
    unittest.main()
