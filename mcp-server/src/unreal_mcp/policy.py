"""Compatible and strict direct-dispatch safety decisions."""

from enum import StrEnum

from unreal_mcp.config import SafetyMode
from unreal_mcp.contracts import ActionSpec, Effect


class DispatchDecision(StrEnum):
    EXECUTE = "execute"
    PLAN_REQUIRED = "plan_required"


class SafetyPolicy:
    def __init__(self, mode: SafetyMode):
        self.mode = mode

    def decide(self, spec: ActionSpec) -> DispatchDecision:
        if self.mode is SafetyMode.STRICT and spec.effect is not Effect.READ:
            return DispatchDecision.PLAN_REQUIRED
        return DispatchDecision.EXECUTE
