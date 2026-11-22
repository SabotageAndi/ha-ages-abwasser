"""AGES-Rohdaten über die öffentliche Shiny-Anwendung abrufen."""

from __future__ import annotations

import asyncio
import csv
from dataclasses import dataclass
from datetime import date, timedelta
from html import unescape
from io import StringIO
import json
import math
import re
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import aiohttp

BASE_URL = "https://abwasser.ages.at/de/"
PLOT_URL = BASE_URL + "cache/plotly/sarscov2_development.json"
DEVELOPMENT = "sarscov2_development"
TREND_MAP = "sarscov2_trendindicators"
DOWNLOAD = DEVELOPMENT + "-download_DT_csv"

TREND_LEVELS = {
    0: "no_data",
    1: "decreasing",
    2: "stable",
    3: "moderate_increase",
    4: "strong_increase",
    5: "stable_low",
}


class AGESDataError(Exception):
    """Die veröffentlichten Daten fehlen oder haben ein unbekanntes Format."""


@dataclass(frozen=True, slots=True)
class StationData:
    """Letzte veröffentlichte Probe und offizieller Trend einer Kläranlage."""

    name: str
    federal_state: str
    sample_date: date | None
    viral_load: float | None
    measurement_status: str
    source_value: str
    trend: str
    trend_percent: float | None
    trend_week: date
    current_week_missing: bool


