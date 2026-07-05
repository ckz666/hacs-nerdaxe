"""Profile selector for the NerdAxe/NerdQAxe/NerdOCTAXE integration.

This is the entity to drive from a Home Assistant automation keyed off solar
surplus: select.nerdaxe_power_profile -> "normal" with ample surplus, "eco"
with some, "off" (POSTs /api/system/shutdown) with none.
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NerdAxeConfigEntry
from .const import DOMAIN, OFF_PROFILE, PROFILES
from .coordinator import NerdAxeCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: NerdAxeConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([NerdAxeProfileSelect(coordinator, entry)])


class NerdAxeProfileSelect(CoordinatorEntity[NerdAxeCoordinator], SelectEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "power_profile"
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator: NerdAxeCoordinator, entry: NerdAxeConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_power_profile"
        self._attr_options = [OFF_PROFILE, *PROFILES.keys()]
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @property
    def current_option(self) -> str | None:
        # "custom" (settings don't match any known profile) isn't one of
        # _attr_options, so it renders as unknown rather than raising —
        # that's the correct state if someone changed settings via the
        # device's own web UI outside of Home Assistant.
        profile = self.coordinator.current_profile
        return profile if profile in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        # Can take up to ~40s if waking the device from "off" (POST restart +
        # poll until it answers again) — that's the real hardware, not a bug.
        await self.coordinator.async_select_profile(option)
