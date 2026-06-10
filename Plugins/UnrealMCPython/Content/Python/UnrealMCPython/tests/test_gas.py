import unreal
from UnrealMCPython.tests.base import MCPTestCase, TEST_ROOT

_GA_PATH = f"{TEST_ROOT}/MCP_TestGA"
_GE_PATH = f"{TEST_ROOT}/MCP_TestGE"
_TEST_ATTR_SET = "/Script/GameplayAbilities.AbilitySystemTestAttributeSet"


class TestGasActions(MCPTestCase):

    def setUp(self):
        if not hasattr(unreal, "GameplayAbility"):
            self.skipTest("GameplayAbilities plugin not enabled")
        self.ensure_test_dir()
        for p in (_GA_PATH, _GE_PATH):
            self.delete_asset(p)

    def tearDown(self):
        for p in (_GA_PATH, _GE_PATH):
            self.delete_asset(p)

    # ── abilities ────────────────────────────────────────────────────────────────

    def test_create_ability_and_info(self):
        r = self.call("gas_actions", "ue_create_ability_blueprint", asset_path=_GA_PATH)
        self.assertSuccess(r)
        r = self.call("gas_actions", "ue_get_ability_info", asset_path=_GA_PATH)
        self.assertSuccess(r)
        self.assertEqual(r["ability_tags"], [])
        self.assertIsNone(r["cost_effect"])

    def test_create_ability_bad_parent(self):
        r = self.call("gas_actions", "ue_create_ability_blueprint",
                      asset_path=_GA_PATH, parent_class_path="/Script/Engine.Actor")
        self.assertFalse(r.get("success"))

    def test_set_ability_costs(self):
        self.call("gas_actions", "ue_create_ability_blueprint", asset_path=_GA_PATH)
        self.call("gas_actions", "ue_create_effect_blueprint", asset_path=_GE_PATH)
        r = self.call("gas_actions", "ue_set_ability_costs",
                      asset_path=_GA_PATH, cost_effect_path=_GE_PATH,
                      cooldown_effect_path=_GE_PATH)
        self.assertSuccess(r)
        info = self.call("gas_actions", "ue_get_ability_info", asset_path=_GA_PATH)
        self.assertIsNotNone(info["cost_effect"])
        self.assertIsNotNone(info["cooldown_effect"])

    def test_set_ability_tags_unregistered(self):
        self.call("gas_actions", "ue_create_ability_blueprint", asset_path=_GA_PATH)
        r = self.call("gas_actions", "ue_set_ability_tags",
                      asset_path=_GA_PATH, tags=["MCP.NoSuchTag.Xyz"])
        self.assertSuccess(r)
        self.assertIn("MCP.NoSuchTag.Xyz", r["unresolved_tags"])

    # ── effects ──────────────────────────────────────────────────────────────────

    def test_create_effect_with_duration(self):
        r = self.call("gas_actions", "ue_create_effect_blueprint",
                      asset_path=_GE_PATH, duration_policy="has_duration",
                      duration_seconds=8.0)
        self.assertSuccess(r)
        info = self.call("gas_actions", "ue_get_effect_info", asset_path=_GE_PATH)
        self.assertSuccess(info)
        self.assertEqual(info["duration_policy"], "has_duration")
        self.assertAlmostEqual(info["duration_seconds"], 8.0, places=2)

    def test_set_effect_duration_bad_policy(self):
        self.call("gas_actions", "ue_create_effect_blueprint", asset_path=_GE_PATH)
        r = self.call("gas_actions", "ue_set_effect_duration",
                      asset_path=_GE_PATH, duration_policy="nonsense")
        self.assertFalse(r.get("success"))

    def test_add_and_clear_modifier(self):
        self.call("gas_actions", "ue_create_effect_blueprint", asset_path=_GE_PATH)
        r = self.call("gas_actions", "ue_add_effect_modifier",
                      asset_path=_GE_PATH, attribute_set_path=_TEST_ATTR_SET,
                      attribute_name="Health", op="add_base", magnitude=25.0)
        self.assertSuccess(r)
        self.assertEqual(r["modifier_count"], 1)
        info = self.call("gas_actions", "ue_get_effect_info", asset_path=_GE_PATH)
        self.assertEqual(len(info["modifiers"]), 1)
        mod = info["modifiers"][0]
        self.assertEqual(mod["attribute"], "Health")
        self.assertEqual(mod["op"], "add_base")
        self.assertAlmostEqual(mod["magnitude"], 25.0, places=2)
        r = self.call("gas_actions", "ue_clear_effect_modifiers", asset_path=_GE_PATH)
        self.assertSuccess(r)
        info = self.call("gas_actions", "ue_get_effect_info", asset_path=_GE_PATH)
        self.assertEqual(info["modifiers"], [])

    def test_add_modifier_bad_op(self):
        self.call("gas_actions", "ue_create_effect_blueprint", asset_path=_GE_PATH)
        r = self.call("gas_actions", "ue_add_effect_modifier",
                      asset_path=_GE_PATH, attribute_set_path=_TEST_ATTR_SET,
                      attribute_name="Health", op="nonsense")
        self.assertFalse(r.get("success"))

    def test_add_modifier_bad_attribute(self):
        self.call("gas_actions", "ue_create_effect_blueprint", asset_path=_GE_PATH)
        r = self.call("gas_actions", "ue_add_effect_modifier",
                      asset_path=_GE_PATH, attribute_set_path=_TEST_ATTR_SET,
                      attribute_name="NoSuchAttr_XYZ")
        self.assertFalse(r.get("success"))

    # ── tags (ini-based) ─────────────────────────────────────────────────────────

    def test_add_and_list_gameplay_tag(self):
        import os
        tag = "MCP.Test.TempTag"
        ini = os.path.join(unreal.Paths.project_config_dir(), "DefaultGameplayTags.ini")
        before = open(ini, encoding="utf-8").read() if os.path.isfile(ini) else None
        try:
            r = self.call("gas_actions", "ue_add_gameplay_tag", tag=tag, comment="mcp test")
            self.assertSuccess(r)
            r = self.call("gas_actions", "ue_list_gameplay_tags", prefix="MCP.Test")
            self.assertSuccess(r)
            self.assertIn(tag, r["tags"])
            r = self.call("gas_actions", "ue_add_gameplay_tag", tag=tag)
            self.assertFalse(r.get("success"))  # duplicate
        finally:
            if before is None:
                if os.path.isfile(ini):
                    os.remove(ini)
            else:
                with open(ini, "w", encoding="utf-8") as f:
                    f.write(before)

    def test_add_gameplay_tag_invalid(self):
        r = self.call("gas_actions", "ue_add_gameplay_tag", tag="bad tag !!")
        self.assertFalse(r.get("success"))
