/** 
 * Explicitly non-AI, client-only preview. It detects user interests by
 * keywords but DOES NOT search hotels, collect evidence or verify claims.
 * The real feature will replace this with a backend evidence-backed pipeline.
 */
export type AttributeKey =
  | 'quiet'
  | 'sunset'
  | 'walkability'
  | 'night-services'
  | 'blackout'
  | 'family'
  | 'pets'
  | 'sea-view'

export type AttributePreview = {
  key: AttributeKey
  label: string
  description: string
  plannedSource: string
  limitation: string
}

type Definition = AttributePreview & {
  pattern: RegExp
}

const definitions: readonly Definition[] = [
  {
    key: 'quiet',
    label: 'Тишина и шум',
    description: 'Оценить внешнюю шумовую нагрузку вокруг здания и со стороны улиц.',
    plannedSource: 'OSM: типы дорог, бары, клубы и железные дороги',
    limitation: 'Риск шума — не измеренные децибелы и не гарантия тишины в номере.',
    pattern: /тишин|тих(?:ий|ая|ое|ие|о)|шум|спокойн/i,
  },
  {
    key: 'sunset',
    label: 'Вид на закат',
    description: 'Проверить геометрию видимости на запад и расположение солнца.',
    plannedSource: 'DEM, высота зданий, геометрия фасадов, положение солнца',
    limitation: 'Нужны этаж и ориентация конкретного окна; без них вид неизвестен.',
    pattern: /закат|заход солнц|вечерн(?:ее|ий|яя) солнц/i,
  },
  {
    key: 'walkability',
    label: 'Пешеходная доступность',
    description: 'Посчитать путь по реальным пешеходным маршрутам до нужных мест.',
    plannedSource: 'OSM/Nominatim и пешеходный OSRM',
    limitation: 'Пока маршрут не рассчитан, обещать конкретное число минут нельзя.',
    pattern: /пешк|пешком|метро|достопримечательност|центр|пляж|прогул|ходьб/i,
  },
  {
    key: 'night-services',
    label: 'Что работает ночью',
    description: 'Найти рядом открытые ночью магазины, аптеки и заведения.',
    plannedSource: 'OSM opening_hours и проверка актуальности',
    limitation: 'Если режим работы не указан, круглосуточность не подтверждена.',
    pattern: /ночью|круглосуточ|24\/7|поздн|ночн(?:ая|ой|ые|ых) (?:аптек|магазин|кафе)/i,
  },
  {
    key: 'blackout',
    label: 'Плотные шторы',
    description: 'Уточнить наличие штор блэкаут в конкретных типах номеров.',
    plannedSource: 'Ответ отельера с указанием типа/номера комнаты',
    limitation: 'Без подтверждения отельера характеристика остаётся неизвестной.',
    pattern: /штор|блэкаут|blackout|затемнен|затемнён/i,
  },
  {
    key: 'family',
    label: 'Семья и дети',
    description: 'Проверить безопасные зоны для прогулок и детскую инфраструктуру.',
    plannedSource: 'OSM playground, пешие маршруты, подтверждение отельера',
    limitation: 'Близость площадки сама по себе не означает безопасность.',
    pattern: /ребен|ребён|детск|детьми|семь[еёийю]|семейн/i,
  },
  {
    key: 'pets',
    label: 'Размещение с питомцами',
    description: 'Спросить про разрешённые виды животных, вес и доплату.',
    plannedSource: 'Ответ отельера; OSM для мест выгула',
    limitation: 'Правила размещения зависят от типа номера и даты.',
    pattern: /питомц|собак|кошк|животн/i,
  },
  {
    key: 'sea-view',
    label: 'Вид на море',
    description: 'Исследовать прямую видимость воды с учётом зданий и рельефа.',
    plannedSource: 'OSM water polygons, DEM, здания, фасады, этаж',
    limitation: 'Без геометрии окон и проверенных высот нельзя обещать вид.',
    pattern: /вид на мор|море из окн|видом на вод|вид на океан/i,
  },
]

export function previewRequestedAttributes(query: string): AttributePreview[] {
  const value = query.trim()
  if (!value) return []
  return definitions
    .filter((definition) => definition.pattern.test(value))
    .map(({ key, label, description, plannedSource, limitation }) => ({
      key,
      label,
      description,
      plannedSource,
      limitation,
    }))
}
