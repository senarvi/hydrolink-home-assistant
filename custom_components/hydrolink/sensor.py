"""Hydrolink sensor platform."""

import json
import logging
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

from .const import DOMAIN, LOGIN_ENDPOINT, METER_DATA_ENDPOINT

_LOGGER = logging.getLogger(__name__)


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)


async def async_setup_platform(
    hass: HomeAssistant, config: ConfigType, async_add_entities, discovery_info=None
) -> bool:
    """Initializes the Hydrolink sensor platform.

    Args:
        hass: The Home Assistant instance.
        config: The configuration for the platform.
        async_add_entities: The function to add entities to the platform.
        discovery_info: Unused.
    """

    if DOMAIN in hass.data:
        api = hass.data[DOMAIN]
    else:
        username = config[CONF_USERNAME]
        password = config[CONF_PASSWORD]
        api = HydrolinkAPI(hass, username, password)
        hass.data[DOMAIN] = api

    await api.async_login_and_refresh()

    if not api.meter_data:
        _LOGGER.error("Did not get any meters from the Hydrolink API")
        _LOGGER.error("Unable to create sensor entities")
        return False

    sensors = [WaterMeter(api, meter) for meter in api.meter_data["meters"]]
    async_add_entities(sensors)
    _LOGGER.info(f"Added {len(sensors)} Hydrolink water meters")
    return True


class HydrolinkAPI:
    """Holds the Hydrolink meter data.

    Args:
        hass: The Home Assistant instance.
        username: The username for the Hydrolink API.
        password: The password for the Hydrolink API.
    """

    def __init__(self, hass: HomeAssistant, username: str, password: str) -> None:
        self._hass = hass
        self._username = username
        self._password = password
        self._token = None

        self.meter_data = defaultdict(dict)

        # Set up a callback for refreshing the meter data at regular intervals.
        # Calling self.stop() will stop Home Assistant from calling the function.
        interval = timedelta(hours=5, minutes=59, seconds=59)
        self.stop = async_track_time_interval(
            hass, self.async_refresh_callback, interval
        )

    async def async_refresh_callback(self, now: datetime) -> None:
        """Refresh the meter data from the API."""
        try:
            _LOGGER.debug("Entered the Hydrolink API refresh callback")
            await self._async_fetch_meter_data()
            return
        except Exception as e:
            _LOGGER.info(f"Failed to refresh meter data: {e}")
            _LOGGER.info("This is expected when the token expires")
            _LOGGER.info("Updating the access token and trying again")
        await self.async_login_and_refresh()

    async def async_login_and_refresh(self) -> None:
        """Obtain a token by logging in to the API and refresh the meter data."""
        try:
            await self._async_login_to_api()
            await self._async_fetch_meter_data()
        except Exception as e:
            _LOGGER.error(f"Failed to login and refresh the meter data: {e}")

    async def _async_login_to_api(self) -> None:
        """Login to the API and return the token."""
        _LOGGER.debug(f"Logging in to the Hydrolink API with username {self._username}")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Connection": "close",
        }
        payload = {"username": self._username, "password": self._password}

        session = async_get_clientsession(self._hass)
        async with session.post(
            LOGIN_ENDPOINT, headers=headers, json=payload
        ) as response:
            if response.status == 200:
                response_text = await response.text()
                response_data = json.loads(response_text)
                if "token" in response_data:
                    self._token = response_data["token"]
                else:
                    raise RuntimeError("Login failed: Token not found in the response.")
            else:
                raise RuntimeError(
                    f"Login failed: {response.status} - {await response.text()}"
                )

    async def _async_fetch_meter_data(self) -> None:
        """Fetch meter data from the API."""
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        payload = {"token": self._token}

        session = async_get_clientsession(self._hass)
        async with session.post(
            METER_DATA_ENDPOINT, headers=headers, json=payload
        ) as response:
            if response.status == 200:
                response_text = await response.text()
                self.meter_data = json.loads(response_text)
                _LOGGER.info(f"Updated Hydrolink meter data from {METER_DATA_ENDPOINT}")
            else:
                raise RuntimeError(
                    f"Failed to fetch meter data: {response.status} - {await response.text()}"
                )


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
    """

    def __init__(self, api: HydrolinkAPI, meter: dict[str, Any]) -> None:
        """Initialize the sensor."""
        self._api = api
        self._address = meter["secondaryAddress"]
        self._attributes = {"warm": meter["warm"]}
        self._read_state(meter)

    @property
    def unique_id(self) -> str:
        return f"hydrolink_{self._address}"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        warm_or_cold = "Warm" if self._attributes["warm"] else "Cold"
        return f"{warm_or_cold} Water Meter {self._address}"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        return "mdi:water-plus" if self._attributes["warm"] else "mdi:water-minus"

    @property
    def state(self) -> int:
        """Return the latest value of the meter."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return self._attributes

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
        try:
            for meter in self._api.meter_data["meters"]:
                if meter["secondaryAddress"] == self._address:
                    self._read_state(meter)
                    break
        except Exception as e:
            _LOGGER.error(f"Failed to update the Hydrolink sensor {self._address}: {e}")

    def _read_state(self, meter: dict[str, Any]) -> None:
        """Read the state from meter data from the API.

        Args:
            meter: A dictionary containing meter data, including:
                - latestValue: The latest reading from the meter.
                - dailyReadings: A list of daily readings, each containing:
                    - created: A timestamp for the reading.
                    - subtraction: The change after the previous reading.
        """

        def _date_from_timestamp(timestamp: int) -> str:
            return datetime.fromtimestamp(timestamp / 1000.0).strftime("%Y-%m-%d")

        self._state = meter["latestValue"]
        # Save the past 7 days in the "readings" attribute.
        readings = meter["dailyReadings"][-7:]
        self._attributes["daily_consumption"] = [
            {
                "timestamp": reading["created"],
                "date": _date_from_timestamp(reading["created"]),
                "value": reading["subtraction"],
            }
            for reading in readings
        ]
