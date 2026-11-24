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
    """Resolve a human-readable device name from HA Registry, mDNS/DHCP, or Vendor."""
    formatted_mac = format_mac(mac)
    dev_reg = dr.async_get(hass)

    # 1. Check if another integration (e.g. ESPHome, OpenBeken, HomeKit) already registered this MAC
    for device in dev_reg.devices.values():
        if (DOMAIN, f"client_{formatted_mac}") in device.identifiers:
            continue
        if (CONNECTION_NETWORK_MAC, formatted_mac) in device.connections:
            existing_name = device.name_by_user or device.name
            if existing_name and not existing_name.startswith("AirPort Client "):
                return f"{existing_name} (AirPort)"

    client_info = coordinator.known_clients.get(mac, {})

    # 2. Fallback to mDNS or DHCP hostname
    mdns_or_dhcp = (
        client_info.get("mdns_name") or client_info.get("hostname") or ""
    ).strip()
    if mdns_or_dhcp and mdns_or_dhcp.lower() not in ("unknown", "*"):
        return f"{mdns_or_dhcp} (AirPort)"

    # 3. Fallback to OUI vendor + short MAC suffix
    vendor = (client_info.get("vendor") or "").strip()
    if vendor:
        short_mac = mac[-5:]
        return f"{vendor} {short_mac} (AirPort)"

    return f"AirPort Client {mac}"


def build_client_device_info(
    hass: HomeAssistant,
    coordinator: AirPortSnmpCoordinator,
    mac: str,
) -> DeviceInfo:
    """Build DeviceInfo and update existing Device Registry entry if resolved."""
    formatted_mac = format_mac(mac)
    resolved_name = resolve_client_device_name(hass, coordinator, mac)
    client_info = coordinator.known_clients.get(mac, {})
    vendor = client_info.get("vendor")

    dev_reg = dr.async_get(hass)
    existing_ap_dev = dev_reg.async_get_device(
        identifiers={(DOMAIN, f"client_{formatted_mac}")}
    )
    if existing_ap_dev is not None:
        updates: dict[str, str] = {}
        if (
            existing_ap_dev.name != resolved_name
            and not existing_ap_dev.name_by_user
        ):
            updates["name"] = resolved_name
        if vendor and not existing_ap_dev.manufacturer:
            updates["manufacturer"] = vendor
        if updates:
            dev_reg.async_update_device(existing_ap_dev.id, **updates)

    return DeviceInfo(
        identifiers={(DOMAIN, f"client_{formatted_mac}")},
        connections={(CONNECTION_NETWORK_MAC, formatted_mac)},
        name=resolved_name,
        manufacturer=vendor,
        via_device=(DOMAIN, coordinator.host),
    )
