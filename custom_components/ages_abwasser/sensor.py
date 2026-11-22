"""Vier Sensoren je AGES-Kläranlage einschließlich später entdeckter Anlagen."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import StationData
from .const import DOMAIN, ENTRY_UNIQUE_ID, MEASUREMENT_STATUS_OPTIONS, TREND_OPTIONS
from .coordinator import AGESConfigEntry, AGESDataUpdateCoordinator

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class AGESSensorEntityDescription(SensorEntityDescription):
    """Sensorbeschreibung mit dem zugehörigen Wert aus den Stationsdaten."""

    value_fn: Callable[[StationData], date | float | str | None]


SENSOR_DESCRIPTIONS: tuple[AGESSensorEntityDescription, ...] = (
    AGESSensorEntityDescription(
        key="viral_load",
        translation_key="viral_load",
        icon="mdi:virus",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Mio. Genkopien/Einwohner",
        suggested_display_precision=2,
        value_fn=lambda station: station.viral_load,
    ),
    AGESSensorEntityDescription(
        key="sample_date",
        translation_key="sample_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda station: station.sample_date,
    ),
    AGESSensorEntityDescription(
        key="trend",
        translation_key="trend",
        device_class=SensorDeviceClass.ENUM,
        icon="mdi:chart-line",
        options=list(TREND_OPTIONS),
        value_fn=lambda station: station.trend,
    ),
    AGESSensorEntityDescription(
        key="measurement_status",
        translation_key="measurement_status",
        device_class=SensorDeviceClass.ENUM,
        icon="mdi:flask-outline",
        options=list(MEASUREMENT_STATUS_OPTIONS),
        value_fn=lambda station: (
            "no_current_sample"
            if station.current_week_missing
            else station.measurement_status
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AGESConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Alle vorhandenen und künftig gemeldeten Kläranlagen hinzufügen."""
    coordinator = entry.runtime_data
    known_stations: set[str] = set()

    @callback
    def async_add_stations() -> None:
        """Neue Anlagen ergänzen, bestehende Entitäten niemals löschen."""
        if not coordinator.last_update_success:
            return

        new_stations = set(coordinator.data) - known_stations
        if not new_stations:
            return
        known_stations.update(new_stations)
        async_add_entities(
            [
                AGESAbwasserSensor(coordinator, station_name, description)
                for station_name in sorted(new_stations)
                for description in SENSOR_DESCRIPTIONS
            ]
        )

    entry.async_on_unload(coordinator.async_add_listener(async_add_stations))
    async_add_stations()


class AGESAbwasserSensor(CoordinatorEntity[AGESDataUpdateCoordinator], SensorEntity):
    """Einen aktuellen Stationswert mit stabiler Geräte- und Entitäts-ID melden."""

    _attr_has_entity_name = True
    entity_description: AGESSensorEntityDescription

    def __init__(
        self,
        coordinator: AGESDataUpdateCoordinator,
        station_name: str,
        description: AGESSensorEntityDescription,
    ) -> None:
        """Den Sensor einer Anlage zuordnen, ohne ihren Namen zu normalisieren."""
        super().__init__(coordinator, context=station_name)
        self.entity_description = description
        self._station_name = station_name
        station_id = f"{ENTRY_UNIQUE_ID}/{station_name}"
        self._attr_unique_id = f"{station_id}/{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, station_id)},
            name=coordinator.data[station_name].name,
            manufacturer="AGES",
            model="SARS-CoV-2-Abwassermonitoring",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        """Bei Abruffehlern und verschwundenen Stationsdaten nicht verfügbar sein."""
        return super().available and self._station_name in self.coordinator.data

    @property
    def native_value(self) -> date | float | str | None:
        """Den letzten echten Wert liefern; Nachweisgrenzen bleiben unbekannt."""
        station = self.coordinator.data.get(self._station_name)
        if station is None:
            return None
        return self.entity_description.value_fn(station)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Nur Metadaten zur letzten Probe und zum offiziellen AGES-Trend liefern."""
        station = self.coordinator.data.get(self._station_name)
        if station is None:
            return {}

        attributes: dict[str, Any] = {
            "federal_state": station.federal_state,
            "current_week_missing": station.current_week_missing,
        }
        key = self.entity_description.key
        if key in ("viral_load", "measurement_status"):
            attributes["source_value"] = station.source_value
        if key == "viral_load":
            attributes["sample_date"] = (
                station.sample_date.isoformat() if station.sample_date else None
            )
        elif key == "trend":
            attributes["trend_percent"] = station.trend_percent
            attributes["trend_week"] = station.trend_week.isoformat()
        elif key == "measurement_status":
            attributes["measurement_status"] = station.measurement_status
        return attributes
