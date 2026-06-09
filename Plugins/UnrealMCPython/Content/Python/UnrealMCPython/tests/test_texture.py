import unreal
from UnrealMCPython.tests.base import MCPTestCase, TEST_ROOT

_SRC = "/Engine/EngineResources/DefaultTexture"


class TestTextureActions(MCPTestCase):

    def test_get_texture_info(self):
        if not unreal.EditorAssetLibrary.does_asset_exist(_SRC):
            self.skipTest("Engine DefaultTexture not available")
        r = self.call("texture_actions", "ue_get_texture_info", asset_path=_SRC)
        self.assertSuccess(r)
        self.assertGreater(r["width"], 0)
        self.assertGreater(r["height"], 0)
        self.assertIsInstance(r["srgb"], bool)

    def test_get_texture_info_invalid(self):
        r = self.call("texture_actions", "ue_get_texture_info", asset_path="/Game/Nope_XYZ")
        self.assertFalse(r.get("success"))

    def _dup(self, name):
        self.ensure_test_dir()
        dst = f"{TEST_ROOT}/{name}"
        self.delete_asset(dst)
        unreal.EditorAssetLibrary.duplicate_asset(_SRC, dst)
        return dst

    def test_set_texture_srgb(self):
        if not unreal.EditorAssetLibrary.does_asset_exist(_SRC):
            self.skipTest("Engine DefaultTexture not available")
        dst = self._dup("MCP_TexSrgb")
        try:
            r = self.call("texture_actions", "ue_set_texture_srgb", asset_path=dst, srgb=False)
            self.assertSuccess(r)
            info = self.call("texture_actions", "ue_get_texture_info", asset_path=dst)
            self.assertFalse(info["srgb"])
        finally:
            self.delete_asset(dst)

    def test_set_texture_compression(self):
        if not unreal.EditorAssetLibrary.does_asset_exist(_SRC):
            self.skipTest("Engine DefaultTexture not available")
        dst = self._dup("MCP_TexComp")
        try:
            r = self.call("texture_actions", "ue_set_texture_compression",
                          asset_path=dst, compression="TC_NORMALMAP")
            self.assertSuccess(r)
        finally:
            self.delete_asset(dst)

    def test_set_texture_compression_invalid(self):
        r = self.call("texture_actions", "ue_set_texture_compression",
                      asset_path=_SRC, compression="NOTACOMPRESSION")
        self.assertFalse(r.get("success"))
