# Startseite / Investor-Cockpit

Die Route `/` liest den dedizierten Read-only-Endpunkt `GET /api/v1/home`.
Der Endpunkt aggregiert ausschließlich bereits gespeicherte Workspace-, Markt-,
Daily-Opportunity-, Sell-Ranking-, Portfolio-, Industry-Group-RS- und Stock-
Assessment-Snapshots. Einzelne nicht verfügbare Quellen werden als Teilfehler
im Feld `errors` zurückgegeben; sie lassen die übrigen Bereiche weiter rendern.

Beim Laden werden keine Bewertungs-, Markt-, Industry-Group- oder Provider-Jobs
gestartet. Die Sell-Übersicht verwendet bewusst nur den gespeicherten Ranking-
Snapshot und fällt auf der Startseite nicht auf eine Live-Berechnung zurück.

Die ausführliche operative Workspace-Seite bleibt unter `/workspace` erhalten.
