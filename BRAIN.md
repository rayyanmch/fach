# BRAIN.md – Topologie, Invarianten, Entscheidungen

Semantisches Gedächtnis des Projekts (siehe AGENT.md). Vor Änderungen lesen, nach Entscheidungen
aktualisieren. Kurz halten: nur was nicht im Code steht oder dort schwer zu sehen ist.

## Was Fach ist

Desktop-App (Windows zuerst, macOS später) für Studierende der Uni Köln: holt Unterlagen aus ILIAS
über PFERD, legt sie pro Kurs in einen Ordner, gleicht automatisch ab (auch wenn die App zu ist).
Zielgruppe ausdrücklich auch ohne Technikwissen → Onboarding ohne Konfigurationsdateien.

## Karte

```
ui/ (Vanilla-JS, ES-Module)          ← nur über HTTP + Token
  └─ server/http.py  (aiohttp, 127.0.0.1, Guard: Token/Host/Origin, CSP; registriert alle Routen)
       ├─ server/api.py        (Zustand, Kurse/Module, Einstellungen, Öffnen; Pfad-/Dateiregeln)
       ├─ server/files_api.py  (Datei-Browser: Liste, Suche, Öffnen mit, Kopieren, Umbenennen, Papierkorb, Ziehen)
       ├─ server/exams_api.py  (Klausuren: wählen, eigene, ausblenden, ICS)
       ├─ server/system_api.py (eigene Titelleiste, Updates)
       ├─ sync/engine.py   (Abgleich, Sperre, Verlauf, Mitteilungen) + sync/progress.py (Prozent/Restzeit)
       │    └─ ilias/models.IliasBackend  ← Protokoll
       │         ├─ ilias/real.py  → ilias/pferd_runtime.py → PFERD 3.10.1 (gepinnt)
       │         └─ ilias/demo.py  (Demo-ILIAS, Platzhalter-PDFs + echte Orga-PDFs mit Klausurterminen)
       ├─ insights/exams.py + service.py (Klausurtermine aus PDFs, im Hintergrund nach jedem Abgleich)
       ├─ sync/timeline.py (Semester-Takt, Speicher, Hover-Daten aus Datei-mtimes)
       ├─ update.py        (latest.json aus GitHub-Releases, SHA-256, stiller Installer)
       ├─ core/*  (config.json, fach.db, Sperre, Bus, Uni-Profil, Namen/Module, Zeitplan-Rechnung)
       └─ platform/* (Aufgabenplanung/launchd, Mitteilungen, Öffnen, Öffnen mit, Zwischenablage, Papierkorb;
                      windows_window.py = rahmenloses Fenster + natives Datei-Ziehen)
app.py = Kompositionswurzel (einziger Ort, der alles zusammensteckt)
desktop.py = Startmodi: Fenster (pywebview, unter Windows rahmenlos) | Browser | --sync (Hintergrund + stilles Update)
```

Abhängigkeitsrichtung: ui → server → (sync, core, platform) → ilias → PFERD. Nie umgekehrt.

**Anker (höchste Zentralität):** `core/config.py` (Datenmodell), `sync/engine.py`, `server/api.py`,
`ilias/pferd_runtime.py` (einzige Stelle mit PFERD-Interna).

## Brücken (wo der Zustand zwischen Teilen lebt)

| Brücke | Mechanik | Was schiefgehen kann |
|---|---|---|
| UI ↔ Server | fetch + `X-Fach-Token`, SSE `/api/events?token=` | Token weg nach Reload ohne sessionStorage → „Bitte über die App öffnen“ |
| Fenster ↔ Server | Server im Hintergrund-Thread mit eigenem asyncio-Loop; pywebview im Haupt-Thread | Ordnerdialog muss per `run_in_executor` vom Loop aus gerufen werden |
| GUI-Prozess ↔ Hintergrund-Prozess | `sync.lock` (flock/msvcrt), `instance.json` (Port+Token, 600), SQLite WAL | `--sync` übergibt an offenes Fenster; sonst läuft es selbst. Sperre gibt das OS beim Prozessende frei |
| Engine ↔ PFERD | `FachCrawler` (Unterklasse), `AppAuthenticator`, Modul-`urljoin` ersetzt | PFERD-Update ändert Interna → Version gepinnt, Tests gegen Schein-ILIAS |
| config.json ↔ OS-Zeitplan | `Api.reconcile_schedule()` bei Start + jeder Zeitplan-Änderung | Zeitplan ist **abgeleitet**, nie Quelle der Wahrheit |
| Datei-Browser ↔ PFERD | Umbenennen/Papierkorb schreiben `Course.rules` → `pferd_runtime.rules_transform()` | ohne Regel lädt der nächste Abgleich das Original wieder herunter |
| UI ↔ rahmenloses Fenster | `POST /api/window` → `WindowsChrome` → `BeginInvoke` auf den WinForms-UI-Thread → `WM_NCLBUTTONDOWN` | Klick muss noch gedrückt sein, wenn die Nachricht ankommt (HTTP-Latenz ~20 ms) |
| Hintergrund-Thread ↔ SQLite | Klausur-Scan und Timeline laufen im Executor | **keine** DB-Zugriffe im Executor – eine Verbindung, ein Thread (Daten vorher/nachher im Loop) |

