"""Support for Google Photos Albums."""
from __future__ import annotations

from .coordinator import ImmichCoordinator

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_WATCHED_ALBUMS,
    DOMAIN,
    FAVORITE_IMAGE_ALBUM,
    MANUFACTURER,
    SETTING_INTERVAL_DEFAULT_OPTION,
    SETTING_INTERVAL_OPTIONS,
    FAVORITE_IMAGE_ALBUM_NAME,
)

async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Immich selections."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    await coordinator.update_albums()

    watched_albums = config_entry.options.get(CONF_WATCHED_ALBUMS, [])

    if FAVORITE_IMAGE_ALBUM in watched_albums:
        async_add_entities([ImmichSelectInterval(coordinator, album_id=FAVORITE_IMAGE_ALBUM, album_name=FAVORITE_IMAGE_ALBUM_NAME)])
    
    # Create entities for random image from each watched album
    for album in coordinator.albums.values():
        if album["id"] in watched_albums:
            async_add_entities([ImmichSelectInterval(coordinator, album_id=album["id"], album_name=album["albumName"])])

class ImmichSelectInterval(SelectEntity, RestoreEntity):
    """Selection of image update interval"""

    _attr_has_entity_name = True
    _attr_icon = "mdi:timer-cog"

    def __init__(self, coordinator: ImmichCoordinator, album_id, album_name) -> None:
        """Initialize a sensor class."""
        super().__init__()
        self.album_id = album_id
        self.album_name = album_name
        self.coordinator = coordinator
        self._attr_device_info = coordinator.get_device_info(self.album_id, f"Immich: {self.album_name}")
        
        self.entity_description = SelectEntityDescription(
            key="update_interval",
            name="Update interval",
            icon=self._attr_icon,
            entity_category=EntityCategory.CONFIG,
            options=SETTING_INTERVAL_OPTIONS,
        )
        self._attr_unique_id = f"{self.album_id}-interval"

    @property
    def should_poll(self) -> bool:
        """No need to poll."""
        return False

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        return self.coordinator.get_interval(self.album_id)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option is not self.coordinator.get_interval(self.album_id):
            self.coordinator.set_interval(self.album_id, option)
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if not state or state.state not in SETTING_INTERVAL_OPTIONS:
            self.coordinator.set_interval(self.album_id, SETTING_INTERVAL_DEFAULT_OPTION)
        else:
            self.coordinator.set_interval(self.album_id, state.state)
        self.async_write_ha_state()
