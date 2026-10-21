# Behebung des Audits vom 20.10.2026

Die zwölf Auditbefunde werden durch dieses Update adressiert. Migration
`0025_portfolio_integrity` ist vor dem Start der neuen API und Worker erforderlich.
Die Migration ergänzt Felder und Prüfbedingungen; bestehende Buchungen und
Positionen werden nicht automatisch bereinigt oder umgeschrieben.

| Befund | Änderung | Prüfung |
|---|---|---|
| F01 Zertifikate | `certifi>=2026.10.19`, vollständige Python-Locks mit Hashes; CI und Images installieren dieselben Runtime-Versionen. | Paket-Audit und Prüfung des gebauten/ausgerollten Images. |
| F02 Verkäufe | Gemeinsame Transaktionssperre für Anlegen, Stopps, Schließen, Verkauf sowie CSV-/TR-Importe. Optionale eindeutige Buchungskennungen verhindern eine zweite Wirkung bei Wiederholung. Geänderte Eingaben mit derselben Kennung ergeben einen Konflikt. | Zwei parallele Verkäufe von jeweils sechs aus zehn Stück; wiederholter Vollverkauf mit gleicher Kennung. |
| F03 Währungen | Kurswährung wird getrennt von der Positionswährung gelesen. Alle manuellen Positionen werden mit gespeicherten FX-Beobachtungen bewertet. Importierte Kurse werden vor dem Schreiben in Börseneinheiten umgerechnet und erhalten ihre Währungskennung. Ohne benötigte FX-Daten wird keine Bewertung erfunden. | EUR/USD, USD/EUR, identische Währung, Pence/Pfund, fehlende FX-Daten und wiederholte Normalisierung. |
| F04 Monitor | Hetzner erhält einen eigenen Monitor-Worker. Worker veröffentlichen kurzlebige Queue-Lebenszeichen; der Betriebsstatus meldet fehlende oder nicht überprüfbare Monitor-Verbraucher. | Compose-Konfiguration, Ablauf von Lebenszeichen und Redis-Ausfall. |
| F05 CSV | Vorschau und Speicherung verwenden pro Ticker die letzte Zeile. Die Ermittlung ist linear; auch direkte und parallele Repository-Aufrufe erzeugen dadurch keine Duplikate. | Wiederholter/gleichzeitiger Import eines bekannten Instruments ohne offene Position. |
| F06 Stopps | Das Formular unterscheidet Prozentstopp, Preisstopp und keinen Stopp. Ein expliziter Prozentwechsel löscht den alten Preisstopp. Die API erkennt auch ältere explizite Prozentänderungen. | Wechsel Preis → Prozent → Preis → kein Stopp; Browser-Speicherung. |
| F07 Setup | Datenbankfehler liefern 503. Ein Dateifehler nach Commit wird ausdrücklich als unvollständige Übernahme gemeldet. Der Entwurf bleibt erhalten. Runtime-Dateien werden atomar und mit Modus 0600 geschrieben. Einzelne Schlüssel werden unter Datenbanksperre zusammengeführt. | Datenbankausfall, Dateifehler, erfolgreicher atomarer Schreibvorgang. |
| F08 Geldwerte | Finanzielle Requests lehnen nichtendliche Werte ab; manuelle Gebühren/Steuern müssen nichtnegativ sein. Zusätzliche Datenbankbedingungen verhindern neue nichtendliche Werte in Positionen, Transaktionen und Cashflows. | NaN/±Infinity, CSV und Datenbankmigration. |
| F09 Ratenlimit | Ausschließlich die Transportadresse bestimmt das Kontingent. Die API startet ohne Uvicorn-Proxy-Header-Auswertung; der private Frontend-Proxy entfernt mitgebrachte Forwarding-Header. Client-Schlüssel verfallen und ihre Zahl ist begrenzt. | Wechselnde gefälschte Header, Kapazitätsgrenze und Ablauf. |
| F10 Restore | Die zu stoppenden Dienste werden aus dem gewählten Compose-Modell ermittelt. Ein fehlgeschlagener Stop verhindert weiterhin jeden Restore. | Echter Dump/Restore in isolierten NAS- und Hetzner-Compose-Projekten mit synthetischer Tabelle. |
| F11 Releasevorlage | Beispielwerte und Anleitung verlangen einen erfolgreichen vollständigen Release-SHA; der Schutz vor `latest` bleibt erhalten. | Konfigurationsprüfung und Ablehnung ungeprüfter Tags. |
| F12 Glob-Abhängigkeit | Ausschließlich die Glob-Abhängigkeit des Next-ESLint-Plugins wird auf `tinyglobby` umgelegt. Die verwendete Funktion `globSync`/Verzeichnissuche und alle Next-Lintregeln bleiben aktiv. | Test der tatsächlich aufgelösten Next-Root-Verzeichnisse, Lint und vollständiger npm-Audit. |

## Betrieb

Vor dem Update einen geprüften Postgres-Dump und die bisherige `.env.nas` samt
Release-SHA sichern. Danach Checkout aktualisieren, den veröffentlichten neuen
SHA als `IMAGE_TAG` setzen und `infra/update-nas.sh` ausführen. Vorhandene
Beta-Instanzen werden vom Updater erhalten. Die Zeilen `booking_id` und
`quote_currency` sind optional, damit alte Datensätze weiter gelesen werden.

Das Backend-Ratenlimit ist eine zusätzliche Schutzgrenze mit einem gemeinsamen
Kontingent für Anfragen aus demselben Frontend-Container. Es behauptet keine
unterschiedlichen Nutzeridentitäten aus Browser-Headern. Die getrennte verteilte
Beta-Zulassung bleibt bestehen. Die derzeitige API läuft mit einem Prozess;
bei einer späteren horizontalen Skalierung muss auch dieses zusätzliche
Transport-Limit zentralisiert werden.

Die Datenbankbedingungen sind zunächst `NOT VALID`: PostgreSQL prüft neue und
geänderte Zeilen, verlangt aber keine automatische Korrektur alter Finanzdaten.
Bestehende Anomalien müssen separat und anhand der Originalausführungen geprüft
werden. Für alte manuelle Importkurse ohne Währungskennung wird die bisherige
Positionswährung angenommen; ein alter Währungswechsel ist daraus nicht
rückwirkend rekonstruierbar. Ein Anbieter-Refresh ersetzt solche Kursbeobachtungen.

Python-Locks aktualisieren, mit Python 3.12 und pip-tools:

```sh
cd backend
pip-compile --generate-hashes --strip-extras --output-file requirements.lock pyproject.toml
pip-compile --generate-hashes --strip-extras --extra dev --constraint requirements.lock --output-file requirements-dev.lock pyproject.toml
```

Der Dependency-Audit läuft in CI gesondert und verändert die Paketumgebung der
Anwendungstests nicht. Beide Lock-Dateien müssen zusammen geprüft und committed
werden. Die Runtime-Lockdatei wird auch beim Image-Publishing verwendet.
