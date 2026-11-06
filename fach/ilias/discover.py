"""Kurse aus ILIAS-Seiten herauslesen („Meine Kurse und Gruppen“, Dashboard, Kurs-Links).

Reine Funktionen ohne Netzwerk – deshalb gut testbar. ILIAS hat über die Versionen
mehrere Link-Formen benutzt, alle werden erkannt:
    goto.php/crs/6997658            (ILIAS 9+, so verlinkt die Uni Köln)
    goto.php?target=crs_6997658
    goto_uk_crs_6997658.html
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ..core.naming import semester_from_title
from .models import FoundCourse

_LINK_PATTERNS = (
    re.compile(r"goto\.php/(crs|grp)/(\d+)"),
    re.compile(r"[?&]target=(crs|grp)_(\d+)"),
    re.compile(r"goto_[A-Za-z0-9]+_(crs|grp)_(\d+)\.html"),
)
_PERIOD = re.compile(r"(\d{1,2}\.\s?\d{1,2}\.\s?\d{4})\s*[-–]\s*(\d{1,2}\.\s?\d{1,2}\.\s?\d{4})")
_ITEM_CLASSES = ("il-item", "il_ContainerListItem", "ilObjListRow", "il-std-item")


def course_id_from_url(url: str) -> str | None:
    """'https://…/goto.php/crs/6997658' → 'crs_6997658'."""
    for pat in _LINK_PATTERNS:
        m = pat.search(url)
        if m:
            return f"{m.group(1)}_{m.group(2)}"
    return None


def _item_container(a: Tag) -> Tag | None:
    for parent in a.parents:
        classes = parent.get("class") or []
        if any(c in _ITEM_CLASSES for c in classes):
            return parent
    return None


def _text(tag: Tag | None) -> str:
    return re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip() if tag else ""


def parse_courses(html: str, base_url: str) -> list[FoundCourse]:
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find(id="ilContentContainer") or soup.find("main") or soup
    found: dict[str, FoundCourse] = {}

    for a in root.find_all("a", href=True):
        href = a["href"]
        cid = course_id_from_url(href)
        if not cid:
            continue
        title = _text(a)
        container = _item_container(a)
        if not title and container:
            # Bild-/Icon-Link: Titel steht im selben Listeneintrag
            title_tag = container.select_one(".il-item-title, .il_ContainerItemTitle, h4, h3")
            title = _text(title_tag)
        if not title or title.lower() in ("öffnen", "open", "mehr", "more", "details"):
            title = ""
        context = _text(container) if container else ""
        period = ""
        if m := _PERIOD.search(context):
            period = f"{m.group(1)} – {m.group(2)}"
        url = urljoin(base_url + "/", href)
        prev = found.get(cid)
        if prev is None:
            found[cid] = FoundCourse(cid, title, url, semester_from_title(title) or semester_from_title(context), period)
        else:
            if len(title) > len(prev.title):
                prev.title = title
            prev.period = prev.period or period
            prev.semester = prev.semester or semester_from_title(title) or semester_from_title(context)

    return [c for c in found.values() if c.title]


def parse_page_title(html: str) -> str:
    """Titel eines Kurses von seiner eigenen Seite."""
    soup = BeautifulSoup(html, "html.parser")
    for sel in ("#il_mhead_t_focus", ".il-page-content-header", "h1.media-heading", "h1"):
        t = _text(soup.select_one(sel))
        if t:
            return t
    title = _text(soup.find("title"))
    # „Kurs: Softwaretechnik - ILIAS Uni Köln“ → „Softwaretechnik“
    title = re.sub(r"^(Kurs|Gruppe|Course|Group)\s*:\s*", "", title)
    return re.split(r"\s+[-–|:]\s+ILIAS", title)[0].strip()
