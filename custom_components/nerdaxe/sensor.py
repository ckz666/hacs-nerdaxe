"""Sensor entities for the NerdAxe/NerdQAxe/NerdOCTAXE integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NerdAxeConfigEntry
from .const import DOMAIN
from .coordinator import NerdAxeCoordinator


@dataclass(frozen=True, kw_only=True)
class NerdAxeSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any] = lambda data: None


SENSOR_TYPES: tuple[NerdAxeSensorDescription, ...] = (
    NerdAxeSensorDescription(
        key="hashRate",
        translation_key="hashrate",
        native_unit_of_measurement="GH/s",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: d.get("hashRate"),
    ),
    NerdAxeSensorDescription(
        key="hashRate_1h",
        translation_key="hashrate_1h",
        native_unit_of_measurement="GH/s",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("hashRate_1h"),
    ),
    NerdAxeSensorDescription(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("power"),
    ),
    NerdAxeSensorDescription(
        key="voltage",
        translation_key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("voltage"),
    ),
    NerdAxeSensorDescription(
        key="current",
        translation_key="current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("current"),
    ),
    NerdAxeSensorDescription(
        key="temp",
        translation_key="chip_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("temp"),
    ),
    NerdAxeSensorDescription(
        key="vrTemp",
        translation_key="vr_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("vrTemp"),
    ),
    NerdAxeSensorDescription(
        key="fanrpm",
        translation_key="fan_speed",
        native_unit_of_measurement="rpm",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("fanrpm"),
    ),
    NerdAxeSensorDescription(
        key="frequency",
        translation_key="frequency",
        native_unit_of_measurement="MHz",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("frequency"),
    ),
    NerdAxeSensorDescription(
        key="coreVoltageActual",
        translation_key="core_voltage_actual",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("coreVoltageActual"),
    ),
    NerdAxeSensorDescription(
        key="sharesAccepted",
        translation_key="shares_accepted",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("sharesAccepted"),
    ),
    NerdAxeSensorDescription(
        key="sharesRejected",
        translation_key="shares_rejected",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("sharesRejected"),
    ),
    NerdAxeSensorDescription(
        key="duplicateHWNonces",
        translation_key="duplicate_hw_nonces",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("duplicateHWNonces"),
    ),
    NerdAxeSensorDescription(
        key="bestDiff",
        translation_key="best_difficulty",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("bestDiff"),
    ),
    NerdAxeSensorDescription(
        key="wifiRSSI",
        translation_key="wifi_rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement="dBm",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("wifiRSSI"),
    ),
    NerdAxeSensorDescription(
        key="uptimeSeconds",
        translation_key="uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("uptimeSeconds"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: NerdAxeConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        NerdAxeSensor(coordinator, entry, description) for description in SENSOR_TYPES
    )


class NerdAxeSensor(CoordinatorEntity[NerdAxeCoordinator], SensorEntity):
    entity_description: NerdAxeSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NerdAxeCoordinator,
        entry: NerdAxeConfigEntry,
        description: NerdAxeSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.data.get("hostname", coordinator.host),
            manufacturer="BitMaker-hub / Patsch91 (open-source)",
            model=coordinator.data.get("deviceModel", "NerdAxe"),
            sw_version=coordinator.data.get("version"),
            configuration_url=coordinator.base_url,
        )

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)
