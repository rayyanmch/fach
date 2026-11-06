# Fach

**Deine Unterlagen aus ILIAS, jeden Morgen auf deinem Rechner.**
Für Studierende der Uni Köln – auch ohne Technikwissen in zwei Minuten eingerichtet.

> Inoffizielles Projekt von Studierenden. Nicht von der Uni Köln oder dem RRZK.

## Was Fach macht

- **Findet deine Kurse selbst.** Einmal mit der Uni-Kennung anmelden, Kurse aus diesem Semester sind
  vorausgewählt.
- **Ein Ordner pro Kurs** in `Dokumente\Uni` (änderbar). Deine eigenen Notizen und markierten PDFs darin
  überschreibt oder löscht Fach nie.
- **Gleicht automatisch ab**, standardmäßig jeden Morgen um 7 Uhr – auch wenn die App geschlossen ist.
  War der Rechner aus, wird es nachgeholt.
- **Zeigt, was neu ist** – wie mit dem Textmarker markiert, bis du die Datei öffnest. Auf Wunsch als
  Mitteilung.
- **Semester-Takt:** auf einen Blick, wann welcher Kurs Material hochgeladen hat.

**Dein Passwort** bleibt auf deinem Rechner, in der Windows-Anmeldeinformationsverwaltung bzw. im
macOS-Schlüsselbund. Fach spricht nur mit `www.ilias.uni-koeln.de` – keine eigenen Server, keine Statistik.

## Installieren (Windows)

1. `Fach-Setup-x.y.z.exe` herunterladen und starten. Es braucht **keine Administratorrechte**.
2. Windows warnt eventuell „Der Computer wurde durch Windows geschützt“, weil die App (noch) nicht signiert
   ist: **Weitere Informationen → Trotzdem ausführen**.
3. In Fach mit Uni-Kennung und Passwort anmelden, Kurse bestätigen, fertig.

Deinstallieren über *Einstellungen → Apps*. Der automatische Abgleich wird dabei entfernt, deine Dateien bleiben.

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

Wo Fach seine Daten ablegt: `%APPDATA%\Fach` (Einstellungen), `%LOCALAPPDATA%\Fach` (Verlauf, Protokolle unter `logs\`).

## Lizenz

MIT – siehe [LICENSE](LICENSE). Enthaltene Fremdsoftware: [THIRD_PARTY.md](THIRD_PARTY.md).
