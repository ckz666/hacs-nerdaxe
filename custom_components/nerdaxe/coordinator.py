"""Data update coordinator for the NerdAxe/NerdQAxe/NerdOCTAXE integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_INFO_PATH,
    API_RESTART_PATH,
    API_SETTINGS_PATH,
    API_SHUTDOWN_PATH,
    ATTR_CORE_VOLTAGE,
    ATTR_FREQUENCY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    OFF_PROFILE,
    PROFILES,
    WAKE_POLL_INTERVAL_S,
    WAKE_TIMEOUT_S,
)

_LOGGER = logging.getLogger(__name__)


class NerdAxeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls /api/system/info and applies profile/setting changes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, host: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{host}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.entry = entry
        self.host = host
        self.base_url = f"http://{host}"
        self.current_profile: str | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        try:
            async with async_timeout.timeout(10):
                async with session.get(f"{self.base_url}{API_INFO_PATH}") as resp:
                    if resp.status != 200:
                        raise UpdateFailed(f"Unexpected status {resp.status} from {self.host}")
                    data: dict[str, Any] = await resp.json(content_type=None)
        except (TimeoutError, ConnectionError) as err:
            raise UpdateFailed(f"Error communicating with {self.host}: {err}") from err

        self._detect_profile(data)
        return data

    def _detect_profile(self, data: dict[str, Any]) -> None:
        """Best-effort match of current frequency/voltage against known
        profiles, so the select entity reflects reality even if settings
        were changed outside Home Assistant (e.g. the device's own web UI)."""
        if data.get("shutdown"):
            self.current_profile = OFF_PROFILE
            return
        freq = data.get(ATTR_FREQUENCY)
        volt = data.get(ATTR_CORE_VOLTAGE)
        for name, profile in PROFILES.items():
            if profile[ATTR_FREQUENCY] == freq and profile[ATTR_CORE_VOLTAGE] == volt:
                self.current_profile = name
                return
        self.current_profile = "custom"

    async def async_select_profile(self, profile_name: str) -> None:
        """Entry point for the select entity: routes to shutdown, or to a
        wake-then-configure sequence if the device is currently off, or to a
        plain live settings PATCH otherwise."""
        if profile_name == OFF_PROFILE:
            await self.async_shutdown()
            return
        if profile_name not in PROFILES:
            raise ValueError(f"Unknown profile: {profile_name}")
        if self.current_profile == OFF_PROFILE:
            await self._async_wake()
        await self.async_apply_settings(PROFILES[profile_name])

    async def async_shutdown(self) -> None:
        """POST /api/system/shutdown — disables ASICs + voltage regulators
        (~0.06W measured) but leaves WiFi/HTTP alive. Verified live against a
        NerdOCTAXE-Gamma: no API call reverses this short of a restart."""
        session = async_get_clientsession(self.hass)
        try:
            async with async_timeout.timeout(10):
                async with session.post(f"{self.base_url}{API_SHUTDOWN_PATH}") as resp:
                    if resp.status != 200:
                        raise UpdateFailed(
                            f"Shutdown POST to {self.host} failed with status {resp.status}"
                        )
        except (TimeoutError, ConnectionError) as err:
            raise UpdateFailed(f"Error shutting down {self.host}: {err}") from err
        await self.async_request_refresh()

    async def async_restart(self) -> None:
        """Fire-and-forget POST /api/system/restart for the manual restart
        button -- unlike _async_wake(), doesn't block waiting for the device
        to come back (a button press shouldn't hang the UI for ~20-30s)."""
        session = async_get_clientsession(self.hass)
        try:
            async with async_timeout.timeout(10):
                async with session.post(f"{self.base_url}{API_RESTART_PATH}") as resp:
                    if resp.status != 200:
                        raise UpdateFailed(
                            f"Restart POST to {self.host} failed with status {resp.status}"
                        )
        except (TimeoutError, ConnectionError) as err:
            raise UpdateFailed(f"Error restarting {self.host}: {err}") from err

    async def _async_wake(self) -> None:
        """POST /api/system/restart and poll until the device answers again.
        Takes ~20-30s on a NerdOCTAXE-Gamma (measured)."""
        session = async_get_clientsession(self.hass)
        try:
            async with async_timeout.timeout(10):
                async with session.post(f"{self.base_url}{API_RESTART_PATH}") as resp:
                    if resp.status != 200:
                        raise UpdateFailed(
                            f"Restart POST to {self.host} failed with status {resp.status}"
                        )
        except (TimeoutError, ConnectionError) as err:
            raise UpdateFailed(f"Error waking {self.host}: {err}") from err

        elapsed = 0.0
        while elapsed < WAKE_TIMEOUT_S:
            await asyncio.sleep(WAKE_POLL_INTERVAL_S)
            elapsed += WAKE_POLL_INTERVAL_S
            try:
                async with async_timeout.timeout(5):
                    async with session.get(f"{self.base_url}{API_INFO_PATH}") as resp:
                        if resp.status == 200:
                            return
            except (TimeoutError, ConnectionError):
                continue
        raise UpdateFailed(f"{self.host} did not come back within {WAKE_TIMEOUT_S}s of restart")

    async def async_apply_settings(self, settings: dict[str, int]) -> None:
        session = async_get_clientsession(self.hass)
        try:
            async with async_timeout.timeout(10):
                async with session.patch(
                    f"{self.base_url}{API_SETTINGS_PATH}", json=settings
                ) as resp:
                    if resp.status != 200:
                        raise UpdateFailed(
                            f"Settings PATCH to {self.host} failed with status {resp.status}"
                        )
        except (TimeoutError, ConnectionError) as err:
            raise UpdateFailed(f"Error applying settings to {self.host}: {err}") from err
        await self.async_request_refresh()


async def async_validate_host(hass: HomeAssistant, host: str) -> dict[str, Any]:
    """Used by the config flow to confirm a host is a reachable ESP-Miner-family device."""
    session = async_get_clientsession(hass)
    async with async_timeout.timeout(10):
        async with session.get(f"http://{host}{API_INFO_PATH}") as resp:
            if resp.status != 200:
                raise ConfigEntryNotReady(f"Unexpected status {resp.status}")
            return await resp.json(content_type=None)
