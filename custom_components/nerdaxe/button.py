"""Shutdown/restart buttons for the NerdAxe/NerdQAxe/NerdOCTAXE integration."""
from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NerdAxeConfigEntry
from .const import DOMAIN
from .coordinator import NerdAxeCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: NerdAxeConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([
        NerdAxeShutdownButton(coordinator, entry),
        NerdAxeRestartButton(coordinator, entry),
    ])


class _NerdAxeButtonBase(CoordinatorEntity[NerdAxeCoordinator], ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: NerdAxeCoordinator, entry: NerdAxeConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})


class NerdAxeShutdownButton(_NerdAxeButtonBase):
    _attr_translation_key = "shutdown"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: NerdAxeCoordinator, entry: NerdAxeConfigEntry) -> None:
        super().__init__(coordinator, entry, "shutdown_button")

    async def async_press(self) -> None:
        await self.coordinator.async_shutdown()


class NerdAxeRestartButton(_NerdAxeButtonBase):
    _attr_translation_key = "restart"
    _attr_device_class = ButtonDeviceClass.RESTART

    def __init__(self, coordinator: NerdAxeCoordinator, entry: NerdAxeConfigEntry) -> None:
        super().__init__(coordinator, entry, "restart_button")

    async def async_press(self) -> None:
        await self.coordinator.async_restart()
