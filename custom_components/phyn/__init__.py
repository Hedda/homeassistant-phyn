"""The phyn integration."""
import asyncio
import logging

from aiophyn import async_get_api
from aiophyn.errors import RequestError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CLIENT, DOMAIN
from .device import PhynDeviceDataUpdateCoordinator
from .exceptions import HaAuthError, HaCannotConnect

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH, Platform.VALVE]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up flo from a config entry."""
    session = async_get_clientsession(hass)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    client_id = f"homeassistant-{hass.data['core.uuid']}"
    try:
        hass.data[DOMAIN][entry.entry_id][CLIENT] = client = await async_get_api(
            entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD],
            phyn_brand=entry.data["Brand"].lower(), session=session,
            client_id=client_id
        )
    except RequestError as err:
        raise ConfigEntryNotReady from err

    homes = await client.home.get_homes(entry.data[CONF_USERNAME])

    _LOGGER.debug("Phyn homes: %s", homes)

    #try:
    await client.mqtt.connect()
    #except:
    #    raise HaCannotConnect("Unknown MQTT connection failure")

    hass.data[DOMAIN][entry.entry_id]["devices"] = devices = [
        PhynDeviceDataUpdateCoordinator(hass, client, home["id"], device["device_id"], device["product_code"])
        for home in homes
        for device in home["devices"]
        if device["product_code"] in ["PP1","PP2"]
    ]

    tasks = [device.async_refresh() for device in devices]
    await asyncio.gather(*tasks)

    tasks = [device.async_setup() for device in devices]
    await asyncio.gather(*tasks)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    client = hass.data[DOMAIN][entry.entry_id][CLIENT]
    await client.mqtt.disconnect_and_wait()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
