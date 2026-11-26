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

_GENERIC_NAMES = {"wlan0", "lwip0", "tuya", "unknown", "*"}


def _is_own_client_device(device: dr.DeviceEntry, formatted_mac: str) -> bool:
    """Return True if this device is a legacy standalone AirPort client device."""
    target = (DOMAIN, f"client_{formatted_mac}")
    return any(len(ident) >= 2 and tuple(ident[:2]) == target for ident in device.identifiers)


def _clean_device_name(name: str | None) -> str | None:
    """Return a usable device name or None if empty or generic."""
    cleaned = (name or "").strip()
    if cleaned.endswith(" (AirPort)"):
        cleaned = cleaned[:-10].strip()
    if not cleaned or cleaned.lower() in _GENERIC_NAMES:
        return None
    return cleaned


def _iter_all_devices(hass: HomeAssistant, dev_reg: dr.DeviceRegistry) -> list[dr.DeviceEntry]:
    """Iterate all registered devices using config entries + entity links (no deprecated API)."""
    seen: dict[str, dr.DeviceEntry] = {}
    for entry in hass.config_entries.async_entries():
        for dev in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
            seen[dev.id] = dev
    ent_reg = er.async_get(hass)
    for entity in ent_reg.entities.values():
        if entity.device_id and entity.device_id not in seen:
            dev = dev_reg.async_get(entity.device_id)
            if dev is not None:
                seen[dev.id] = dev
    return list(seen.values())


def _find_entry_device_by_identifier(
    dev_reg: dr.DeviceRegistry,
    config_entry_id: str,
    identifier: tuple[str, str],
) -> dr.DeviceEntry | None:
    """Find a DeviceEntry for a config entry matching (domain, id) identifier."""
    for dev in dr.async_entries_for_config_entry(dev_reg, config_entry_id):
        if any(len(ident) >= 2 and tuple(ident[:2]) == identifier for ident in dev.identifiers):
            return dev
    return None


def _find_localtuya_device(
    hass: HomeAssistant,
    dev_reg: dr.DeviceRegistry,
    ip: str | None,
) -> dr.DeviceEntry | None:
    """Match a LocalTuya HA device via config entry host IP -> device_id."""
    if not ip:
        return None

    for entry in hass.config_entries.async_entries("localtuya"):
        devices = entry.data.get("devices") or entry.options.get("devices") or {}
        if isinstance(devices, dict):
            for dev_id, cfg in devices.items():
                if isinstance(cfg, dict) and str(cfg.get("host", "")).strip() == ip:
                    dev = _find_entry_device_by_identifier(
                        dev_reg, entry.entry_id, ("localtuya", str(dev_id))
                    )
                    if dev is not None:
                        return dev

        entry_host = str(
            entry.data.get("host") or entry.options.get("host") or ""
        ).strip()
        dev_id = entry.data.get("device_id") or entry.options.get("device_id")
        if entry_host == ip and dev_id:
            dev = _find_entry_device_by_identifier(
                dev_reg, entry.entry_id, ("localtuya", str(dev_id))
            )
            if dev is not None:
                return dev

    return None


def _find_tuya_local_device(
    hass: HomeAssistant,
    dev_reg: dr.DeviceRegistry,
    ip: str | None,
) -> dr.DeviceEntry | None:
    """Match a Tuya Local (tuya_local) HA device via config entry host IP -> device_id."""
    if not ip:
        return None

    for entry in hass.config_entries.async_entries("tuya_local"):
        entry_host = str(
            entry.data.get("host")
            or entry.data.get("ip_address")
            or entry.options.get("host")
            or entry.options.get("ip_address")
            or ""
        ).strip()
        if entry_host != ip:
            continue

        dev_id = (
            entry.data.get("device_id")
            or entry.options.get("device_id")
            or entry.unique_id
        )
        if dev_id:
            dev = _find_entry_device_by_identifier(
                dev_reg, entry.entry_id, ("tuya_local", str(dev_id))
            )
            if dev is not None:
                return dev

        # Fallback: single-device config entry with one device in registry
        entry_devices = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
        if len(entry_devices) == 1:
            return entry_devices[0]

    return None


