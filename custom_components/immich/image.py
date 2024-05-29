"""Image device for Immich integration."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
import random

from .coordinator import ImmichCoordinator
from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import CONF_WATCHED_ALBUMS, DOMAIN, FAVORITE_IMAGE_ALBUM, FAVORITE_IMAGE_ALBUM_NAME, SETTING_THUMBNAILS_MODE_ORIGINAL, SETTING_THUMBNAILS_MODE_THUMBNAIL, SETTING_THUMBNAILS_MODE_THUMBNAIL_BACKUP
from .hub import ImmichHub


# How often to refresh the list of available asset IDs
_ID_LIST_REFRESH_INTERVAL = timedelta(hours=12)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Immich image platform."""

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    await coordinator.update_albums()

    watched_albums = config_entry.options.get(CONF_WATCHED_ALBUMS, [])
    # Create entity for random favorite image
    if FAVORITE_IMAGE_ALBUM in watched_albums:
        favorite = ImmichImageFavorite(hass, coordinator)
        async_add_entities([favorite])
        coordinator.image_entities.update({FAVORITE_IMAGE_ALBUM: {'name': FAVORITE_IMAGE_ALBUM_NAME, 'entity': favorite}})

    # Create entities for random image from each watched album
    for album in coordinator.albums.values():
        if album["id"] in watched_albums:
            entity = ImmichImageAlbum(
                        hass, coordinator, album_id=album["id"], album_name=album["albumName"]
                    )
            async_add_entities([entity])
            coordinator.image_entities.update({album["id"]: {'name': album["albumName"], 'entity': entity}})

    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle options updates."""
    await hass.config_entries.async_reload(config_entry.entry_id)


class BaseImmichImage(ImageEntity, CoordinatorEntity):
    """Base image entity for Immich. Subclasses will define where the random image comes from (e.g. favorite images, by album ID,..)."""

    _attr_has_entity_name = True

    # We want to get a new image every so often, as defined by the refresh interval
    _attr_should_poll = True

    _current_image_bytes: bytes | None = None
    _cached_available_asset_ids: list[str] | None = None
    _available_asset_ids_last_updated: datetime | None = None
    last_updated: datetime

    def __init__(self, hass: HomeAssistant, coordinator: ImmichCoordinator) -> None:
        """Initialize the Immich image entity."""
        super().__init__(hass=hass, verify_ssl=True)
        self.hass = hass
        self.coordinator = coordinator
        self.coordinator_context = object
        self._attr_extra_state_attributes = {}
        self.last_updated = datetime.now()

    async def async_update(self, thumbnail_mode) -> None:
        """Force a refresh of the image."""
        await self._load_and_cache_next_image(thumbnail_mode)

    async def async_image(self) -> bytes | None:
        """Return the current image. If no image is available, load and cache the image."""
        if not self._current_image_bytes:
            await self._load_and_cache_next_image(self.coordinator.get_thumbnail_mode(self._album_id))

        return self._current_image_bytes

    async def _refresh_available_asset_ids(self) -> list[str] | None:
        """Refresh the list of available asset IDs."""
        raise NotImplementedError

    async def _get_next_asset_id(self) -> str | None:
        """Get the asset id of the next image we want to display."""
        if (
            not self._available_asset_ids_last_updated
            or (datetime.now() - self._available_asset_ids_last_updated)
            > _ID_LIST_REFRESH_INTERVAL
        ):
            # If we don't have any available asset IDs yet, or the list is stale, refresh it
            _LOGGER.debug("Refreshing available asset IDs")
            self._cached_available_asset_ids = await self._refresh_available_asset_ids()
            self._available_asset_ids_last_updated = datetime.now()

        if not self._cached_available_asset_ids:
            # If we still don't have any available asset IDs, that's a problem
            _LOGGER.error("No assets are available")
            return None

        # Select random item in list
        random_asset = random.choice(self._cached_available_asset_ids)

        return random_asset

    async def _load_and_cache_next_image(self, thumbnail_mode) -> None:
        """Download and cache the image."""
        asset_bytes = None

        while not asset_bytes:
            asset_id = await self._get_next_asset_id()

            if not asset_id:
                return

            if thumbnail_mode == SETTING_THUMBNAILS_MODE_ORIGINAL:
                asset_bytes = await self.coordinator.hub.download_asset(asset_id)
            
            if thumbnail_mode == SETTING_THUMBNAILS_MODE_THUMBNAIL or (thumbnail_mode == SETTING_THUMBNAILS_MODE_THUMBNAIL_BACKUP and not asset_bytes):
                asset_bytes = await self.coordinator.hub.download_thumbnail(asset_id)

            if not asset_bytes:
                await asyncio.sleep(1)
                continue

            asset_info = await self.coordinator.hub.get_asset_info(asset_id)
            
            self._attr_extra_state_attributes["media_filename"] = (asset_info.get('originalFileName') or '')
            self._attr_extra_state_attributes["media_exifInfo"] = (asset_info.get('exifInfo') or '')
            self._attr_extra_state_attributes["media_localdatetime"] = (asset_info.get('localDateTime ') or '')

            self._current_image_bytes = asset_bytes
            self._attr_image_last_updated = datetime.now()
            self.last_updated = datetime.now()
            self.async_write_ha_state()

class ImmichImageFavorite(BaseImmichImage):
    """Image entity for Immich that displays a random image from the user's favorites."""

    _attr_unique_id = FAVORITE_IMAGE_ALBUM
    _attr_name = f"Immich: {FAVORITE_IMAGE_ALBUM_NAME}"
    _album_id = FAVORITE_IMAGE_ALBUM

    def __init__(
        self, hass: HomeAssistant, coordinator: ImmichCoordinator) -> None:
        super().__init__(hass, coordinator)
        self._attr_device_info = coordinator.get_device_info(self._attr_unique_id, self._attr_name)

    async def _refresh_available_asset_ids(self) -> list[str] | None:
        """Refresh the list of available asset IDs."""
        return [image["id"] for image in await self.coordinator.hub.list_favorite_images()]

class ImmichImageRandom(BaseImmichImage):
    """Image entity for Immich that displays a random image from the user's favorites."""

    _attr_unique_id = "random_image"
    _attr_name = "Immich: Random image"

    async def _get_next_asset_id(self) -> str | None:
        """Get the asset id of the next image we want to display."""

        random_asset = await self.hub.get_random_image()

        if not random_asset:
            # If we still don't have any available asset IDs, that's a problem
            _LOGGER.error("No assets are available")
            return None

        return random_asset

class ImmichImageAlbum(BaseImmichImage):
    """Image entity for Immich that displays a random image from a specific album."""

    def __init__(
        self, hass: HomeAssistant, coordinator: ImmichCoordinator, album_id: str, album_name: str
    ) -> None:
        """Initialize the Immich image entity."""
        super().__init__(hass, coordinator)
        self._album_id = album_id
        self._attr_unique_id = album_id
        self._attr_name = f"Immich: {album_name}"
        self._attr_device_info = coordinator.get_device_info(album_id, self._attr_name)

    async def _refresh_available_asset_ids(self) -> list[str] | None:
        """Refresh the list of available asset IDs."""
        return [
            image["id"] for image in await self.coordinator.hub.list_album_images(self._album_id)
        ]
