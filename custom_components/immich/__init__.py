"""The immich integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import CONF_WATCHED, DOMAIN
from .hub import ImmichHub, InvalidAuth
from .coordinator import ImmichCoordinator

PLATFORMS: list[Platform] = [Platform.IMAGE, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up immich from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    hub = ImmichHub(host=entry.data[CONF_HOST], api_key=entry.data[CONF_API_KEY])
    coordinator = ImmichCoordinator(hass, hub)

    if not await hub.authenticate():
        raise InvalidAuth

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Remove a config entry from a device."""
    identifier = next((id for id in device_entry.identifiers if id[0] == DOMAIN), None)
    if identifier is None:
        return False
    
    id = identifier[1]
    type = identifier[2]
    created = identifier[3]

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    await coordinator.remove_device(id, created)
    
    options = config_entry.options.copy()
    entries = options.get(CONF_WATCHED, []).copy()
    for entry in list(entries):
        if entry.get('id') == id and entry.get('type') == type and entry.get('created') == created:
            entries.remove(entry)
    options.update({CONF_WATCHED: entries})
    hass.config_entries.async_update_entry(config_entry, options=options)    
    return True