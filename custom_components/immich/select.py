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
    CONF_WATCHED,
    CONF_WATCHED_ALBUMS,
    CONF_WATCHED_PERSONS,
    CONF_WATCHED_TYPE_ALBUM,
    CONF_WATCHED_TYPE_PERSON,
    DOMAIN,
    FAVORITE_IMAGE_ALBUM,
    MANUFACTURER,
    RANDOM_IMAGE_ALBUM,
    RANDOM_IMAGE_ALBUM_NAME,
    SETTING_INTERVAL_DEFAULT_OPTION,
    SETTING_INTERVAL_OPTIONS,
    FAVORITE_IMAGE_ALBUM_NAME,
    SETTING_ORIENTATION_DEFAULT,
    SETTING_ORIENTATION_OPTIONS,
    SETTING_THUMBNAILS_MODE_DEFAULT,
    SETTING_THUMBNAILS_MODE_OPTIONS,
)

async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Immich selections."""
    coordinator : ImmichCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    await coordinator.update_albums()
    await coordinator.update_persons()

    watched_entries = config_entry.options.get(CONF_WATCHED, [])
    for entry in watched_entries:
        select_interval = ImmichSelectInterval(coordinator, entry)
        select_thumbnails = ImmichSelectThumbnailsMode(coordinator, entry)
        select_orientation = ImmichSelectOrientation(coordinator, entry)
        
        async_add_entities([select_interval])
        async_add_entities([select_thumbnails])
        async_add_entities([select_orientation])
        await coordinator.update_device(entry, select = [select_interval, select_thumbnails, select_orientation])

class ImmichSelectInterval(SelectEntity, RestoreEntity):
    """Selection of image update interval"""

    _attr_has_entity_name = True
    _attr_icon = "mdi:timer-cog"

    def __init__(self, coordinator: ImmichCoordinator, entry) -> None:
        """Initialize a sensor class."""
        super().__init__()
        self.entry = entry
        self.coordinator = coordinator
        self._attr_device_info = coordinator.get_device_info(entry)
        
        self.entity_description = SelectEntityDescription(
            key="update_interval",
            name="Update interval",
            icon=self._attr_icon,
            entity_category=EntityCategory.CONFIG,
            options=SETTING_INTERVAL_OPTIONS,
        )
        self._attr_unique_id = f"{coordinator.get_device_id(entry)}-interval"

    @property
    def should_poll(self) -> bool:
        """No need to poll."""
        return False

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        return self.coordinator.get_interval(self.entry)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option is not self.coordinator.get_interval(self.entry):
            await self.coordinator.set_interval(self.entry, option)
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if not state or state.state not in SETTING_INTERVAL_OPTIONS:
            await self.coordinator.set_interval(self.entry, SETTING_INTERVAL_DEFAULT_OPTION)
        else:
            await self.coordinator.set_interval(self.entry, state.state)
        self.async_write_ha_state()

class ImmichSelectThumbnailsMode(SelectEntity, RestoreEntity):
    """Selection of thumbnails mode"""

    _attr_has_entity_name = True
    _attr_icon = "mdi:file-image"

    def __init__(self, coordinator: ImmichCoordinator, entry) -> None:
        """Initialize a sensor class."""
        super().__init__()
        self.entry = entry
        self.coordinator = coordinator
        self._attr_device_info = coordinator.get_device_info(entry)
        
        self.entity_description = SelectEntityDescription(
            key="thumbnail_mode",
            name="Thumbnail mode",
            icon=self._attr_icon,
            entity_category=EntityCategory.CONFIG,
            options=SETTING_THUMBNAILS_MODE_OPTIONS,
        )
        self._attr_unique_id = f"{coordinator.get_device_id(entry)}-thumbnailmode"

    @property
    def should_poll(self) -> bool:
        """No need to poll."""
        return False

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        return self.coordinator.get_thumbnail_mode(self.entry)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option is not self.coordinator.get_thumbnail_mode(self.entry):
            await self.coordinator.set_thumbnail_mode(self.entry, option)
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if not state or state.state not in SETTING_THUMBNAILS_MODE_OPTIONS:
            await self.coordinator.set_thumbnail_mode(self.entry, SETTING_THUMBNAILS_MODE_DEFAULT)
        else:
            await self.coordinator.set_thumbnail_mode(self.entry, state.state)
        self.async_write_ha_state()

class ImmichSelectOrientation(SelectEntity, RestoreEntity):
    """Selection of orientation"""

    _attr_has_entity_name = True
    _attr_icon = "mdi:directions"

    def __init__(self, coordinator: ImmichCoordinator, entry) -> None:
        """Initialize a sensor class."""
        super().__init__()
        self.entry = entry
        self.coordinator = coordinator
        self._attr_device_info = coordinator.get_device_info(entry)
        
        self.entity_description = SelectEntityDescription(
            key="orientation",
            name="Orientation",
            icon=self._attr_icon,
            entity_category=EntityCategory.CONFIG,
            options=SETTING_ORIENTATION_OPTIONS,
        )
        self._attr_unique_id = f"{coordinator.get_device_id(entry)}-orientation"

    @property
    def should_poll(self) -> bool:
        """No need to poll."""
        return False

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        return self.coordinator.get_orientation(self.entry)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option is not self.coordinator.get_orientation(self.entry):
            await self.coordinator.set_orientation(self.entry, option)
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if not state or state.state not in SETTING_ORIENTATION_OPTIONS:
            await self.coordinator.set_orientation(self.entry, SETTING_ORIENTATION_DEFAULT)
        else:
            await self.coordinator.set_orientation(self.entry, state.state)
        self.async_write_ha_state()