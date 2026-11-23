import os
import unittest
from unittest import mock

from scripts.freios.apoio_de_teste import RepositorioTemporario


class IsolamentoDoAmbiente(unittest.TestCase):
    def test_o_repositorio_temporario_tira_ci_e_git_do_ambiente_e_devolve_ao_limpar(self):
        with mock.patch.dict(os.environ, {"CI": "true", "GIT_DIR": "x"}):
            repo = RepositorioTemporario()
            self.assertNotIn("CI", os.environ)
            self.assertNotIn("GIT_DIR", os.environ)
            repo.limpar()
            self.assertEqual(os.environ["CI"], "true")
            self.assertEqual(os.environ["GIT_DIR"], "x")


if __name__ == "__main__":
    unittest.main()
