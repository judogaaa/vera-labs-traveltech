"""Declarative characteristic definitions and explicit registered executors.

A textual definition alone NEVER computes a fact. A real callable must be
registered for every needed tool, otherwise the orchestrator must ask a
hotelier or return unknown. Orchestration/API are future work.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

ToolHandler = Callable[..., Any]


class AttributeDefinition(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    description: str = Field(min_length=8)
    value_type: str = Field(min_length=2)
    needed_tools: list[str] = Field(default_factory=list)
    hotelier_question: str | None = None
    ttl_days: int = Field(ge=1, le=3650)
    # Extensibility metadata (defaults keep older tests/contracts valid)
    intent_patterns: list[str] = Field(default_factory=list)
    default_role: Literal["must", "should"] = "should"
    matcher: str = "presence"
    calculator_tool: str | None = None
    is_geo: bool = False
    constraint_defaults: dict[str, Any] = Field(default_factory=dict)


class AttributeRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, AttributeDefinition] = {}
        self._tools: dict[str, ToolHandler] = {}

    def register_tool(self, tool_name: str, handler: ToolHandler) -> None:
        if not tool_name:
            raise ValueError("tool_name cannot be empty")
        if not callable(handler):
            raise TypeError("Registered tools must be executable callables")
        if tool_name in self._tools:
            raise ValueError(f"Duplicate tool: {tool_name}")
        self._tools[tool_name] = handler

    def get_tool(self, tool_name: str) -> ToolHandler:
        return self._tools[tool_name]

    def add(self, definition: AttributeDefinition) -> None:
        if definition.key in self._definitions:
            raise ValueError(f"Duplicate characteristic: {definition.key}")
        self._definitions[definition.key] = definition

    def get(self, key: str) -> AttributeDefinition:
        return self._definitions[key]

    def missing_tools(self, key: str) -> list[str]:
        definition = self.get(key)
        needed = set(definition.needed_tools)
        if definition.calculator_tool:
            needed.add(definition.calculator_tool)
        return sorted(needed - self._tools.keys())

    def can_attempt_computation(self, key: str) -> bool:
        definition = self.get(key)
        needed = set(definition.needed_tools)
        if definition.calculator_tool:
            needed.add(definition.calculator_tool)
        if not needed:
            return False
        return not bool(needed - self._tools.keys())

    def keys(self) -> list[str]:
        return sorted(self._definitions)
