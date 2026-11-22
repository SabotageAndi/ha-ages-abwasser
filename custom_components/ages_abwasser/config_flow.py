"""Bestätigungsdialog mit echtem AGES-Datenabruf."""

import asyncio
import logging
from typing import Any

from aiohttp import ClientError
import probatio

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AGESClient, AGESDataError
from .const import DOMAIN, ENTRY_UNIQUE_ID, NAME, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class AGESAbwasserConfigFlow(ConfigFlow, domain=DOMAIN):
    """Eine gemeinsame Integration für alle österreichischen Anlagen anlegen."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Die Einrichtung bestätigen und Verbindung sowie Daten prüfen."""
        await self.async_set_unique_id(ENTRY_UNIQUE_ID)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            client = AGESClient(async_get_clientsession(self.hass))
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    data = await client.async_get_data()
                if not data:
                    raise AGESDataError("AGES liefert keine Kläranlagendaten.")
            except TimeoutError:
                _LOGGER.debug("Zeitüberschreitung beim AGES-Datenabruf", exc_info=True)
                errors["base"] = "timeout"
            except ClientError:
                _LOGGER.debug("Verbindung zu AGES fehlgeschlagen", exc_info=True)
                errors["base"] = "cannot_connect"
            except AGESDataError:
                _LOGGER.debug("Ungültige AGES-Daten beim Einrichten", exc_info=True)
                errors["base"] = "invalid_data"
            except Exception:
                _LOGGER.exception("Unerwarteter Fehler beim Einrichten von AGES")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=NAME, data={})

        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema({}),
            errors=errors,
        )
