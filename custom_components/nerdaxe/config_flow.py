"""Config flow for the NerdAxe/NerdQAxe/NerdOCTAXE integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_HOST, DOMAIN
from .coordinator import async_validate_host

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})


class NerdAxeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow — just asks for the device's IP/hostname."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            try:
                info = await async_validate_host(self.hass, host)
            except ConfigEntryNotReady:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 — surface anything unexpected as a form error
                _LOGGER.exception("Unexpected error validating %s", host)
                errors["base"] = "unknown"
            else:
                device_model = info.get("deviceModel", "NerdAxe")
                return self.async_create_entry(title=f"{device_model} ({host})", data={CONF_HOST: host})

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
