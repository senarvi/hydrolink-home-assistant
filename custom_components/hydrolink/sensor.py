import json
import logging
from aiohttp import ClientSession
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from .const import CONF_TIME_PERIOD, DOMAIN, LOGIN_ENDPOINT, METER_DATA_ENDPOINT

_LOGGER = logging.getLogger(__name__)


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_TIME_PERIOD, default=7): cv.positive_int,
    }
)


async def async_setup_platform(hass: HomeAssistant, config: ConfigType, async_add_entities, discovery_info=None) -> True:
    """Set up the Hydrolink sensor platform."""

    if DOMAIN in hass.data:
        api = hass.data[DOMAIN]
    else:
        username = config[CONF_USERNAME]
        password = config[CONF_PASSWORD]
        api = HydrolinkAPI(hass, username, password)
        hass.data[DOMAIN] = api

    await api.async_refresh()

    if not api.meter_data:
        _LOGGER.error("Did not get any meters from the Hydrolink API. Unable to create sensor entities.")
    else:
        time_period = config[CONF_TIME_PERIOD]
        sensors = [WaterMeter(api, meter, time_period) for meter in api.meter_data["meters"]]
        for sensor in sensors:
            await sensor.async_update()
        async_add_entities(sensors)

    return True


class HydrolinkAPI:
    """Holds the data"""

    def __init__(self, hass: HomeAssistant, username: str, password: str) -> None:
        self._hass = hass
        self._username = username
        self._password = password
        self._token = None

        self.meter_data = defaultdict(dict)

        interval = timedelta(hours=23, minutes=59, seconds=59)
        async_track_time_interval(hass, self.async_refresh, interval)

    async def async_refresh(self):
        """Refresh the meter data from the API."""
        try:
            _LOGGER.info("Refreshing Hydrolink meter data.")
            session = async_get_clientsession(self._hass)
            if self._token is not None:
                try:
                    await self._async_fetch_meter_data(session)
                    return
                except Exception as e:
                    _LOGGER.info(f"Failed to refresh meter data: {e}")
                    _LOGGER.info("Trying to update the access token.")
            await self._async_login_to_api(session)
            await self._async_fetch_meter_data(session)
        except Exception as e:
            _LOGGER.error(f"Failed to refresh meter data: {e}")

    async def _async_login_to_api(self, session: ClientSession) -> None:
        """Login to the API and return the token."""
        _LOGGER.info(f"Logging in to the Hydrolink API with username {self._username}.")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Connection": "close"
        }
        payload = {
            "username": self._username,
            "password": self._password
        }

        async with session.post(LOGIN_ENDPOINT, headers=headers, json=payload) as response:
            if response.status == 200:
                response_text = await response.text()
                response_data = json.loads(response_text)
                if "token" in response_data:
                    self._token = response_data["token"]
                else:
                    raise RuntimeError("Login failed: Token not found in the response.")
            else:
                raise RuntimeError(f"Login failed: {response.status} - {await response.text()}")

    async def _async_fetch_meter_data(self, session: ClientSession) -> None:
        """Fetch meter data from the API."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        payload = {
            "token": self._token
        }

        async with session.post(METER_DATA_ENDPOINT, headers=headers, json=payload) as response:
            if response.status == 200:
                response_text = await response.text()
                self.meter_data = json.loads(response_text)
                _LOGGER.info(f"Updated Hydrolink meter data from {METER_DATA_ENDPOINT}.")
            else:
                raise RuntimeError(f"Failed to fetch meter data: {response.status} - {await response.text()}")


class WaterMeter(Entity):
    """A Hydrolink water meter.

    Args:
        api: An instance of the HydrolinkAPI class.
        meter: A dictionary containing meter data, including:
            - secondaryAddress: The unique identifier for the meter.
            - latestValue: The latest reading from the meter.
            - warm: A boolean indicating if the meter is for warm water.
            - dailyReadings: A list of daily readings, each containing:
                - created: A timestamp for the reading.
                - subtraction: The change after the previous reading.
        time_period: The number of days of historical data to keep.
    """

    def __init__(self, api: HydrolinkAPI, meter: dict[str, Any], time_period: int) -> None:
        """Initialize the sensor."""
        self._api = api
        self._address = meter["secondaryAddress"]
        self._state = meter["latestValue"]
        self._attributes = {"warm": meter["warm"]}
        self._time_period = time_period

    @property
    def name(self):
        """Return the name of the sensor."""
        warm_or_cold = "Warm" if self._attributes["warm"] else "Cold"
        return f"{warm_or_cold} Water Meter {self._address}"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def unique_id(self):
        return f"hydrolink_{self._address}"

    async def async_update(self):
        """Fetch new state data for the sensor."""
        try:
            def _date_from_timestamp(timestamp: int) -> str:
                return datetime.fromtimestamp(timestamp / 1000.0).strftime("%Y-%m-%d")

            for meter in self._api.meter_data["meters"]:
                if meter["secondaryAddress"] == self._address:
                    self._state = meter["latestValue"]
                    readings = meter["dailyReadings"][-self._time_period:]
                    self._attributes["readings"] = [
                        {
                            "date": _date_from_timestamp(reading["created"]),
                            "subtraction": reading["subtraction"]
                        }
                        for reading in readings
                    ]
                    _LOGGER.info(f"Updated Hydrolink sensor {self._address}.")
                    break
        except Exception as e:
            _LOGGER.error(f"Failed to update the Hydrolink sensor {self._address}: {e}")
