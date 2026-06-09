import unreal
from UnrealMCPython.tests.base import MCPTestCase

_LAYER = "MCP_TestLayer"
_CLASS_PATH = "/Script/Engine.PointLight"


class TestLayerActions(MCPTestCase):

    def setUp(self):
        self._actor_label = None
        r = self.call("actor_actions", "ue_spawn_from_class",
                      class_path=_CLASS_PATH, location=[0, 0, 550])
        if r.get("success"):
            self._actor_label = r["actor_label"]

    def tearDown(self):
        self.call("layer_actions", "ue_delete_layer", layer_name=_LAYER)
        if self._actor_label:
            self.delete_actor_by_label(self._actor_label)

    def test_list_layers(self):
        r = self.call("layer_actions", "ue_list_layers")
        self.assertSuccess(r)
        self.assertIsInstance(r["layers"], list)

    def test_create_and_delete_layer(self):
        r = self.call("layer_actions", "ue_create_layer", layer_name=_LAYER)
        self.assertSuccess(r)
        layers = self.call("layer_actions", "ue_list_layers")["layers"]
        self.assertIn(_LAYER, layers)
        r = self.call("layer_actions", "ue_delete_layer", layer_name=_LAYER)
        self.assertSuccess(r)

    def test_delete_layer_missing(self):
        r = self.call("layer_actions", "ue_delete_layer", layer_name="NoSuchLayer_XYZ")
        self.assertFalse(r.get("success"))

    def test_add_and_remove_actor_in_layer(self):
        if not self._actor_label:
            self.skipTest("Actor not spawned in setUp")
        self.call("layer_actions", "ue_create_layer", layer_name=_LAYER)
        r = self.call("layer_actions", "ue_add_actor_to_layer",
                      actor_label=self._actor_label, layer_name=_LAYER)
        self.assertSuccess(r)
        actors = self.call("layer_actions", "ue_get_actors_in_layer", layer_name=_LAYER)
        self.assertIn(self._actor_label, actors["actors"])
        r = self.call("layer_actions", "ue_remove_actor_from_layer",
                      actor_label=self._actor_label, layer_name=_LAYER)
        self.assertSuccess(r)
        actors = self.call("layer_actions", "ue_get_actors_in_layer", layer_name=_LAYER)
        self.assertNotIn(self._actor_label, actors["actors"])

    def test_add_actor_unknown(self):
        r = self.call("layer_actions", "ue_add_actor_to_layer",
                      actor_label="NoSuchActor_XYZ", layer_name=_LAYER)
        self.assertFalse(r.get("success"))
