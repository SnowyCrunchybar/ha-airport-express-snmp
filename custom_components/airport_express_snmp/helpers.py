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


def _find_existing_ha_device(
    hass: HomeAssistant,
    formatted_mac: str,
    mdns_name: str | None,
) -> dr.DeviceEntry | None:
    """Find an existing HA device by MAC connection or OpenBeken/mDNS hostname."""
    dev_reg = dr.async_get(hass)
    mdns_lower = (mdns_name or "").strip().lower()

    for device in dev_reg.devices.values():
        if (DOMAIN, f"client_{formatted_mac}") in device.identifiers:
            continue

        # 1. Exact MAC match (ESPHome, Tapo, HomeKit, etc.)
        if (CONNECTION_NETWORK_MAC, formatted_mac) in device.connections:
            return device

        # 2. Match OpenBeken / MQTT devices via mDNS hostname == MQTT client_id or device name
        if mdns_lower:
            for ident_domain, ident_val in device.identifiers:
                if ident_domain == "mqtt" and str(ident_val).lower() == mdns_lower:
                    return device
            dev_name = (device.name_by_user or device.name or "").strip().lower()
            if dev_name == mdns_lower:
                return device

    return None


def resolve_client_device_name(
    hass: HomeAssistant,
    coordinator: AirPortSnmpCoordinator,
    mac: str,
) -> str:
    """Resolve a human-readable device name from HA Registry, mDNS/DHCP, or Vendor."""
    formatted_mac = format_mac(mac)
    client_info = coordinator.known_clients.get(mac, {})
    mdns_or_dhcp = (
        client_info.get("mdns_name") or client_info.get("hostname") or ""
    ).strip()

    existing = _find_existing_ha_device(hass, formatted_mac, mdns_or_dhcp)
    if existing is not None:
        existing_name = existing.name_by_user or existing.name
        if existing_name:
            return existing_name

    if mdns_or_dhcp and mdns_or_dhcp.lower() not in ("unknown", "*"):
        return mdns_or_dhcp

    vendor = (client_info.get("vendor") or "").strip()
    if vendor:
        short_mac = mac[-5:]
        return f"{vendor} {short_mac}"

    return f"AirPort Client {mac}"


def build_client_device_info(
    hass: HomeAssistant,
    coordinator: AirPortSnmpCoordinator,
    mac: str,
) -> DeviceInfo:
    """Attach tracker to an existing HA device if found, or create a client device."""
    formatted_mac = format_mac(mac)
    client_info = coordinator.known_clients.get(mac, {})
    mdns_or_dhcp = (
        client_info.get("mdns_name") or client_info.get("hostname") or ""
    ).strip()
    vendor = client_info.get("vendor")

    # Merge directly into an existing HA device (ESPHome, OpenBeken, Tapo, etc.)
    existing = _find_existing_ha_device(hass, formatted_mac, mdns_or_dhcp)
    if existing is not None:
        return DeviceInfo(
            identifiers=existing.identifiers,
            connections={(CONNECTION_NETWORK_MAC, formatted_mac)},
        )

    resolved_name = resolve_client_device_name(hass, coordinator, mac)
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
