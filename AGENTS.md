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
├── button.py          # команды (запуск обогрева)
├── strings.json       # источник истины для всех строк UI
└── translations/      # en.json (копия strings.json), ru.json (перевод)
tests/                 # юнит-тесты, общие фикстуры в conftest.py
```

## Поток данных

1. `VoyahApiClient.async_get_car_data()` опрашивает `/car-service/tbox/{car_id}/sensors`
   и нормализует ответ в `{"sensors_data": ..., "position_data": ..., "time": ..., "last_ping": ...}` (метод `_parse`).
2. `VoyahDataUpdateCoordinator` хранит этот словарь; все сущности читают из `coordinator.data`.
3. При 401 клиент сам обновляет токены через refresh-token; координатор
   персистит новые токены в config entry (`_persist_tokens_if_changed`).
4. `VoyahApiAuthError` → `ConfigEntryAuthFailed` (запускает reauth flow);
   `VoyahApiError` → `UpdateFailed` (сущности становятся unavailable, HA ретраит).

## Ключевые конвенции

- **Декларативные сущности**: описания (`SensorEntityDescription`) лежат кортежами в `const.py`.
  Ключ описания = ключ в `sensors_data` ответа API (camelCase, как в API).
- **Условное создание**: сенсоры, бинарные сенсоры и трекер добавляются только
  если их ключи присутствуют в первом снимке данных координатора
  (см. `async_setup_entry` платформ). Кнопки-команды создаются безусловно.
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
- Минимальная версия HA задана в `hacs.json` (`homeassistant: 2024.11.0`) — не использовать
  API ядра новее без её поднятия. Планка 2024.11 продиктована хелперами reauth
  (`_get_reauth_entry`, `_abort_if_unique_id_mismatch`, `async_update_reload_and_abort(data_updates=...)`)
  и типом `ConfigFlowResult`.
- HACS подтягивает версии из GitHub-релизов — после поднятия версии создать релиз.
