"""Klausurtermine in den eigenen Unterlagen finden (Orga-Folien, erste/letzte Vorlesung, Infoblätter).

Grundsatz: Fach schlägt vor, entscheiden tust du. Jeder Fund trägt seine Quelle (Datei, Seite, Zitat),
damit man ihn in Sekunden prüfen kann. Verbindlich bleiben KLIPS und die Ankündigungen der Lehrenden.

Ablauf
1. extract_pages(): Text pro Seite aus einem PDF (pypdf). Orga-artige Dateien ganz, andere nur Anfang/Ende –
   dort stehen Klausurinfos fast immer, und ein Semester hat schnell 15 000 Seiten.
2. find_exams(): In jeder Seite nach Klausur-Stichwörtern suchen und Datumsangaben in der Nähe auswerten.
   Anmelde-, Abgabe- und Einsichtsfristen werden ausgeschlossen – sie sind keine Klausurtermine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterator, Optional

MAX_PDF_BYTES = 40 * 1024 * 1024
FULL_SCAN_MAX_PAGES = 80
HEAD_PAGES, TAIL_PAGES = 12, 6

_ORGA_NAME = re.compile(
    r"orga|organis|info|einf(ü|ue)hrung|introduction|intro\b|kick.?off|(ü|ue)berblick|overview|klausur|pr(ü|ue)fung|"
    r"exam|syllabus|modulbeschreibung|admin|(^|[^\d])0?0[_\s.-]|(^|[^\d])0?1[_\s.-]|lecture.?0?1|vl.?0?1|kapitel.?0",
    re.IGNORECASE,
)

_KEYWORD = re.compile(
    r"(klausur\w*|nachklausur|wiederholungsklausur|nachschreib\w*|pr(ü|ue)fungstermin\w*|pr(ü|ue)fung\b|"
    r"\bexams?\b|\bexamination\b|final exam|resit)",
    re.IGNORECASE,
)
# Was in der Nähe eines Datums steht und es als Nicht-Klausurtermin kennzeichnet
_EXCLUDE = re.compile(
    r"(anmeld|abmeld|registr|einsicht|bonus|probeklausur|testat|abgabe|deadline|zulassung|vorbesprechung|"
    r"sprechstunde|review|inspection|feedback|ergebnis|noten|grades|results|übungsblatt|hausaufgabe|homework)",
    re.IGNORECASE,
)

_MONTHS = {
    "januar": 1, "jan": 1, "january": 1, "februar": 2, "feb": 2, "february": 2, "märz": 3, "maerz": 3, "mär": 3,
    "mrz": 3, "march": 3, "mar": 3, "april": 4, "apr": 4, "mai": 5, "may": 5, "juni": 6, "jun": 6, "june": 6,
    "juli": 7, "jul": 7, "july": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10, "october": 10, "oct": 10, "november": 11, "nov": 11, "dezember": 12, "dez": 12,
    "december": 12, "dec": 12,
}
_MONTH_WORDS = "|".join(sorted(_MONTHS, key=len, reverse=True))

_DATE_PATTERNS = (
    ("dmy", re.compile(r"(?<![\d.])(\d{1,2})\.\s?(\d{1,2})\.(?:\s?(\d{4}|\d{2})(?![\d:]))?")),
    ("dMy", re.compile(rf"(?<!\d)(\d{{1,2}})\.?\s+({_MONTH_WORDS})\.?(?:\s+(\d{{4}}))?", re.IGNORECASE)),
    ("Mdy", re.compile(rf"\b({_MONTH_WORDS})\.?\s+(\d{{1,2}})(?!\d)(?:st|nd|rd|th)?,?(?:\s+(\d{{4}}))?", re.IGNORECASE)),
    ("iso", re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")),
)
_TIME_RANGE = re.compile(
    r"(?<![\d.])(?P<h1>\d{1,2})(?:[:.](?P<m1>\d{2}))?(?![.\d])\s*(?P<a1>am|pm|uhr|h\b)?\s*(?:-|–|—|bis|to|until)\s*"
    r"(?P<h2>\d{1,2})(?:[:.](?P<m2>\d{2}))?(?![.\d])\s*(?P<a2>uhr|h\b|am|pm)?", re.IGNORECASE)
_TIME_SINGLE = re.compile(
    r"(?<![\d.])(?P<h>\d{1,2})[:.](?P<m>\d{2})(?![.\d])\s*(?P<a>am|pm)?|(?<![\d.])(?P<hu>\d{1,2})\s*(?:uhr|(?P<au>am|pm))",
    re.IGNORECASE)
_ROOM = re.compile(
    r"([A-ZÄÖÜ][\wäöüß-]*-?H(ö|oe)rsaal\b[^\n,;]{0,20}|H(ö|oe)rsaal[^\n,;]{0,40}|\bHS\s?[\dA-Z][^\n,;]{0,20}|"
    r"\bAula\b[^\n,;]{0,25}|\bRaum\s[^\n,;]{1,30}|\bRoom\s[^\n,;]{1,30}|lecture hall[^\n,;]{0,30}|\bS\d{2,3}\b)",
    re.IGNORECASE,
)


@dataclass
class ExamFind:
    date: date
    start: str = ""
    end: str = ""
    room: str = ""
    kind: str = "Klausur"
    page: int = 0
    snippet: str = ""
    score: int = 0          # höher = verlässlicher (Stichwort und Datum in derselben Zeile …)


def _year_for(month: int, ref: date) -> int:
    """Jahr für Daten ohne Jahreszahl: im Wintersemester gehören Jan–Sep ins Folgejahr."""
    if ref.month >= 10 and month <= 9:
        return ref.year + 1
    if ref.month <= 3 and month >= 10:
        return ref.year - 1
    return ref.year


def _parse_date(kind: str, m: re.Match, ref: date) -> Optional[date]:
    try:
        if kind == "dmy":
            d, mo = int(m.group(1)), int(m.group(2))
            y = m.group(3)
            year = (int(y) + 2000 if len(y) == 2 else int(y)) if y else _year_for(mo, ref)
        elif kind == "dMy":
            d, mo = int(m.group(1)), _MONTHS[m.group(2).lower()]
            year = int(m.group(3)) if m.group(3) else _year_for(mo, ref)
        elif kind == "Mdy":
            mo, d = _MONTHS[m.group(1).lower()], int(m.group(2))
            year = int(m.group(3)) if m.group(3) else _year_for(mo, ref)
        else:
            year, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(year, mo, d)
    except (ValueError, KeyError):
        return None


def _fmt(h: str, mi: Optional[str], ampm: Optional[str] = None) -> str:
    hour = int(h)
    if ampm and ampm.lower() == "pm" and hour < 12:
        hour += 12
    if not 0 <= hour <= 23:
        return ""
    return f"{hour:02d}:{int(mi or 0):02d}"


def _find_time(text: str) -> tuple[str, str]:
    """Uhrzeit(en) direkt hinter einem Datum – nur in derselben Zeile, damit kein Folgedatum als Zeit gilt."""
    text = text.split("\n", 1)[0]
    m = _TIME_RANGE.search(text)
    if m and (m.group("m1") or m.group("m2") or m.group("a1") or m.group("a2")):
        a1 = m.group("a1") if (m.group("a1") or "").lower() in ("am", "pm") else m.group("a2")
        start, end = _fmt(m.group("h1"), m.group("m1"), a1), _fmt(m.group("h2"), m.group("m2"), m.group("a2"))
        if start and end and start < end:
            return start, end
    m = _TIME_SINGLE.search(text)
    if m:
        if m.group("h"):
            return _fmt(m.group("h"), m.group("m"), m.group("a")), ""
        return _fmt(m.group("hu"), None, m.group("au")), ""
    return "", ""


def _kind(context: str) -> str:
    c = context.lower()
    if re.search(r"nachklausur|wiederhol|nachschreib|resit|retake", c):
        return "Nachklausur"
    if re.search(r"2\.\s?(termin|klausur|prüfungstermin|pruefungstermin)|zweit(termin|klausur)|second (exam|date|attempt)", c):
        return "2. Termin"
    if re.search(r"1\.\s?(termin|klausur|prüfungstermin|pruefungstermin)|erst(termin|klausur)|first (exam|date|attempt)|hauptklausur", c):
        return "1. Termin"
    return "Klausur"


def _line_at(text: str, pos: int) -> tuple[int, int]:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return start, (end if end != -1 else len(text))


def find_exams(text: str, page: int, ref: date) -> list[ExamFind]:
    """Klausurtermine in einer Seite Text. `ref` = Bezugsdatum für Jahreszahlen (Upload-Datum der Datei)."""
    text = re.sub(r"[ \t ]+", " ", text)
    finds: dict[tuple[date, str], ExamFind] = {}
    for kw in _KEYWORD.finditer(text):
        lo, hi = max(0, kw.start() - 160), min(len(text), kw.end() + 220)
        window = text[lo:hi]
        for kind, pat in _DATE_PATTERNS:
            for m in pat.finditer(window):
                dpos, dend = lo + m.start(), lo + m.end()
                d = _parse_date(kind, m, ref)
                if d is None:
                    continue
                l_start, l_end = _line_at(text, dpos)
                between = text[min(kw.start(), dpos):max(kw.end(), dend)]
                line = text[l_start:l_end]
                if _EXCLUDE.search(between) or _EXCLUDE.search(line):
                    continue
                after = text[dend:min(len(text), dend + 140)]
                start, end = _find_time(text[dend:min(len(text), dend + 70)])
                room_m = _ROOM.search(after)
                same_line = l_start <= kw.start() <= l_end
                dist = abs(dpos - kw.start())
                score = (3 if same_line else 1) + (1 if dist < 60 else 0) + (1 if start else 0) + (1 if room_m else 0)
                kw_line = text[slice(*_line_at(text, kw.start()))].strip()
                snippet = line.strip() if same_line else f"{kw_line} … {line.strip()}"
                find = ExamFind(d, start, end, room_m.group(0).strip(" .:-") if room_m else "",
                                _kind(kw_line + " " + line), page, snippet[:180], score)
                key = (d, start)
                if key not in finds or finds[key].score < find.score:
                    finds[key] = find
    return list(finds.values())


def should_scan_fully(name: str) -> bool:
    return bool(_ORGA_NAME.search(name))


def extract_pages(path: Path) -> Iterator[tuple[int, str]]:
    """(Seitennummer ab 1, Text). Kaputte oder verschlüsselte PDFs liefern nichts statt abzustürzen."""
    try:
        if path.stat().st_size > MAX_PDF_BYTES:
            return
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        if reader.is_encrypted:
            return
        n = len(reader.pages)
        if should_scan_fully(path.name):
            pages = range(min(n, FULL_SCAN_MAX_PAGES))
        else:
            pages = sorted(set(range(min(n, HEAD_PAGES))) | set(range(max(0, n - TAIL_PAGES), n)))
        for i in pages:
            try:
                yield i + 1, reader.pages[i].extract_text() or ""
            except Exception:
                continue
    except Exception:
        return


def scan_file(path: Path, ref: date, today: date) -> list[ExamFind]:
    out: list[ExamFind] = []
    for page, text in extract_pages(path):
        if not _KEYWORD.search(text):
            continue
        for f in find_exams(text, page, ref):
            # Nur plausible Termine: nicht lange vorbei, nicht absurd weit weg
            if (f.date - today).days >= -60 and (f.date - today).days <= 420 and f.score >= 2:
                out.append(f)
    return out
