# Benachrichtigungen einstellen

Unter **Einstellungen → Überwachung & Alerts** steuert der Abschnitt
**Welche Nachrichten möchtest du erhalten?** den Versand. Änderungen bleiben
zunächst im Entwurf und greifen erst nach **Änderungen speichern**. Verwerfen
stellt den gespeicherten Stand wieder her. Ein fehlgeschlagener Speicherversuch
behält den Entwurf. **Empfohlene Werte übernehmen** bereitet das ruhige
Startprofil als Entwurf vor.

Die Berechnung der Positionen, Durchschnittslinien und Aktienbewertung läuft
unabhängig vom Versandmodus weiter:

| Auswahl | Verhalten |
|---|---|
| Aus | Kein Push und keine Aufnahme dieses Anlasses in die Tagesübersicht |
| Tagesübersicht | Gesammelt zur eingestellten Uhrzeit |
| Sofort | Erster erlaubter Versand; Folgemeldungen können gebündelt oder begrenzt werden |

Für 10-SMA, 21-EMA, 50-SMA und 200-SMA lassen sich **Bruch**, **Rückeroberung**
und **weitere Verschlechterung** getrennt einstellen. Unter der jeweiligen Linie
sind Bestätigung zum Handelsschluss oder Intraday, Bestätigungsdauer,
Mindestabstand in Prozent oder ATR, zusätzliche Verschlechterung in ATR,
Tageslimit, Handelszeit und Priorität einstellbar. Ein Tageslimit von null
bedeutet unbegrenzt. Die Handelsbestätigung erfordert unterschiedliche gültige
Kursbeobachtungen. Zum Handelsschluss werden ausschließlich bestätigte finale
Tageskurse verwendet.
Ein bestätigtes Signal zum neuesten regulären Schlusskurs darf nach
Börsenschluss versendet werden; Ruhezeiten und eigene Versandfenster gelten
weiterhin.

Das ruhige Startprofil bündelt 10-/21-Tage-Linien und meldet nur Brüche der
50-/200-Tage-Linie sofort. Alle Rückeroberungen und zusätzlichen
Verschlechterungen landen in der Übersicht. Intraday gilt eine Bestätigung von
zehn Minuten und ein Mindestabstand von 0,2 ATR. Diese Werte sind veränderbar.

**Stopps und ATR** haben jeweils Versandmodus, Wiederholungsmodus, Handelszeit
und Priorität. Zur Auswahl stehen einmal pro Überwachungstag, erst nach
manuellem Scharfstellen, nach bestätigter Erholung oder nach einer Wartezeit.
Stopps behalten ihren Zustand je Position und konkreter Stoppgrenze. Eine neue
Grenze wird neu bewertet. Im Modus nach Erholung müssen gültige, frische Kurse
die eingestellte Dauer und Erholungsschwelle bestätigen. Fehlende oder
wiederverwendete Kurse sind keine Erholung.

Die erste ATR-Schwelle und die Referenz bleiben im Positionsmonitor
einstellbar. Die zusätzliche Eskalation ist separat abschaltbar und hat eine
eigene absolute ATR-Schwelle; sie muss oberhalb der ersten Warnschwelle liegen.
Die Erholungsschwelle muss bei Wiederholung nach Erholung unter der ersten
Warnschwelle liegen. Der Start ist einmal pro Tag, mit zusätzlicher Eskalation
bei drei ATR. Die bisher gespeicherte Stunden-Cooldown-Zahl ist ein altes
Kompatibilitätsfeld; maßgeblich sind die neuen Wiederholungsregeln.

**Gesamtscore und Aktienurteil** haben getrennte Versandmodi, einen einstellbaren
Mindestabstand beim Score sowie gemeinsame Schalter für Verbesserungen und
Verschlechterungen. Im Startprofil werden beide gesammelt. Fachliche
Einzelkriterien werden als Zusatzinformation in der Übersicht berücksichtigt,
ohne hierfür weitere Sofortmeldungen auszulösen. Verbesserungen werden anhand
der Veränderung beurteilt und nicht allein deshalb als neue Verschlechterung
bezeichnet, weil das Gesamturteil noch schwach ist.

