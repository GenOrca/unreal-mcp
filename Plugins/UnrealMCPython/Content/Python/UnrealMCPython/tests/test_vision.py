import base64
from UnrealMCPython.tests.base import MCPTestCase


class TestVisionActions(MCPTestCase):

    def test_capture_viewport(self):
        r = self.call("vision_actions", "ue_capture_viewport", width=320, height=180)
        self.assertSuccess(r)
        self.assertIn("image_data", r)
        png = base64.b64decode(r["image_data"])
        self.assertEqual(png[:4], b"\x89PNG", "image_data is not a PNG")
        self.assertEqual(r["width"], 320)
        self.assertEqual(len(r["camera_location"]), 3)

    def test_capture_viewport_default_size(self):
        r = self.call("vision_actions", "ue_capture_viewport")
        self.assertSuccess(r)
        self.assertGreater(len(r["image_data"]), 0)
