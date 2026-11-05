import unittest
from unittest.mock import patch
import hardware


class TestHardwareMemory(unittest.TestCase):
    def test_memoria_status_linux(self):
        conteudo = "MemTotal:       16384000 kB\nMemAvailable:    8192000 kB\n"
        with patch.object(hardware.sys, "platform", "linux"), patch("builtins.open", unittest.mock.mock_open(read_data=conteudo)):
            total, livre = hardware._memoria_status_gb()
        self.assertEqual(total, 15.6)
        self.assertEqual(livre, 7.8)

    def test_vram_nvidia_ausente_nao_falha(self):
        with patch.object(hardware.shutil, "which", return_value=None):
            self.assertEqual(hardware._vram_disponivel_nvidia(), {})
