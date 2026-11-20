"""Config flow for AirPort Express SNMP."""
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_COMMUNITY,
    CONF_SCAN_INTERVAL,
    CONF_TRACK_CLIENTS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TRACK_CLIENTS,
    DOMAIN,
)
from .coordinator import async_test_snmp_connection


class AirPortExpressSnmpConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AirPort Express SNMP."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            community = user_input[CONF_COMMUNITY].strip()

            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            ap_name = await async_test_snmp_connection(self.hass, host, community)
            if ap_name:
                return self.async_create_entry(
                    title=ap_name,
                    data={
                        CONF_HOST: host,
                        CONF_COMMUNITY: community,
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                        CONF_TRACK_CLIENTS: user_input[CONF_TRACK_CLIENTS],
                    },
                )
            errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_COMMUNITY): str,
                vol.Required(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                vol.Required(
                    CONF_TRACK_CLIENTS, default=DEFAULT_TRACK_CLIENTS
                ): bool,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

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
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_COMMUNITY,
                    default=current.get(CONF_COMMUNITY, ""),
                ): str,
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                vol.Required(
                    CONF_TRACK_CLIENTS,
                    default=current.get(CONF_TRACK_CLIENTS, DEFAULT_TRACK_CLIENTS),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
