"""Example integration using DataUpdateCoordinator."""

from datetime import datetime, timedelta
import logging
from platform import node

import async_timeout

from .hub import ImmichHub
from homeassistant.components.light import LightEntity
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers.entity import DeviceInfo


from .const import ALBUM_REFRESH_INTERVAL, DOMAIN, MANUFACTURER, SETTING_INTERVAL_DEFAULT_OPTION, SETTING_INTERVAL_MAP, SETTING_ORIENTATION_DEFAULT, SETTING_THUMBNAILS_MODE_DEFAULT

_LOGGER = logging.getLogger(__name__)

class ImmichCoordinator(DataUpdateCoordinator):
    """Immich coordinator."""

    album_last_update = datetime.fromtimestamp(0)
    persons_last_update = datetime.fromtimestamp(0)
    hub: ImmichHub

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
        self.devices = dict()
        self.albums = dict()
        self.persons = dict()

    async def update_albums(self):
        if self.albums:
            time_delta = (datetime.now() - self.album_last_update).total_seconds()
            if time_delta < (ALBUM_REFRESH_INTERVAL*60):
                return

        albums = await self.hub.list_all_albums()
        for album in albums:
            self.albums.update({album['id']: album})
        self.album_last_update = datetime.now();
    
    async def update_persons(self):
        if self.persons:
            time_delta = (datetime.now() - self.persons_last_update).total_seconds()
            if time_delta < (ALBUM_REFRESH_INTERVAL*60):
                return

        persons = await self.hub.list_named_people()
        for person in persons:
            self.persons.update({person['id']: person})
        self.persons_last_update = datetime.now();    

    def get_device_id(self, entry = None, id = None, created = None):
        if entry:
            return '-'.join([entry.get('id'), str(entry.get('created'))])
        else:
            return '-'.join([id, str(created)]) 

    async def update_device(self, entry, image = None, select = None, interval = None, thumbnail = None, orientation = None):
        device_id = self.get_device_id(entry)
        if device_id in self.devices.keys():
            device_entry = self.devices.get(device_id)
        else:
            device_entry = {
                'id': entry.get('id'),
                'name': entry.get('name'),
                'type': entry.get('type'),
                'created': entry.get('created'),
                'interval': SETTING_INTERVAL_DEFAULT_OPTION,
                'thumbnail': SETTING_THUMBNAILS_MODE_DEFAULT,
                'orientation': SETTING_ORIENTATION_DEFAULT,
                'image': None,
                'select_interval': None,
                'select_thumbnail': None,
                'select_orientation': None,
            }

        if image:
            device_entry.update({'image': image})
        elif select:
            device_entry.update({'select_interval': select[0]})
            device_entry.update({'select_thumbnail': select[1]})
            device_entry.update({'select_orientation': select[2]})
        elif interval:
            device_entry.update({'interval': interval})
        elif thumbnail:
            device_entry.update({'thumbnail': thumbnail})
        elif orientation:
            device_entry.update({'orientation': orientation})

        self.devices.update({device_id: device_entry})

    async def remove_device(self, id, created):
        device_id = self.get_device_id(id = id, created = created)
        if device_id in self.devices.keys():
            self.devices.pop(device_id)

    def get_interval(self, entry):
        device_entry = self.devices.get(self.get_device_id(entry), {})
        return device_entry.get('interval', SETTING_INTERVAL_DEFAULT_OPTION)
    
    async def set_interval(self, entry, interval):
        await self.update_device(entry, interval = interval)
        
    def get_thumbnail_mode(self, entry):
        device_entry = self.devices.get(self.get_device_id(entry), {})
        return device_entry.get('thumbnail', SETTING_THUMBNAILS_MODE_DEFAULT)
    
    async def set_thumbnail_mode(self, entry, mode):
        await self.update_device(entry, thumbnail = mode)
        await self.update_image(entry)
                
    def get_orientation(self, entry):
        device_entry = self.devices.get(self.get_device_id(entry), {})
        return device_entry.get('orientation', SETTING_ORIENTATION_DEFAULT)
    
    async def set_orientation(self, entry, orientation):
        await self.update_device(entry, orientation = orientation)
        await self.update_image(entry)

    async def update_image(self, entry):
        device_entry = self.devices.get(self.get_device_id(entry), {})
        image_entity = device_entry.get('image')
        if image_entity:
            await image_entity.async_update(device_entry.get('thumbnail'), device_entry.get('orientation'))

    def get_device_info(self, entry) -> DeviceInfo:
        return DeviceInfo(
            identifiers={
                (
                    DOMAIN, 
                    entry.get('id'),
                    entry.get('type'),
                    entry.get('created')
                )
            },
            name=f"Immich: {entry.get('name')}",
            model=entry.get('type'),
            manufacturer=MANUFACTURER,
        )

    async def _async_update_data(self):
        """
        Update each Image Entity
        """
        for device_entry in self.devices.values():
            image_entity = device_entry.get('image')
            time_delta = (datetime.now() - image_entity.last_updated).total_seconds()
            interval = SETTING_INTERVAL_MAP.get(device_entry.get('interval'))
            if interval is None:
                continue
            if time_delta > interval:
                await image_entity.async_update(device_entry.get('thumbnail'), device_entry.get('orientation'))