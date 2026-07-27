from uuid import uuid4

import unreal

from UnrealMCPython.tests.base import MCPTestCase


class TestWorkflowActions(MCPTestCase):

    def test_editor_context_contains_stable_fields(self):
        result = self.call(
            "workflow_actions",
            "ue_get_editor_context",
            asset_paths=[],
        )
        self.assertSuccess(result)
        self.assertIn("project_id", result)
        self.assertIn("editor_session_id", result)
        self.assertIn("engine_version", result)
        self.assertIn("current_map", result)
        self.assertEqual(result["asset_fingerprints"], {})

    def test_editor_context_fingerprints_an_existing_asset(self):
        asset_path = "/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial"
        result = self.call(
            "workflow_actions",
            "ue_get_editor_context",
            asset_paths=[asset_path],
        )
        self.assertSuccess(result)
        fingerprint = result["asset_fingerprints"][asset_path]
        self.assertTrue(fingerprint["exists"])
        self.assertEqual(fingerprint["asset_path"], asset_path)
        self.assertTrue(fingerprint["package_guid"])
        self.assertGreater(fingerprint["disk_size"], 0)
        self.assertTrue(fingerprint["modified_time"])
        self.assertFalse(fingerprint["dirty"])

    def test_editor_context_fingerprints_an_unsaved_asset(self):
        name = f"M_WorkflowFingerprint_{uuid4().hex}"
        package_path = "/Game/Tests/MCP"
        asset_path = f"{package_path}/{name}.{name}"
        asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name,
            package_path,
            unreal.Material,
            unreal.MaterialFactoryNew(),
        )
        self.assertIsNotNone(asset)
        try:
            result = self.call(
                "workflow_actions",
                "ue_get_editor_context",
                asset_paths=[asset_path],
            )
            self.assertSuccess(result)
            fingerprint = result["asset_fingerprints"][asset_path]
            self.assertTrue(fingerprint["exists"])
            self.assertTrue(fingerprint["dirty"])
        finally:
            unreal.EditorAssetLibrary.delete_asset(asset_path)

    def test_begin_rejects_a_preexisting_editor_transaction(self):
        tx_id = f"mcp_test_nested_{uuid4().hex}"
        with unreal.ScopedEditorTransaction("Outer editor transaction"):
            begun = self.call(
                "workflow_actions",
                "ue_begin_transaction",
                transaction_id=tx_id,
                description="Nested MCP transaction",
            )
            if begun["success"]:
                self.call(
                    "workflow_actions",
                    "ue_commit_transaction",
                    transaction_id=tx_id,
                )
            self.assertFalse(begun["success"])

    def test_transaction_can_begin_commit_and_undo(self):
        tx_id = f"mcp_test_commit_{uuid4().hex}"
        spawned = self.call(
            "actor_actions",
            "ue_spawn_from_class",
            class_path="/Script/Engine.Actor",
            location=[0.0, 0.0, 0.0],
        )
        self.assertSuccess(spawned)
        label = spawned["actor_label"]
        try:
            begun = self.call(
                "workflow_actions",
                "ue_begin_transaction",
                transaction_id=tx_id,
                description="MCP test transaction",
            )
            self.assertSuccess(begun)
            self.assertGreaterEqual(begun["transaction_index"], 0)
            self.assertSuccess(
                self.call(
                    "actor_actions",
                    "ue_set_location",
                    actor_label=label,
                    location=[100.0, 0.0, 0.0],
                )
            )
            committed = self.call(
                "workflow_actions",
                "ue_commit_transaction",
                transaction_id=tx_id,
            )
            self.assertSuccess(committed)
            self.assertTrue(committed["transaction_recorded"])
            self.assertTrue(committed["undo_available"])
            self.assertEqual(
                committed["transaction_index"], begun["transaction_index"]
            )
            undone = self.call(
                "workflow_actions",
                "ue_undo_transaction",
                transaction_id=tx_id,
            )
            self.assertSuccess(undone)
            self.assertTrue(undone["transaction_recorded"])
            self.assertFalse(undone["undo_available"])
            self.assertEqual(
                undone["transaction_index"], begun["transaction_index"]
            )
            restored = self.call(
                "actor_actions", "ue_get_transform", actor_label=label
            )
            self.assertEqual(restored["location"], [0.0, 0.0, 0.0])
        finally:
            self.call(
                "workflow_actions",
                "ue_cancel_transaction",
                transaction_id=tx_id,
            )
            self.call("actor_actions", "ue_delete_by_label", actor_label=label)

    def test_active_transaction_can_roll_back_state(self):
        tx_id = f"mcp_test_rollback_{uuid4().hex}"
        spawned = self.call(
            "actor_actions",
            "ue_spawn_from_class",
            class_path="/Script/Engine.Actor",
            location=[0.0, 0.0, 0.0],
        )
        self.assertSuccess(spawned)
        label = spawned["actor_label"]
        try:
            begun = self.call(
                "workflow_actions",
                "ue_begin_transaction",
                transaction_id=tx_id,
                description="MCP rollback test",
            )
            self.assertSuccess(begun)
            self.assertSuccess(
                self.call(
                    "actor_actions",
                    "ue_set_location",
                    actor_label=label,
                    location=[200.0, 0.0, 0.0],
                )
            )
            rolled_back = self.call(
                "workflow_actions",
                "ue_rollback_transaction",
                transaction_id=tx_id,
            )
            self.assertSuccess(rolled_back)
            self.assertTrue(rolled_back["transaction_recorded"])
            self.assertFalse(rolled_back["undo_available"])
            self.assertEqual(
                rolled_back["transaction_index"], begun["transaction_index"]
            )
            restored = self.call(
                "actor_actions", "ue_get_transform", actor_label=label
            )
            self.assertEqual(restored["location"], [0.0, 0.0, 0.0])
        finally:
            self.call(
                "workflow_actions",
                "ue_cancel_transaction",
                transaction_id=tx_id,
            )
            self.call("actor_actions", "ue_delete_by_label", actor_label=label)

    def test_empty_transaction_does_not_undo_previous_editor_action(self):
        tx_id = f"mcp_test_empty_{uuid4().hex}"
        spawned = self.call(
            "actor_actions",
            "ue_spawn_from_class",
            class_path="/Script/Engine.Actor",
            location=[0.0, 0.0, 0.0],
        )
        self.assertSuccess(spawned)
        label = spawned["actor_label"]
        try:
            self.assertSuccess(
                self.call(
                    "workflow_actions",
                    "ue_begin_transaction",
                    transaction_id=tx_id,
                    description="MCP empty transaction test",
                )
            )
            self.assertSuccess(
                self.call(
                    "workflow_actions",
                    "ue_commit_transaction",
                    transaction_id=tx_id,
                )
            )
            undo = self.call(
                "workflow_actions",
                "ue_undo_transaction",
                transaction_id=tx_id,
            )
            self.assertFalse(undo["success"])
            self.assertSuccess(
                self.call(
                    "actor_actions", "ue_get_transform", actor_label=label
                )
            )
        finally:
            self.call(
                "workflow_actions",
                "ue_cancel_transaction",
                transaction_id=tx_id,
            )
            self.call("actor_actions", "ue_delete_by_label", actor_label=label)

    def test_empty_rollback_does_not_undo_previous_editor_action(self):
        tx_id = f"mcp_test_empty_rollback_{uuid4().hex}"
        spawned = self.call(
            "actor_actions",
            "ue_spawn_from_class",
            class_path="/Script/Engine.Actor",
            location=[0.0, 0.0, 0.0],
        )
        self.assertSuccess(spawned)
        label = spawned["actor_label"]
        try:
            self.assertSuccess(
                self.call(
                    "workflow_actions",
                    "ue_begin_transaction",
                    transaction_id=tx_id,
                    description="MCP empty rollback test",
                )
            )
            rollback = self.call(
                "workflow_actions",
                "ue_rollback_transaction",
                transaction_id=tx_id,
            )
            self.assertFalse(rollback["success"])
            self.assertSuccess(
                self.call(
                    "actor_actions", "ue_get_transform", actor_label=label
                )
            )
        finally:
            self.call(
                "workflow_actions",
                "ue_cancel_transaction",
                transaction_id=tx_id,
            )
            self.call("actor_actions", "ue_delete_by_label", actor_label=label)

    def test_previous_workflow_undo_survives_empty_commit_and_rollback(self):
        committed_tx_id = f"mcp_test_preserved_{uuid4().hex}"
        empty_tx_id = f"mcp_test_empty_{uuid4().hex}"
        rollback_tx_id = f"mcp_test_rollback_{uuid4().hex}"
        spawned = self.call(
            "actor_actions",
            "ue_spawn_from_class",
            class_path="/Script/Engine.Actor",
            location=[0.0, 0.0, 0.0],
        )
        self.assertSuccess(spawned)
        label = spawned["actor_label"]
        try:
            self.assertSuccess(
                self.call(
                    "workflow_actions",
                    "ue_begin_transaction",
                    transaction_id=committed_tx_id,
                    description="MCP transaction to preserve",
                )
            )
            self.assertSuccess(
                self.call(
                    "actor_actions",
                    "ue_set_location",
                    actor_label=label,
                    location=[100.0, 0.0, 0.0],
                )
            )
            self.assertSuccess(
                self.call(
                    "workflow_actions",
                    "ue_commit_transaction",
                    transaction_id=committed_tx_id,
                )
            )

            self.assertSuccess(
                self.call(
                    "workflow_actions",
                    "ue_begin_transaction",
                    transaction_id=empty_tx_id,
                    description="MCP empty transaction",
                )
            )
            empty_commit = self.call(
                "workflow_actions",
                "ue_commit_transaction",
                transaction_id=empty_tx_id,
            )
            self.assertSuccess(empty_commit)
            self.assertFalse(empty_commit["transaction_recorded"])
            self.assertFalse(empty_commit["undo_available"])

            self.assertSuccess(
                self.call(
                    "workflow_actions",
                    "ue_begin_transaction",
                    transaction_id=rollback_tx_id,
                    description="MCP rollback transaction",
                )
            )
            self.assertSuccess(
                self.call(
                    "actor_actions",
                    "ue_set_location",
                    actor_label=label,
                    location=[200.0, 0.0, 0.0],
                )
            )
            self.assertSuccess(
                self.call(
                    "workflow_actions",
                    "ue_rollback_transaction",
                    transaction_id=rollback_tx_id,
                )
            )
            restored_after_rollback = self.call(
                "actor_actions", "ue_get_transform", actor_label=label
            )
            self.assertEqual(
                restored_after_rollback["location"], [100.0, 0.0, 0.0]
            )

            self.assertSuccess(
                self.call(
                    "workflow_actions",
                    "ue_undo_transaction",
                    transaction_id=committed_tx_id,
                )
            )
            restored_after_undo = self.call(
                "actor_actions", "ue_get_transform", actor_label=label
            )
            self.assertEqual(
                restored_after_undo["location"], [0.0, 0.0, 0.0]
            )
        finally:
            for tx_id in (rollback_tx_id, empty_tx_id, committed_tx_id):
                self.call(
                    "workflow_actions",
                    "ue_cancel_transaction",
                    transaction_id=tx_id,
                )
            self.call("actor_actions", "ue_delete_by_label", actor_label=label)

    def test_transform_validation_prevents_partial_mutation(self):
        spawned = self.call(
            "actor_actions",
            "ue_spawn_from_class",
            class_path="/Script/Engine.Actor",
            location=[0.0, 0.0, 0.0],
        )
        self.assertSuccess(spawned)
        label = spawned["actor_label"]
        try:
            result = self.call(
                "actor_actions",
                "ue_set_transform",
                actor_label=label,
                location=[300.0, 0.0, 0.0],
                rotation=[0.0, 0.0],
            )
            self.assertFalse(result["success"])
            unchanged = self.call(
                "actor_actions", "ue_get_transform", actor_label=label
            )
            self.assertEqual(unchanged["location"], [0.0, 0.0, 0.0])
        finally:
            self.call("actor_actions", "ue_delete_by_label", actor_label=label)
