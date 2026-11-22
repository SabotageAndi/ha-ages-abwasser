"""Gemeinsamer täglicher Datenabruf für alle Kläranlagen."""

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AGESClient, AGESDataError, StationData
from .const import DOMAIN, REQUEST_TIMEOUT, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type AGESConfigEntry = ConfigEntry[AGESDataUpdateCoordinator]


class AGESDataUpdateCoordinator(DataUpdateCoordinator[dict[str, StationData]]):
    """Daten aller Anlagen abrufen und Abruffehler an Home Assistant melden."""

    config_entry: AGESConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: AGESConfigEntry,
        client: AGESClient,
    ) -> None:
        """Den gemeinsamen Abruf mit der HA-Sitzung vorbereiten."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, StationData]:
        """Aktuelle AGES-Daten ohne Ersatzwerte bei Fehlern liefern."""
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                data = await self.client.async_get_data()
            if not data:
                raise AGESDataError("AGES liefert keine Kläranlagendaten.")
        except AGESDataError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="invalid_data",
                translation_placeholders={"error": str(err)},
            ) from err
        return data
