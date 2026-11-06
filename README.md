# Fach

**Deine Unterlagen aus ILIAS, jeden Morgen auf deinem Rechner.**
Für Studierende der Uni Köln – auch ohne Technikwissen in zwei Minuten eingerichtet.

> Inoffizielles Projekt von Studierenden. Nicht von der Uni Köln oder dem RRZK.

## Was Fach macht

- **Findet deine Kurse selbst.** Einmal mit der Uni-Kennung anmelden, Kurse aus diesem Semester sind
  vorausgewählt.
- **Ein Ordner pro Modul** in `Dokumente\Uni` (änderbar). Deine eigenen Notizen und markierten PDFs darin
  überschreibt oder löscht Fach nie.
- **Gleicht automatisch ab**, standardmäßig jeden Morgen um 7 Uhr – auch wenn die App geschlossen ist.
  War der Rechner aus, wird es nachgeholt.
- **Zeigt, was neu ist** – wie mit dem Textmarker markiert, bis du die Datei öffnest. Auf Wunsch als
  Mitteilung.
- **Module statt Kurs-Wirrwarr:** Vorlesung und Übung eines Fachs landen in einem Ordner (`Visualisierung/Vorlesung`,
  `Visualisierung/Übung`).
- **Semester-Takt:** wann welches Modul hochgeladen hat – mit Details beim Drüberfahren.
- **Klausuren:** Fach findet Termine in deinen Orga-Folien, du wählst pro Modul einen, Kollisionen werden markiert,
  alles als Kalenderdatei exportierbar. Verbindlich bleibt KLIPS.
- **Dateien:** ein eigener Explorer für den Uni-Ordner – Doppelklick öffnet mit deinem PDF-Programm, Rechtsklick für
  Öffnen mit, Kopieren, Umbenennen, Papierkorb; Dateien lassen sich direkt in andere Programme ziehen (z. B. in einen
  KI-Chat). Umbenannte oder gelöschte Dateien lädt Fach nicht erneut herunter.
- **Updates von selbst** – beim Start und im Hintergrund; in den Einstellungen auch auf Knopfdruck.

**Dein Passwort** bleibt auf deinem Rechner, in der Windows-Anmeldeinformationsverwaltung bzw. im
macOS-Schlüsselbund. Fach spricht nur mit `www.ilias.uni-koeln.de` – keine eigenen Server, keine Statistik.

## Installieren (Windows)

1. `Fach-Setup-x.y.z.exe` herunterladen und starten. Es braucht **keine Administratorrechte**.
2. Windows warnt eventuell „Der Computer wurde durch Windows geschützt“, weil die App (noch) nicht signiert
   ist: **Weitere Informationen → Trotzdem ausführen**.
3. In Fach mit Uni-Kennung und Passwort anmelden, Kurse bestätigen, fertig.

Deinstallieren über *Einstellungen → Apps*. Der automatische Abgleich wird dabei entfernt, deine Dateien bleiben.

**Updates:** Ab Version 0.2 aktualisiert sich Fach selbst – beim Start, alle sechs Stunden und nach dem
Hintergrund-Abgleich. Der Installer kommt von den GitHub-Releases dieses Projekts und wird vor dem Start gegen eine
Prüfsumme geprüft. Abschalten: *Einstellungen → Updates*.

---

## Für Entwickler

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"          # Windows: .venv\Scripts\pip ...
.venv/bin/fach --serve --demo --dev        # Oberfläche im Browser, mit Demo-ILIAS
.venv/bin/python -m pytest -q
```

| Befehl | Zweck |
|---|---|
| `fach` | App-Fenster (braucht `pip install -e ".[window]"`, sonst Browser) |
| `fach --demo` | Demo-ILIAS: jede Kennung geht, Passwort „falsch“ zeigt den Fehlerfall |
| `fach --sync` | ein Abgleich ohne Fenster (so ruft die Aufgabenplanung Fach auf) |
| `fach --home PFAD` | alle App-Daten in `PFAD` – zum gefahrlosen Testen |

Architektur, Invarianten und Entscheidungen: **[BRAIN.md](BRAIN.md)**. Feature-Ideen: **[docs/IDEEN.md](docs/IDEEN.md)**.

### Bauen

Windows-Installer und portable ZIP baut GitHub Actions bei jedem Push auf `main`
(Actions → letzter Lauf → Artefakt **Fach-Windows**). Ein Tag `v*` erzeugt zusätzlich ein Release.
Lokal unter Windows:

```bash
pip install -e ".[window]" pyinstaller
pyinstaller --noconfirm packaging/fach.spec
iscc packaging\windows\fach.iss
```

### Auf Windows testen – Checkliste

Diese Teile laufen in CI nur automatisiert, nicht mit echter Oberfläche:

- [ ] Installer läuft ohne Admin-Abfrage, Startmenü-Eintrag „Fach“ erscheint
- [ ] Fenster öffnet (WebView2); zweiter Start holt das Fenster nach vorne statt ein zweites zu öffnen
- [ ] Demo durchklicken: Startmenü-Verknüpfung kopieren, Ziel `Fach.exe --demo`
- [ ] Echter Login + Kurssuche (findet „Meine Kurse“ alle Kurse?)
- [ ] Einstellungen → Speicherort → „Ändern“ öffnet den Windows-Ordnerdialog
- [ ] Aufgabenplanung: Aufgabe „Fach ILIAS-Abgleich“ existiert (`taskschd.msc`), „Ausführen“ startet einen Abgleich ohne Fenster
- [ ] Mitteilung nach automatischem Abgleich mit neuen Dateien (Absender „Fach“)
- [ ] Datei in der Übersicht anklicken öffnet sie; Ordner-Symbol zeigt sie im Explorer
- [ ] Deinstallieren entfernt die Aufgabe, Uni-Ordner bleibt

Neu in 0.2:

- [ ] Eigene Titelleiste: ziehen, an Kanten/Ecken Größe ändern, Doppelklick maximiert (Taskleiste bleibt frei), Minimieren über Taskleisten-Klick
- [ ] Notfalls: *Einstellungen → Fenster → Windows-Titelleiste* und Fach neu starten
- [ ] Dateien: eine PDF in Chrome/Edge (z. B. einen KI-Chat) ziehen → wird als Kopie hochgeladen
- [ ] Rechtsklick → Kopieren, dann im Explorer Strg V; „Öffnen mit …“ zeigt den Windows-Dialog
- [ ] In den Papierkorb → Datei liegt im Windows-Papierkorb und kommt beim nächsten Abgleich nicht wieder
- [ ] Erster Abgleich: Prozent, Restzeit und MB laufen mit
- [ ] Update: nach Veröffentlichung von 0.2.1 startet Fach von selbst neu in der neuen Version

Fehler aus Fenster und Updater stehen in `%LOCALAPPDATA%\Fach\logs\app.log`.

Wo Fach seine Daten ablegt: `%APPDATA%\Fach` (Einstellungen), `%LOCALAPPDATA%\Fach` (Verlauf, Protokolle unter `logs\`).

## Lizenz

MIT – siehe [LICENSE](LICENSE). Enthaltene Fremdsoftware: [THIRD_PARTY.md](THIRD_PARTY.md).
