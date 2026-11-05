from __future__ import annotations

import unittest

from image_generator import parametros_checkpoint


class TestImageCheckpointProfiles(unittest.TestCase):
    def test_dreamshaper_turbo_usa_poucos_passos_e_cfg_baixo(self):
        profile = parametros_checkpoint("DreamShaperXL_Turbo_SFWdpmppSde_half_pruned.safetensors")
        self.assertEqual(profile["steps"], 6)
        self.assertEqual(profile["cfg"], 2.0)
        self.assertEqual(profile["sampler_name"], "dpmpp_sde")

    def test_animagine_tem_prompt_suffix_e_parametros_proprios(self):
        profile = parametros_checkpoint("animagine-xl-4.0-opt.safetensors")
        self.assertEqual(profile["steps"], 25)
        self.assertEqual(profile["sampler_name"], "euler_ancestral")
        self.assertIn("masterpiece", profile["prompt_suffix"])

    def test_juggernaut_e_realvis_tem_presets_distintos(self):
        juggernaut = parametros_checkpoint("Juggernaut-XL_v9.safetensors")
        realvis = parametros_checkpoint("RealVisXL_V5.0_fp16.safetensors")
        self.assertEqual(juggernaut["steps"], 30)
        self.assertEqual(juggernaut["sampler_name"], "dpmpp_2m")
        self.assertEqual(realvis["steps"], 32)
        self.assertEqual(realvis["sampler_name"], "dpmpp_sde")

    def test_checkpoint_desconhecido_recebe_fallback_seguro(self):
        profile = parametros_checkpoint("custom.safetensors")
        self.assertGreaterEqual(profile["steps"], 1)
        self.assertLessEqual(profile["steps"], 50)
        self.assertGreater(profile["cfg"], 0)


if __name__ == "__main__":
    unittest.main()
