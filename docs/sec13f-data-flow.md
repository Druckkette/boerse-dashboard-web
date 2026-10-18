# SEC-13F: Datenstand und Einzelmeldungen

Die SEC-Gesamtpakete enthalten Einreichungen eines dreimonatigen Veröffentlichungsfensters. Dieses Fenster und die darin gemeldeten Bestandsstichtage sind unterschiedliche Daten. Ein Paket bis August enthält überwiegend Bestände zum 30. Juni. Frühe Meldungen zum 30. September können bereits vor der regulären Novemberfrist verfügbar sein.

Der bestehende tägliche Berichtspflege-Worker prüft weiterhin die SEC-Paketliste. Zusätzlich paginiert er die EDGAR-Suche für `13F-HR` einschließlich `13F-HR/A` ab dem Tag nach dem neuesten Paketfenster. Sehr große Suchfenster werden aufgeteilt, damit die Ergebnisgrenze keine Meldungen verschluckt. Die für die beiden Vergleichsperioden und neue Quartale relevanten vollständigen Einreichungen werden geladen. Ältere Nachmeldungen erscheinen in der Trefferzahl, ändern aber nicht diese beiden Vergleichsperioden.

Originaleinreichungen bleiben unter `sec13f/filings/` im persistenten Docker-Volume `backend_cache` als Gzip-Dateien mit SHA-256-Nachweis erhalten. Sie haben keine zeitgesteuerte Löschung und bleiben bei Imagewechseln erhalten. Dieses Volume muss bei einer vollständigen NAS-Sicherung mitgesichert werden; ein Datenbank-Dump allein enthält keine Originaldateien. Die Datenbank enthält die berechneten Trends, Quellenprüfstände und vorläufigen Aktienzusammenfassungen. Ein verlorenes Volume kann aus SEC-Quellen neu aufgebaut werden, soweit diese weiterhin erreichbar sind.

Ein vollständiges SEC-Submission-Dokument liefert Deckblatt und Informationstabellen. Managerkennung, Stichtag, Korrekturtyp und angekündigte Zeilenanzahl werden geprüft. Ein nachweislich leerer Bericht mit einer vollständigen Null-Platzhalterzeile gilt als leer. Widersprüchliche Quelldokumente werden separat archiviert, gezählt und nicht als Ersatz geprüfter Bestände verwendet. Abruf- oder Suchfehler brechen die Aktualisierung ab; sie setzen den Quellenprüfstand nicht erfolgreich fort.

`RESTATEMENT` ersetzt die vorherige Meldung desselben Managers und Quartals. `NEW HOLDINGS` ergänzt sie. Gleiche Zugangsnummern werden einmal ausgewählt. Neue Quartale bleiben vorläufig und werden separat angezeigt; sie ersetzen keinen vollständigen Quartalsvergleich und beeinflussen dessen Trend-Score nicht. Die Darstellung vergleicht keine Teilmenge früher Melder mit der Gesamtheit des Vorquartals. Eine Korrektur ohne verbleibenden Bestand entfernt eine alte Vorschau im aktualisierten Aktienumfang.

Ein gemeinsames PostgreSQL-Advisory-Lock verhindert überschreibende gleichzeitige Aktualisierungen. Der vorhandene gemeinsame SEC-Rate-Guard begrenzt auch die parallelen Dokumentabrufe. Originale werden aus dem geprüften lokalen Archiv wiederverwendet; Informationstabellen werden ohne das gesamte Quartal im Arbeitsspeicher in das ergänzende ZIP geschrieben.

Die Setup-Meldung unterscheidet eine zu alte Berichtsperiode von fehlender Aktienabdeckung. Der dortige Aktualisierungsknopf bedient das gesamte aktive US-Aktienuniversum. Eine vollständige Abdeckung wird nicht behauptet, solange Aktien ohne passende, belegbare 13F-Daten verbleiben.

Die neue und die klassische UI bleiben über den vorhandenen Umschalter erreichbar. Der vollständige Rücksprung auf das Release vor der UI-Umstellung wird nach dieser Backendkorrektur vom bestehenden Schutz im Rollback-Skript abgelehnt: Er würde auch den korrigierten 13F-Import zurücknehmen. Der Browser-Umschalter benötigt diesen Rücksprung nicht.

Quellen: [SEC-Datenpakete](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets), [SEC-FAQ zu Fristen und Korrekturmeldungen](https://www.sec.gov/rules-regulations/staff-guidance/frequently-asked-questions-about-form-13f).