## Invarianten

1. Passwort nur im System-Passwortspeicher, nie in Dateien/Logs. Gespeichert erst **nach** erfolgreichem Login.
2. Höchstens ein Abgleich gleichzeitig, prozessübergreifend.
3. `on_conflict = local-first`: eigene Dateien/Notizen werden nie überschrieben oder gelöscht.
4. Erster Abgleich eines Kurses (`initial`) erscheint nicht im Eingang.
5. Dateien werden nur über Verlaufs-IDs/Kurs-IDs geöffnet; Pfad muss im Uni-Ordner liegen; ausführbare
   Dateien (`platform.base.RISKY_SUFFIXES`) werden nur im Ordner gezeigt.
6. Dateinamen aus ILIAS sind fremde Daten → UI setzt Text nur per `textContent` (`dom.h`), CSP ohne Inline-Skripte.
7. PFERD-Berichte und Cookies liegen im App-Datenordner (`data/pferd/`), nicht im Uni-Ordner.
8. Kursänderungen erst prüfen, dann umbenennen/speichern (`_apply_courses` → `_commit`), nie halb.
9. Nur `app.py` kennt konkrete Implementierungen; Demo-Modus fasst nie den echten Zeitplan oder Schlüsselbund an.
10. Ein Modul = erster Ordnerteil (`Course.module`). Kursordner dürfen nicht ineinander liegen (sonst überschneiden sich
    PFERD-Ausgabeordner). Verschieben passiert zweiphasig (`_commit`): erst alles zur Seite, dann ans Ziel.
11. Pro Modul höchstens ein gewählter Klausurtermin. Gefundene Termine sind Vorschläge mit Quelle, nie stillschweigend „wahr“.
12. Updates nur über den Installer, nur wenn Fach per Installer installiert ist, nur mit passender SHA-256 aus latest.json,
    nie während Einrichtung oder Abgleich.

## Entscheidungen (kurz, mit Grund)

- **pywebview + lokaler aiohttp-Server statt Electron/Tauri.** PFERD ist Python → ein Laufzeitsystem, eine
  Sprache, aiohttp ist durch PFERD schon da. Server statt reiner js_api: Oberfläche ist im Browser testbar,
  und fehlt WebView2, läuft sie im Standardbrowser weiter.
- **Laufzeit-Fixes statt Datei-Patch** (`~/ilias-sync/patch-pferd.py`): in der gebauten App gibt es keine
  .py-Dateien zum Patchen. `fixed_urljoin` greift nur bei der nackten Basisadresse → harmlos, falls PFERD
  es selbst behebt. Bewiesen durch `tests/test_ilias.py` (ohne Fix scheitert der Login wie in Köln).
- **Ein Crawler pro Kurs, Kurse über „Meine Kurse und Gruppen“ gefunden** – PFERDs Dashboard-Ziel findet in
  Köln nichts (neue `goto.php/crs/ID`-Links). Parser erkennt drei Linkformen.
- **OS-Zeitplan statt Tray-Icon/Autostart.** Läuft ohne offene App, holt verpasste Läufe nach
  (Windows `StartWhenAvailable`, launchd koalesziert). Zufälliger Versatz in der App, nicht im OS → ein Codepfad.
