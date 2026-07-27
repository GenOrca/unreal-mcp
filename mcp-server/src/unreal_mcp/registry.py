"""Validated read/query interface over the generated Action Registry v2."""

from collections.abc import Iterator
from typing import Any

from unreal_mcp.contracts import ActionSpec
from unreal_mcp.dispatchers._catalog import CATALOG
from unreal_mcp.dispatchers._registry import ACTION_SPECS


class UnknownActionError(LookupError):
    def __init__(self, domain: str, action: str):
        self.domain = domain
        self.action = action
        super().__init__(f"Unknown action '{domain}.{action}'")


class ActionRegistry:
    """Immutable validated registry view used by discovery and workflows."""

    def __init__(self, raw: dict | None = None):
        source = ACTION_SPECS if raw is None else raw
        self._actions = {
            (domain, action): ActionSpec.model_validate(spec)
            for domain, actions in source.items()
            for action, spec in actions.items()
        }

    def get(self, domain: str, action: str) -> ActionSpec:
        try:
            return self._actions[(domain, action)]
        except KeyError as exc:
            raise UnknownActionError(domain, action) from exc

    def iter_actions(self) -> Iterator[ActionSpec]:
        for key in sorted(self._actions):
            yield self._actions[key]

    @property
    def legacy_catalog(self) -> dict[str, dict[str, dict[str, str]]]:
        return {
            domain: {action: dict(info) for action, info in actions.items()}
            for domain, actions in CATALOG.items()
        }

    @property
    def count(self) -> int:
        return len(self._actions)

    def export(self) -> dict[str, dict[str, dict[str, Any]]]:
        exported: dict[str, dict[str, dict[str, Any]]] = {}
        for spec in self.iter_actions():
            exported.setdefault(spec.domain, {})[spec.action] = spec.model_dump(mode="json")
        return exported
