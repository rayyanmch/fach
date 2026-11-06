"""Aus ILIAS-Titeln werden Ordnernamen und Kürzel.

Ordnernamen müssen auf Windows UND macOS gültig sein – Windows ist strenger, also gilt Windows.
"""

from __future__ import annotations

import re
import unicodedata

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_SEMESTER = re.compile(
    r"\s*[\(\[]?\s*(?:WiSe|WS|SoSe|SS|Wintersemester|Sommersemester)\s*\d{2,4}(?:\s*/\s*\d{2,4})?\s*[\)\]]?\s*",
    re.IGNORECASE,
)
_STOP = {
    "für", "fuer", "der", "die", "das", "des", "den", "dem", "und", "in", "im", "zu", "zur", "zum", "von",
    "vom", "mit", "an", "am", "auf", "aus", "bei", "ein", "eine", "einer", "einen", "studierende",
    "the", "of", "and", "for", "to", "a", "an", "on", "with", "introduction", "einführung",
}
# Bekannte Abkürzungen für zusammengesetzte Fachwörter (an der WiSo-Fakultät allgegenwärtig)
_KNOWN = {
    "betriebswirtschaftslehre": "BWL", "volkswirtschaftslehre": "VWL", "wirtschaftsinformatik": "WINF",
    "softwaretechnik": "SWT", "softwareentwicklung": "SWE", "wirtschaftsmathematik": "WIMA",
}
_ROMAN = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6"}


def semester_from_title(title: str) -> str:
    """'Softwaretechnik (WiSe 2026/27)' → 'WiSe 2026/27'. Leer, wenn nichts erkennbar."""
    m = re.search(r"(WiSe|WS|Wintersemester)\s*(\d{2,4})\s*/\s*(\d{2,4})", title, re.IGNORECASE)
    if m:
        y1 = int(m.group(2)) % 100 + 2000
        y2 = int(m.group(3)) % 100
        return f"WiSe {y1}/{y2:02d}"
    m = re.search(r"(SoSe|SS|Sommersemester)\s*(\d{2,4})", title, re.IGNORECASE)
    if m:
        return f"SoSe {int(m.group(2)) % 100 + 2000}"
    return ""


def clean_title(title: str) -> str:
    """Titel ohne Semesterangabe und überflüssige Leerzeichen – für die Anzeige."""
    t = _SEMESTER.sub(" ", title)
    t = re.sub(r"\s+", " ", t).strip(" -–·,")
    return t or title.strip()