**Bündelung** fasst mehrere gleichzeitig erkannte Anlässe derselben Aktie in
einer Nachricht zusammen. Folgemeldungen können für die eingestellte Sammelzeit
warten. Tageslimits gelten je Aktie beziehungsweise je MA-Linie. Stopps und
ATR-Eskalationen können über sichtbare Schalter Sammelzeit und Tageslimit
umgehen. Ausgeschaltete Regeln gelten auch für bereits wartende Nachrichten.
Außerhalb ihres Versandfensters erkannte MA- und Bewertungsmeldungen werden
in der Übersicht berücksichtigt, damit ein alter Bruch nicht erst am nächsten
Börsenmorgen als neue Sofortmeldung erscheint. Neuere Zustandswechsel ersetzen
überholte vorgemerkte Entwicklungen desselben Anlasses.

**Tagesübersicht** hat einen eigenen Schalter, Uhrzeit, Zeitzone, Kategorien,
Priorität und maximale Aktienzahl. Bereits sofort gemeldete Anlässe können
aufgenommen oder weggelassen werden. Mit **Nur Änderungen aufnehmen** werden
unveränderte Zustände ausgelassen; ohne diesen Schalter können aktuelle,
tatsächlich beobachtete Risikozustände ergänzt werden. Sie werden als zuletzt
beobachteter Zustand bezeichnet, nicht aus alten versandten Meldungen erfunden.
Die reguläre Einstellung ist 22:45 Uhr in Europe/Berlin, höchstens fünf Aktien,
ohne Wiederholung bereits sofort gemeldeter Anlässe.

**Ruhezeiten** haben Start und Ende sowie gesonderte Ausnahmen für Stopps und
ATR-Eskalationen. Ein eigenes Versandfenster ist alternativ zum regulären
Börsenhandel auswählbar. Regulärer Börsenhandel berücksichtigt die Börse der
Aktie einschließlich Feiertagen, verkürzten Sitzungen und Zeitumstellungen.
Ein Überwachungstag beginnt um 07:30 Uhr deutscher Zeit; die Nachbörse bleibt
beim vorangegangenen Handelstag. Versandzeiten verwenden die ausgewählte
Zeitzone. Eine während der Ruhezeit fällige Übersicht bleibt mit ihrem
ursprünglichen Datum vorgemerkt und wird danach zugestellt.

Im **Benachrichtigungsprotokoll** stehen Versand, Bündelung, Vormerkung für die
Übersicht und Unterdrückungsgrund. Die Anzeige zeigt maximal 100 passende
Einträge; gespeichert werden maximal 500. Stopp- und ATR-Warnungen können dort
ausdrücklich manuell erneut scharfgestellt werden. Diese Aktion sendet selbst
keine Nachricht. Der bestehende Pushover-Test wird ebenfalls ausschließlich
bewusst per Knopf ausgelöst.

## Speicherung und Betrieb

Die validierten Einstellungen liegen unter `runtime.notification_preferences`.
Teiländerungen werden tief zusammengeführt; eine MA-Änderung setzt keine
anderen gespeicherten Entscheidungen zurück. Ausdrückliche bisherige
Abschaltungen bleiben bei der Einführung berücksichtigt. Das Startprofil greift
für bestehende aktive Meldungsarten, wenn noch keine neuen Einstellungen
gespeichert wurden. Eine Datenbankmigration ist nicht erforderlich.

Der Dispatcher verwendet `notification_dispatch_state` mit einer
PostgreSQL-Transaktionssperre. Eine dauerhafte Vormerkung wird dem Detektor als
angenommen bestätigt; dadurch entdeckt er dieselbe Meldung nicht fortlaufend
neu. Bestätigte, vorgemerkte und fehlgeschlagene Zustellungen bleiben
nachvollziehbar. Providerfehler werden mit Abstand erneut versucht.
`flush_position_notifications` bearbeitet Warteschlangen und Übersichten
minütlich ohne neue Marktdatenabfragen, auch außerhalb der Kursprüfungszeiten.

Die Texte sind deutsche Sätze mit lesbaren Zahlen, beispielsweise:

> MRNA hat deine Verlustschwelle erreicht. Der Kurs liegt 1,50 ATR unter dem
> Vortagesschluss. Deine Warnschwelle liegt bei 1,50 ATR.

Vergleichszeichen und Formelnotation werden in Benachrichtigungen in Worte
übersetzt. Das verändert weder Berechnung noch Auslöseschwelle.
