# AGES-Abwassermonitoring für Home Assistant

Custom Integration für die SARS-CoV-2-Viruslast aller von [AGES veröffentlichten österreichischen Kläranlagen](https://abwasser.ages.at/de/#SARSCOV2). Einrichtung über die Home-Assistant-Oberfläche, täglicher gemeinsamer Datenabruf und automatische Aufnahme neuer Anlagen.

Die Integration ist ein unabhängiges Projekt und keine offizielle AGES-Integration. Influenza, RSV und Virusvarianten sind nicht enthalten.

## Sensoren

Jede Kläranlage erhält ein Gerät und vier Sensoren:

| Sensor | Inhalt |
| --- | --- |
| Viruslast | Letzte veröffentlichte quantitative Viruslast in Millionen Genkopien pro Einwohner |
| Probedatum | Tatsächliches Datum der letzten Probe, nicht der Wochenanfang des Diagramms |
| AGES-Trend | Offizielle Trendkategorie; prozentuale wöchentliche Änderung und Trendwoche als Attribute |
| Messstatus | Quantifiziert, unter Nachweisgrenze, unter Bestimmungsgrenze, keine Messdaten oder keine aktuelle Probe |

Alle verfügbaren Kläranlagen werden aktiviert. Beim Live-Datenabruf wurden 20 Anlagen erkannt. Es werden keine zusätzlichen Österreich-Aggregatsensoren angelegt. Einzelne Sensoren lassen sich wie üblich in Home Assistant deaktivieren.

## Installation

Voraussetzung: Home Assistant 2026.11.0 oder neuer.

### HACS / Marketplace

1. `SabotageAndi/ha-ages-abwasser` als benutzerdefiniertes Repository der Kategorie **Integration** hinzufügen. Das Repository muss für das verbundene GitHub-Konto erreichbar sein.
2. **AGES Abwassermonitoring** herunterladen.
3. Home Assistant neu starten, damit der neue Python-Code geladen wird.
4. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach **AGES Abwassermonitoring** suchen und die Einrichtung bestätigen.

Die Integration benötigt keine AGES-Zugangsdaten und keine YAML-Konfiguration.

### Manuell

Den Ordner `custom_components/ages_abwasser` aus dem Repository vollständig nach `/config/custom_components/ages_abwasser` kopieren. Danach Home Assistant neu starten und die Integration über **Geräte & Dienste** hinzufügen.

## Messlücken und Nachweisgrenzen

- `<NG` bezeichnet einen Wert unter der analytischen Nachweisgrenze; `<BG` einen Wert unter der Bestimmungsgrenze. In beiden Fällen bleibt der numerische Viruslast-Sensor `unknown`. Der Messstatus benennt die Grenze. Ein von AGES verwendeter Ersatzwert wird nicht als quantitative Messung ausgegeben.
- Fehlt eine Probe in der neuesten veröffentlichten Trendwoche, bleiben die letzte Viruslast und ihr tatsächliches Probedatum erhalten. Der Messstatus zeigt **Keine aktuelle Probe**. Das Attribut `current_week_missing` ist dann `true`; `measurement_status` am Messstatus-Sensor beschreibt weiterhin die letzte vorhandene Probe.
- Der Trend kann trotz einer fehlenden aktuellen Probe verfügbar sein, da AGES ihn aus mehreren Wochen berechnet. `trend_week` bezeichnet den Montag der offiziellen Trendwoche; `trend_percent` die mittlere relative Änderung pro Woche, nicht den Unterschied zwischen zwei Einzelproben.
- Bei Abruffehlern oder unvereinbaren Datenquellen werden die Sensoren `unavailable`. Es gibt keine Ersatznullen. Anlagen, die aus der Quelle verschwinden, behalten ihre Entitäts-IDs und werden ebenfalls `unavailable`.
- Messwerte können von AGES nachträglich korrigiert werden. Bei mehreren Proben in derselben Woche wird der gerundete CSV-Wert mit den Diagrammbeobachtungen abgeglichen. Bleibt die Zuordnung mehrdeutig, schlägt der Abruf fehl, statt ein Probedatum zu erfinden.

Home Assistant zeichnet die künftig abgerufenen Zustände über seinen Recorder auf. Die Zeitstempel dieser Historie sind die Abrufzeitpunkte. Die AGES-Historie wird nicht rückwirkend in den Recorder importiert.

## Datenquelle und Wartungsrisiko

Das Dashboard ist eine öffentliche R-Shiny-Anwendung. Die Integration öffnet pro Aktualisierung eine begrenzte SockJS-XHR-Sitzung und lädt den CSV-Export der SARS-CoV-2-Messungen. Präzise Messwerte und NG/BG-Kennzeichnungen stammen aus dem [öffentlichen Diagramm-JSON](https://abwasser.ages.at/de/cache/plotly/sarscov2_development.json); Trendkategorien und Prozentwerte aus der vom Server gelieferten Trendkarte. Die Sitzung wird nach dem Abruf geschlossen. Ein Browser ist nicht erforderlich.

Diese Schnittstellen gehören zum Dashboard und sind keine zugesicherte öffentliche API. Änderungen an Shiny-Ausgaben, CSV-Spalten, Diagrammstruktur oder Trendmarkern können eine Anpassung der Integration erfordern. Die Quellen werden gegeneinander geprüft; unbekannte Formate führen zu einem sichtbaren Abruffehler.

## Entwicklung und Prüfung

Python 3.14, für die isolierten Parser-Prüfungen genügt `aiohttp`:

```sh
python -m pip install aiohttp
python -m unittest discover -s tests -v
```

Die Regressionstests prüfen Probedaten, Nachweisgrenzen, Messlücken, Mehrfachproben, mehrdeutige Zuordnungen und fehlerhafte oder widersprüchliche Quellen. GitHub Actions führt diese Prüfungen bei Pushes und Pull Requests aus.

## Lizenz

Der Quellcode und die zugehörige Dokumentation stehen unter der [MIT-Lizenz](LICENSE).

Die von AGES abgerufenen Messdaten sind davon nicht umfasst. Für ihre Nutzung gelten die jeweiligen Nutzungsbedingungen der Datenquelle; dieses Projekt räumt keine Rechte an den AGES-Daten ein.

## Quellen

- [AGES: SARS-CoV-2-Abwassermonitoring, Einheiten und Trendberechnung](https://abwasser.ages.at/de/#SARSCOV2)
- [Home Assistant: gemeinsamer Datenabruf mit DataUpdateCoordinator](https://developers.home-assistant.io/docs/integration_fetching_data/)
- [HACS: Anforderungen an Integrations-Repositories](https://www.hacs.xyz/docs/publish/integration/)
