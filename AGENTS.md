# AGENTS.md — руководство для агентов и разработчиков

Кастомная интеграция Home Assistant для автомобилей Voyah. Получает телеметрию
из облачного API [Voyah Assist](https://app.voyahassist.ru) (`cloud_polling`).
Распространяется через HACS. Язык общения в проекте — русский (коммиты, README, обсуждения).

## Команды

```bash
pytest                          # все тесты (asyncio_mode=auto, testpaths=tests)
pytest tests/test_sensor.py -k charging   # выборочно
pytest --cov=custom_components.voyah --cov-report=term-missing  # с покрытием
ruff check .                    # линт (ruff >= 0.15.1, line-length 120)
ruff format .                   # форматирование
```

Окружение — любой Python ≥ 3.13 venv: `pip install -r requirements_test.txt`
(`pytest-homeassistant-custom-component` тянет за собой Home Assistant) плюс `ruff` (>= 0.15.1).
Лежащий в репозитории `.envrc` — для пользователей direnv, опционально.

## Структура

```
custom_components/voyah/
├── __init__.py        # async_setup_entry: клиент → 2 координатора → платформы
├── api.py             # VoyahApiClient: HTTP-клиент, авторефреш токенов, иерархия исключений
├── coordinator.py     # VoyahDataUpdateCoordinator (телеметрия, интервал из конфига)
│                      # VoyahCarInfoCoordinator (медленные данные: SOH, раз в 12 ч)
├── config_flow.py     # SMS-авторизация: телефон → код → [организация] → машина; reauth
├── const.py           # DOMAIN, конфиг-ключи, SENSOR_DESCRIPTIONS, BINARY_SENSOR_DESCRIPTIONS
├── sensor.py          # обычные сенсоры + вычисляемые (время окончания зарядки, SOH, last ping)
├── binary_sensor.py   # бинарные сенсоры по BINARY_SENSOR_DESCRIPTIONS
├── device_tracker.py  # GPS-трекер (TrackerEntity, точность из HDOP)
├── button.py          # команды (обогрев, охлаждение, замок, багажник, поиск)
├── switch.py          # прогрев/охлаждение вкл/выкл (только новый API, состояние из command_states)
├── strings.json       # источник истины для всех строк UI
└── translations/      # en.json (копия strings.json), ru.json (перевод)
tests/                 # юнит-тесты, общие фикстуры в conftest.py
```

## Поток данных

1. `VoyahApiClient.async_get_car_data()` при первом вызове выясняет, какой API обслуживает машину,
   так же, как это делает веб-приложение: `imei`/`vin`/`carModel.modname` из `/car-service/car/v2/{car_id}`
   → флаг `newTelemetryEnabled` из `/config-service/config/flags`. Если флаг включён, клиент опрашивает
   `/client-bff-service/telemetry/{imei}` (метод `_parse_telemetry`: строки → числа, новые ключи →
   прежние имена вроде `remainsMileage`/`chargingStatus`, чтобы не менять unique_id). Если выключен —
   `/car-service/tbox/{car_id}/sensors` (метод `_parse`). Флаг перепроверяется раз в 12 ч в обе стороны;
   при ошибке проверки остаётся последний известный API (до первой успешной — прежний, как в вебе)
   с повтором через 5 мин, ошибка запроса телеметрии тоже ускоряет перепроверку.
   Оба парсера возвращают `{"sensors_data": ..., "position_data": ..., "time": ..., "last_ping": ...}`,
   новый — ещё `command_states` (состояния кнопок для toggle-команд и свитчей) и `checks`
   (`firmwareCheck`/`settingsCheck`). Сущности, которых нет у старого API (статус авто,
   свитчи, «Найти автомобиль», проверки версий), создаются только при наличии этих данных.
   Команды кнопок и свитчей: `coordinator.async_send_command(tbox_command, telemetry_command)` →
   клиент → `POST /client-bff-service/telemetry-commands` `{commandName, imei}` или прежний
   `POST /car-service/tbox/{car_id}/{command}`; координатор переводит ошибку в `HomeAssistantError`
   и обновляет данные через `COMMAND_REFRESH_DELAY_SECONDS`.
2. `VoyahDataUpdateCoordinator` хранит этот словарь; все сущности читают из `coordinator.data`.
   Если машина сменила API (`client.uses_telemetry_api`), координатор перезагружает entry,
   чтобы платформы заново создали сущности по новому снимку.
3. При 401 клиент сам обновляет токены через refresh-token (один рефреш на все одновременные 401,
   под `asyncio.Lock`); оба координатора персистят новые токены в config entry
   (`VoyahBaseCoordinator._persist_tokens_if_changed`).
4. `VoyahApiAuthError` → `ConfigEntryAuthFailed` (запускает reauth flow);
   `VoyahApiError` → `UpdateFailed` (сущности становятся unavailable, HA ретраит).

## Ключевые конвенции

- **Декларативные сущности**: описания (`SensorEntityDescription`) лежат кортежами в `const.py`.
  Ключ описания = ключ в `sensors_data` ответа API (camelCase, как в API).
- **Условное создание**: сенсоры, бинарные сенсоры и трекер добавляются только
  если их ключи присутствуют в первом снимке данных координатора
  (см. `async_setup_entry` платформ). Кнопки с командой старого API (`command`) создаются
  безусловно; кнопки и свитчи, которые есть только в новом API, — если их команда
  есть в `command_states`.
- У каждой сущности: `_attr_has_entity_name = True`, `_attr_translation_key`,
  `_attr_unique_id = f"{car_id}_{key}"`, общий `DeviceInfo(identifiers={(DOMAIN, car_id)})` —
  все сущности принадлежат одному устройству-машине.
- **Никаких захардкоженных имён** — только `translation_key` + строки в
  `strings.json` / `translations/{en,ru}.json` (все три файла обновляются синхронно).
- Весь I/O — асинхронный, через общую `aiohttp`-сессию HA (`async_get_clientsession`).
  Никаких блокирующих вызовов в event loop.
- Тип-аннотации обязательны (`from __future__ import annotations`).
- Координаторы и клиент доступны через `hass.data[DOMAIN][entry.entry_id]`
  (ключи `"coordinator"`, `"car_info_coordinator"`) — следуй этому паттерну.

## Чек-лист: добавление новой сущности

1. `const.py` — добавить `SensorEntityDescription`/`BinarySensorEntityDescription`
   с `key` (как в API), `translation_key`, `device_class`, `state_class`, единицами.
2. `strings.json` + `translations/en.json` + `translations/ru.json` — имя сущности.
3. Тест в `tests/` (значение читается, отсутствие ключа → `None`).
4. README.md — строка в таблицу, в **обе** языковые секции (русскую и английскую `#english`).
5. `pytest && ruff check . && ruff format --check .` — зелёные.

Подробные плейбуки: скиллы `/ha-code`, `/ha-tests`, `/ha-docs`
(`.agents/skills/`; для Claude Code доступны через симлинк `.claude/skills`).

## Ориентиры качества

Целимся в соответствие [Integration Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/).
Большинство правил Bronze выполнено (config flow, unique_id, has_entity_name,
тесты config flow), но не все: например, `runtime-data` — проект пока хранит
координаторы в `hass.data`, а не в `ConfigEntry.runtime_data`. Из Silver уже
есть reauth flow и выгрузка entry. Целевое покрытие тестами — ≥ 95% (правило
`test-coverage`); текущее ниже, поэтому новый код всегда приходит с тестами
и не опускает планку.
Перед изменениями API-слоя или config flow сверяйся с
[developers.home-assistant.io](https://developers.home-assistant.io/) — правила меняются между релизами HA.

## Релиз

- Поднять `version` в `custom_components/voyah/manifest.json`.
- Минимальная версия HA задана в `hacs.json` (`homeassistant: 2024.1.0`) — не использовать
  API ядра новее без её поднятия.
- HACS подтягивает версии из GitHub-релизов — после поднятия версии создать релиз.
