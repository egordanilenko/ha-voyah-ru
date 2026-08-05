---
name: ha-tests
description: Написание и запуск тестов интеграции Voyah — юнит-тесты сущностей, координаторов, API-клиента и config flow на pytest-homeassistant-custom-component. Использовать при добавлении/изменении тестов в tests/ или когда новый код требует покрытия.
---

# Тесты интеграции Voyah

## Запуск

```bash
pytest                                                # всё
pytest tests/test_sensor.py -k charging               # выборочно
pytest --cov=custom_components.voyah --cov-report=term-missing
```

`pytest.ini`: `asyncio_mode = auto` — тесты пишутся как `async def test_...`,
без декораторов `@pytest.mark.asyncio`. Целевое покрытие — ≥ 95% (уровень
Silver в Quality Scale); текущее ниже цели, поэтому новый код не должен
снижать процент, а изменяемые модули — повод добрать недостающие тесты.

## Инфраструктура (`tests/conftest.py`)

Используй готовые фикстуры-фабрики, не создавай моки с нуля:

| Хелпер | Что даёт |
|---|---|
| `MOCK_CAR_DATA` | полный снимок данных координатора (все сенсоры, GPS, time, last_ping) |
| `MOCK_CAR_INFO_DATA` | данные car-info координатора (`liveSensors.soh` и т.п.) |
| `make_coordinator(hass, data)` | `VoyahDataUpdateCoordinator` с предустановленным `data` (клиент — `MagicMock`) |
| `make_car_info_coordinator(hass, data)` | то же для `VoyahCarInfoCoordinator` |
| `make_config_entry(hass)` | зарегистрированный `MockConfigEntry` с `MOCK_CONFIG_DATA` |

Фикстура `hass` приходит из `pytest_homeassistant_custom_component`.

## Паттерн: тест сущности

Сущности тестируются **напрямую**, без полного setup интеграции — быстро и изолированно:

```python
async def test_sensor_returns_value(hass: HomeAssistant) -> None:
    """Sensor reads value from coordinator data."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == "batteryPercentage")
    sensor = VoyahSensorEntity(coordinator, desc, entry)
    assert sensor.native_value == 80
```

Обязательная пара тестов для каждой новой сущности:
1. значение читается из `MOCK_CAR_DATA` (добавь ключ туда, если его нет);
2. отсутствие ключа в данных → `native_value is None` (модифицируй копию:
   `data = {**MOCK_CAR_DATA, "sensors_data": {...без ключа...}}`).

Для сущностей с внутренним состоянием (как сенсор окончания зарядки) дополнительно:
- инициализация из снимка, где процесс уже идёт;
- переходы состояний через `coordinator.async_set_updated_data(new_data)`
  (он вызовет `_handle_coordinator_update`);
- сброс при завершении процесса.

## Паттерн: время

Для логики, зависящей от текущего времени, используй `time_machine`
(уже в `requirements_test.txt`):

```python
with time_machine.travel(datetime(2024, 1, 1, tzinfo=timezone.utc)):
    ...
```

API-временные метки (`time` в данных) — обычные unix-секунды, их мокать не нужно.

## Паттерн: API-клиент

`test_api.py`: мокается `aiohttp`-сессия. Проверяй:
- успешный запрос и парсинг (`_parse`: `sensorsData`/`positionData`/`time`/`lastPing`);
- 401 → рефреш токена → повтор запроса; повторный 401 → `VoyahApiAuthError`;
- сетевые ошибки → `VoyahApiConnectionError`;
- неуспешный рефреш (не-200, отсутствие токенов в ответе) → `False`.

## Паттерн: config flow

`test_config_flow.py`: мокай статические методы `VoyahApiClient`
(`async_request_sms`, `async_sign_in`, `async_get_organizations`,
`async_search_cars`, `async_sign_in_org`) через `unittest.mock.patch`.
Покрывай каждый шаг и каждую ветку ошибок (`invalid_code`, `cannot_connect`,
`no_cars`, `already_configured`, reauth). Это требование Bronze-уровня —
config flow должен быть покрыт полностью.

Если тест делает полный setup интеграции (`hass.config_entries.async_setup`),
нужна фикстура `enable_custom_integrations`:

```python
async def test_full_setup(hass, enable_custom_integrations): ...
```

## Правила

- Докстринг на английском в каждом тесте — одно предложение о проверяемом поведении.
- Один тест — одно поведение; имя `test_<субъект>_<поведение>`.
- Не ассерти внутренности (`_pct_history` и т.п.) без необходимости — проверяй
  наблюдаемое поведение (`native_value`, созданные сущности).
- Секции в файле разделяются комментарием `# ── Название ──...` (см. `test_sensor.py`).
- В `tests/**` ruff отключает `T20` и `SLF001` — print и доступ к приватным
  членам допустимы, но не злоупотребляй.
