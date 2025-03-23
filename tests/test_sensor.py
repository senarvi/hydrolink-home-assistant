import json
import pytest
from copy import deepcopy
from unittest.mock import AsyncMock, patch, MagicMock

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD

from custom_components.hydrolink.const import (
    DOMAIN,
    LOGIN_ENDPOINT,
    METER_DATA_ENDPOINT,
)
from custom_components.hydrolink.sensor import (
    HydrolinkAPI,
    WaterMeter,
    async_setup_platform,
)


MOCK_METER_DATA = {
    "meters": [
        {
            "secondaryAddress": "01234567",
            "latestValue": 100,
            "warm": True,
            "dailyReadings": [
                {"created": 1633072800000, "subtraction": 10},
                {"created": 1633159200000, "subtraction": 15},
            ],
        }
    ]
}


class MockRequestContextManager:
    def __init__(self, url, **kwargs):
        self.response = AsyncMock()
        self.response.status = 200
        if url == LOGIN_ENDPOINT:
            response_data = {"token": "test_token"}
        elif url == METER_DATA_ENDPOINT:
            response_data = MOCK_METER_DATA
        else:
            assert False, f"session.post() called with an unknown URL '{url}'."
        self.response.text.return_value = json.dumps(response_data)

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc, tb):
        pass


@pytest.fixture
def session():
    result = MagicMock()
    result.post = MockRequestContextManager
    return result


class MockEntityAdder:
    def __init__(self):
        self.call_count = 0
        self.sensors = []

    def __call__(self, sensors, update_before_add=False):
        self.call_count += 1
        if update_before_add:
            for sensor in sensors:
                sensor.async_schedule_update_ha_state(True)
        self.sensors = sensors

    def assert_called_once(self):
        assert self.call_count == 1


def assert_water_meter_state(water_meter):
    assert water_meter.unique_id == "hydrolink_01234567"
    assert water_meter.name == "Warm Water Meter 01234567"
    assert water_meter.icon == "mdi:water-plus"
    assert water_meter.state_class == SensorStateClass.TOTAL_INCREASING
    assert water_meter.device_class == SensorDeviceClass.WATER
    assert water_meter.unit_of_measurement == "L"
    assert water_meter.state == 100
    assert water_meter.extra_state_attributes["warm"] is True
    assert water_meter.extra_state_attributes["daily_consumption"] == [
        {
            "timestamp": 1633072800000,
            "date": "2021-10-01",
            "value": 10,
        },
        {
            "timestamp": 1633159200000,
            "date": "2021-10-02",
            "value": 15,
        },
    ]


@pytest.mark.asyncio
async def test_async_setup_platform(hass, session):
    config = {CONF_USERNAME: "test_user", CONF_PASSWORD: "test_pass"}
    async_add_entities = MockEntityAdder()
    with patch(
        "custom_components.hydrolink.sensor.async_get_clientsession",
        return_value=session,
    ):
        result = await async_setup_platform(hass, config, async_add_entities)

    assert result is True
    assert DOMAIN in hass.data
    api = hass.data[DOMAIN]
    assert api._token == "test_token"
    assert api.meter_data == MOCK_METER_DATA
    async_add_entities.assert_called_once()
    sensors = async_add_entities.sensors
    assert len(sensors) == 1
    assert_water_meter_state(sensors[0])
    api.stop()


@pytest.mark.asyncio
async def test_hydrolink_api_login(hass, session):
    api = HydrolinkAPI(hass, "test_user", "test_pass")
    with patch(
        "custom_components.hydrolink.sensor.async_get_clientsession",
        return_value=session,
    ):
        await api._async_login_to_api()

    assert api._token == "test_token"
    api.stop()


@pytest.mark.asyncio
async def test_hydrolink_api_fetch_meter_data(hass, session):
    api = HydrolinkAPI(hass, "test_user", "test_pass")
    api._token = "test_token"
    with patch(
        "custom_components.hydrolink.sensor.async_get_clientsession",
        return_value=session,
    ):
        await api._async_fetch_meter_data()

    assert api.meter_data == MOCK_METER_DATA
    api.stop()


def test_water_meter_properties(hass):
    api = HydrolinkAPI(hass, "test_user", "test_pass")
    water_meter = WaterMeter(api, MOCK_METER_DATA["meters"][0])

    assert_water_meter_state(water_meter)
    api.stop()


@pytest.mark.asyncio
async def test_water_meter_update(hass):
    api = HydrolinkAPI(hass, "test_user", "test_pass")
    api.meter_data = MOCK_METER_DATA
    # Initialize the meter with incorrect data.
    meter_data = deepcopy(MOCK_METER_DATA["meters"][0])
    meter_data["latestValue"] = 200
    meter_data["dailyReadings"][0] = {"created": 1633245600000, "subtraction": 20}
    water_meter = WaterMeter(api, meter_data)
    await water_meter.async_update()

    assert_water_meter_state(water_meter)
    api.stop()
