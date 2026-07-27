"""Environment-backed MCP server settings."""

from dataclasses import dataclass
from enum import StrEnum
from os import environ
from typing import Mapping


class SafetyMode(StrEnum):
    COMPATIBLE = "compatible"
    STRICT = "strict"


@dataclass(frozen=True)
class Settings:
    safety_mode: SafetyMode
    debug: bool


def load_settings(values: Mapping[str, str] | None = None) -> Settings:
    source = environ if values is None else values
    raw_mode = source.get("UNREAL_MCP_SAFETY_MODE", "compatible").lower()
    try:
        mode = SafetyMode(raw_mode)
    except ValueError as exc:
        raise ValueError(
            "UNREAL_MCP_SAFETY_MODE must be 'compatible' or 'strict'"
        ) from exc
    return Settings(mode, source.get("UNREAL_MCP_DEBUG", "0") == "1")
