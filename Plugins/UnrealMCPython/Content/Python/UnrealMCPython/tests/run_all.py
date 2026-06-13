"""
Run all MCP unittest suites inside the Unreal Python environment.

Usage — single line in the Unreal Python console (Output Log):

    import runpy; runpy.run_module("UnrealMCPython.tests.run_all", run_name="__main__")

Or via MCP execute_python tool (multi-line is fine there):

    import runpy
    runpy.run_module("UnrealMCPython.tests.run_all", run_name="__main__")
"""
import sys
import importlib
import unittest

_MODULES = [
    "UnrealMCPython.tests.test_util",
    "UnrealMCPython.tests.test_actor",
    "UnrealMCPython.tests.test_anim_blueprint",
    "UnrealMCPython.tests.test_animation",
    "UnrealMCPython.tests.test_asset",
    "UnrealMCPython.tests.test_level",
    "UnrealMCPython.tests.test_level_sequence",
    "UnrealMCPython.tests.test_material",
    "UnrealMCPython.tests.test_blueprint",
    "UnrealMCPython.tests.test_behavior_tree",
    "UnrealMCPython.tests.test_data_table",
    "UnrealMCPython.tests.test_umg",
    "UnrealMCPython.tests.test_editor",
    "UnrealMCPython.tests.test_game",
    "UnrealMCPython.tests.test_static_mesh",
    "UnrealMCPython.tests.test_layer",
    "UnrealMCPython.tests.test_texture",
    "UnrealMCPython.tests.test_retarget",
    "UnrealMCPython.tests.test_control_rig",
    "UnrealMCPython.tests.test_gas",
    "UnrealMCPython.tests.test_vision",
]

suite = unittest.TestSuite()
loader = unittest.TestLoader()

for mod_name in _MODULES:
    try:
        mod = importlib.import_module(mod_name)
        importlib.reload(mod)
        suite.addTests(loader.loadTestsFromModule(mod))
    except Exception as e:
        print(f"[LOAD ERROR] {mod_name}: {e}")

runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
result = runner.run(suite)

total = result.testsRun
fails = len(result.failures)
errors = len(result.errors)
skipped = len(result.skipped)
passed = total - fails - errors - skipped

print(f"\n{'='*60}")
print(f"Results: {passed} passed | {fails} failed | {errors} errors | {skipped} skipped / {total} total")
print('='*60)
