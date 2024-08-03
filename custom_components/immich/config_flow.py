"""Config flow for Immich integration."""
from __future__ import annotations

from datetime import datetime
import logging
import re
from typing import Any
from urllib.parse import urlparse

from url_normalize import url_normalize
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import selector

from .const import CONF_WATCHED, CONF_WATCHED_ALBUMS, CONF_WATCHED_PERSONS, CONF_WATCHED_TYPE_ALBUM, CONF_WATCHED_TYPE_FAVORITE, CONF_WATCHED_TYPE_PERSON, CONF_WATCHED_TYPE_RANDOM, DOMAIN, FAVORITE_IMAGE_ALBUM, FAVORITE_IMAGE_ALBUM_NAME, RANDOM_IMAGE_ALBUM, RANDOM_IMAGE_ALBUM_NAME
from .hub import CannotConnect, ImmichHub, InvalidAuth

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_API_KEY): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """

    url = url_normalize(data[CONF_HOST])
    api_key = data[CONF_API_KEY]

    hub = ImmichHub(host=url, api_key=api_key)

    if not await hub.authenticate():
        raise InvalidAuth

    user_info = await hub.get_my_user_info()
    username = user_info["name"]
    clean_hostname = urlparse(url).hostname

    # Return info that you want to store in the config entry.
    return {
        "title": f"{username} @ {clean_hostname}",
        "data": {CONF_HOST: url, CONF_API_KEY: api_key},
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for immich."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Immich options flow handler."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["albumselect", "personselect", "addrandom", "addfavorite"],
            description_placeholders={
                "model": "Example model",
            },
        )

    async def async_step_addrandom(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a random album."""
        album_id = RANDOM_IMAGE_ALBUM
        album_name = RANDOM_IMAGE_ALBUM_NAME
        
        entries = self.config_entry.options.get(CONF_WATCHED, []).copy()
        entry = {'id': album_id, 'name': album_name, 'type': CONF_WATCHED_TYPE_RANDOM, 'created': datetime.now().timestamp()}
        entries.append(entry)
        data = self.config_entry.options.copy()
        data.update({CONF_WATCHED: entries})
        return self.async_create_entry(title="", data=data)
    
    async def async_step_addfavorite(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        album_id = FAVORITE_IMAGE_ALBUM
        album_name = FAVORITE_IMAGE_ALBUM_NAME
        
        entries = self.config_entry.options.get(CONF_WATCHED, []).copy()
        entry = {'id': album_id, 'name': album_name, 'type': CONF_WATCHED_TYPE_FAVORITE, 'created': datetime.now().timestamp()}
        entries.append(entry)
        data = self.config_entry.options.copy()
        data.update({CONF_WATCHED: entries})
        return self.async_create_entry(title="", data=data)

    async def async_step_albumselect(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the album selection."""
        if user_input is not None:
            album_str = user_input.get(CONF_WATCHED_ALBUMS)
            album_id = re.findall(r'\(.*?\)', album_str)[-1]
            album_name = album_str.replace(album_id, '')[:-1]
            album_id = album_id[1:-1]
            
            entries = self.config_entry.options.get(CONF_WATCHED, []).copy()
            entry = {'id': album_id, 'name': album_name, 'type': CONF_WATCHED_TYPE_ALBUM, 'created': datetime.now().timestamp()}
            entries.append(entry)
            data = self.config_entry.options.copy()
            data.update({CONF_WATCHED: entries})
            return self.async_create_entry(title="", data=data)                 

        # Get a connection to the hub in order to list the available albums
        url = url_normalize(self.config_entry.data[CONF_HOST])
        api_key = self.config_entry.data[CONF_API_KEY]
        hub = ImmichHub(host=url, api_key=api_key)

        if not await hub.authenticate():
            raise InvalidAuth

        # Get the list of albums and create a mapping of album id to album name
        albums = await hub.list_all_albums()
        album_map = [f'{album["albumName"]} ({album["id"]})' for album in albums]
        album_map.append(f'{FAVORITE_IMAGE_ALBUM} ({FAVORITE_IMAGE_ALBUM_NAME})')
        album_map.append(f'{RANDOM_IMAGE_ALBUM} ({RANDOM_IMAGE_ALBUM_NAME})')

        # Allow the user to select which albums they want to create entities for
        return self.async_show_form(
            step_id="albumselect",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_WATCHED_ALBUMS,
                    ) :vol.In(album_map)
                }
            ),
        )
    
    async def async_step_personselect(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the person selection."""

        if user_input is not None:
            person_str = user_input.get(CONF_WATCHED_PERSONS)
            person_id = re.findall(r'\(.*?\)', person_str)[-1]
            person_name = person_str.replace(person_id, '')[:-1]
            person_id = person_id[1:-1]
            entries = self.config_entry.options.get(CONF_WATCHED, []).copy()
            entry = {'id': person_id, 'name': person_name, 'type': CONF_WATCHED_TYPE_PERSON, 'created': datetime.now().timestamp()}
            entries.append(entry)
            data = self.config_entry.options.copy()
            data.update({CONF_WATCHED: entries})
            return self.async_create_entry(title="", data=data)     

        # Get a connection to the hub in order to list the available albums
        url = url_normalize(self.config_entry.data[CONF_HOST])
        api_key = self.config_entry.data[CONF_API_KEY]
        hub = ImmichHub(host=url, api_key=api_key)

        if not await hub.authenticate():
            raise InvalidAuth

        # Get the list of persons and create a mapping of person id to person name
        persons = await hub.list_named_people()
        persons_map = [f"{person["name"]} ({person["id"]})" for person in persons]

        # Allow the user to select which persons they want to create entities for
        return self.async_show_form(
            step_id="personselect",
            data_schema=vol.Schema(
                { vol.Required(
                    CONF_WATCHED_PERSONS
                )
                    :vol.In(persons_map)
                }
            ),
        )
