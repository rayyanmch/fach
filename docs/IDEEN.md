# Feature-Ideen: vom Downloader zum Semester-Begleiter

Stand 06.11.2026 · nichts davon ist gebaut. Die Architektur ist aber so geschnitten, dass jede Idee an
einer klaren Stelle andockt (siehe „Andockstelle“).

## Worum es eigentlich geht

Fach beantwortet heute eine Frage: **„Was ist in ILIAS neu?“** Das spart Klicks, ist aber austauschbar –
jeder PFERD-Nutzer hat das schon. Studierende haben im Semester vier Aufgaben, bei denen ihnen niemand hilft:

| Aufgabe | Heute | Schmerz |
|---|---|---|
| **Nichts verpassen** – Fristen, Ausfälle, geänderte Folien | ILIAS, KLIPS, Mails, Orga-Folien | verstreut, man merkt es zu spät |
| **Wiederfinden** – „wo kam das nochmal dran?“ | Ordner durchklicken, PDFs einzeln öffnen | kostet in der Klausurphase Stunden |
| **Lernen planen** – wie viel ist es, wie weit bin ich? | Bauchgefühl | Rückstand fällt erst im Februar auf |
| **Ordnung halten** – über Semester hinweg | jedes Semester neu sortieren | genau hier geben Nicht-Techniker auf |

Jede Idee unten zahlt auf eine dieser Aufgaben ein. Ein Beleg, dass das nicht ausgedacht ist: Deinen
`Semesterplan_WiSe_2026-27.md` (Klausuren, Fristen, Zulassungen) hast du von Hand aus den Orga-Folien
zusammengetragen. Genau das kann Fach automatisch – die Folien liegen ja schon auf der Platte.

**Leitplanken für alles:** Nichts verlässt den Rechner außer Richtung ILIAS. Kein Konto, keine Statistik.
Funktioniert ohne Einstellungen. Schont den ILIAS-Server. Respektiert Urheberrecht.

Aufwand: **S** ≈ ein Abend, **M** ≈ ein Wochenende, **L** ≈ mehrere Wochenenden.

---

## Meine Empfehlung: diese drei zuerst

1. **Semesterwechsel-Assistent** (S) – der nächste Wechsel kommt im April 2027. Wenn Fach dann nicht
   hilft, ist es für Nicht-Techniker das Ende.
2. **Fristen-Radar** (M) – der größte neue Nutzen, und dein eigener Semesterplan beweist den Bedarf.
3. **Volltextsuche** (M) – rechtzeitig vor der Klausurphase (ab Februar 2027) fertig.

**Vor einer breiten Verteilung außerdem: Folien-Versionen** (siehe 3). Dahinter steckt eine Lücke im
heutigen Verhalten, keine Kür.

---

## Erste Reihe

### 1 · Fristen-Radar – Abgaben, Klausuren, Anmeldungen
**Was:** Eine Liste „Als Nächstes“ mit allen Fristen aller Kurse, Erinnerungen 3 Tage und 1 Tag vorher,
dazu eine Kalenderdatei (ICS) zum Abonnieren in Google/Outlook/Apple-Kalender.
**Woher die Daten kommen:**
- ILIAS-Übungen haben echte Abgabetermine (PFERD kennt den Elementtyp `EXERCISE` schon).
- ILIAS bietet für den persönlichen Kalender einen iCal-Export (Kurstermine, Sitzungen).
- Orga-PDFs: Datumsangaben in der Nähe von Wörtern wie *Klausur, Abgabe, Anmeldung, Zulassung,
  Bonustest* erkennen. Erkanntes erscheint als **Vorschlag mit Quelle** („Orga_Folien.pdf, S. 4“) und wird
  erst nach einem Klick übernommen – Texterkennung irrt, eine falsche Klausurzeit darf nie stillschweigend
  im Kalender landen.

**Andockstelle:** neues Modul `fach/insights/deadlines.py`, liest nach jedem Abgleich die neuen Dateien;
Speicher in `fach.db` (Tabelle `deadlines`). Übersicht bekommt einen Block über dem Semester-Takt.

