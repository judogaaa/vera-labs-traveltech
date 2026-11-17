"""GigaChat bridge: intent understanding + tool loop. Never a POI source of truth."""

from __future__ import annotations

from typing import Any

from services.ai.gigachat_client import GigaChatClient, get_gigachat_client
from services.ai.gigachat_types import ChatMessage, GigaChatError

from .intent_parser import KNOWN_CATEGORIES, normalize_intent, try_parse_json_intent
from .models import HotelContext, TripIntent

INTENT_SYSTEM = (
    "Ты извлекаешь travel intent из свободного запроса пользователя. "
    "Верни ТОЛЬКО валидный JSON-объект, без мест, координат и выдуманных фактов. "
    "Поля: destination (город/страна/место как в тексте, обязательно если есть), "
    "days (int 1..7), startTime/endTime (HH:MM), "
    "wishSequence (массив пожеланий СТРОГО в порядке упоминания: "
    '{label, kind: interest|must, category, query}), '
    "каждое отдельное желание — отдельный элемент, включая общие "
    "формулировки: «что-нибудь интересное»→attraction, «кофе»→cafe, "
    "«погулять»→park; "
    "interests[] (краткие категории), avoid[], "
    "travelers {adults:int, children:[ages]}, "
    "transportPreference (walk|car|transit|mixed), budget (число или null), "
    "pace (relaxed|normal|intensive), mustVisit[] (именованные места), "
    "returnBy (HH:MM или null), editAction (remove_stop|add_stop|replace_stop|"
    "return_by|change_transport|rebuild_day|null), editTarget. "
    f"category только из: {sorted(KNOWN_CATEGORIES)} или null. "
    "Категории по смыслу: ресторан/еда/кухня/морепродукты→restaurant; "
    "бар/выпить/пиво/вино/коктейль/ночная жизнь→bar; кофе→cafe; "
    "музей→museum; парк/прогулка→park; море/пляж→beach; "
    "вид/смотровая/панорама→viewpoint; "
    "достопримечательности/старый город/атмосфера→attraction. "
    "Явный старт («с 10:00», «начало в 10:00»)→startTime и НЕ сдвигай из‑за слова «вечер». "
    "«Вечером бар/ужин» — это пожелание стопа, НЕ startTime 18:00. "
    "Только если весь день вечерний («вечерний маршрут», «на вечер»)→startTime 18:00. "
    "«Утром»→startTime 09:00. «Днём»→startTime 11:00, endTime 18:00. "
    "С ребёнком→travelers.children и pace relaxed. "
    "Без долгих пеших переходов→transportPreference car. "
    "Если город неоднозначный — destination как в тексте, не выдумывай страну."
)


class TripGigaChatBridge:
    """Intent + tool-loop bridge. Never a POI source of truth."""

    def __init__(self, client: GigaChatClient | None = None) -> None:
        self._client = client if client is not None else get_gigachat_client()

    @property
    def available(self) -> bool:
        return bool(self._client and self._client.available)

    @property
    def client(self) -> GigaChatClient | None:
        return self._client

    def extract_intent(
        self,
        message: str,
        hotel: HotelContext | None,
        existing: TripIntent | None,
    ) -> TripIntent | None:
        if not self.available or not self._client:
            return None
        ctx: dict[str, Any] = {
            "hotel": hotel.model_dump() if hotel else None,
            "existingIntent": existing.model_dump() if existing else None,
            "userMessage": message,
        }
        try:
            data = self._client.structured_json(str(ctx), system=INTENT_SYSTEM, repair_attempts=1)
            return normalize_intent(data)
        except (GigaChatError, Exception):  # noqa: BLE001
            try:
                result = self._client.complete_text(str(ctx), system=INTENT_SYSTEM)
                parsed = try_parse_json_intent(result.content or "")
                if parsed is None:
                    return None
                return normalize_intent(parsed.model_dump())
            except Exception:  # noqa: BLE001
                return None


# Back-compat name used by older agent imports
GigaChatClientCompat = TripGigaChatBridge
