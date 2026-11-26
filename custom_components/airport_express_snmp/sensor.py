"""Sensor platform for AirPort Express SNMP."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_INCLUDE_CLIENT_DIAGNOSTICS,
    CONF_INCLUDE_RATES,
    CONF_INCLUDE_SYSTEM,
    CONF_INCLUDE_TRAFFIC_TOTALS,
    CONF_INTERFACE_SCOPE,
    CORE_INTERFACES,
    DEFAULT_INCLUDE_CLIENT_DIAGNOSTICS,
    DEFAULT_INCLUDE_RATES,
    DEFAULT_INCLUDE_SYSTEM,
    DEFAULT_INCLUDE_TRAFFIC_TOTALS,
    DEFAULT_INTERFACE_SCOPE,
    DOMAIN,
    INTERFACE_LABELS,
    SCOPE_CORE,
)
from .coordinator import AirPortSnmpCoordinator
from .helpers import build_client_device_info


def _ap_device_info(coordinator: AirPortSnmpCoordinator) -> dict[str, Any]:
    data = coordinator.data
    return {
        "identifiers": {(DOMAIN, coordinator.host)},
        "name": data.get("name", "AirPort Express"),
        "manufacturer": "Apple",
        "model": f"AirPort Express A1392 (ID {data.get('model_id', '1771')})",
        "sw_version": data.get("firmware", "7.8.1"),
        "configuration_url": f"http://{coordinator.host}",
    }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AirPort Express SNMP sensors based on user selections."""
    coordinator: AirPortSnmpCoordinator = hass.data[DOMAIN][entry.entry_id]
    opts = {**entry.data, **entry.options}

    include_system = opts.get(CONF_INCLUDE_SYSTEM, DEFAULT_INCLUDE_SYSTEM)
    include_rates = opts.get(CONF_INCLUDE_RATES, DEFAULT_INCLUDE_RATES)
    include_totals = opts.get(
        CONF_INCLUDE_TRAFFIC_TOTALS, DEFAULT_INCLUDE_TRAFFIC_TOTALS
    )
    interface_scope = opts.get(CONF_INTERFACE_SCOPE, DEFAULT_INTERFACE_SCOPE)
    include_client_diag = opts.get(
        CONF_INCLUDE_CLIENT_DIAGNOSTICS, DEFAULT_INCLUDE_CLIENT_DIAGNOSTICS
    )

    entities: list[SensorEntity] = []

    if include_system:
        entities.extend(
            [
                AirPortUptimeSensor(coordinator),
                AirPortClientsSensor(coordinator),
                AirPortDhcpSensor(coordinator),
            ]
        )

    for if_name in coordinator.data.get("interfaces", {}):
        if if_name not in INTERFACE_LABELS:
            continue
        if interface_scope == SCOPE_CORE and if_name not in CORE_INTERFACES:
            continue

        if include_rates:
            entities.extend(
                [
                    AirPortInterfaceSensor(
                        coordinator,
                        if_name,
                        "rx_mbps",
                        "Download Rate",
                        UnitOfDataRate.MEGABITS_PER_SECOND,
                        SensorDeviceClass.DATA_RATE,
                        SensorStateClass.MEASUREMENT,
                    ),
                    AirPortInterfaceSensor(
                        coordinator,
                        if_name,
                        "tx_mbps",
                        "Upload Rate",
                        UnitOfDataRate.MEGABITS_PER_SECOND,
                        SensorDeviceClass.DATA_RATE,
                        SensorStateClass.MEASUREMENT,
                    ),
                ]
            )

        if include_totals:
            entities.extend(
                [
                    AirPortInterfaceSensor(
                        coordinator,
                        if_name,
                        "in_bytes",
                        "Incoming Traffic",
                        UnitOfInformation.BYTES,
                        SensorDeviceClass.DATA_SIZE,
                        SensorStateClass.TOTAL_INCREASING,
                    ),
                    AirPortInterfaceSensor(
                        coordinator,
                        if_name,
                        "out_bytes",
                        "Outgoing Traffic",
                        UnitOfInformation.BYTES,
                        SensorDeviceClass.DATA_SIZE,
                        SensorStateClass.TOTAL_INCREASING,
                    ),
                    AirPortInterfaceSensor(
                        coordinator,
                        if_name,
                        "status",
                        "Status",
                        None,
                        None,
                        None,
                    ),
                    AirPortInterfaceSensor(
                        coordinator,
                        if_name,
                        "in_errors",
                        "Incoming Errors",
                        "err",
                        None,
                        SensorStateClass.TOTAL_INCREASING,
                        category=EntityCategory.DIAGNOSTIC,
                        enabled_default=False,
                    ),
                    AirPortInterfaceSensor(
                        coordinator,
                        if_name,
                        "out_errors",
                        "Outgoing Errors",
                        "err",
                        None,
                        SensorStateClass.TOTAL_INCREASING,
                        category=EntityCategory.DIAGNOSTIC,
                        enabled_default=False,
                    ),
                ]
            )

    if entities:
        async_add_entities(entities)

    if include_client_diag:
        tracked_diag_macs: set[str] = set()

        @callback
        def _async_add_client_diagnostics() -> None:
            new_diag: list[SensorEntity] = []
            for mac in coordinator.data.get("active_clients", {}):
                if mac not in tracked_diag_macs:
                    tracked_diag_macs.add(mac)
                    new_diag.extend(
                        [
                            AirPortClientRssiSensor(hass, coordinator, mac),
                            AirPortClientSnrSensor(hass, coordinator, mac),
                            AirPortClientRateSensor(hass, coordinator, mac),
                            AirPortClientIpSensor(hass, coordinator, mac),
                        ]
                    )
            if new_diag:
                async_add_entities(new_diag)

        _async_add_client_diagnostics()
        entry.async_on_unload(
            coordinator.async_add_listener(_async_add_client_diagnostics)
        )


