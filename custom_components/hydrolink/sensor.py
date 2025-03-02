import logging
import requests
import json
from datetime import datetime
from homeassistant.helpers.entity import Entity
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD

log = logging.getLogger(__name__)

DOMAIN = "hydrolink"
API_BASE_URL = "https://hydrolink.fi/api/v2"
LOGIN_ENDPOINT = f"{API_BASE_URL}/login"
METER_DATA_ENDPOINT = f"{API_BASE_URL}/getResidentMeterData"

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Hydrolink sensor platform."""
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    time_period = config.get("time_period", 7)

    if not username or not password:
        log.error("Username and password must be provided")
        return

    try:
        token = login_to_api(username, password)
        meter_data = fetch_meter_data(token)
        entities = [WaterMeter(meter, time_period) for meter in meter_data["meters"]]
        add_entities(entities, True)
    except Exception as e:
        log.error(f"Failed to setup Hydrolink sensors: {e}")

def login_to_api(username, password):
    """Login to the API and return the token."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Connection": "close"
    }
    payload = {
        "username": username,
        "password": password
    }

    response = requests.post(LOGIN_ENDPOINT, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        response_data = response.json()
        if "token" in response_data:
            return response_data["token"]
        else:
            raise RuntimeError("Login failed: Token not found in the response.")
    else:
        raise RuntimeError(f"Login failed: {response.status_code} - {response.text}")

def fetch_meter_data(token):
    """Fetch meter data from the API."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "token": token
    }

    response = requests.post(METER_DATA_ENDPOINT, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        return response.json()
    else:
        raise RuntimeError(f"Failed to fetch meter data: {response.status_code} - {response.text}")

class WaterMeter(Entity):
    """Representation of a Hydrolink sensor."""

    def __init__(self, meter, time_period):
        """Initialize the sensor."""
        warm_or_cold = "Warm" if meter["warm"] else "Cold"
        self._address = meter['secondaryAddress']
        self._name = f"{warm_or_cold} {self._address}"
        self._time_period = time_period
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    def update(self):
        """Fetch new state data for the sensor."""
        try:
            token = login_to_api(self.hass.data[DOMAIN][CONF_USERNAME], self.hass.data[DOMAIN][CONF_PASSWORD])
            meter_data = fetch_meter_data(token)

            for meter in meter_data["meters"]:
                if meter["secondaryAddress"] == self._address:
                    self._state = meter["latestValue"]
                    daily_readings = meter["dailyReadings"]
                    self._attributes = {
                        "readings": [
                            {
                                "date": datetime.fromtimestamp(reading["created"] / 1000.0).strftime("%Y-%m-%d"),
                                "subtraction": reading["subtraction"]
                            }
                            for reading in daily_readings[-self._time_period:]
                        ]
                    }
                    break
        except Exception as e:
            log.error(f"Failed to update Hydrolink sensor {self._name}: {e}")
