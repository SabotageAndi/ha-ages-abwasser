# Änderungen

## 0.1.1

- Reguläre SockJS-Sitzungskennungen, Cache-Buster und Sequenzbestätigungen für aufeinanderfolgende Abrufe mit derselben Home-Assistant-HTTP-Sitzung.

## 0.1.0

- SARS-CoV-2-Abwassermonitoring aller von AGES verfügbaren österreichischen Kläranlagen.
- Vier Sensoren pro Anlage: Viruslast, tatsächliches Probedatum, offizieller Trend und Messstatus.
- Täglicher gemeinsamer Abruf, UI-Einrichtung und automatische Aufnahme neuer Anlagen.
- NG/BG-Kennzeichnungen, fehlende aktuelle Proben und Abruffehler werden getrennt behandelt.
- HACS-/Marketplace-kompatible Struktur, deutsches und englisches UI, lokales Integrationsicon.
- Regressionstests für Datenqualität und Zuordnung mehrerer Proben innerhalb einer Woche.
