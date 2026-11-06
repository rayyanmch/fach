"""Kern: Namen, Zeitplan, Semester, Konfiguration, OS-Zeitplan-Dateien."""

import plistlib
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

import pytest

from fach.core.config import AppConfig, ConfigStore, Course, Schedule
from fach.core.naming import clean_title, course_label, folder_name, is_valid_folder, semester_from_title
from fach.core.schedule import next_run, validate
from fach.core.university import KOELN, lecture_week, semester_for
from fach.platform.macos import plist_data
from fach.platform.windows import task_xml, toast_xml


def test_folder_name_windows_rules():
    assert folder_name("Softwaretechnik (WiSe 2026/27)") == "Softwaretechnik"
    assert folder_name('Mathe: Teil 1/2 "neu"?') == "Mathe Teil 1 2 neu"
    assert folder_name("CON") == "CON (Kurs)"
    assert folder_name("Kurs.") == "Kurs"
    assert folder_name("BWL", {"bwl"}) == "BWL (2)"
    assert len(folder_name("x" * 200)) <= 80


def test_is_valid_folder():
    assert is_valid_folder("Softwaretechnik")
    for bad in ["", " x", "a/b", "a:b", "x.", "NUL", "..", "a\\b"]:
        assert not is_valid_folder(bad), bad


@pytest.mark.parametrize("title,label", [
    ("Information Systems Management (WiSe 2026/27)", "ISM"),
    ("Grundlagen der Betriebswirtschaftslehre", "BWL"),
    ("Softwaretechnik", "SWT"),
    ("Visualisierung", "VIS"),
    ("Mathematik für Studierende der Informatik I", "MI1"),
    ("Übung zu Mathematik für Studierende der Informatik I", "MI1Ü"),
    ("Algorithmen und Datenstrukturen", "AD"),
])
def test_course_label(title, label):
    assert course_label(title) == label


def test_semester_from_title():
    assert semester_from_title("Softwaretechnik (WiSe 2026/27)") == "WiSe 2026/27"
    assert semester_from_title("ADS SoSe 2026") == "SoSe 2026"
    assert semester_from_title("Statistik WS 25/26") == "WiSe 2025/26"
    assert semester_from_title("Softwaretechnik") == ""
    assert clean_title("Softwaretechnik (WiSe 2026/27)") == "Softwaretechnik"


def test_semester_and_week():
    sem = semester_for(KOELN, date(2026, 11, 6))
    assert sem.name == "WiSe 2026/27" and not sem.estimated
    assert lecture_week(sem, date(2026, 10, 12)) == 1
    assert lecture_week(sem, date(2026, 11, 6)) == 4
    assert lecture_week(sem, date(2027, 3, 1)) is None
    est = semester_for(KOELN, date(2027, 5, 3))
    assert est.name == "SoSe 2027" and est.estimated


def test_next_run():
    s = Schedule(enabled=True, days=[0, 2, 4], times=["07:00", "18:30"])
    assert next_run(s, datetime(2026, 11, 6, 8, 0)) == datetime(2026, 11, 6, 18, 30)   # Freitag
    assert next_run(s, datetime(2026, 11, 6, 19, 0)) == datetime(2026, 11, 9, 7, 0)    # → Montag
    assert next_run(Schedule(enabled=False), datetime(2026, 11, 6)) is None


def test_validate_schedule():
    v = validate(Schedule(enabled=True, days=[6, 1, 1, 9], times=["7:00" if False else "07:00", "07:00"], spread_min=500))
    assert v.days == [1, 6] and v.times == ["07:00"] and v.spread_min == 60
    with pytest.raises(ValueError):
        validate(Schedule(times=["25:00"]))


def test_config_roundtrip_and_broken_file(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    cfg = store.load()
    cfg.username = "jmuster1"
    cfg.courses.append(Course(id="crs_1", title="X", folder="X", label="X"))
    store.save(cfg)
    again = ConfigStore(tmp_path / "config.json").load()
    assert again.username == "jmuster1" and again.courses[0].ref == 1
    (tmp_path / "config.json").write_text("{kaputt")
    fresh = ConfigStore(tmp_path / "config.json").load()
    assert fresh.username == "" and list(tmp_path.glob("config.broken-*.json"))


def test_windows_task_xml_is_valid():
    xml = task_xml(Schedule(days=[0, 2], times=["07:00", "18:00"]), [r"C:\Program Files\Fach\Fach.exe", "--sync"],
                   Path(r"C:\Program Files\Fach"), today=date(2026, 11, 6))
    root = ET.fromstring(xml.split("\n", 1)[1])  # ohne XML-Deklaration (UTF-16-Angabe)
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    triggers = root.findall(".//t:CalendarTrigger", ns)
    assert len(triggers) == 2
    assert triggers[0].find("t:StartBoundary", ns).text == "2026-11-06T07:00:00"
    assert root.find(".//t:DaysOfWeek/t:Monday", ns) is not None
    assert root.find(".//t:DaysOfWeek/t:Wednesday", ns) is not None
    assert root.find(".//t:StartWhenAvailable", ns).text == "true"
    assert root.find(".//t:Command", ns).text == r"C:\Program Files\Fach\Fach.exe"
    assert root.find(".//t:Arguments", ns).text == "--sync"
    every_day = task_xml(Schedule(), ["x.exe"], Path("."), today=date(2026, 11, 6))
    assert "<ScheduleByDay>" in every_day


def test_toast_xml_escapes():
    assert "&lt;b&gt;" in toast_xml("<b>", "a & b") and "a &amp; b" in toast_xml("x", "a & b")


def test_mac_plist_weekdays():
    data = plist_data(Schedule(days=[0, 6], times=["07:00"]), ["/x/Fach", "--sync"], Path("/x"))
    assert {i["Weekday"] for i in data["StartCalendarInterval"]} == {1, 0}  # Mo=1, So=0 bei launchd
    plistlib.dumps(data)
    assert plist_data(Schedule(), ["x"], Path("/"))["StartCalendarInterval"] == [{"Hour": 7, "Minute": 0}]


def test_appconfig_enabled_courses():
    cfg = AppConfig(courses=[Course("crs_1", "A", "A", "A"), Course("crs_2", "B", "B", "B", enabled=False)])
    assert [c.id for c in cfg.enabled_courses()] == ["crs_1"]
