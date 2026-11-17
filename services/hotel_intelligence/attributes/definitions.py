"""Register AttributeDefinition entries for the Ostrovok demo set."""
from __future__ import annotations

from ..calculators.car_access import compute_car_access
from ..calculators.family_infrastructure import compute_family_infrastructure
from ..calculators.late_night_pharmacy_walk import compute_late_night_pharmacy_walk
from ..calculators.night_services import compute_night_services
from ..calculators.noise_proxy import compute_noise_risk
from ..calculators.walk_access import compute_walk_to_metro
from ..registry import AttributeDefinition, AttributeRegistry

DEFINITIONS: list[AttributeDefinition] = [
    AttributeDefinition(
        key="walk_to_metro",
        description="Foot route distance and duration to the nearest metro/subway stop",
        value_type="object",
        needed_tools=["walk_to_metro_calc"],
        hotelier_question=None,
        ttl_days=14,
        intent_patterns=[
            r"(?i)(?:пешк\w*\s+(?:до|от|к)\s+)?метро",
            r"(?i)метрополитен|subway|metro\b",
            r"(?i)(?:до|от|к)\s+метро",
            r"(?i)минут\w*\s+(?:пешк\w*\s+)?(?:до\s+)?метро",
        ],
        default_role="must",
        matcher="walk_max_min",
        calculator_tool="walk_to_metro_calc",
        is_geo=True,
        constraint_defaults={},
    ),
    AttributeDefinition(
        key="external_noise_risk",
        description="Heuristic outdoor noise risk from nearby roads, rail and nightlife (not dB)",
        value_type="object",
        needed_tools=["noise_risk_calc"],
        hotelier_question=None,
        ttl_days=14,
        intent_patterns=[
            r"(?i)тишин|тих(?:ий|ая|ое|ие|о)|шум|спокойн|quiet",
            r"(?i)ночн\w*\s+клуб|night\s*club|nightclub",
            r"(?i)(?:не\s+возле|без|away\s+from).{0,20}клуб",
        ],
        default_role="must",
        matcher="risk_max",
        calculator_tool="noise_risk_calc",
        is_geo=True,
        constraint_defaults={"prefer_risk": ["low", "medium"]},
    ),
    AttributeDefinition(
        key="night_services",
        description="Nearby POIs with opening_hours suggesting late-night or 24/7 service",
        value_type="object",
        needed_tools=["night_services_calc"],
        hotelier_question=None,
        ttl_days=7,
        # Do NOT match "ночных клубов" — that is noise intent, not 24h services.
        intent_patterns=[
            r"(?i)круглосуточ",
            r"(?i)24/?7",
            r"(?i)работ\w*\s+ночью",
            r"(?i)ночн\w*\s+(?:аптек|магазин|сервис|служб)",
            r"(?i)(?:аптек|магазин).{0,20}ночь",
        ],
        default_role="should",
        matcher="night_confirmed",
        calculator_tool="night_services_calc",
        is_geo=True,
    ),
    AttributeDefinition(
        key="family_infrastructure",
        description="Nearby playgrounds and parks from OpenStreetMap",
        value_type="object",
        needed_tools=["family_infra_calc"],
        hotelier_question=None,
        ttl_days=14,
        # Avoid matching «парковка» via bare «парк»
        intent_patterns=[
            # «семейный номер» is a room_type, not nearby playgrounds — exclude bare «семейн* номер»
            r"(?i)(?:с\s+детьми|для\s+семьи|ребен|ребён|детск|playground)",
            r"(?i)\bпарк(?:а|е|и|ов)?\b(?!\w)",
            r"(?i)\bpark\b",
            r"(?i)семей\w*\s+(?:отдых|путешеств|инфраструктур)",
        ],
        default_role="should",
        matcher="presence",
        calculator_tool="family_infra_calc",
        is_geo=True,
    ),
    AttributeDefinition(
        key="car_access",
        description="Parking and pedestrian-zone hints near the hotel from OSM",
        value_type="object",
        needed_tools=["car_access_calc"],
        hotelier_question=None,
        ttl_days=14,
        intent_patterns=[
            r"(?i)парковк",
            r"(?i)без\s+машин",
            r"(?i)машин(?:ы|а)?\s+под\s+окн",
            r"(?i)на\s+машин",
            r"(?i)автомоб",
            r"(?i)пешеходн(?:ая|ой)\s+зон",
        ],
        default_role="should",
        matcher="car_access",
        calculator_tool="car_access_calc",
        is_geo=True,
    ),
    AttributeDefinition(
        key="blackout_curtains",
        description="Whether rooms have blackout curtains; requires hotelier confirmation",
        value_type="boolean",
        needed_tools=["hotelier_qa"],
        hotelier_question=(
            "Есть ли в номерах (укажите тип/номер) плотные шторы blackout? "
            "Если да — в каких категориях?"
        ),
        ttl_days=90,
        intent_patterns=[r"(?i)штор|блэкаут|блекаут|blackout|затемнен|затемнён"],
        default_role="must",
        matcher="boolean_true",
        calculator_tool=None,
        is_geo=False,
        constraint_defaults={"equals": True},
    ),
    AttributeDefinition(
        key="late_night_pharmacy_walk",
        description="Foot walk minutes to a pharmacy confirmed open late or 24h by opening_hours",
        value_type="object",
        needed_tools=["late_night_pharmacy_walk_calc"],
        hotelier_question=None,
        ttl_days=7,
        intent_patterns=[
            r"(?i)аптек.*(?:ноч|круглосуточ|24)",
            r"(?i)(?:ноч|круглосуточ|24).*аптек",
            r"(?i)pharmacy.*(?:night|24)",
            r"(?i)late.?night.?pharmacy",
        ],
        default_role="should",
        matcher="pharmacy_walk",
        calculator_tool="late_night_pharmacy_walk_calc",
        is_geo=True,
    ),
    AttributeDefinition(
        key="courtyard_rooms",
        description="Rooms facing an inner courtyard (quieter); hotelier-confirmed",
        value_type="boolean",
        needed_tools=["hotelier_qa"],
        hotelier_question=(
            "Есть ли номера во внутренний двор (courtyard)? "
            "В каких категориях?"
        ),
        ttl_days=90,
        intent_patterns=[
            r"(?i)(?:во\s+)?(?:внутренн\w*\s+)?двор",
            r"(?i)courtyard",
            r"(?i)окна?\s+во\s+двор",
        ],
        default_role="must",
        matcher="boolean_true",
        calculator_tool=None,
        is_geo=False,
        constraint_defaults={"equals": True},
    ),
]


