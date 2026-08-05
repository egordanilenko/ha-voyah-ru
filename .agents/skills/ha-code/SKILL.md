---
name: ha-code
description: Написание и изменение кода интеграции Voyah для Home Assistant — добавление сенсоров, бинарных сенсоров, кнопок, платформ, работа с API-клиентом, координаторами и config flow. Использовать при любых изменениях в custom_components/voyah/.
---

# Написание кода интеграции Voyah

## Перед началом

Прочитай `AGENTS.md` (архитектура, команды) и файл, который собираешься менять.
Все изменения должны проходить `ruff check .`, `ruff format --check .` и `pytest`
(весь репозиторий отформатирован — держим это инвариантом).

## Рецепт 1: новый сенсор из существующих данных API

Самый частый случай: API уже возвращает значение в `sensorsData`, нужно завести сенсор.

1. Найди ключ в ответе API (camelCase, например `coolantTemp`). Где взять реальный ответ:
   - debug-логирование интеграции (`VoyahApiClient` логирует ключи ответа);
   - HAR-файлы `tmp/app.voyahassist.ru_*.har`. Каталог `tmp/` в `.gitignore`,
     поэтому файлов может не быть. В этом случае предложи разработчику снять HAR
     со своей реальной сессии: открыть <https://app.voyahassist.ru> в браузере,
     DevTools → вкладка Network → выполнить нужные действия в приложении →
     экспортировать HAR (кнопка «Export HAR» / «Save all as HAR»; инструкция:
     <https://developer.chrome.com/docs/devtools/network/reference#save-as-har>) —
     и положить файл в `tmp/`. **HAR содержит токены авторизации — коммитить его
     нельзя**, потому каталог и находится в `.gitignore`.
2. Добавь описание в `SENSOR_DESCRIPTIONS` в `const.py`:

```python
SensorEntityDescription(
    key="coolantTemp",  # точное имя ключа из API
    translation_key="coolant_temperature",  # snake_case
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    device_class=SensorDeviceClass.TEMPERATURE,  # если подходит стандартный
    state_class=SensorStateClass.MEASUREMENT,  # TOTAL_INCREASING для одометров
    # icon="mdi:..." — только если нет device_class с подходящей иконкой
)
```

3. Добавь имя в `strings.json` → `entity.sensor.<translation_key>.name`, продублируй
   в `translations/en.json`, переведи в `translations/ru.json`.
4. Тест + строка в обе таблицы README (см. скиллы `/ha-tests`, `/ha-docs`).

Больше ничего не нужно: `sensor.py` создаст сущность автоматически, если ключ
присутствует в данных (`if description.key in sensors_data`).

Бинарный сенсор — то же самое через `BINARY_SENSOR_DESCRIPTIONS` и `binary_sensor.py`
(значение приводится к bool, в API это 0/1).

## Рецепт 2: вычисляемый сенсор (своя логика)

Образцы: `VoyahChargingEndTimeSensor`, `VoyahLastPingSensor` в `sensor.py`.

- Наследуй `CoordinatorEntity[VoyahDataUpdateCoordinator], SensorEntity`.
- Обязательные атрибуты: `_attr_has_entity_name = True`, `_attr_translation_key`,
  `_attr_unique_id = f"{car_id}_<suffix>"`, `_attr_device_info` с
  `identifiers={(DOMAIN, car_id)}` — скопируй конструктор из существующего класса.
- Если нужна реакция на обновление данных (а не просто чтение в `native_value`) —
  переопредели `_handle_coordinator_update` с декоратором `@callback` и в конце
  вызови `super()._handle_coordinator_update()`.
- Состояние держи в памяти сущности (как `_pct_history` в сенсоре зарядки);
  HA может перезапуститься — инициализируй из первого снимка координатора.
- Зарегистрируй создание в `async_setup_entry` платформы, с проверкой наличия
  нужных ключей в данных.

## Рецепт 3: новая команда (кнопка)

Образец: `VoyahStartHeatingButton` в `button.py`.

1. Метод в `VoyahApiClient` (`api.py`) через `self._request(...)` — он сам
   обрабатывает 401 и рефреш токенов. Существующая команда обогрева использует
   `POST /car-service/tbox/{car_id}/heating`, но не предполагай, что остальные
   команды живут по тому же шаблону: точный метод и путь сверь с реальным
   запросом приложения (HAR-файл, см. Рецепт 1).
2. Класс кнопки в `button.py`: в `async_press` вызови метод клиента, затем
   `await self.coordinator.async_request_refresh()` — чтобы состояние обновилось.
3. Если команда может отказать — пробрось понятную ошибку: HA покажет её
   пользователю (`HomeAssistantError` с текстом).
4. Переводы (`strings.json`, en, ru) и README.

## Рецепт 4: новый эндпоинт API

- Все авторизованные вызовы — только через `VoyahApiClient._request`:
  он добавляет заголовки (`Bearer`, `x-app: web`), повторяет запрос после
  рефреша токена при 401 и оборачивает сетевые ошибки в `VoyahApiConnectionError`.
- Парсинг ответа держи в статических методах клиента (как `_parse`), чтобы
  сущности получали уже нормализованный словарь, а не сырой ответ API.
- Медленно меняющиеся данные (раз в часы) — в `VoyahCarInfoCoordinator`,
  телеметрия — в основной `VoyahDataUpdateCoordinator`. Не добавляй третий
  координатор без необходимости.

## Обработка ошибок — правила

| Где | Что бросать | Что произойдёт |
|---|---|---|
| `api.py` | `VoyahApiAuthError` / `VoyahApiConnectionError` / `VoyahApiError` | — |
| координатор | `ConfigEntryAuthFailed` (из auth) / `UpdateFailed` (остальное) | reauth flow / сущности unavailable |
| `config_flow.py` | ловить исключения API, возвращать `errors["base"] = "<ключ из strings.json>"` | сообщение в форме |
| кнопки/команды | `HomeAssistantError("текст")` | уведомление пользователю |

Никогда не глотай исключения молча; `except Exception` допустим только в
config flow с `_LOGGER.exception(...)` и `errors["base"] = "unknown"`.

## Стиль

- `from __future__ import annotations` в каждом модуле; полные тип-аннотации.
- Логирование: `_LOGGER.debug` с ленивой подстановкой (`%s`, не f-строки) — правило ruff `G`.
- Не запускай блокирующий код в event loop; файлы/CPU — через `hass.async_add_executor_job`.
- Константы интеграции — в `const.py`; локальные пороги алгоритмов (как
  `RATE_WINDOW_POINTS`) можно держать в модуле платформы.
- Свериться с актуальными правилами HA: <https://developers.home-assistant.io/docs/core/integration-quality-scale/>.
