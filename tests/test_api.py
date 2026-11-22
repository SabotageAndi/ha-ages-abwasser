"""Datenqualität, Probenzuordnung und fehlende Messungen absichern."""

from copy import deepcopy
from datetime import date
import importlib.util
from pathlib import Path
import sys
import unittest

# Der Parser bleibt ohne Home-Assistant-Laufzeit prüfbar.
SPEC = importlib.util.spec_from_file_location(
    "ages_api_test", Path(__file__).parents[1] / "custom_components/ages_abwasser/api.py"
)
API = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = API
SPEC.loader.exec_module(API)

HEADER = '"Datum";"Kläranlage";"Bundesland";"Genkopien"\n'
WEEK = date(2026, 11, 16)


def plot_trace(name, days, values, labels=None):
    return {
        "name": name, "mode": "lines+markers", "hoverinfo": ["text"] * len(days),
        "x": days, "y": values, "text": labels or [name] * len(days),
    }


def trend_map(names, levels, percents):
    args = [None] * 13
    args[0] = [48.0] * len(names)
    args[1] = [16.0] * len(names)
    args[2] = {"iconUrl": {
        "data": [f"visualizations/images/level{level}.png?v=0.3" for level in levels],
        "index": list(range(len(names))),
    }}
    args[6] = [
        name + (f"<br>Mittlere Änderung pro Woche: {percent}%" if percent is not None else "<br>Keine Daten")
        for name, percent in zip(names, percents, strict=True)
    ]
    args[10] = names
    return {"x": {"calls": [{"method": "addMarkers", "args": args}]}}


