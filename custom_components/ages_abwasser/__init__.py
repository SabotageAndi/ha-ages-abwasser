"""AGES-SARS-CoV-2-Abwassermonitoring für Home Assistant."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AGESClient
from .coordinator import AGESConfigEntry, AGESDataUpdateCoordinator

PLATFORMS = (Platform.SENSOR,)


async def async_setup_entry(hass: HomeAssistant, entry: AGESConfigEntry) -> bool:
    """Die Integration nach einem erfolgreichen ersten Datenabruf einrichten."""
    coordinator = AGESDataUpdateCoordinator(
        hass,
        entry,
        AGESClient(async_get_clientsession(hass)),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AGESConfigEntry) -> bool:
    """Alle Plattformen und ihre Koordinator-Abonnements entladen."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
