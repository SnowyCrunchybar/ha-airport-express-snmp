"""Two-step Config Flow and Options Flow for AirPort Express SNMP."""
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_COMMUNITY,
    CONF_INCLUDE_CLIENT_DIAGNOSTICS,
    CONF_INCLUDE_RATES,
    CONF_INCLUDE_SYSTEM,
    CONF_INCLUDE_TRAFFIC_TOTALS,
    CONF_INTERFACE_SCOPE,
    CONF_SCAN_INTERVAL,
    CONF_TRACK_CLIENTS,
    DEFAULT_INCLUDE_CLIENT_DIAGNOSTICS,
    DEFAULT_INCLUDE_RATES,
    DEFAULT_INCLUDE_SYSTEM,
    DEFAULT_INCLUDE_TRAFFIC_TOTALS,
    DEFAULT_INTERFACE_SCOPE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TRACK_CLIENTS,
    DOMAIN,
    SCOPE_ALL,
    SCOPE_CORE,
)
from .coordinator import async_test_snmp_connection


def _sensor_options_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build schema for sensor & tracking selection."""
    return vol.Schema(
        {
            vol.Required(
                CONF_INTERFACE_SCOPE,
                default=defaults.get(CONF_INTERFACE_SCOPE, DEFAULT_INTERFACE_SCOPE),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[SCOPE_CORE, SCOPE_ALL],
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="interface_scope",
                )
            ),
            vol.Required(
                CONF_INCLUDE_SYSTEM,
                default=defaults.get(CONF_INCLUDE_SYSTEM, DEFAULT_INCLUDE_SYSTEM),
            ): bool,
            vol.Required(
                CONF_INCLUDE_RATES,
                default=defaults.get(CONF_INCLUDE_RATES, DEFAULT_INCLUDE_RATES),
            ): bool,
            vol.Required(
                CONF_INCLUDE_TRAFFIC_TOTALS,
                default=defaults.get(
                    CONF_INCLUDE_TRAFFIC_TOTALS, DEFAULT_INCLUDE_TRAFFIC_TOTALS
                ),
            ): bool,
            vol.Required(
                CONF_TRACK_CLIENTS,
                default=defaults.get(CONF_TRACK_CLIENTS, DEFAULT_TRACK_CLIENTS),
            ): bool,
            vol.Required(
                CONF_INCLUDE_CLIENT_DIAGNOSTICS,
                default=defaults.get(
                    CONF_INCLUDE_CLIENT_DIAGNOSTICS,
                    DEFAULT_INCLUDE_CLIENT_DIAGNOSTICS,
                ),
            ): bool,
        }
    )


class AirPortExpressSnmpConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a two-step config flow for AirPort Express SNMP."""

    VERSION = 1

    def __init__(self) -> None:
        self._connection_data: dict[str, Any] = {}
        self._ap_name: str = "AirPort Express"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            community = user_input[CONF_COMMUNITY].strip()

            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            ap_name = await async_test_snmp_connection(self.hass, host, community)
            if ap_name:
                self._ap_name = ap_name
                self._connection_data = {
                    CONF_HOST: host,
                    CONF_COMMUNITY: community,
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                }
                return await self.async_step_sensors()

            errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_COMMUNITY): str,
                vol.Required(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Choose sensors and client tracking."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._ap_name,
                data={**self._connection_data, **user_input},
            )

        return self.async_show_form(
            step_id="sensors",
            data_schema=_sensor_options_schema({}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> AirPortExpressOptionsFlow:
        """Get the options flow for this handler."""
        return AirPortExpressOptionsFlow()


class AirPortExpressOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        base_schema = vol.Schema(
            {
                vol.Required(
                    CONF_COMMUNITY,
                    default=current.get(CONF_COMMUNITY, ""),
                ): str,
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
            }
        )
        full_schema = base_schema.extend(_sensor_options_schema(current).schema)
        return self.async_show_form(step_id="init", data_schema=full_schema)
