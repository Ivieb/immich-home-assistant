"""The immich integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import CONF_WATCHED_ALBUMS, DOMAIN
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
    album_id = identifier[len(identifier) - 1]
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    await coordinator.remove_album(album_id)
    
    options = config_entry.options.copy()
    albums = options.get(CONF_WATCHED_ALBUMS, []).copy()
    if album_id in albums:
        albums.remove(album_id)
        options.update({CONF_WATCHED_ALBUMS: albums})
        hass.config_entries.async_update_entry(config_entry, options=options)
    return True