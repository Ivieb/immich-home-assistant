"""Image device for Immich integration."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
import random
from typing import Tuple

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

from .const import (
    CONF_WATCHED,
    CONF_WATCHED_TYPE_ALBUM,
    CONF_WATCHED_TYPE_FAVORITE,
    CONF_WATCHED_TYPE_PERSON,
    CONF_WATCHED_TYPE_RANDOM,
    DOMAIN,
    FAVORITE_IMAGE_ALBUM,
    FAVORITE_IMAGE_ALBUM_NAME,
    RANDOM_IMAGE_ALBUM,
    RANDOM_IMAGE_COUNT,
    SETTING_ORIENTATION_LANDSCAPE,
    SETTING_ORIENTATION_PORTRAIT,
    SETTING_THUMBNAILS_MODE_ORIGINAL,
    SETTING_THUMBNAILS_MODE_THUMBNAIL,
    SETTING_THUMBNAILS_MODE_THUMBNAIL_BACKUP,
)
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

    coordinator: ImmichCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    await coordinator.update_albums()
    await coordinator.update_persons()

    watched_entries = config_entry.options.get(CONF_WATCHED, [])
    for entry in watched_entries:
        if entry.get("type") == CONF_WATCHED_TYPE_ALBUM:
            entity = ImmichImageAlbum(hass, coordinator, entry)
        elif entry.get("type") == CONF_WATCHED_TYPE_PERSON:
            entity = ImmichPersonAlbum(hass, coordinator, entry)
        elif entry.get("type") == CONF_WATCHED_TYPE_RANDOM:
            entity = ImmichImageRandom(hass, coordinator, entry)
        elif entry.get("type") == CONF_WATCHED_TYPE_FAVORITE:
            entity = ImmichImageFavorite(hass, coordinator, entry)

        async_add_entities([entity])

        await coordinator.update_device(entry, image=entity)

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
    _cached_available_asset_id: list[str] | None = None
    _cached_available_asset_id_portrait: list[str] | None = None
    _cached_available_asset_id_landscape: list[str] | None = None
    _available_asset_ids_last_updated: datetime | None = None
    last_updated: datetime

    def __init__(
        self, hass: HomeAssistant, coordinator: ImmichCoordinator, entry
    ) -> None:
        """Initialize the Immich image entity."""
        super().__init__(hass=hass, verify_ssl=True)
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.coordinator_context = object
        self._attr_name = "Image"
        self._attr_unique_id = coordinator.get_device_id(entry)
        self._attr_device_info = coordinator.get_device_info(entry)
        self._attr_extra_state_attributes = {}
        self.last_updated = datetime.now()

    async def async_update(self, thumbnail_mode, orientation) -> None:
        """Force a refresh of the image."""
        await self._load_and_cache_next_image(thumbnail_mode, orientation)

    async def async_image(self) -> bytes | None:
        """Return the current image. If no image is available, load and cache the image."""
        if not self._current_image_bytes:
            await self._load_and_cache_next_image(
                self.coordinator.get_thumbnail_mode(self.entry),
                self.coordinator.get_orientation(self.entry),
            )

        return self._current_image_bytes

    async def _refresh_available_asset_ids(self) -> list[str] | None:
        """Refresh the list of available asset IDs."""
        raise NotImplementedError

    def _is_portrait(self, dimensions: Tuple[float, float], orientation) -> bool:
        """Returns if the given dimension represent a portrait media item"""
        try:
            orientation = int(orientation)
        except:
            orientation = 0
        if orientation <= 4:
            return dimensions[0] < dimensions[1]
        else:
            return dimensions[0] > dimensions[1]

    async def _get_next_asset_id(self, orientation) -> str | None:
        """Get the asset id of the next image we want to display."""
        if (
            not self._available_asset_ids_last_updated
            or (datetime.now() - self._available_asset_ids_last_updated)
            > _ID_LIST_REFRESH_INTERVAL
        ):
            # If we don't have any available asset IDs yet, or the list is stale, refresh it
            _LOGGER.debug("Refreshing available asset IDs")
            await self._refresh_available_asset_ids()
            self._available_asset_ids_last_updated = datetime.now()



        # Select random item in list
        if orientation == SETTING_ORIENTATION_PORTRAIT:
            if not self._cached_available_asset_id_portrait:
                # If we still don't have any available asset IDs, that's a problem
                _LOGGER.error("No assets are available")
                return None
            random_asset = random.choice(self._cached_available_asset_id_portrait)
        elif orientation == SETTING_ORIENTATION_LANDSCAPE:
            if not self._cached_available_asset_id_landscape:
                # If we still don't have any available asset IDs, that's a problem
                _LOGGER.error("No assets are available")
                return None            
            random_asset = random.choice(self._cached_available_asset_id_landscape)
        else:
            if not self._cached_available_asset_id:
                # If we still don't have any available asset IDs, that's a problem
                _LOGGER.error("No assets are available")
                return None
            random_asset = random.choice(self._cached_available_asset_id)

        return random_asset

    async def _load_and_cache_next_image(self, thumbnail_mode, orientation) -> None:
        """Download and cache the image."""
        asset_bytes = None

        while not asset_bytes:
            asset_id = await self._get_next_asset_id(orientation)

            if not asset_id:
                return

            if thumbnail_mode == SETTING_THUMBNAILS_MODE_ORIGINAL:
                asset_bytes = await self.coordinator.hub.download_asset(asset_id)

            if thumbnail_mode == SETTING_THUMBNAILS_MODE_THUMBNAIL or (
                thumbnail_mode == SETTING_THUMBNAILS_MODE_THUMBNAIL_BACKUP
                and not asset_bytes
            ):
                asset_bytes = await self.coordinator.hub.download_thumbnail(asset_id)

            if not asset_bytes:
                await asyncio.sleep(1)
                continue

            asset_info = await self.coordinator.hub.get_asset_info(asset_id)

            self._attr_extra_state_attributes["media_filename"] = (
                asset_info.get("originalFileName") or ""
            )
            self._attr_extra_state_attributes["media_exifInfo"] = (
                asset_info.get("exifInfo") or ""
            )
            self._attr_extra_state_attributes["media_localdatetime"] = (
                asset_info.get("localDateTime ") or ""
            )

            self._current_image_bytes = asset_bytes
            self._attr_image_last_updated = datetime.now()
            self.last_updated = datetime.now()
            self.async_write_ha_state()


class ImmichImageFavorite(BaseImmichImage):
    """Image entity for Immich that displays a random image from the user's favorites."""

    _attr_name = f"Immich: {FAVORITE_IMAGE_ALBUM_NAME}"
    _album_id = FAVORITE_IMAGE_ALBUM

    def __init__(
        self, hass: HomeAssistant, coordinator: ImmichCoordinator, entry
    ) -> None:
        super().__init__(hass, coordinator, entry)

    async def _refresh_available_asset_ids(self) -> list[str] | None:
        """Refresh the list of available asset IDs."""
        asset_ids = []
        asset_ids_portrait = []
        asset_ids_landscape = []
        for image in await self.coordinator.hub.list_favorite_images():
            asset_ids.append(image["id"])
            if (
                not image.get("exifInfo")
                or not image.get("exifInfo").get("exifImageWidth", 0)
                or not image.get("exifInfo").get("exifImageHeight", 0)
            ):
                continue
            width = image.get("exifInfo").get("exifImageWidth")
            height = image.get("exifInfo").get("exifImageHeight")
            orientation = image.get("exifInfo").get("orientation", "0")            
            if self._is_portrait(((float(width), float(height))), orientation):
                asset_ids_portrait.append(image["id"])
            else:
                asset_ids_landscape.append(image["id"])

        self._cached_available_asset_id = asset_ids
        self._cached_available_asset_id_portrait = asset_ids_portrait
        self._cached_available_asset_id_landscape = asset_ids_landscape