### 2 · Volltextsuche über alle Unterlagen
**Was:** Ein Suchfeld (Strg K), Treffer **auf Seitenebene** mit Textausschnitt, über alle Kurse und
Semester. „Kapitalwertmethode“ → BWL, Woche 4, Folie 17. Klick öffnet das PDF an der Stelle.
**Wie:** Text pro Seite extrahieren (pypdf/pdfium), in SQLite FTS5 ablegen – lokal, schnell, ein paar MB.
Indexiert wird im Hintergrund nach jedem Abgleich, nur neue/geänderte Dateien.
**Haken:** Eingescannte Folien haben keinen Text (OCR wäre L). Das Springen zu einer Seite klappt nicht in
jedem PDF-Programm – Fach kann aber selbst einen Betrachter mitbringen (pdf.js läuft im App-Fenster).
**Andockstelle:** `fach/insights/search.py` + Seite „Suche“; Index-Aufbau als Nachlauf im Sync-Engine-Ereignis
`run_done`.

### 3 · Folien-Versionen & „was hat sich geändert?“
**Problem heute:** Lädt eine Dozentin korrigierte Folien hoch und du hast die alte Datei schon markiert
oder kommentiert, behält Fach (richtigerweise) deine Datei – **und die neue Version geht still verloren**.
Du merkst nicht, dass Folie 12 einen Fehler hatte.
**Was:** Bei Änderungen die alte Version behalten (`Folien_06 (Version vom 03.11.).pdf`), in der Übersicht
„aktualisiert: Seiten 12–14 anders“ zeigen (Textvergleich pro Seite). Bei einem Konflikt mit deiner
bearbeiteten Datei: neue Version daneben legen und Bescheid sagen statt verwerfen.
**Andockstelle:** `pferd_runtime.FachCrawler` (Konfliktentscheidung) + Datei-Ereignis `changed` im Verlauf,
das es schon gibt.

### 4 · Semesterwechsel-Assistent
**Was:** Fach merkt, dass ein neues Semester begonnen hat (Semesterdaten im Uni-Profil, neue Kurse in
„Meine Kurse“) und bietet in einem Schritt an: neue Kurse übernehmen, alte nicht mehr abgleichen,
alte Ordner nach `Uni/WiSe 2026-27/` verschieben. Kürzel und Ordnernamen aus dem letzten Semester
werden für gleichnamige Folgekurse vorgeschlagen („Mathe I“ → „Mathe II“).
**Andockstelle:** `core/university.py` (Semester gibt es schon) + Banner in der Übersicht + vorhandene
Kurssuche (`/api/discover`).

### 5 · Lern-Eingang: was habe ich schon durchgearbeitet?
**Was:** Der Textmarker wird zum Fortschritt: pro Kurs und Woche „3 von 4 gelesen“, vor der Klausur ein
ehrlicher Rückstand („23 Folien-PDFs nie geöffnet, 9 davon BWL“). Abhaken auch von Hand.
**Haken:** Fach sieht nur, was über Fach geöffnet wird. Öffnen per Explorer bleibt unsichtbar (das
Zugriffsdatum von Dateien ist unter Windows unzuverlässig). Deshalb: manuelles Abhaken als Hauptweg.
**Andockstelle:** `files.opened_at` existiert schon; neue Ansicht pro Kurs.

---

## Zweite Reihe

### 6 · Ankündigungen und Forum, gefiltert
ILIAS-„Neuigkeiten“ pro Kurs einsammeln (ILIAS hat dafür einen persönlichen RSS-Feed mit Token; PFERD
kann Foren) und nur das Wichtige als Mitteilung schicken: *fällt aus, verschoben, Raumänderung, Klausur*.
Alles andere als ruhige Liste. Ausfälle verpasst man heute am häufigsten. **M**

### 7 · Stundenplan aus KLIPS + „vor der Vorlesung“
KLIPS 2.0 kann den persönlichen Stundenplan als iCal exportieren. Fach ordnet Termine den Kursen zu
(Titelähnlichkeit, Bestätigung durch dich) und meldet 30 Minuten vorher: *„ISM in 30 Min – Folien 06 sind
da“*. Im Semester-Takt erscheinen die Vorlesungstage als feine Markierung. **M**

### 8 · Ordnungsregeln & Vorlagen von der Fachschaft
Heute spiegelt Fach die ILIAS-Struktur. Deine handgeschriebenen PFERD-Regeln (Folien → Vorlesung,
Übungsblätter → Übungen) werden zu **Vorlagen**: Vorher/Nachher-Vorschau als Baum, ein Klick zum
Anwenden. Vorlagen sind reiner Text ohne Kursmaterial und lassen sich über ein öffentliches Repository
teilen – die Fachschaft pflegt sie für große Veranstaltungen wie BWL einmal für alle. **M–L**

