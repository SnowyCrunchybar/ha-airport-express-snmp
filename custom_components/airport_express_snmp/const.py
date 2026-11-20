"""Constants for the AirPort Express SNMP integration."""

DOMAIN = "airport_express_snmp"

CONF_COMMUNITY = "community"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_TRACK_CLIENTS = "track_clients"

DEFAULT_HOST = "10.0.1.1"
DEFAULT_COMMUNITY = "Helmi"
DEFAULT_SCAN_INTERVAL = 15
DEFAULT_TRACK_CLIENTS = True

# Standard MIB-2 OIDs
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"

# Interface Table base OIDs
OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"
OID_IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"
OID_IF_IN_ERRORS = "1.3.6.1.2.1.2.2.1.14"
OID_IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"
OID_IF_OUT_ERRORS = "1.3.6.1.2.1.2.2.1.20"

# Apple AirPort Enterprise MIB (1.3.6.1.4.1.63.501.3)
OID_AP_NAME = "1.3.6.1.4.1.63.501.3.1.1.0"
OID_AP_MODEL_ID = "1.3.6.1.4.1.63.501.3.1.4.0"
OID_AP_FIRMWARE = "1.3.6.1.4.1.63.501.3.1.5.0"

OID_AP_NUM_CLIENTS = "1.3.6.1.4.1.63.501.3.2.1.0"
OID_AP_CLIENT_BASE = "1.3.6.1.4.1.63.501.3.2.2.1"

OID_AP_NUM_DHCP = "1.3.6.1.4.1.63.501.3.3.1.0"
OID_AP_DHCP_BASE = "1.3.6.1.4.1.63.501.3.3.2.1"

# Friendly names for AirPort Express interfaces
INTERFACE_LABELS = {
    "eth0": "WAN (eth0)",
    "eth1": "LAN (eth1)",
    "wlan0": "Wi-Fi 2.4 GHz (wlan0)",
    "wlan1": "Wi-Fi 5 GHz (wlan1)",
    "bridge0": "Silta (bridge0)",
}
