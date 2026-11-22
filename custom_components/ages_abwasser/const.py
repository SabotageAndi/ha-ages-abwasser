"""Konstanten für das AGES-Abwassermonitoring."""

from datetime import timedelta

DOMAIN = "ages_abwasser"
NAME = "AGES Abwassermonitoring"
ENTRY_UNIQUE_ID = "Austria/SARSCOV2"
UPDATE_INTERVAL = timedelta(days=1)
REQUEST_TIMEOUT = 60

MEASUREMENT_STATUS_OPTIONS = (
    "quantified",
    "below_detection_limit",
    "below_quantification_limit",
    "no_data",
    "no_current_sample",
)
TREND_OPTIONS = (
    "decreasing",
    "stable",
    "moderate_increase",
    "strong_increase",
    "stable_low",
    "no_data",
)