class ImmichImageRandom(BaseImmichImage):
    """Image entity for Immich that displays a random image from the user's favorites."""

    _album_id = RANDOM_IMAGE_ALBUM

    def __init__(
        self, hass: HomeAssistant, coordinator: ImmichCoordinator, entry
    ) -> None:
        super().__init__(hass, coordinator, entry)

    async def _get_next_asset_id(self, orientation) -> str | None:
        """Get the asset id of the next image we want to display."""
        if (
            not self._cached_available_asset_id
            or not self._cached_available_asset_id_landscape
            or not self._cached_available_asset_id_portrait
        ):
            # If out of random ids
            _LOGGER.debug("Refreshing available asset IDs")
            await self._refresh_available_asset_ids()

        if (
            not self._cached_available_asset_id
            or not self._cached_available_asset_id_landscape
            or not self._cached_available_asset_id_portrait
        ):
            # If we still don't have any available asset IDs, that's a problem
            _LOGGER.error("No assets are available")
            return None

        # Pop last random asset
        # Select random item in list
        if orientation == SETTING_ORIENTATION_PORTRAIT:
            if not self._cached_available_asset_id_portrait:
                # If we still don't have any available asset IDs, that's a problem
                _LOGGER.error("No assets are available")
                return None            
            random_asset = self._cached_available_asset_id_portrait.pop()
            if random_asset in self._cached_available_asset_id: 
                self._cached_available_asset_id.remove(random_asset)
        elif orientation == SETTING_ORIENTATION_LANDSCAPE:
            if not self._cached_available_asset_id_landscape:
                # If we still don't have any available asset IDs, that's a problem
                _LOGGER.error("No assets are available")
                return None                        
            random_asset = self._cached_available_asset_id_landscape.pop()
            if random_asset in self._cached_available_asset_id: 
                self._cached_available_asset_id.remove(random_asset)
        else:
            if not self._cached_available_asset_id:
                # If we still don't have any available asset IDs, that's a problem
                _LOGGER.error("No assets are available")
                return None            
            random_asset = self._cached_available_asset_id.pop()
            if random_asset in self._cached_available_asset_id_portrait: 
                self._cached_available_asset_id_portrait.remove(random_asset)
            elif random_asset in self._cached_available_asset_id_landscape: 
                self._cached_available_asset_id_landscape.remove(random_asset)

        return random_asset

    async def _refresh_available_asset_ids(self) -> None:
        """Refresh the list of available asset IDs."""
        asset_ids = []
        asset_ids_portrait = []
        asset_ids_landscape = []

        asset_stats = await self.coordinator.hub.get_asset_stats()
        images_count = asset_stats.get("images", 0)
        if images_count == 0:
            _LOGGER.error("No assets are available")
            return None

        random_count = (
            RANDOM_IMAGE_COUNT if RANDOM_IMAGE_COUNT < images_count else images_count
        )

        for image in await self.coordinator.hub.get_random_images(random_count):
            asset_ids.append(image["id"])
            if not (
                image.get("exifInfo").get("exifImageWidth", None)
                and image.get("exifInfo").get("exifImageHeight", None)
            ):
                continue
            width = image.get("exifInfo").get("exifImageWidth")
            height = image.get("exifInfo").get("exifImageHeight")
            orientation = image.get("exifInfo").get("orientation", "0")
            if self._is_portrait(((float(width), float(height))), orientation):
                asset_ids_portrait.append(image["id"])
            else:
                asset_ids_landscape.append(image["id"])

        self._cached_available_asset_id = asset_ids
        self._cached_available_asset_id_portrait = asset_ids_portrait
        self._cached_available_asset_id_landscape = asset_ids_landscape


