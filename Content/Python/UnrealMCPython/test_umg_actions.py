# UMG Actions Test Script
# Paste each section into the Unreal Python console (Output Log) to verify functionality.
# Run sections in order: 1 → 2 → 3 → 4 → 5

import importlib, json, unreal

def run(module_func, **kwargs):
    """Reload module and call a ue_* function, printing the result."""
    mod = importlib.import_module("UnrealMCPython.umg_actions")
    importlib.reload(mod)
    fn = getattr(mod, module_func)
    result = fn(**kwargs)
    parsed = json.loads(result)
    print(json.dumps(parsed, indent=2))
    return parsed

TEST_PATH = "/Game/Tests"
TEST_NAME = "TestWidget_MCP"
FULL_PATH = f"{TEST_PATH}/{TEST_NAME}.{TEST_NAME}"

# ─── 1. Create Widget Blueprint ───────────────────────────────────────────────
print("=== 1. create_widget_blueprint ===")
r = run("ue_create_widget_blueprint", name=TEST_NAME, path=TEST_PATH)
assert r["success"], f"FAIL: {r}"
print("PASS")

# ─── 2. Get Info (empty) ──────────────────────────────────────────────────────
print("\n=== 2. get_widget_blueprint_info (empty) ===")
r = run("ue_get_widget_blueprint_info", asset_path=FULL_PATH)
assert r["success"], f"FAIL: {r}"
print(f"  root: {r['root_widget']}, widgets: {r['widget_count']}")
print("PASS")

# ─── 3. Add CanvasPanel as root ───────────────────────────────────────────────
print("\n=== 3. add_widget: CanvasPanel (root) ===")
r = run("ue_add_widget", asset_path=FULL_PATH, widget_type="CanvasPanel", widget_name="RootCanvas")
assert r["success"], f"FAIL: {r}"
assert r["is_root"], "Expected is_root=True"
print("PASS")

# ─── 4. Add TextBlock under CanvasPanel ───────────────────────────────────────
print("\n=== 4. add_widget: TextBlock under RootCanvas ===")
r = run("ue_add_widget", asset_path=FULL_PATH, widget_type="TextBlock",
        widget_name="TitleText", parent_name="RootCanvas")
assert r["success"], f"FAIL: {r}"
print("PASS")

# ─── 5. Add Button under CanvasPanel ─────────────────────────────────────────
print("\n=== 5. add_widget: Button under RootCanvas ===")
r = run("ue_add_widget", asset_path=FULL_PATH, widget_type="Button",
        widget_name="StartButton", parent_name="RootCanvas")
assert r["success"], f"FAIL: {r}"
print("PASS")

# ─── 6. Set TextBlock properties ─────────────────────────────────────────────
print("\n=== 6. set_widget_properties: TitleText ===")
r = run("ue_set_widget_properties", asset_path=FULL_PATH, widget_name="TitleText",
        properties={
            "text": "Hello UMG!",
            "font_size": 32,
            "color_and_opacity": [1.0, 1.0, 0.0, 1.0],
            "slot_position": [100.0, 50.0],
            "slot_size": [400.0, 60.0],
        })
assert r["success"], f"FAIL errors: {r.get('errors')}"
print(f"  set: {r['set']}")
print("PASS")

# ─── 7. Set Button slot position ─────────────────────────────────────────────
print("\n=== 7. set_widget_properties: StartButton slot ===")
r = run("ue_set_widget_properties", asset_path=FULL_PATH, widget_name="StartButton",
        properties={
            "slot_position": [150.0, 150.0],
            "slot_size": [200.0, 60.0],
        })
assert r["success"], f"FAIL errors: {r.get('errors')}"
print("PASS")

# ─── 8. Get Info (populated) ─────────────────────────────────────────────────
print("\n=== 8. get_widget_blueprint_info (populated) ===")
r = run("ue_get_widget_blueprint_info", asset_path=FULL_PATH)
assert r["success"], f"FAIL: {r}"
assert r["widget_count"] == 3, f"Expected 3 widgets, got {r['widget_count']}"
for w in r["widgets"]:
    print(f"  {w['type']}: {w['name']} (parent: {w.get('parent', 'ROOT')})")
print("PASS")

# ─── 9. Remove TextBlock ─────────────────────────────────────────────────────
print("\n=== 9. remove_widget: TitleText ===")
r = run("ue_remove_widget", asset_path=FULL_PATH, widget_name="TitleText")
assert r["success"], f"FAIL: {r}"
print("PASS")

# ─── 10. Compile ─────────────────────────────────────────────────────────────
print("\n=== 10. compile_widget_blueprint ===")
r = run("ue_compile_widget_blueprint", asset_path=FULL_PATH)
assert r["success"], f"FAIL: {r}"
print("PASS")

print("\n=== ALL TESTS PASSED ===")
