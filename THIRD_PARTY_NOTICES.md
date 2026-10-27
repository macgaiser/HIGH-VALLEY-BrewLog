# Drittanbieter-Komponenten

HIGH VALLEY BrewLog bringt die folgenden Fremdkomponenten mit. Sie stehen
jeweils unter ihrer eigenen Lizenz und sind **nicht** von der Lizenz des
BrewLog-Quellcodes (siehe `LICENSE`) erfasst.

## Mitgelieferte Dateien

| Komponente | Verwendung | Lizenz | Quelle |
|---|---|---|---|
| **Roboto** (Regular, Bold) | Fließtext der Oberfläche (`app/static/fonts/roboto-*.woff2`) | Apache License 2.0 | https://github.com/googlefonts/roboto |
| **Ranchers** | Überschriften und Etiketten (`app/static/fonts/ranchers.woff2`) | SIL Open Font License 1.1 | https://github.com/googlefonts/ranchers |
| **Chart.js** 4.4.4 | Diagramme der Statistik (`app/static/vendor/chartjs/`) | MIT | https://www.chartjs.org |
| **flatpickr** 4.6.13 | Datumsauswahl (`app/static/vendor/flatpickr/`) | MIT | https://flatpickr.js.org |

Urheberrechtsvermerke:

- Roboto: Copyright The Roboto Project Authors.
  Lizenztext: https://www.apache.org/licenses/LICENSE-2.0
- Ranchers: Copyright The Ranchers Project Authors (Vernon Adams).
  Lizenztext: https://openfontlicense.org
- Chart.js: Copyright (c) 2014-2024 Chart.js Contributors.
  Lizenztext: https://github.com/chartjs/Chart.js/blob/master/LICENSE.md
- flatpickr: Copyright (c) 2017 Gregory Petrosyan.
  Lizenztext: https://github.com/flatpickr/flatpickr/blob/master/LICENSE.md

Die Schriften werden unverändert verwendet. Bei Chart.js und flatpickr
steht der jeweilige Lizenzhinweis zusätzlich im Kopf der mitgelieferten
Dateien.

## Python-Abhängigkeiten (werden per `requirements.txt` installiert)

| Paket | Lizenz |
|---|---|
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| SQLModel | MIT |
| Jinja2 | BSD-3-Clause |
| python-multipart | Apache License 2.0 |

Diese Pakete werden nicht mit dem Quellcode ausgeliefert, sondern beim Bauen
des Docker-Images bzw. per `pip install -r requirements.txt` geladen; ihre
Lizenzen liegen den jeweiligen Paketen bei.

## Bilder und Marke

Bilder, Logos, Symbole und die Marke "HIGH VALLEY" sind selbst erstellt
(Rechteinhaber: macgaiser) und stehen **nicht** unter der Quellcode-Lizenz,
sondern unter eigenen Bedingungen: **alle Rechte vorbehalten**, siehe
[`LICENSE-ASSETS.md`](LICENSE-ASSETS.md). Weitergabe und Weiterverwendung
sind nicht erlaubt; erlaubt sind nur der Betrieb der unveränderten App und das
Drucken eigener, mit der App erzeugter Etiketten.

Der voreingestellte Etikett-Bierkrug (`app/static/img/label-default-mug.svg`)
ist dieselbe selbst erstellte Zeichnung wie das Krug-Symbol der EBC-Anzeige.