class ImmichImageAlbum(BaseImmichImage):
    """Image entity for Immich that displays a random image from a specific album."""

    def __init__(
        self, hass: HomeAssistant, coordinator: ImmichCoordinator, entry
    ) -> None:
        """Initialize the Immich image entity."""
        super().__init__(hass, coordinator, entry)
        self._album_id = entry.get("id")

    async def _refresh_available_asset_ids(self) -> None:
        """Refresh the list of available asset IDs."""
        asset_ids = []
        asset_ids_portrait = []
        asset_ids_landscape = []
        for image in await self.coordinator.hub.list_album_images(self._album_id):
            asset_ids.append(image["id"])
            if not (
                image.get("exifInfo").get("exifImageWidth", 0)
                and image.get("exifInfo").get("exifImageHeight", 0)
            ):
                continue
            width = image.get("exifInfo").get("exifImageWidth")
            height = image.get("exifInfo").get("exifImageHeight")
            orientation = image.get("exifInfo").get("orientation", "0")            
            if self._is_portrait(((float(width), float(height))), orientation):
                asset_ids_portrait.append(image["id"])
            else:
                asset_ids_landscape.append(image["id"])

        self._cached_available_asset_id = asset_ids
        self._cached_available_asset_id_portrait = asset_ids_portrait
        self._cached_available_asset_id_landscape = asset_ids_landscape


class ImmichPersonAlbum(BaseImmichImage):
    """Image entity for Immich that displays a random image from a specific person."""

    def __init__(
        self, hass: HomeAssistant, coordinator: ImmichCoordinator, entry
    ) -> None:
        """Initialize the Immich image entity."""
        super().__init__(hass, coordinator, entry)
        self._album_id = entry.get("id")

    async def _refresh_available_asset_ids(self) -> None:
        """Refresh the list of available asset IDs."""
        asset_ids = []
        asset_ids_portrait = []
        asset_ids_landscape = []
        for image in await self.coordinator.hub.list_person_images(self._album_id):
            asset_ids.append(image["id"])
            if not (
                image.get("exifInfo").get("exifImageWidth", 0)
                and image.get("exifInfo").get("exifImageHeight", 0)
            ):
                continue
            width = image.get("exifInfo").get("exifImageWidth")
            height = image.get("exifInfo").get("exifImageHeight")
            orientation = image.get("exifInfo").get("orientation", "0")   
            if self._is_portrait(((float(width), float(height))), orientation):
                asset_ids_portrait.append(image["id"])
            else:
                asset_ids_landscape.append(image["id"])

        self._cached_available_asset_id = asset_ids
        self._cached_available_asset_id_portrait = asset_ids_portrait
        self._cached_available_asset_id_landscape = asset_ids_landscape
