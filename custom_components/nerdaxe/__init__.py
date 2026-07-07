"""The NerdAxe/NerdQAxe/NerdOCTAXE miner integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOST
from .coordinator import NerdAxeCoordinator

PLATFORMS = ["sensor", "select", "button"]

type NerdAxeConfigEntry = ConfigEntry[NerdAxeCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: NerdAxeConfigEntry) -> bool:
    host = entry.data[CONF_HOST]
    coordinator = NerdAxeCoordinator(hass, entry, host)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NerdAxeConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