- **Windows-Aufgabe ohne Ordner** („Fach ILIAS-Abgleich“ im Stamm): Unterordner anlegen kann Adminrechte brauchen.
- **Toasts per PowerShell + WinRT, Daten per Umgebungsvariable** – keine Zusatzpakete, keine String-Injektion.
  App-ID `Fach.Desktop` per Installer-Verknüpfung und HKCU-Registry.
- **Semester-Takt aus Datei-mtimes:** PFERD setzt das Upload-Datum → volle Historie schon nach dem ersten Lauf.
- **Vanilla-JS ohne Build-Schritt:** nichts zu bündeln, PyInstaller nimmt die Dateien wie sie sind.
- **Restzeit in Zeit, nicht in Dateien:** PFERD kennt die Dateizahl erst am Ende. Dauer je Kurs wird in `course_stats`
  gemerkt (erster Abgleich und normale getrennt); ohne Grundlage zeigt die UI „wird geschätzt“ statt einer erfundenen Zahl.
- **Module automatisch, Umzug nur mit Zustimmung:** Neue Einrichtungen werden gleich gruppiert; bestehende bekommen
  einen Vorschlag im Kurse-Tab, weil dabei Dateien verschoben werden.
- **Klausuren aus PDFs mit pypdf:** Orga-artige Dateien ganz, sonst erste 12 + letzte 6 Seiten. Anmelde-, Einsichts-,
  Bonus- und Abgabedaten werden ausgeschlossen. Demo enthält echte Text-PDFs, damit der Tab ohne Uni testbar ist.
- **Updates über `releases/latest/download/latest.json`** statt GitHub-API: kein Rate-Limit (Wohnheim-NAT!).
- **Eigene Titelleiste wie Tauri/wry:** rahmenlos + `WM_NCLBUTTONDOWN` (Ziehen/Skalieren macht Windows). Maximieren
  selbst gebaut (rahmenlose WinForms würden die Taskleiste verdecken). Abschaltbar: Einstellungen → Fenster.

## Nicht verifiziert (ehrlich)

- **Kurssuche gegen echtes ILIAS Köln** – am 06.11.2026 abends war ILIAS nicht erreichbar (Timeout, auch
  außerhalb der Sandbox). Parser ist gegen synthetisches HTML getestet. **Erster echter Lauf: prüfen, ob
  „Meine Kurse“ alle Kurse liefert.** Fallback in der UI: Kurs per Link hinzufügen.
- **Windows:** In CI laufen alle Tests, und `Fach.exe --selftest` bestätigt im fertigen Paket PFERD + Fix,
  `WinVaultKeyring`, pywebview 6, pypdf, Oberfläche. 0.1 lief bei Rayyan auf Windows (07.11.2026).
  **In 0.2 neu und nur auf Windows prüfbar:** rahmenloses Fenster (Ziehen, Kanten, Doppelklick, Maximieren),
  natives Datei-Ziehen nach außen, Kopieren als Datei (CF_HDROP), „Öffnen mit“, Papierkorb, stilles Update mit Neustart.
  Fehler davon landen in `%LOCALAPPDATA%\Fach\logs\app.log`. → Checkliste in README.
- **Auto-Update:** Repo ist seit 07.11.2026 öffentlich; `latest.json` und Installer sind anonym abrufbar, der Updater
  wurde gegen v0.2.0 geprüft (Check + Download + SHA-256). Der Neustart nach stillem Update ist nur auf Windows prüfbar.
- macOS-Build und launchd mit gebauter App ungetestet (nicht Ziel dieser Runde).

## Entwicklung

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/fach --serve --demo --dev --port 6230   # Oberfläche im Browser, Demo-ILIAS, Token "dev"
.venv/bin/python -m pytest -q
```
`--home PFAD` legt alle App-Daten in PFAD (nie mit echten Daten testen). Beim Testen ohne `--demo` installiert
der Server-Start einen echten Zeitplan (launchd/Aufgabenplanung), sobald `onboarded` – vorsichtig sein.

## Offene Fragen an Rayyan

- Name „Fach“ ist ein Arbeitstitel (Doppelsinn: Studienfach / Postfach). Passt er?
- Commits tragen die Uni-Mail (zeigt die Kennung). Für künftige Commits die GitHub-noreply-Adresse nehmen?
- Soll Fach deine bestehende Ordnerstruktur (eigene PFERD-Regeln) übernehmen können? → Idee 8 in docs/IDEEN.md.
