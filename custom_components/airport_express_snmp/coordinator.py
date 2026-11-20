"""DataUpdateCoordinator for AirPort Express SNMP."""
from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
    next_cmd,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    OID_AP_CLIENT_BASE,
    OID_AP_DHCP_BASE,
    OID_AP_FIRMWARE,
    OID_AP_MODEL_ID,
    OID_AP_NAME,
    OID_AP_NUM_CLIENTS,
    OID_AP_NUM_DHCP,
    OID_IF_DESCR,
    OID_IF_IN_ERRORS,
    OID_IF_IN_OCTETS,
    OID_IF_OPER_STATUS,
    OID_IF_OUT_ERRORS,
    OID_IF_OUT_OCTETS,
    OID_SYS_NAME,
    OID_SYS_UPTIME,
)

_LOGGER = logging.getLogger(__name__)
MAX_32BIT = 4294967296


async def _snmp_get(
    engine: SnmpEngine, host: str, community: str, oids: list[str]
) -> dict[str, Any]:
    """Perform an async SNMP GET for a list of scalar OIDs."""
    target = await UdpTransportTarget.create((host, 161), timeout=3.0, retries=1)
    var_binds = [ObjectType(ObjectIdentity(oid)) for oid in oids]
    error_indication, error_status, _, var_bind_table = await get_cmd(
        engine,
        CommunityData(community, mpModel=1),
        target,
        ContextData(),
        *var_binds,
    )
    if error_indication or error_status:
        raise UpdateFailed(
            f"SNMP GET error: {error_indication or error_status.prettyPrint()}"
        )

    results: dict[str, Any] = {}
    for oid_obj, val_obj in var_bind_table:
        results[str(oid_obj)] = val_obj
    return results


async def _snmp_walk(
    engine: SnmpEngine, host: str, community: str, base_oid: str
) -> list[tuple[str, Any]]:
    """Perform an async SNMP WALK under a base OID."""
    target = await UdpTransportTarget.create((host, 161), timeout=3.0, retries=1)
    results: list[tuple[str, Any]] = []
    current_oid = base_oid

    while True:
        error_indication, error_status, _, var_bind_table = await next_cmd(
            engine,
            CommunityData(community, mpModel=1),
            target,
            ContextData(),
            ObjectType(ObjectIdentity(current_oid)),
            lexicographicMode=False,
        )
        if error_indication or error_status or not var_bind_table:
            break

        oid_obj, val_obj = var_bind_table[0]
        oid_str = str(oid_obj)
        if not oid_str.startswith(base_oid + "."):
            break
        results.append((oid_str, val_obj))
        current_oid = oid_str

    return results


async def async_test_snmp_connection(
    hass: HomeAssistant, host: str, community: str
) -> str | None:
    """Test SNMP connectivity and return AirPort name."""
    engine = SnmpEngine()
    try:
        res = await _snmp_get(engine, host, community, [OID_AP_NAME, OID_SYS_NAME])
        name = str(res.get(OID_AP_NAME) or res.get(OID_SYS_NAME) or "").strip()
        return name if name else f"AirPort Express ({host})"
    except Exception as err:
        _LOGGER.debug("SNMP connection test failed for %s: %s", host, err)
        return None


class AirPortSnmpCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to poll AirPort Express via SNMP."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        community: str,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{host}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.host = host
        self.community = community
        self._engine = SnmpEngine()
        self._prev_counters: dict[str, tuple[float, int, int]] = {}
        self.known_clients: dict[str, dict[str, Any]] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all scalar and table data from AirPort Express."""
        now = time.monotonic()

        scalars = await _snmp_get(
            self._engine,
            self.host,
            self.community,
            [
                OID_AP_NAME,
                OID_AP_MODEL_ID,
                OID_AP_FIRMWARE,
                OID_SYS_UPTIME,
                OID_AP_NUM_CLIENTS,
                OID_AP_NUM_DHCP,
            ],
        )

        # Walk interfaces
        if_names = await _snmp_walk(self._engine, self.host, self.community, OID_IF_DESCR)
        if_status = dict(
            await _snmp_walk(self._engine, self.host, self.community, OID_IF_OPER_STATUS)
        )
        if_in = dict(
            await _snmp_walk(self._engine, self.host, self.community, OID_IF_IN_OCTETS)
        )
        if_out = dict(
            await _snmp_walk(self._engine, self.host, self.community, OID_IF_OUT_OCTETS)
        )
        if_in_err = dict(
            await _snmp_walk(self._engine, self.host, self.community, OID_IF_IN_ERRORS)
        )
        if_out_err = dict(
            await _snmp_walk(self._engine, self.host, self.community, OID_IF_OUT_ERRORS)
        )

        interfaces: dict[str, dict[str, Any]] = {}
        for oid_str, name_val in if_names:
            idx = oid_str.split(".")[-1]
            if_name = str(name_val).strip()
            if if_name == "lo0":
                continue

            in_bytes = int(if_in.get(f"{OID_IF_IN_OCTETS}.{idx}", 0))
            out_bytes = int(if_out.get(f"{OID_IF_OUT_OCTETS}.{idx}", 0))
            in_errors = int(if_in_err.get(f"{OID_IF_IN_ERRORS}.{idx}", 0))
            out_errors = int(if_out_err.get(f"{OID_IF_OUT_ERRORS}.{idx}", 0))
            oper = int(if_status.get(f"{OID_IF_OPER_STATUS}.{idx}", 2))

            rx_mbps = 0.0
            tx_mbps = 0.0
            if if_name in self._prev_counters:
                prev_time, prev_in, prev_out = self._prev_counters[if_name]
                dt = now - prev_time
                if dt > 0:
                    d_in = (
                        in_bytes - prev_in
                        if in_bytes >= prev_in
                        else (MAX_32BIT - prev_in + in_bytes)
                    )
                    d_out = (
                        out_bytes - prev_out
                        if out_bytes >= prev_out
                        else (MAX_32BIT - prev_out + out_bytes)
                    )
                    rx_mbps = round((d_in * 8) / (dt * 1_000_000), 3)
                    tx_mbps = round((d_out * 8) / (dt * 1_000_000), 3)

            self._prev_counters[if_name] = (now, in_bytes, out_bytes)

            interfaces[if_name] = {
                "index": idx,
                "name": if_name,
                "status": "Yhdistetty" if oper == 1 else "Katkaistu",
                "in_bytes": in_bytes,
                "out_bytes": out_bytes,
                "rx_mbps": rx_mbps,
                "tx_mbps": tx_mbps,
                "in_errors": in_errors,
                "out_errors": out_errors,
            }

        # Walk DHCP table (MAC -> IP & Lease)
        dhcp_rows = await _snmp_walk(
            self._engine, self.host, self.community, OID_AP_DHCP_BASE
        )
        dhcp_map: dict[str, dict[str, Any]] = {}
        for oid_str, val in dhcp_rows:
            parts = oid_str.removeprefix(f"{OID_AP_DHCP_BASE}.").split(".")
            col = parts[0]
            key = ".".join(parts[1:])
            entry = dhcp_map.setdefault(key, {})
            if col == "1":
                entry["mac"] = str(val).upper()
            elif col == "2":
                entry["ip"] = val.prettyPrint()
            elif col == "4":
                entry["lease_remaining"] = int(val)

        mac_to_dhcp = {v["mac"]: v for v in dhcp_map.values() if "mac" in v}

        # Walk active Wi-Fi clients
        client_rows = await _snmp_walk(
            self._engine, self.host, self.community, OID_AP_CLIENT_BASE
        )
        raw_clients: dict[str, dict[str, Any]] = {}
        for oid_str, val in client_rows:
            parts = oid_str.removeprefix(f"{OID_AP_CLIENT_BASE}.").split(".")
            col = parts[0]
            key = ".".join(parts[1:])
            entry = raw_clients.setdefault(key, {})
            if col == "1":
                entry["mac"] = str(val).upper()
            elif col == "3":
                entry["rates"] = str(val).strip()
            elif col == "4":
                entry["connected_seconds"] = int(val)
            elif col == "6":
                entry["rssi_dbm"] = int(val)
            elif col == "7":
                entry["noise_dbm"] = int(val)
            elif col == "8":
                entry["rate_mbps"] = int(val)

        active_clients: dict[str, dict[str, Any]] = {}
        for item in raw_clients.values():
            mac = item.get("mac")
            if not mac:
                continue
            dhcp_info = mac_to_dhcp.get(mac, {})
            rssi = item.get("rssi_dbm")
            noise = item.get("noise_dbm")
            snr = (rssi - noise) if (rssi is not None and noise is not None) else None
            client_data = {
                "mac": mac,
                "ip": dhcp_info.get("ip"),
                "rssi_dbm": rssi,
                "noise_dbm": noise,
                "snr_db": snr,
                "rate_mbps": item.get("rate_mbps"),
                "connected_seconds": item.get("connected_seconds"),
                "lease_remaining": dhcp_info.get("lease_remaining"),
                "connected": True,
            }
            active_clients[mac] = client_data
            self.known_clients[mac] = client_data

        # Mark disconnected known clients as not connected
        for mac, cached in self.known_clients.items():
            if mac not in active_clients:
                cached["connected"] = False

        uptime_ticks = int(scalars.get(OID_SYS_UPTIME, 0))
        return {
            "name": str(scalars.get(OID_AP_NAME, "AirPort Express")).strip(),
            "model_id": str(scalars.get(OID_AP_MODEL_ID, "1771")).strip(),
            "firmware": str(scalars.get(OID_AP_FIRMWARE, "7.8.1")).strip(),
            "uptime_seconds": int(uptime_ticks / 100),
            "client_count": int(scalars.get(OID_AP_NUM_CLIENTS, len(active_clients))),
            "dhcp_count": int(scalars.get(OID_AP_NUM_DHCP, len(mac_to_dhcp))),
            "interfaces": interfaces,
            "active_clients": active_clients,
        }
