import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from .const import (
    DOMAIN,
    ISSUES_URL,
    NAME,
    VERSION,
)
from .sensor import HydrolinkAPI

STARTUP = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom component
If you have any issues with this you need to open an issue here:
{ISSUES_URL}
-------------------------------------------------------------------
"""

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Hydrolink component."""

    if DOMAIN in hass.data:
        _LOGGER.debug(f"Hydrolink component has already been configured.")

    hass.data[DOMAIN] = HydrolinkAPI(hass, config)
    _LOGGER.debug(f"Added {DOMAIN} to hass.data.")
    return True
