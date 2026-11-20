"""Device tracker platform for AirPort Express Wi-Fi clients."""
from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_TRACK_CLIENTS, DEFAULT_TRACK_CLIENTS, DOMAIN
from .coordinator import AirPortSnmpCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device trackers for connected Wi-Fi clients."""
    opts = {**entry.data, **entry.options}
    if not opts.get(CONF_TRACK_CLIENTS, DEFAULT_TRACK_CLIENTS):
        return

    coordinator: AirPortSnmpCoordinator = hass.data[DOMAIN][entry.entry_id]
    tracked_macs: set[str] = set()

    @callback
    def _async_add_new_clients() -> None:
        new_entities: list[AirPortClientTracker] = []
        for mac in coordinator.data.get("active_clients", {}):
            if mac not in tracked_macs:
                tracked_macs.add(mac)
                new_entities.append(AirPortClientTracker(coordinator, mac))
        if new_entities:
            async_add_entities(new_entities)

    _async_add_new_clients()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_clients))


class AirPortClientTracker(CoordinatorEntity[AirPortSnmpCoordinator], ScannerEntity):
    """Represent a Wi-Fi client linked via MAC address to its HA device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AirPortSnmpCoordinator, mac: str) -> None:
        super().__init__(coordinator)
        self._mac = mac
        formatted_mac = format_mac(mac)
        clean_mac = mac.replace(":", "").lower()
        self._attr_unique_id = f"{coordinator.host}_client_{clean_mac}"
        self._attr_name = f"Wi-Fi {mac}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"client_{formatted_mac}")},
            connections={(CONNECTION_NETWORK_MAC, formatted_mac)},
            name=f"AirPort Client {mac}",
            via_device=(DOMAIN, coordinator.host),
        )

    @property
    def source_type(self) -> SourceType:
        return SourceType.ROUTER

    @property
    def mac_address(self) -> str:
        return self._mac

    @property
    def ip_address(self) -> str | None:
        client = self.coordinator.known_clients.get(self._mac, {})
        return client.get("ip")

    @property
    def is_connected(self) -> bool:
        return self._mac in self.coordinator.data.get("active_clients", {})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        client = self.coordinator.known_clients.get(self._mac, {})
        return {
            "ip_address": client.get("ip"),
            "rssi_dbm": client.get("rssi_dbm"),
            "noise_dbm": client.get("noise_dbm"),
            "snr_db": client.get("snr_db"),
            "rate_mbps": client.get("rate_mbps"),
            "connected_seconds": client.get("connected_seconds"),
            "lease_remaining": client.get("lease_remaining"),
        }