def _week(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _number(value: object) -> float:
    if isinstance(value, bool):
        raise AGESDataError("Boolescher Wert statt Viruslast oder Trend")
    try:
        number = float(str(value).replace(",", "."))
    except (ValueError, TypeError) as err:
        raise AGESDataError("Ungültiger Zahlenwert") from err
    if not math.isfinite(number):
        raise AGESDataError("Nicht endlicher Zahlenwert")
    return number


def _plot_samples(plot: dict) -> dict[str, dict[date, set[tuple[float | None, str]]]]:
    """Plotwerte samt NG/BG lesen; eine Woche kann mehrere Proben enthalten."""
    result: dict[str, dict[date, set[tuple[float | None, str]]]] = {}
    for trace in plot["data"]:
        name = trace.get("name")
        if not name or trace.get("mode") != "lines+markers" or "hoverinfo" not in trace:
            continue
        xs, ys, texts = trace.get("x"), trace.get("y"), trace.get("text")
        if not isinstance(xs, list) or not isinstance(ys, list) or not isinstance(texts, list):
            raise AGESDataError("Unvollständige Messreihe im AGES-Diagramm")
        if len(xs) != len(ys) or len(xs) != len(texts):
            raise AGESDataError("Unterschiedliche Längen in der Messreihe")
        samples = result.setdefault(name, {})
        for day, value, text in zip(xs, ys, texts, strict=True):
            if not isinstance(day, str):
                raise AGESDataError("Ungültiges Datum in der Messreihe")
            sample_week = date.fromisoformat(day)
            label = unescape(str(text))
            numeric = _number(value) if value is not None else None
            if numeric is not None and numeric < 0:
                raise AGESDataError("Negative Viruslast")
            if re.search(r"<\s*NG\b", label, re.IGNORECASE):
                status = "below_detection_limit"
            elif re.search(r"<\s*BG\b", label, re.IGNORECASE):
                status = "below_quantification_limit"
            elif numeric is None:
                status = "no_data"
            else:
                status = "quantified"
            samples.setdefault(sample_week, set()).add((numeric, status))
    return result


def _expand(value: object, count: int) -> list:
    """Die von htmlwidgets komprimierten Leaflet-Arrays expandieren."""
    if isinstance(value, dict) and "data" in value and "index" in value:
        data = value["data"]
        data = data if isinstance(data, list) else [data]
        indexes = value["index"]
        indexes = indexes if isinstance(indexes, list) else [indexes] * count
        if len(indexes) != count or any(
            isinstance(i, bool) or not isinstance(i, int) or i < 0 or i >= len(data)
            for i in indexes
        ):
            raise AGESDataError("Ungültige Leaflet-Indexliste")
        return [data[i] for i in indexes]
    if isinstance(value, list):
        if len(value) != count:
            raise AGESDataError("Unterschiedliche Längen in der Trendkarte")
        return value
    return [value] * count


def _trends(trend_map: dict) -> dict[str, tuple[str, float | None]]:
    """Offizielle Trendpfeile übernehmen, keine eigene Regression berechnen."""
    result: dict[str, tuple[str, float | None]] = {}
    for call in trend_map["x"]["calls"]:
        if call.get("method") != "addMarkers":
            continue
        args = call["args"]
        if not args[6]:  # Unsichtbare Hilfsmarker besitzen keine Popups.
            continue
        labels = args[10]
        count = len(labels) if isinstance(labels, list) else 1
        labels = _expand(labels, count)
        popups = _expand(args[6], count)
        icons = _expand(args[2]["iconUrl"], count)
        for name, popup, icon in zip(labels, popups, icons, strict=True):
            if name == "Österreich-Trend":
                continue
            if not isinstance(name, str) or not name.strip():
                raise AGESDataError("Trendmarker ohne Anlagenname")
            level = re.search(r"(?:^|/)level([0-5])\.png(?:\?|$)", str(icon))
            if not level:
                raise AGESDataError("Unbekannter AGES-Trendpfeil")
            trend = TREND_LEVELS[int(level.group(1))]
            percent = re.search(r"(-?\d+(?:[.,]\d+)?)\s*%", unescape(str(popup)))
            change = _number(percent.group(1)) if percent else None
            if change is None and trend not in ("no_data", "stable_low"):
                raise AGESDataError("Trendpfeil ohne Änderungswert")
            if name in result:
                raise AGESDataError("Doppelter Trendmarker")
            result[name] = (trend, change)
    if not result:
        raise AGESDataError("Keine Kläranlagen in der AGES-Trendkarte")
    return result


def parse_data(csv_text: str, plot: dict, trend_map: dict, trend_week: date) -> dict[str, StationData]:
    """Probedatum aus CSV mit präziser Viruslast und Grenzwerten verknüpfen."""
    try:
        reader = csv.DictReader(StringIO(csv_text.lstrip("\ufeff")), delimiter=";")
        required = {"Datum", "Kläranlage", "Bundesland", "Genkopien"}
        if not required.issubset(reader.fieldnames or []):
            raise AGESDataError("Unbekanntes Format des AGES-CSV-Exports")
        latest: dict[str, tuple[date, str, str]] = {}
        for row in reader:
            name = row["Kläranlage"]
            if not name or not row["Bundesland"] or row["Genkopien"] is None:
                raise AGESDataError("Unvollständige CSV-Zeile")
            day = date.fromisoformat(row["Datum"])
            item = (day, row["Bundesland"], row["Genkopien"].strip())
            previous = latest.get(name)
            if previous is None or day > previous[0]:
                latest[name] = item
            elif day == previous[0] and item != previous:
                raise AGESDataError("Widersprüchliche CSV-Werte für dieselbe Probe")
        samples = _plot_samples(plot)
        trends = _trends(trend_map)
        if not latest:
            raise AGESDataError("AGES-CSV enthält keine Proben")
        result = {}
        for name, (trend, percent) in trends.items():
            item = latest.get(name)
            if item is None:
                result[name] = StationData(
                    name, "", None, None, "no_data", "", trend, percent, trend_week, True
                )
                continue
            day, federal_state, source_value = item
            sample_week = _week(day)
            if sample_week > trend_week:
                raise AGESDataError("CSV und Trendkarte stammen aus unterschiedlichen Wochen")
            candidates = samples.get(name, {}).get(sample_week, set())
            if not candidates:
                raise AGESDataError("CSV-Probe fehlt im AGES-Diagramm")
            # Diagrammdaten haben nur Wochenauflösung. Bei mehreren Proben
            # identifiziert der gerundete CSV-Wert die passende Beobachtung.
            csv_value = _number(source_value)
            matches = {
                (value, status) for value, status in candidates
                if value is not None and abs(csv_value - value) <= 0.500001
            }
            if len(matches) != 1:
                raise AGESDataError("CSV-Probe ist im Diagramm nicht eindeutig zuordenbar")
            value, status = matches.pop()
            viral_load = value if status == "quantified" else None
            result[name] = StationData(
                name, federal_state, day, viral_load, status, source_value,
                trend, percent, trend_week, sample_week < trend_week,
            )
        if any(_week(latest[name][0]) >= trend_week for name in set(latest) - set(trends)):
            raise AGESDataError("Aktuelle Kläranlagen aus dem CSV fehlen in der Trendkarte")
        return result
    except (KeyError, IndexError, TypeError, ValueError, AttributeError, csv.Error) as err:
        raise AGESDataError("Unbekanntes AGES-Datenformat") from err


class AGESClient:
    """Öffentliche Shiny-Exporte ohne Browser oder zusätzliche Abhängigkeiten."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def async_get_data(self) -> dict[str, StationData]:
        async with asyncio.timeout(90):
            shiny = _ShinySession(self._session)
            try:
                csv_text, trend_map, trend_week = await shiny.read_data()
                async with self._session.get(
                    PLOT_URL,
                    headers={"Cache-Control": "no-cache"},
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as response:
                    response.raise_for_status()
                    plot = await response.json()
                return parse_data(csv_text, plot, trend_map, trend_week)
            except (json.JSONDecodeError, ValueError) as err:
                raise AGESDataError("Ungültige AGES-Nachricht") from err
            finally:
                await shiny.close()


class _ShinySession:
    """Begrenzte SockJS-XHR-Sitzung für genau einen SARS-CoV-2-Export."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._url = BASE_URL + "__sockjs__/000/" + uuid4().hex
        self._opened = False

    async def _post(self, endpoint: str, messages: list[str] | None = None) -> str:
        async with self._session.post(
            self._url + "/" + endpoint,
            data=json.dumps(messages) if messages is not None else None,
            headers={"Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=35),
        ) as response:
            response.raise_for_status()
            return await response.text()

    async def _update(self, data: dict) -> None:
        await self._post("xhr_send", ["0|m|" + json.dumps({"method": "update", "data": data})])

    async def read_data(self) -> tuple[str, dict, date]:
        if (await self._post("xhr")).strip() != "o":
            raise AGESDataError("AGES-Shiny-Sitzung wurde nicht geöffnet")
        self._opened = True
        initial = {
            "_tabs_": "SARSCOV2",
            "url_hash": "SARSCOV2",
            "header-language_picker": "DE",
            DEVELOPMENT + "-view_DT_btn:shiny.action": 0,
            ".clientdata_output_" + DEVELOPMENT + "_hidden": False,
            ".clientdata_output_" + TREND_MAP + "_hidden": False,
            ".clientdata_url_protocol": "https:",
            ".clientdata_url_hostname": "abwasser.ages.at",
            ".clientdata_url_pathname": "/de/",
        }
        await self._post("xhr_send", [
            "0|o|",
            "0|m|" + json.dumps({"method": "init", "data": initial}),
        ])
        trend_map = None
        trend_week = None
        csv_text = None
        while csv_text is None or trend_map is None or trend_week is None:
            frame = (await self._post("xhr")).strip()
            if frame == "h":
                continue
            if not frame.startswith("a"):
                raise AGESDataError("AGES-Shiny-Verbindung wurde geschlossen")
            for message in json.loads(frame[1:]):
                if message.startswith("0|c|"):
                    raise AGESDataError("AGES hat den Datenkanal geschlossen")
                if not message.startswith("0|m|"):
                    continue
                payload = json.loads(message[4:])
                errors = payload.get("errors", {})
                if any(key.startswith((DEVELOPMENT, TREND_MAP)) for key in errors):
                    raise AGESDataError("AGES konnte die SARS-CoV-2-Ausgabe nicht erzeugen")
                if "config" in payload:
                    await self._update({DEVELOPMENT + "-view_DT_btn:shiny.action": 1})
                if payload.get("modal", {}).get("type") == "show":
                    await self._update({
                        ".clientdata_output_" + DOWNLOAD + "_hidden": False,
                    })
                values = payload.get("values", {})
                if values.get(TREND_MAP) is not None:
                    trend_map = values[TREND_MAP]
                for item in payload.get("inputMessages", []):
                    if item.get("id") == TREND_MAP + "_source_date_picker":
                        choices = item["message"].get("choices", "")
                        dates = re.findall(r'<option value="(\d{4}-\d{2}-\d{2})">', choices)
                        if not dates:
                            raise AGESDataError("AGES veröffentlicht keine Trendwoche")
                        trend_week = max(date.fromisoformat(day) for day in dates)
                if values.get(DOWNLOAD):
                    csv_text = await self._download(values[DOWNLOAD])
        return csv_text, trend_map, trend_week

    async def _download(self, path: str) -> str:
        if not isinstance(path, str) or not path.startswith("session/"):
            raise AGESDataError("Ungültiger AGES-Downloadpfad")
        url = urljoin(BASE_URL, path)
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc != "abwasser.ages.at" or not parts.path.startswith("/de/session/"):
            raise AGESDataError("AGES-Export verweist auf eine fremde Adresse")
        async with self._session.get(
            url, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=False
        ) as response:
            response.raise_for_status()
            if response.content_type != "text/csv":
                raise AGESDataError("AGES-Download ist kein CSV")
            return await response.text()

    async def close(self) -> None:
        if not self._opened:
            return
        try:
            async with asyncio.timeout(3):
                await self._post("xhr_send", ['0|c|{"code":1000,"reason":"Complete"}'])
        except (aiohttp.ClientError, TimeoutError):
            pass  # Die begrenzte Export-Sitzung ist eventuell bereits abgelaufen.
        finally:
            self._opened = False
