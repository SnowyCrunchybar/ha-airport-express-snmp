"""Device naming and registry helpers for AirPort Express SNMP."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)

from .const import DOMAIN
from .coordinator import AirPortSnmpCoordinator


def _is_own_client_device(device: dr.DeviceEntry, formatted_mac: str) -> bool:
    """Return True if this device is our own AirPort client device."""
    target = (DOMAIN, f"client_{formatted_mac}")
    return any(ident[:2] == target for ident in device.identifiers)


def _find_existing_ha_device(
    hass: HomeAssistant,
    formatted_mac: str,
    mdns_name: str | None,
    ip: str | None,
) -> dr.DeviceEntry | None:
    """Find an existing HA device by MAC, OpenBeken URL/IP sensor, or mDNS name."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    mdns_lower = (mdns_name or "").strip().lower()
    expected_url = f"http://{ip}" if ip else None

    for device in dev_reg.devices.values():
        if _is_own_client_device(device, formatted_mac):
            continue

        # 1. Exact MAC match (ESPHome, Tapo, HomeKit, etc.)
        if (CONNECTION_NETWORK_MAC, formatted_mac) in device.connections:
            return device

        # 2. Match OpenBeken / web-UI devices via configuration_url (http://10.0.1.x)
        if expected_url and device.configuration_url:
            cfg_url = device.configuration_url.rstrip("/")
            if cfg_url == expected_url:
                return device

        # 3. Match OpenBeken / MQTT devices via mDNS hostname == MQTT client_id or device name
        if mdns_lower:
            for ident in device.identifiers:
                if len(ident) >= 2 and ident[0] == "mqtt" and str(ident[-1]).lower() == mdns_lower:
                    return device
            dev_name = (device.name_by_user or device.name or "").strip().lower()
            if dev_name == mdns_lower:
                return device

    # 4. Fallback: check if any existing device has an IP diagnostic sensor matching this IP
    if ip:
        for entity in ent_reg.entities.values():
            if entity.domain != "sensor" or not entity.device_id:
                continue
            if entity.platform == DOMAIN:
                continue
            if not (
                entity.entity_id.endswith("_ip")
                or entity.entity_id.endswith("_ip_address")
                or (entity.original_name or "").strip().lower() in ("ip", "ip address")
            ):
                continue
            state = hass.states.get(entity.entity_id)
            if state is not None and state.state.strip() == ip:
                matched_dev = dev_reg.async_get(entity.device_id)
                if matched_dev is not None and not any(
                    len(i) >= 2 and i[0] == DOMAIN and str(i[1]).startswith("client_")
                    for i in matched_dev.identifiers
                ):
                    return matched_dev

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
    ip = client_info.get("ip")

    existing = _find_existing_ha_device(hass, formatted_mac, mdns_or_dhcp, ip)
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
    ip = client_info.get("ip")
    vendor = client_info.get("vendor")

    # Merge directly into an existing HA device (ESPHome, OpenBeken, Tapo, etc.)
    existing = _find_existing_ha_device(hass, formatted_mac, mdns_or_dhcp, ip)
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