def _find_existing_ha_device(
    hass: HomeAssistant,
    formatted_mac: str,
    mdns_name: str | None,
    ip: str | None,
) -> dr.DeviceEntry | None:
    """Find an existing non-AirPort HA device by MAC, URL, mDNS, LocalTuya/Tuya Local, or entity."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    mdns_lower = (mdns_name or "").strip().lower()
    mac_compact = formatted_mac.replace(":", "").lower()
    expected_url = f"http://{ip}" if ip else None

    for device in _iter_all_devices(hass, dev_reg):
        if _is_own_client_device(device, formatted_mac):
            continue
        if any(len(ident) >= 2 and ident[0] == DOMAIN for ident in device.identifiers):
            continue

        # 1. Exact MAC match (ESPHome, Tapo, HomeKit, etc.)
        if (CONNECTION_NETWORK_MAC, formatted_mac) in device.connections:
            return device

        # 2. Match OpenBeken / web-UI devices via configuration_url (http://10.0.1.x)
        if expected_url and device.configuration_url:
            if device.configuration_url.rstrip("/") == expected_url:
                return device

        # 3. Match OpenBeken / MQTT devices via mDNS hostname == MQTT client_id or device name
        if mdns_lower and mdns_lower not in _GENERIC_NAMES:
            for ident in device.identifiers:
                if (
                    len(ident) >= 2
                    and ident[0] == "mqtt"
                    and str(ident[-1]).lower() == mdns_lower
                ):
                    return device
            dev_name = (device.name_by_user or device.name or "").strip().lower()
            if dev_name == mdns_lower:
                return device

    # 4. LocalTuya and Tuya Local IP -> device_id matches
    localtuya_dev = _find_localtuya_device(hass, dev_reg, ip)
    if localtuya_dev is not None:
        return localtuya_dev

    tuya_local_dev = _find_tuya_local_device(hass, dev_reg, ip)
    if tuya_local_dev is not None:
        return tuya_local_dev

    # 5. Match MQTT / Tuya / IP sensor entities via MAC or IP
    for entity in ent_reg.entities.values():
        if not entity.device_id or entity.platform == DOMAIN:
            continue
        matched_dev = dev_reg.async_get(entity.device_id)
        if matched_dev is None or any(
            len(i) >= 2 and i[0] == DOMAIN for i in matched_dev.identifiers
        ):
            continue

        state = hass.states.get(entity.entity_id)
        attrs = state.attributes if state else {}
        attr_mac = str(attrs.get("mac") or "").replace(":", "").lower()
        attr_ip = str(attrs.get("ip") or attrs.get("ip_address") or "").strip()
        state_val = (state.state or "").strip() if state else ""

        if attr_mac and attr_mac == mac_compact:
            return matched_dev
        if ip and (attr_ip == ip or (entity.domain == "sensor" and state_val == ip)):
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
        existing_name = _clean_device_name(existing.name_by_user or existing.name)
        if existing_name:
            return existing_name

    clean_mdns = _clean_device_name(mdns_or_dhcp)
    if clean_mdns:
        return clean_mdns

    vendor = (client_info.get("vendor") or "").strip()
    if vendor:
        short_mac = mac[-5:]
        return f"{vendor} {short_mac}"

    return formatted_mac


def build_client_device_info(
    hass: HomeAssistant,
    coordinator: AirPortSnmpCoordinator,
    mac: str,
) -> DeviceInfo | None:
    """Attach tracker only to an existing HA device; do not create new client devices."""
    formatted_mac = format_mac(mac)
    client_info = coordinator.known_clients.get(mac, {})
    mdns_or_dhcp = (
        client_info.get("mdns_name") or client_info.get("hostname") or ""
    ).strip()
    ip = client_info.get("ip")

    existing = _find_existing_ha_device(hass, formatted_mac, mdns_or_dhcp, ip)
    if existing is not None and existing.identifiers:
        return DeviceInfo(
            identifiers=existing.identifiers,
            connections={(CONNECTION_NETWORK_MAC, formatted_mac)},
        )

    return None
