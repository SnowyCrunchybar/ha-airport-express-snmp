"""Device naming and registry helpers for AirPort Express SNMP."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)

from .const import DOMAIN
from .coordinator import AirPortSnmpCoordinator


def resolve_client_device_name(
    hass: HomeAssistant,
    coordinator: AirPortSnmpCoordinator,
    mac: str,
) -> str:
    """Resolve a human-readable device name from HA Device Registry or DHCP."""
    formatted_mac = format_mac(mac)
    dev_reg = dr.async_get(hass)

    # Check if another integration (e.g. ESPHome, OpenBeken, HomeKit) already registered this MAC
    for device in dev_reg.devices.values():
        if (DOMAIN, f"client_{formatted_mac}") in device.identifiers:
            continue
        if (CONNECTION_NETWORK_MAC, formatted_mac) in device.connections:
            existing_name = device.name_by_user or device.name
            if existing_name and not existing_name.startswith("AirPort Client "):
                return f"{existing_name} (AirPort)"

    # Fallback to DHCP client-id / hostname if reported by AirPort
    client_info = coordinator.known_clients.get(mac, {})
    dhcp_name = (client_info.get("hostname") or "").strip()
    if dhcp_name and dhcp_name.lower() not in ("unknown", "*"):
        return f"{dhcp_name} (AirPort)"

    return f"AirPort Client {mac}"


def build_client_device_info(
    hass: HomeAssistant,
    coordinator: AirPortSnmpCoordinator,
    mac: str,
) -> DeviceInfo:
    """Build DeviceInfo and update existing Device Registry entry name if resolved."""
    formatted_mac = format_mac(mac)
    resolved_name = resolve_client_device_name(hass, coordinator, mac)

    dev_reg = dr.async_get(hass)
    existing_ap_dev = dev_reg.async_get_device(
        identifiers={(DOMAIN, f"client_{formatted_mac}")}
    )
    if (
        existing_ap_dev is not None
        and existing_ap_dev.name != resolved_name
        and not existing_ap_dev.name_by_user
    ):
        dev_reg.async_update_device(existing_ap_dev.id, name=resolved_name)

    return DeviceInfo(
        identifiers={(DOMAIN, f"client_{formatted_mac}")},
        connections={(CONNECTION_NETWORK_MAC, formatted_mac)},
        name=resolved_name,
        via_device=(DOMAIN, coordinator.host),
    )
