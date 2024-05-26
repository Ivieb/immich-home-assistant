"""Example integration using DataUpdateCoordinator."""

from datetime import datetime, timedelta
import logging

import async_timeout

from homeassistant.components.light import LightEntity
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers.entity import DeviceInfo


from .const import ALBUM_REFRESH_INTERVAL, DOMAIN, FAVORITE_IMAGE, MANUFACTURER, SETTING_INTERVAL_DEFAULT_OPTION, SETTING_INTERVAL_MAP

_LOGGER = logging.getLogger(__name__)

class ImmichCoordinator(DataUpdateCoordinator):
    """Immich coordinator."""

    album_last_update = datetime.fromtimestamp(0)

    def __init__(self, hass, hub):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name=DOMAIN,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=10),
        )
        self.hub = hub
        self.image_entities = dict()
        self.albums = dict()
        self.intervals = dict()

    async def update_albums(self):
        if self.albums:
            time_delta = (datetime.now() - self.album_last_update).total_seconds()
            if time_delta < (ALBUM_REFRESH_INTERVAL*60):
                return

        albums = await self.hub.list_all_albums()
        for album in albums:
            self.albums.update({album['id']: album})
        self.album_last_update = datetime.now();


    def get_interval(self, album_id):
        return self.intervals.get(album_id, SETTING_INTERVAL_DEFAULT_OPTION)
    
    def set_interval(self, album_id, interval):
        self.intervals.update({album_id: interval})
        
    def get_device_info(self, unique_id, name) -> DeviceInfo:
        return DeviceInfo(
            identifiers={
                (
                    DOMAIN, 
                    unique_id,
                )
            },
            name=name,
            manufacturer=MANUFACTURER,
        )

    async def _async_update_data(self):
        """
        Update each Image Entity
        """
        for album_id in self.image_entities:
            image_entity = self.image_entities.get(album_id).get('entity')
            time_delta = (datetime.now() - image_entity.last_updated).total_seconds()
            interval = SETTING_INTERVAL_MAP.get(self.get_interval(album_id))
            if time_delta > interval:
                await image_entity.async_update()