### 9 · Lernplan bis zur Klausur
Baut auf 1, 2 und 5 auf: Klausurtermin + Stoffmenge (Seiten pro Kurs aus dem Index) + Lesestand →
Wochenplan („BWL: ~46 Folien pro Woche bis 24.03.“), als Kalenderdatei. **M**

### 10 · Doppelte Dateien erkennen
Gleicher Inhalt unter zwei Namen (bei dir: `SE_01_Introduction.pdf` = `01_Introduction.pdf`), dieselbe Datei
in Vorlesung und Übung. Per Prüfsumme erkennen, zusammenfassen oder markieren. **S**

---

## Dritte Reihe

- **Aufs Handy** – Uni-Ordner in OneDrive/iCloud legen, Fach erklärt die Fallstricke (unter Windows können
  OneDrive-Platzhalterdateien die Konflikterkennung verwirren – vorher testen). **S**
- **Videos mit Verstand** – Aufzeichnungen nur im WLAN und am Netzteil, nur die letzten Wochen, nach der
  Klausur aufräumen. **M**
- **Wochenrückblick** – Sonntagabend eine Mitteilung: neue Dateien, Fristen der nächsten Woche. **S** (nach 1)
- **Weitere Unis** – das Uni-Profil ist schon ein eigener Baustein (`core/university.py`). Andere
  ILIAS-Hochschulen brauchen ein Profil und einen Testzugang; Shibboleth-Login kann PFERD. **S je Uni**
- **KI-Hilfen, nur auf Wunsch** – Zusammenfassungen und Karteikarten aus Folien. Ehrlich: Folien an einen
  Cloud-Dienst zu schicken ist urheberrechtlich heikel und widerspricht dem Versprechen „nichts verlässt
  den Rechner“. Wenn überhaupt: lokales Modell oder eigener Schlüssel, pro Kurs ausdrücklich einschalten.
  Bewusst ans Ende gestellt. **L**

## Bewusst nicht

- **Dateien oder Altklausuren zwischen Studierenden teilen** – Urheberrecht, Prüfungsordnung, Haftung.
- **Abgaben über Fach hochladen** – Schreibzugriff auf ILIAS heißt: ein Fehler kostet Punkte.
- **Eigener Server oder Konto** – bräche das Vertrauensversprechen (Passwort bleibt lokal) und kostet.

---

## Vor einer Verteilung an viele (keine Features, aber Pflicht)

1. **Mit dem RRZK / ILIAS-Team sprechen.** 500 Studierende × 7 Kurse × täglicher Komplettdurchlauf sind
   echte Last. Fach verteilt die Starts zufällig (bis 20 Min) und lädt nur nacheinander, aber die Uni sollte
   es wissen – und vielleicht sagen, welches Zeitfenster ihr lieber ist. Nutzungsbedingungen prüfen.
2. **Code-Signatur für Windows.** Unsigniert zeigt Windows „Der Computer wurde durch Windows geschützt –
   unbekannter Herausgeber“. Das schreckt genau die Zielgruppe ab. Wege: Azure Trusted Signing (günstig,
   Verfügbarkeit für Einzelpersonen in der EU prüfen) oder ein OV-Zertifikat (~200–400 €/Jahr). Bis dahin
   die Warnung in der Anleitung mit Bild erklären.
3. **macOS:** Ohne Apple-Entwicklerkonto (99 €/Jahr) und Notarisierung blockiert Gatekeeper die App.
4. **Updates.** ILIAS-Updates können PFERD brechen, dann müssen Korrekturen schnell bei allen ankommen:
   Versionsprüfung gegen GitHub-Releases (ohne Telemetrie), Installer herunterladen, Signatur prüfen.
5. **Öffentlicher Quellcode.** Wer sein Uni-Passwort eintippt, will nachsehen können, was damit passiert.
   Builds laufen deshalb schon jetzt nachvollziehbar über GitHub Actions.
6. **Datenschutz-Hinweis** in einfacher Sprache: was liegt wo, was geht wohin (nur ILIAS).
