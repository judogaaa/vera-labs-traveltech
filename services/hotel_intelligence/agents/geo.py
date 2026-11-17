"""GeoAgent: execute geo tools via registry for a hotel location."""
from __future__ import annotations

from typing import Any

from ..models import AttributeObservation
from ..registry import AttributeRegistry
from .research import AgentTrace


class GeoAgent:
    name = "geo"

    def __init__(self, registry: AttributeRegistry) -> None:
        self.registry = registry

    def compute(
        self,
        hotel_id: str,
        lat: float,
        lon: float,
        attribute_keys: list[str],
        *,
        tool_overrides: dict[str, Any] | None = None,
    ) -> tuple[list[AttributeObservation], AgentTrace]:
        trace = AgentTrace(agent=self.name)
        observations: list[AttributeObservation] = []
        overrides = tool_overrides or {}

        for key in attribute_keys:
            try:
                definition = self.registry.get(key)
            except KeyError:
                trace.add("skip_unknown_attr", attribute_key=key)
                continue
            if not definition.is_geo:
                trace.add("skip_non_geo", attribute_key=key)
                continue
            if not self.registry.can_attempt_computation(key):
                trace.add(
                    "missing_tools",
                    attribute_key=key,
                    missing=self.registry.missing_tools(key),
                )
                continue
            # One calculator invoke per attribute — never both osm_nearest_metro + osrm_foot_route
            tool_name = definition.calculator_tool or (
                definition.needed_tools[0] if definition.needed_tools else None
            )
            if not tool_name:
                trace.add("no_calculator_tool", attribute_key=key)
                continue
            handler = overrides.get(tool_name) or self.registry.get_tool(tool_name)
            trace.add("invoke_tool", tool=tool_name, attribute_key=key)
            try:
                result = handler(hotel_id=hotel_id, lat=lat, lon=lon)
            except TypeError:
                result = handler(hotel_id, lat, lon)
            except Exception as exc:  # noqa: BLE001
                trace.add("tool_error", tool=tool_name, error=str(exc))
                continue
            if isinstance(result, AttributeObservation):
                observations.append(result)
                trace.add(
                    "observation",
                    observation_id=result.observation_id,
                    status=result.status.value,
                    attribute_key=key,
                )
            else:
                trace.add(
                    "non_observation_result",
                    tool=tool_name,
                    result_type=type(result).__name__,
                )
        return observations, trace
