"""Generic Z-Wave Entity Class."""

import logging
from typing import Optional, Union

from zwave_js_server.client import Client as ZwaveClient
from zwave_js_server.model.value import Value as ZwaveValue, get_value_id

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .discovery import ZwaveDiscoveryInfo

LOGGER = logging.getLogger(__name__)

EVENT_VALUE_UPDATED = "value updated"


class ZWaveBaseEntity(Entity):
    """Generic Entity Class for a Z-Wave Device."""

    def __init__(self, client: ZwaveClient, info: ZwaveDiscoveryInfo) -> None:
        """Initialize a generic Z-Wave device entity."""
        self.client = client
        self.info = info
        # entities requiring additional values, can add extra ids to this list
        self.watched_value_ids = {self.info.primary_value.value_id}

    @callback
    def on_value_update(self) -> None:
        """Call when one of the watched values change.

        To be overridden by platforms needing this event.
        """

    async def async_added_to_hass(self) -> None:
        """Call when entity is added."""
        assert self.hass  # typing
        # Add value_changed callbacks.
        self.async_on_remove(
            self.info.node.on(EVENT_VALUE_UPDATED, self._value_changed)
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{DOMAIN}_connection_state", self.async_write_ha_state
            )
        )

    @property
    def device_info(self) -> dict:
        """Return device information for the device registry."""
        # device is precreated in main handler
        return {
            "identifiers": {
                (
                    DOMAIN,
                    f"{self.client.driver.controller.home_id}-{self.info.node.node_id}",
                )
            },
        }

    @property
    def name(self) -> str:
        """Return default name from device name and value name combination."""
        node_name = self.info.node.name or self.info.node.device_config.description
        value_name = (
            self.info.primary_value.metadata.label
            or self.info.primary_value.property_key_name
            or self.info.primary_value.property_name
        )
        return f"{node_name}: {value_name}"

    @property
    def unique_id(self) -> str:
        """Return the unique_id of the entity."""
        return f"{self.client.driver.controller.home_id}.{self.info.value_id}"

    @property
    def available(self) -> bool:
        """Return entity availability."""
        return self.client.connected and bool(self.info.node.ready)

    @callback
    def _value_changed(self, event_data: Union[dict, ZwaveValue]) -> None:
        """Call when (one of) our watched values changes.

        Should not be overridden by subclasses.
        """
        if isinstance(event_data, ZwaveValue):
            value_id = event_data.value_id
        else:
            value_id = event_data["value"].value_id

        if value_id not in self.watched_value_ids:
            return

        value = self.info.node.values[value_id]

        LOGGER.debug(
            "[%s] Value %s/%s changed to: %s",
            self.entity_id,
            value.property_,
            value.property_key_name,
            value.value,
        )

        self.on_value_update()
        self.async_write_ha_state()

    @callback
    def get_zwave_value(
        self,
        value_property: Union[str, int],
        command_class: Optional[int] = None,
        endpoint: Optional[int] = None,
        value_property_key_name: Optional[str] = None,
        add_to_watched_value_ids: bool = True,
    ) -> Optional[ZwaveValue]:
        """Return specific ZwaveValue on this ZwaveNode."""
        # use commandclass and endpoint from primary value if omitted
        return_value = None
        if command_class is None:
            command_class = self.info.primary_value.command_class
        if endpoint is None:
            endpoint = self.info.primary_value.endpoint
        # lookup value by value_id
        value_id = get_value_id(
            self.info.node,
            {
                "commandClass": command_class,
                "endpoint": endpoint,
                "property": value_property,
                "propertyKeyName": value_property_key_name,
            },
        )
        return_value = self.info.node.values.get(value_id)
        # add to watched_ids list so we will be triggered when the value updates
        if (
            return_value
            and return_value.value_id not in self.watched_value_ids
            and add_to_watched_value_ids
        ):
            self.watched_value_ids.add(return_value.value_id)
        return return_value

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False