class ParseDataTests(unittest.TestCase):
    def test_preserves_actual_sampling_date_precision_and_official_trend(self):
        csv = HEADER + '2026-11-17;"Wien";"Wien";145\n'
        plot = {"data": [plot_trace("Wien", ["2026-11-16"], [145.1817669])]}
        station = API.parse_data(csv, plot, trend_map(["Wien"], [3], ["27,78"]), WEEK)["Wien"]
        self.assertEqual(station.sample_date, date(2026, 11, 17))
        self.assertAlmostEqual(station.viral_load, 145.1817669)
        self.assertEqual(station.federal_state, "Wien")
        self.assertEqual(station.trend, "moderate_increase")
        self.assertEqual(station.trend_percent, 27.78)
        self.assertEqual(station.measurement_status, "quantified")
        self.assertFalse(station.current_week_missing)

    def test_censored_values_are_unknown_but_real_zero_remains_numeric(self):
        names = ["Nachweisgrenze", "Bestimmungsgrenze", "Quantifizierte Null"]
        csv = HEADER + "".join(f'2026-11-17;"{name}";"Wien";{value}\n' for name, value in zip(names, [0, 6, 0]))
        plot = {"data": [
            plot_trace(names[0], ["2026-11-16"], [0], [names[0] + " (&lt; NG)"]),
            plot_trace(names[1], ["2026-11-16"], [6.2], [names[1] + " (< BG)"]),
            plot_trace(names[2], ["2026-11-16"], [0]),
        ]}
        data = API.parse_data(csv, plot, trend_map(names, [5, 5, 2], [None, None, 0]), WEEK)
        self.assertIsNone(data[names[0]].viral_load)
        self.assertIsNone(data[names[1]].viral_load)
        self.assertEqual(data[names[0]].measurement_status, "below_detection_limit")
        self.assertEqual(data[names[1]].measurement_status, "below_quantification_limit")
        self.assertEqual(data[names[2]].viral_load, 0)
        self.assertEqual(data[names[2]].measurement_status, "quantified")

    def test_latest_censored_sample_does_not_fall_back_to_old_numeric_sample(self):
        csv = HEADER + '2026-11-10;"Wien";"Wien";40\n2026-11-17;"Wien";"Wien";0\n'
        plot = {"data": [plot_trace("Wien", ["2026-11-09", "2026-11-16"], [40, 0], ["Wien", "Wien (< NG)"])]}
        station = API.parse_data(csv, plot, trend_map(["Wien"], [5], [None]), WEEK)["Wien"]
        self.assertEqual(station.sample_date, date(2026, 11, 17))
        self.assertIsNone(station.viral_load)
        self.assertEqual(station.measurement_status, "below_detection_limit")

    def test_missing_week_keeps_last_dated_measurement(self):
        csv = HEADER + '2026-11-10;"Welser Heide";"Oberösterreich";68\n'
        plot = {"data": [plot_trace("Welser Heide", ["2026-11-09"], [68.2668])]}
        station = API.parse_data(csv, plot, trend_map(["Welser Heide"], [3], [17.67]), WEEK)["Welser Heide"]
        self.assertTrue(station.current_week_missing)
        self.assertEqual(station.sample_date, date(2026, 11, 10))
        self.assertEqual(station.viral_load, 68.2668)
        self.assertEqual(station.trend_week, WEEK)

    def test_multiple_samples_in_one_week_match_latest_actual_sample(self):
        csv = HEADER + '2026-11-17;"Wien";"Wien";18\n2026-11-22;"Wien";"Wien";42\n'
        trace = plot_trace("Wien", ["2026-11-16", "2026-11-16"], [17.949, 42.186])
        plot = {"data": [trace, deepcopy(trace), {"name": "Wien", "mode": "lines+markers", "x": [1], "y": [1]}]}
        station = API.parse_data(csv, plot, trend_map(["Wien"], [3], [11]), WEEK)["Wien"]
        self.assertEqual(station.sample_date, date(2026, 11, 22))
        self.assertEqual(station.viral_load, 42.186)

    def test_same_week_same_rounded_value_is_rejected_when_ambiguous(self):
        csv = HEADER + '2026-11-22;"Wien";"Wien";42\n'
        plot = {"data": [plot_trace("Wien", ["2026-11-16", "2026-11-16"], [42.1, 42.2])]}
        with self.assertRaises(API.AGESDataError):
            API.parse_data(csv, plot, trend_map(["Wien"], [3], [11]), WEEK)

    def test_conflicting_source_snapshots_fail_instead_of_publishing_wrong_value(self):
        csv = HEADER + '2026-11-17;"Wien";"Wien";145\n'
        for day, value in [("2026-11-16", 40), ("2026-11-09", 145), ("2026-11-16", float("nan"))]:
            with self.subTest(day=day, value=value), self.assertRaises(API.AGESDataError):
                API.parse_data(csv, {"data": [plot_trace("Wien", [day], [value])]}, trend_map(["Wien"], [3], [11]), WEEK)

    def test_trend_station_without_any_sample_has_no_data(self):
        csv = HEADER + '2026-11-17;"Wien";"Wien";40\n'
        plot = {"data": [plot_trace("Wien", ["2026-11-16"], [40])]}
        station = API.parse_data(csv, plot, trend_map(["Wien", "Neue Anlage"], [2, 0], [0, None]), WEEK)["Neue Anlage"]
        self.assertIsNone(station.sample_date)
        self.assertIsNone(station.viral_load)
        self.assertEqual(station.measurement_status, "no_data")
        self.assertEqual(station.trend, "no_data")
        self.assertTrue(station.current_week_missing)

    def test_retired_historical_station_does_not_break_current_stations(self):
        csv = HEADER + '2026-11-17;"Wien";"Wien";40\n2026-08-04;"Historische Anlage";"Wien";18\n'
        plot = {"data": [plot_trace("Wien", ["2026-11-16"], [40])]}
        data = API.parse_data(csv, plot, trend_map(["Wien"], [2], [0]), WEEK)
        self.assertEqual(set(data), {"Wien"})

    def test_corrupt_compressed_trend_index_is_rejected(self):
        csv = HEADER + '2026-11-17;"Wien";"Wien";40\n'
        plot = {"data": [plot_trace("Wien", ["2026-11-16"], [40])]}
        trends = trend_map(["Wien"], [2], [0])
        trends["x"]["calls"][0]["args"][2]["iconUrl"]["index"] = [-1]
        with self.assertRaises(API.AGESDataError):
            API.parse_data(csv, plot, trends, WEEK)

    def test_html_or_empty_export_is_rejected(self):
        for csv in ["<html>Service unavailable</html>", HEADER]:
            with self.subTest(csv=csv), self.assertRaises(API.AGESDataError):
                API.parse_data(csv, {"data": []}, trend_map(["Wien"], [2], [0]), WEEK)


if __name__ == "__main__":
    unittest.main()
