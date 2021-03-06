"""Support for RFXtrx switches."""
import logging

import RFXtrx as rfxtrxmod

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import ATTR_STATE, CONF_DEVICES, STATE_ON
from homeassistant.helpers.restore_state import RestoreEntity

from . import (
    ATTR_FIRE_EVENT,
    CONF_AUTOMATIC_ADD,
    CONF_FIRE_EVENT,
    CONF_SIGNAL_REPETITIONS,
    DEFAULT_SIGNAL_REPETITIONS,
    DOMAIN,
    SIGNAL_EVENT,
    RfxtrxDevice,
    fire_command_event,
    get_device_id,
    get_rfx_object,
)
from .const import COMMAND_OFF_LIST, COMMAND_ON_LIST

DATA_SWITCH = f"{DOMAIN}_switch"

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities_callback, discovery_info=None):
    """Set up the RFXtrx platform."""
    if discovery_info is None:
        return

    device_ids = set()

    def supported(event):
        return (
            isinstance(event.device, rfxtrxmod.LightingDevice)
            and not event.device.known_to_be_dimmable
            and not event.device.known_to_be_rollershutter
        )

    # Add switch from config file
    entities = []
    for packet_id, entity_info in discovery_info[CONF_DEVICES].items():
        event = get_rfx_object(packet_id)
        if event is None:
            _LOGGER.error("Invalid device: %s", packet_id)
            continue
        if not supported(event):
            continue

        device_id = get_device_id(event.device)
        if device_id in device_ids:
            continue
        device_ids.add(device_id)

        datas = {ATTR_STATE: None, ATTR_FIRE_EVENT: entity_info[CONF_FIRE_EVENT]}
        entity = RfxtrxSwitch(event.device, datas, entity_info[CONF_SIGNAL_REPETITIONS])
        entities.append(entity)

    add_entities_callback(entities)

    def switch_update(event):
        """Handle sensor updates from the RFXtrx gateway."""
        if not supported(event):
            return

        device_id = get_device_id(event.device)
        if device_id in device_ids:
            return
        device_ids.add(device_id)

        _LOGGER.info(
            "Added switch (Device ID: %s Class: %s Sub: %s, Event: %s)",
            event.device.id_string.lower(),
            event.device.__class__.__name__,
            event.device.subtype,
            "".join(f"{x:02x}" for x in event.data),
        )

        datas = {ATTR_STATE: None, ATTR_FIRE_EVENT: False}
        entity = RfxtrxSwitch(
            event.device, datas, DEFAULT_SIGNAL_REPETITIONS, event=event
        )
        add_entities_callback([entity])

    # Subscribe to main RFXtrx events
    if discovery_info[CONF_AUTOMATIC_ADD]:
        hass.helpers.dispatcher.dispatcher_connect(SIGNAL_EVENT, switch_update)


class RfxtrxSwitch(RfxtrxDevice, SwitchEntity, RestoreEntity):
    """Representation of a RFXtrx switch."""

    async def async_added_to_hass(self):
        """Restore RFXtrx switch device state (ON/OFF)."""
        await super().async_added_to_hass()

        old_state = await self.async_get_last_state()
        if old_state is not None:
            self._state = old_state.state == STATE_ON

        self.async_on_remove(
            self.hass.helpers.dispatcher.async_dispatcher_connect(
                SIGNAL_EVENT, self._handle_event
            )
        )

    def _apply_event(self, event):
        """Apply command from rfxtrx."""
        if event.values["Command"] in COMMAND_ON_LIST:
            self._state = True
        elif event.values["Command"] in COMMAND_OFF_LIST:
            self._state = False

    def _handle_event(self, event):
        """Check if event applies to me and update."""
        if event.device.id_string != self._device.id_string:
            return

        self._apply_event(event)

        self.schedule_update_ha_state()
        if self.should_fire_event:
            fire_command_event(self.hass, self.entity_id, event.values["Command"])

    def turn_on(self, **kwargs):
        """Turn the device on."""
        self._send_command("turn_on")
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        """Turn the device off."""
        self._send_command("turn_off")
        self.schedule_update_ha_state()
