"""The AirPort Express SNMP integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_COMMUNITY,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import AirPortSnmpCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.DEVICE_TRACKER]


def _cleanup_orphaned_client_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove empty client devices that no longer have any entities."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    for device in list(dr.async_entries_for_config_entry(dev_reg, entry.entry_id)):
        is_client_device = any(
            len(ident) >= 2 and ident[0] == DOMAIN and "_client_" in str(ident[1])
            for ident in device.identifiers
        )
        if not is_client_device:
            continue
        if not er.async_entries_for_device(ent_reg, device.id, include_disabled_entities=True):
            dev_reg.async_remove_device(device.id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AirPort Express SNMP from a config entry."""
    host = entry.data[CONF_HOST]
    community = entry.options.get(CONF_COMMUNITY, entry.data[CONF_COMMUNITY])
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )

    coordinator = AirPortSnmpCoordinator(
        hass=hass,
        host=host,
        community=community,
        scan_interval=scan_interval,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _cleanup_orphaned_client_devices(hass, entry)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
