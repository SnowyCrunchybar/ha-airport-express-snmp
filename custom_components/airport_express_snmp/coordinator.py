"""Pure-Python async SNMPv2c DataUpdateCoordinator for AirPort Express."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import random
import socket
import time
from typing import Any

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


def _ber_len(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    raw = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def _ber_tlv(tag: int, payload: bytes) -> bytes:
    return bytes([tag]) + _ber_len(len(payload)) + payload


def _ber_int(value: int) -> bytes:
    if value == 0:
        return _ber_tlv(0x02, bytes([0]))
    length = (value.bit_length() + 8) // 8
    return _ber_tlv(0x02, value.to_bytes(length, "big", signed=True))


def _ber_oid(oid_str: str) -> bytes:
    parts = [int(p) for p in oid_str.strip(".").split(".")]
    encoded = bytearray([40 * parts[0] + parts[1]])
    for part in parts[2:]:
        if part == 0:
            encoded.append(0)
        else:
            chunks = []
            while part > 0:
                chunks.append(part & 0x7F)
                part >>= 7
            chunks.reverse()
            for i, c in enumerate(chunks):
                encoded.append(c | (0x80 if i < len(chunks) - 1 else 0))
    return _ber_tlv(0x06, bytes(encoded))


def _build_snmpv2_packet(
    community: str, pdu_tag: int, req_id: int, oids: list[str]
) -> bytes:
    null_tlv = bytes([5, 0])
    varbinds = b"".join(
        _ber_tlv(0x30, _ber_oid(oid) + null_tlv) for oid in oids
    )
    pdu = _ber_tlv(
        pdu_tag,
        _ber_int(req_id) + _ber_int(0) + _ber_int(0) + _ber_tlv(0x30, varbinds),
    )
    msg = _ber_int(1) + _ber_tlv(0x04, community.encode("utf-8")) + pdu
    return _ber_tlv(0x30, msg)


def _read_len(buf: bytes, idx: int) -> tuple[int, int]:
    first = buf[idx]
    idx += 1
    if first < 0x80:
        return first, idx
    n_bytes = first & 0x7F
    val = int.from_bytes(buf[idx : idx + n_bytes], "big")
    return val, idx + n_bytes


def _decode_oid(raw: bytes) -> str:
    if not raw:
        return ""
    first = raw[0]
    parts = [first // 40, first % 40]
    val = 0
    for b in raw[1:]:
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            parts.append(val)
            val = 0
    return ".".join(str(p) for p in parts)


def _decode_value(tag: int, raw: bytes) -> Any:
    if tag == 0x02:
        return int.from_bytes(raw, "big", signed=True)
    if tag in (0x41, 0x42, 0x43, 0x46):
        return int.from_bytes(raw, "big", signed=False)
    if tag == 0x04:
        try:
            text = raw.decode("utf-8")
            if all(32 <= ord(ch) <= 126 or ch in "\r\n\t" for ch in text):
                return text
        except UnicodeDecodeError:
            pass
        if len(raw) == 6:
            return ":".join(f"{b:02X}" for b in raw)
        return raw.hex(":")
    if tag == 0x40:
        return ".".join(str(b) for b in raw)
    if tag == 0x06:
        return _decode_oid(raw)
    if tag in (0x05, 0x80, 0x81, 0x82):
        return None
    return raw


def _parse_snmp_response(pkt: bytes) -> tuple[int, int, list[tuple[str, Any]]]:
    idx = 0
    assert pkt[idx] == 0x30
    _, idx = _read_len(pkt, idx + 1)

    assert pkt[idx] == 0x02
    vlen, idx = _read_len(pkt, idx + 1)
    idx += vlen

    assert pkt[idx] == 0x04
    clen, idx = _read_len(pkt, idx + 1)
    idx += clen

    assert pkt[idx] == 0xA2
    _, idx = _read_len(pkt, idx + 1)

    assert pkt[idx] == 0x02
    rlen, idx = _read_len(pkt, idx + 1)
    req_id = int.from_bytes(pkt[idx : idx + rlen], "big", signed=True)
    idx += rlen

    assert pkt[idx] == 0x02
    elen, idx = _read_len(pkt, idx + 1)
    err_status = int.from_bytes(pkt[idx : idx + elen], "big", signed=True)
    idx += elen

    assert pkt[idx] == 0x02
    eilen, idx = _read_len(pkt, idx + 1)
    idx += eilen

    assert pkt[idx] == 0x30
    vbl_len, idx = _read_len(pkt, idx + 1)
    end_idx = idx + vbl_len

    results: list[tuple[str, Any]] = []
    while idx < end_idx:
        assert pkt[idx] == 0x30
        vb_len, idx = _read_len(pkt, idx + 1)
        vb_end = idx + vb_len

        assert pkt[idx] == 0x06
        oid_len, idx = _read_len(pkt, idx + 1)
        oid_str = _decode_oid(pkt[idx : idx + oid_len])
        idx += oid_len

        val_tag = pkt[idx]
        val_len, idx = _read_len(pkt, idx + 1)
        val_raw = pkt[idx : idx + val_len]
        idx = vb_end

        if val_tag in (0x80, 0x81, 0x82):
            results.append((oid_str, "__END_OF_MIB__"))
        else:
            results.append((oid_str, _decode_value(val_tag, val_raw)))

    return req_id, err_status, results


class _SnmpUdpProtocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport | None = None
        self.pending: dict[int, asyncio.Future[bytes]] = {}

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            req_id, _, _ = _parse_snmp_response(data)
            fut = self.pending.pop(req_id, None)
            if fut and not fut.done():
                fut.set_result(data)
        except Exception:
            pass


async def _snmp_exchange(
    host: str, community: str, pdu_tag: int, oids: list[str], timeout: float = 2.5
) -> list[tuple[str, Any]]:
    loop = asyncio.get_running_loop()
    protocol = _SnmpUdpProtocol()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: protocol,
        family=socket.AF_INET,
    )
    try:
        for attempt in range(2):
            req_id = random.randint(1, 0x7FFFFFFF)
            pkt = _build_snmpv2_packet(community, pdu_tag, req_id, oids)
            fut: asyncio.Future[bytes] = loop.create_future()
            protocol.pending[req_id] = fut
            transport.sendto(pkt, (host, 161))
            try:
                resp = await asyncio.wait_for(fut, timeout=timeout)
                _, err_status, results = _parse_snmp_response(resp)
                if err_status != 0:
                    raise UpdateFailed(f"SNMP error status: {err_status}")
                return results
            except asyncio.TimeoutError:
                protocol.pending.pop(req_id, None)
                if attempt == 1:
                    raise UpdateFailed(f"SNMP timeout contacting {host}:161")
    finally:
        transport.close()
    return []


async def _snmp_get(host: str, community: str, oids: list[str]) -> dict[str, Any]:
    rows = await _snmp_exchange(host, community, 0xA0, oids)
    return {oid: val for oid, val in rows if val != "__END_OF_MIB__"}


async def _snmp_walk(
    host: str, community: str, base_oid: str
) -> list[tuple[str, Any]]:
    results: list[tuple[str, Any]] = []
    current_oid = base_oid
    prefix = base_oid + "."

    for _ in range(512):
        rows = await _snmp_exchange(host, community, 0xA1, [current_oid])
        if not rows:
            break
        oid_str, val = rows[0]
        if val == "__END_OF_MIB__" or not oid_str.startswith(prefix):
            break
        if oid_str == current_oid:
            break
        results.append((oid_str, val))
        current_oid = oid_str

    return results


async def async_test_snmp_connection(
    hass: HomeAssistant, host: str, community: str
) -> str | None:
    """Test SNMP connectivity and return AirPort name."""
    try:
        res = await _snmp_get(host, community, [OID_AP_NAME, OID_SYS_NAME])
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
        self._prev_counters: dict[str, tuple[float, int, int]] = {}
        self.known_clients: dict[str, dict[str, Any]] = {}
        self._vendor_cache: dict[str, str | None] = {}
        self._mdns_cache: dict[str, tuple[float, str | None]] = {}
        self._mac_lookup: Any = None
        self._mac_lookup_initialized = False

    async def _async_lookup_vendor(self, mac: str) -> str | None:
        """Resolve hardware vendor from MAC OUI locally."""
        prefix = mac.upper()[:8]
        if prefix in self._vendor_cache:
            return self._vendor_cache[prefix]

        if not self._mac_lookup_initialized:
            self._mac_lookup_initialized = True
            try:
                from mac_vendor_lookup import AsyncMacLookup

                lookup = AsyncMacLookup()
                try:
                    await lookup.load_vendors()
                except Exception:
                    pass
                self._mac_lookup = lookup
            except Exception as err:
                _LOGGER.debug("mac_vendor_lookup unavailable: %s", err)

        vendor: str | None = None
        if self._mac_lookup is not None:
            try:
                vendor = await self._mac_lookup.lookup(mac)
            except Exception:
                vendor = None

        self._vendor_cache[prefix] = vendor
        return vendor

    async def _async_resolve_mdns(self, ip: str | None) -> str | None:
        """Resolve mDNS / reverse DNS hostname for an IPv4 address with caching."""
        if not ip:
            return None

        now = time.monotonic()
        cached = self._mdns_cache.get(ip)
        if cached is not None:
            ts, cached_name = cached
            ttl = 600.0 if cached_name else 120.0
            if (now - ts) < ttl:
                return cached_name

        resolved: str | None = None
        try:
            host_info = await asyncio.wait_for(
                self.hass.async_add_executor_job(socket.gethostbyaddr, ip),
                timeout=0.8,
            )
            raw_name = (host_info[0] or "").strip().rstrip(".")
            if raw_name and raw_name != ip:
                if raw_name.endswith(".local"):
                    raw_name = raw_name[:-6]
                resolved = raw_name
        except Exception:
            resolved = None

        self._mdns_cache[ip] = (now, resolved)
        return resolved

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all scalar and table data from AirPort Express."""
        now = time.monotonic()

        scalars = await _snmp_get(
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

        if_names = await _snmp_walk(self.host, self.community, OID_IF_DESCR)
        if_status = dict(
            await _snmp_walk(self.host, self.community, OID_IF_OPER_STATUS)
        )
        if_in = dict(
            await _snmp_walk(self.host, self.community, OID_IF_IN_OCTETS)
        )
        if_out = dict(
            await _snmp_walk(self.host, self.community, OID_IF_OUT_OCTETS)
        )
        if_in_err = dict(
            await _snmp_walk(self.host, self.community, OID_IF_IN_ERRORS)
        )
        if_out_err = dict(
            await _snmp_walk(self.host, self.community, OID_IF_OUT_ERRORS)
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
                "status": "Connected" if oper == 1 else "Disconnected",
                "in_bytes": in_bytes,
                "out_bytes": out_bytes,
                "rx_mbps": rx_mbps,
                "tx_mbps": tx_mbps,
                "in_errors": in_errors,
                "out_errors": out_errors,
            }

        # Walk DHCP table (MAC -> IP, Hostname/Client-ID & Lease)
        dhcp_rows = await _snmp_walk(self.host, self.community, OID_AP_DHCP_BASE)
        dhcp_map: dict[str, dict[str, Any]] = {}
        for oid_str, val in dhcp_rows:
            parts = oid_str.removeprefix(f"{OID_AP_DHCP_BASE}.").split(".")
            col = parts[0]
            key = ".".join(parts[1:])
            entry = dhcp_map.setdefault(key, {})
            if col == "1":
                entry["mac"] = str(val).upper()
            elif col == "2":
                entry["ip"] = str(val)
            elif col == "3" and isinstance(val, str):
                entry["hostname"] = val.strip()
            elif col == "4":
                entry["lease_remaining"] = int(val)

        mac_to_dhcp = {v["mac"]: v for v in dhcp_map.values() if "mac" in v}

        # Walk active Wi-Fi clients
        client_rows = await _snmp_walk(
            self.host, self.community, OID_AP_CLIENT_BASE
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
            ip = dhcp_info.get("ip")
            vendor = await self._async_lookup_vendor(mac)
            mdns_name = await self._async_resolve_mdns(ip)
            hostname = dhcp_info.get("hostname") or mdns_name

            rssi = item.get("rssi_dbm")
            noise = item.get("noise_dbm")
            snr = (rssi - noise) if (rssi is not None and noise is not None) else None
            client_data = {
                "mac": mac,
                "ip": ip,
                "hostname": hostname,
                "mdns_name": mdns_name,
                "vendor": vendor,
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
