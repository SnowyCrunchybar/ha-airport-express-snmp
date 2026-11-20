"""Sensor platform for AirPort Express SNMP."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfDataRate, UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, INTERFACE_LABELS
from .coordinator import AirPortSnmpCoordinator


def _device_info(coordinator: AirPortSnmpCoordinator) -> DeviceInfo:
    data = coordinator.data
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.host)},
        name=data.get("name", "AirPort Express"),
        manufacturer="Apple",
        model=f"AirPort Express A1392 (ID {data.get('model_id', '1771')})",
        sw_version=data.get("firmware", "7.8.1"),
        configuration_url=f"http://{coordinator.host}",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AirPort Express SNMP sensors."""
    coordinator: AirPortSnmpCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        AirPortUptimeSensor(coordinator),
        AirPortClientsSensor(coordinator),
        AirPortDhcpSensor(coordinator),
    ]

    for if_name in coordinator.data.get("interfaces", {}):
        if if_name not in INTERFACE_LABELS:
            continue
        entities.extend(
            [
                AirPortInterfaceSensor(
                    coordinator,
                    if_name,
                    "rx_mbps",
                    "Latausnopeus",
                    UnitOfDataRate.MEGABITS_PER_SECOND,
                    SensorDeviceClass.DATA_RATE,
                    SensorStateClass.MEASUREMENT,
                ),
                AirPortInterfaceSensor(
                    coordinator,
                    if_name,
                    "tx_mbps",
                    "Lähetysnopeus",
                    UnitOfDataRate.MEGABITS_PER_SECOND,
                    SensorDeviceClass.DATA_RATE,
                    SensorStateClass.MEASUREMENT,
                ),
                AirPortInterfaceSensor(
                    coordinator,
                    if_name,
                    "in_bytes",
                    "Sisääntuleva liikenne",
                    UnitOfInformation.BYTES,
                    SensorDeviceClass.DATA_SIZE,
                    SensorStateClass.TOTAL_INCREASING,
                ),
                AirPortInterfaceSensor(
                    coordinator,
                    if_name,
                    "out_bytes",
                    "Lähtevä liikenne",
                    UnitOfInformation.BYTES,
                    SensorDeviceClass.DATA_SIZE,
                    SensorStateClass.TOTAL_INCREASING,
                ),
                AirPortInterfaceSensor(
                    coordinator,
                    if_name,
                    "status",
                    "Tila",
                    None,
                    None,
                    None,
                ),
            ]
        )

    async_add_entities(entities)


class AirPortBaseSensor(CoordinatorEntity[AirPortSnmpCoordinator], SensorEntity):
    """Base sensor class."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AirPortSnmpCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = _device_info(coordinator)


class AirPortUptimeSensor(AirPortBaseSensor):
    """Uptime sensor."""

    _attr_name = "Käyttöaika"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: AirPortSnmpCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.host}_uptime"

    @property
    def native_value(self) -> int:
        return self.coordinator.data["uptime_seconds"]


class AirPortClientsSensor(AirPortBaseSensor):
    """Connected Wi-Fi clients count + full client table in attributes."""

    _attr_name = "Wi-Fi-asiakkaat"
    _attr_native_unit_of_measurement = "kpl"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:wifi"

    def __init__(self, coordinator: AirPortSnmpCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.host}_wifi_clients"

    @property
    def native_value(self) -> int:
        return self.coordinator.data["client_count"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        clients = list(self.coordinator.data.get("active_clients", {}).values())
        clients.sort(key=lambda c: c.get("rssi_dbm") or -999, reverse=True)
        return {"clients": clients}


class AirPortDhcpSensor(AirPortBaseSensor):
    """Active DHCP leases count."""

    _attr_name = "DHCP-vuokrat"
    _attr_native_unit_of_measurement = "kpl"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:ip-network-outline"

    def __init__(self, coordinator: AirPortSnmpCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.host}_dhcp_leases"

    @property
    def native_value(self) -> int:
        return self.coordinator.data["dhcp_count"]


class AirPortInterfaceSensor(AirPortBaseSensor):
    """Interface traffic, speed, and status sensor."""

    def __init__(
        self,
        coordinator: AirPortSnmpCoordinator,
        if_name: str,
        metric_key: str,
        metric_label: str,
        unit: str | None,
        device_class: SensorDeviceClass | None,
        state_class: SensorStateClass | None,
    ) -> None:
        super().__init__(coordinator)
        self._if_name = if_name
        self._metric_key = metric_key
        label = INTERFACE_LABELS.get(if_name, if_name)
        self._attr_name = f"{label} {metric_label}"
        self._attr_unique_id = f"{coordinator.host}_{if_name}_{metric_key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class

    @property
    def native_value(self) -> Any:
        iface = self.coordinator.data.get("interfaces", {}).get(self._if_name, {})
        return iface.get(self._metric_key)
