# Sicherheitshinweise

## Unterstützte Version

HIGH VALLEY BrewLog befindet sich in der **Beta**. Sicherheitskorrekturen gibt
es nur für den jeweils aktuellsten Stand (neueste Version bzw. `main`).

## Sicherheitslücke melden

Bitte **keine öffentlichen Issues** für Sicherheitslücken anlegen.

Melde sie privat über GitHub: Reiter **Security** → **Report a vulnerability**
im Repository. Beschreibe möglichst, was betroffen ist, wie man es nachstellt
und welche Version du nutzt. Bitte keine echten Zugangsdaten oder Braudaten
mitschicken.

Die Meldungen werden nach bestem Bemühen bearbeitet (Hobbyprojekt, keine
feste Reaktionszeit).

## Bekannte Einschränkungen (kein Fehler)

- Die Oberfläche ist nur per **HTTP Basic Auth** geschützt (ein Benutzer, kein
  Rollenmodell). Ohne HTTPS werden Zugangsdaten unverschlüsselt übertragen -
  für Zugriff außerhalb des eigenen Netzwerks einen Reverse-Proxy mit HTTPS
  und idealerweise VPN verwenden.
- Die App ist für den Betrieb im eigenen Netzwerk gedacht, nicht für den
  direkten Betrieb im offenen Internet.
- `APP_PASSWORD` muss selbst gesetzt werden; die App startet nicht mit den
  Beispielwerten.