def register_default_attributes(registry: AttributeRegistry) -> AttributeRegistry:
    for definition in DEFINITIONS:
        if definition.key not in registry.keys():
            registry.add(definition)
    return registry


def build_default_registry(
    *,
    register_tools: bool = True,
) -> AttributeRegistry:
    """Create a registry with definitions and (optionally) real tool callables."""
    reg = AttributeRegistry()
    register_default_attributes(reg)
    if register_tools:
        _register_tools(reg)
    return reg


def _register_tools(reg: AttributeRegistry) -> None:
    def hotelier_qa(**kwargs):  # noqa: ANN003
        return {"status": "needs_hotelier", **kwargs}

    tools = [
        ("walk_to_metro_calc", compute_walk_to_metro),
        ("noise_risk_calc", compute_noise_risk),
        ("night_services_calc", compute_night_services),
        ("family_infra_calc", compute_family_infrastructure),
        ("car_access_calc", compute_car_access),
        ("late_night_pharmacy_walk_calc", compute_late_night_pharmacy_walk),
        ("hotelier_qa", hotelier_qa),
        # Compatibility aliases for older needed_tools / overrides in tests
        ("osm_nearest_metro", compute_walk_to_metro),
        ("osrm_foot_route", compute_walk_to_metro),
        ("osm_roads_nearby", compute_noise_risk),
        ("osm_night_pois", compute_night_services),
        ("osm_family_pois", compute_family_infrastructure),
        ("osm_car_access", compute_car_access),
    ]
    for name, handler in tools:
        try:
            reg.register_tool(name, handler)
        except ValueError:
            pass
