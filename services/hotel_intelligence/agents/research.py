"""ResearchAgent: plan which registry tools to call for requested attributes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..registry import AttributeRegistry


@dataclass
class AgentTrace:
    agent: str
    steps: list[dict[str, Any]] = field(default_factory=list)

    def add(self, action: str, **detail: Any) -> None:
        self.steps.append({"action": action, **detail})


class ResearchAgent:
    name = "research"

    def __init__(self, registry: AttributeRegistry) -> None:
        self.registry = registry

    def plan(self, attribute_keys: list[str]) -> tuple[list[dict[str, Any]], AgentTrace]:
        """Return ordered tool-call plan. Never invents attribute values."""
        trace = AgentTrace(agent=self.name)
        plan: list[dict[str, Any]] = []
        for key in attribute_keys:
            try:
                definition = self.registry.get(key)
            except KeyError:
                trace.add("unknown_attribute", attribute_key=key)
                continue
            missing = self.registry.missing_tools(key)
            can = self.registry.can_attempt_computation(key)
            step = {
                "attribute_key": key,
                "needed_tools": list(definition.needed_tools),
                "missing_tools": missing,
                "can_compute": can,
                "hotelier_question": definition.hotelier_question,
            }
            plan.append(step)
            trace.add("planned", **step)
        return plan, trace
