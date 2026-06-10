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

    def test_capture_from(self):
        r = self.call("vision_actions", "ue_capture_from",
                      location=[600, 600, 400], rotation=[-20, -135, 0],
                      width=320, height=180)
        self.assertSuccess(r)
        import base64
        self.assertEqual(base64.b64decode(r["image_data"])[:4], b"\x89PNG")

    def test_capture_from_missing(self):
        r = self.call("vision_actions", "ue_capture_from")
        self.assertFalse(r.get("success"))

    def test_capture_actors(self):
        spawn = self.call("actor_actions", "ue_spawn_from_object",
                          asset_path="/Engine/BasicShapes/Cube", location=[0, 0, 100])
        self.assertSuccess(spawn)
        label = spawn["actor_label"]
        try:
            r = self.call("vision_actions", "ue_capture_actors",
                          actor_labels=[label], width=320, height=180)
            self.assertSuccess(r)
            self.assertIn(label, r["framed_actors"])
            import base64
            self.assertEqual(base64.b64decode(r["image_data"])[:4], b"\x89PNG")
        finally:
            self.delete_actor_by_label(label)

    def test_capture_actors_unknown(self):
        r = self.call("vision_actions", "ue_capture_actors", actor_labels=["NoSuchActor_XYZ"])
        self.assertFalse(r.get("success"))

    def test_capture_actors_no_annotate(self):
        spawn = self.call("actor_actions", "ue_spawn_from_object",
                          asset_path="/Engine/BasicShapes/Cube", location=[0, 0, 100])
        self.assertSuccess(spawn)
        label = spawn["actor_label"]
        try:
            r = self.call("vision_actions", "ue_capture_actors",
                          actor_labels=[label], width=320, height=180, annotate=False)
            self.assertSuccess(r)
            import base64
            self.assertEqual(base64.b64decode(r["image_data"])[:4], b"\x89PNG")
        finally:
            self.delete_actor_by_label(label)
