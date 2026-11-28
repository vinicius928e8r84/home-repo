import os
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest import mock

from scripts import crew

exe = crew.module("crew_exe")


class AcharCase(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.real = os.path.join(self.pasta, "real")
        os.mkdir(self.real)
        nome = "herdr.exe" if os.name == "nt" else "herdr"
        self.binario = os.path.join(self.real, nome)
        with open(self.binario, "w") as arquivo:
            arquivo.write("")
        os.chmod(self.binario, 0o755)

    def test_acha_o_que_esta_no_path(self):
        with mock.patch.dict(os.environ, {"PATH": self.real}):
            self.assertEqual(os.path.normcase(exe.achar("herdr")), os.path.normcase(self.binario))

    def test_sem_o_programa_no_path_devolve_none(self):
        with mock.patch.dict(os.environ, {"PATH": self.pasta}):
            self.assertIsNone(exe.achar("herdr"))

    @unittest.skipUnless(os.name == "nt", "o junction é do Windows")
    def test_atravessa_um_junction_que_o_windows_nao_deixa_atravessar(self):
        junction = os.path.join(self.pasta, "bin")
        subprocess.run(["cmd", "/c", "mklink", "/J", junction, self.real], check=True, capture_output=True)
        bloqueado = types.SimpleNamespace(which=lambda nome, path=None: None if path is None else shutil.which(nome, path=path))
        with mock.patch.dict(os.environ, {"PATH": junction}), mock.patch.object(exe, "shutil", bloqueado):
            achado = exe.achar("herdr")
        self.assertEqual(os.path.normcase(achado), os.path.normcase(self.binario))


if __name__ == "__main__":
    unittest.main()