class AirPortBaseSensor(CoordinatorEntity[AirPortSnmpCoordinator], SensorEntity):
    """Base sensor attached to AirPort Express device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AirPortSnmpCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = _ap_device_info(coordinator)


class AirPortUptimeSensor(AirPortBaseSensor):
    """Uptime sensor."""

    _attr_name = "Uptime"
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

    _attr_name = "Wi-Fi Clients"
    _attr_native_unit_of_measurement = "clients"
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

    _attr_name = "DHCP Leases"
    _attr_native_unit_of_measurement = "leases"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:ip-network-outline"

    def __init__(self, coordinator: AirPortSnmpCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.host}_dhcp_leases"

    @property
    def native_value(self) -> int:
        return self.coordinator.data["dhcp_count"]


class AirPortInterfaceSensor(AirPortBaseSensor):
    """Interface traffic, speed, status, and error sensor."""

    def __init__(
        self,
        coordinator: AirPortSnmpCoordinator,
        if_name: str,
        metric_key: str,
        metric_label: str,
        unit: str | None,
        device_class: SensorDeviceClass | None,
        state_class: SensorStateClass | None,
        category: EntityCategory | None = None,
        enabled_default: bool = True,
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
        self._attr_entity_category = category
        self._attr_entity_registry_enabled_default = enabled_default

    @property
    def native_value(self) -> Any:
        iface = self.coordinator.data.get("interfaces", {}).get(self._if_name, {})
        return iface.get(self._metric_key)


class AirPortClientDiagnosticSensor(
    CoordinatorEntity[AirPortSnmpCoordinator], SensorEntity
):
    """Base diagnostic sensor attached to the client's own HA device."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: AirPortSnmpCoordinator,
        mac: str,
        metric_label: str,
    ) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self._attr_name = metric_label
        self._attr_device_info = build_client_device_info(hass, self.coordinator, self._mac)

    @property
    def available(self) -> bool:
        return super().available and (
            self._mac in self.coordinator.data.get("active_clients", {})
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Refresh dedicated client device metadata on coordinator update."""
        self._attr_device_info = build_client_device_info(
            self.hass, self.coordinator, self._mac
        )
        super()._handle_coordinator_update()


class AirPortClientRssiSensor(AirPortClientDiagnosticSensor):
    """Wi-Fi RSSI signal strength sensor for a connected client."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, hass: HomeAssistant, coordinator: AirPortSnmpCoordinator, mac: str
    ) -> None:
        super().__init__(hass, coordinator, mac, "Wi-Fi Signal (RSSI)")
        clean_mac = mac.replace(":", "").lower()
        self._attr_unique_id = f"{coordinator.host}_client_{clean_mac}_rssi"

    @property
    def native_value(self) -> int | None:
        client = self.coordinator.data.get("active_clients", {}).get(self._mac, {})
        return client.get("rssi_dbm")


class AirPortClientSnrSensor(AirPortClientDiagnosticSensor):
    """Wi-Fi Signal-to-Noise Ratio (SNR) sensor for a connected client."""

    _attr_native_unit_of_measurement = "dB"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:signal-cellular-3"

    def __init__(
        self, hass: HomeAssistant, coordinator: AirPortSnmpCoordinator, mac: str
    ) -> None:
        super().__init__(hass, coordinator, mac, "Wi-Fi SNR")
        clean_mac = mac.replace(":", "").lower()
        self._attr_unique_id = f"{coordinator.host}_client_{clean_mac}_snr"

    @property
    def native_value(self) -> int | None:
        client = self.coordinator.data.get("active_clients", {}).get(self._mac, {})
        return client.get("snr_db")


class AirPortClientRateSensor(AirPortClientDiagnosticSensor):
    """Wi-Fi negotiated link rate sensor for a connected client."""

    _attr_device_class = SensorDeviceClass.DATA_RATE
    _attr_native_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:speedometer"

    def __init__(
        self, hass: HomeAssistant, coordinator: AirPortSnmpCoordinator, mac: str
    ) -> None:
        super().__init__(hass, coordinator, mac, "Wi-Fi Link Rate")
        clean_mac = mac.replace(":", "").lower()
        self._attr_unique_id = f"{coordinator.host}_client_{clean_mac}_rate"

    @property
    def native_value(self) -> int | None:
        client = self.coordinator.data.get("active_clients", {}).get(self._mac, {})
        return client.get("rate_mbps")


class AirPortClientIpSensor(AirPortClientDiagnosticSensor):
    """DHCP IP address sensor for a connected client (disabled by default)."""

    _attr_icon = "mdi:ip-network"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self, hass: HomeAssistant, coordinator: AirPortSnmpCoordinator, mac: str
    ) -> None:
        super().__init__(hass, coordinator, mac, "IP Address")
        clean_mac = mac.replace(":", "").lower()
        self._attr_unique_id = f"{coordinator.host}_client_{clean_mac}_ip"

    @property
    def native_value(self) -> str | None:
        client = self.coordinator.known_clients.get(self._mac, {})
        return client.get("ip")