def folder_name(title: str, taken: set[str] | None = None) -> str:
    """Gültiger, eindeutiger Ordnername (Windows-Regeln, max. 80 Zeichen)."""
    name = unicodedata.normalize("NFC", clean_title(title))
    name = _ILLEGAL.sub(" ", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    if not name:
        name = "Kurs"
    if name.split(".")[0].upper() in _RESERVED:
        name = f"{name} (Kurs)"
    if len(name) > 80:
        name = name[:80].rstrip(" .-–")
    taken_lower = {t.lower() for t in (taken or set())}
    if name.lower() not in taken_lower:
        return name
    i = 2
    while f"{name} ({i})".lower() in taken_lower:
        i += 1
    return f"{name} ({i})"


def is_valid_folder(name: str) -> bool:
    if not name or name != name.strip() or name.endswith("."):
        return False
    if _ILLEGAL.search(name) or name in (".", ".."):
        return False
    return name.split(".")[0].upper() not in _RESERVED and len(name) <= 120


def course_label(title: str) -> str:
    """Kurzes Kürzel für Listen: 'Information Systems Management' → 'ISM', 'Visualisierung' → 'VIS'."""
    t = clean_title(title)
    # Steht schon eine Abkürzung im Titel (ISM, BWL, IIS), nimm sie.
    for token in re.findall(r"\b[A-ZÄÖÜ]{2,5}\b", t):
        if token not in _ROMAN:
            return token
    words = re.findall(r"[A-Za-zÄÖÜäöüß]+", t)
    for w in words:
        if w.lower() in _KNOWN:
            return _KNOWN[w.lower()]
    numeral = ""
    if words and words[-1] in _ROMAN:
        numeral = _ROMAN[words.pop()]
    exercise = any(w.lower() in ("übung", "übungen", "tutorium", "exercise", "exercises") for w in words)
    sig = [w for w in words if w.lower() not in _STOP and w.lower() not in ("übung", "übungen", "tutorium")]
    if not sig:
        sig = words or ["K"]
    if len(sig) == 1:
        base = sig[0][:3].upper()
    else:
        base = "".join(w[0] for w in sig[:3]).upper()
    label = base + numeral + ("Ü" if exercise else "")
    return label[:5]


# --- Module: Vorlesung + Übung desselben Fachs gehören in einen Ordner -------------------------

_ROLE = {
    "übung": "Übung", "übungen": "Übung", "übungsgruppe": "Übung", "übungsgruppen": "Übung",
    "exercise": "Übung", "exercises": "Übung", "tutorium": "Tutorium", "tutorien": "Tutorium",
    "tutorial": "Tutorium", "praktikum": "Praktikum", "vorlesung": "Vorlesung", "lecture": "Vorlesung",
}
_ROLE_WORDS = "|".join(sorted(_ROLE, key=len, reverse=True))
_PREFIX = re.compile(rf"^({_ROLE_WORDS})\s+(?:zu[mr]?|zur|for|to|in)\s+(.+)$", re.IGNORECASE)
_SUFFIX = re.compile(rf"^(.+?)\s*(?:[-–—:|/]\s*|\(\s*|\s+)({_ROLE_WORDS})\s*\)?$", re.IGNORECASE)


def module_parts(title: str) -> tuple[str, str]:
    """'Visualisierung – Übungen' → ('Visualisierung', 'Übung'); 'Visualisierung' → ('Visualisierung', '')."""
    t = clean_title(title)
    m = _PREFIX.match(t)
    if m:
        return m.group(2).strip(" -–—:|"), _ROLE[m.group(1).lower()]
    m = _SUFFIX.match(t)
    if m and len(m.group(1).strip()) >= 3:
        return m.group(1).strip(" -–—:|"), _ROLE[m.group(2).lower()]
    return t, ""


def module_key(title: str) -> str:
    return re.sub(r"\s+", " ", module_parts(title)[0]).casefold()


def plan_layout(items: list[tuple[str, str]], taken: set[str] | None = None) -> dict[str, tuple[str, str]]:
    """Ordner und Kürzel für Kurse (id, Titel). Kurse desselben Moduls landen gemeinsam in einem Ordner:

        Visualisierung/Vorlesung, Visualisierung/Übung
    Einzelne Kurse behalten einen Ordner auf oberster Ebene.
    """
    taken = set(taken or set())
    groups: dict[str, list[tuple[str, str, str, str]]] = {}
    for cid, title in items:
        base, role = module_parts(title)
        groups.setdefault(module_key(title), []).append((cid, title, base, role))
    out: dict[str, tuple[str, str]] = {}
    for members in groups.values():
        if len(members) == 1:
            cid, title, _, _ = members[0]
            folder = folder_name(title, taken)
            taken.add(folder)
            out[cid] = (folder, course_label(title))
            continue
        main = next((m for m in members if not m[3]), members[0])
        module = folder_name(main[2], taken)
        taken.add(module)
        label = course_label(main[2])
        used: set[str] = set()
        for cid, title, _, role in members:
            sub = role or "Vorlesung"
            if sub.lower() in used:
                sub = folder_name(title, used)
            used.add(sub.lower())
            out[cid] = (f"{module}/{sub}", label)
    return out


def is_valid_relpath(path: str) -> bool:
    """Ordnerpfad relativ zum Uni-Ordner, höchstens drei Ebenen, jede Ebene ein gültiger Ordnername."""
    parts = path.split("/")
    return 1 <= len(parts) <= 3 and all(is_valid_folder(p) for p in parts)


def module_of(folder: str) -> str:
    return folder.split("/", 1)[0]
