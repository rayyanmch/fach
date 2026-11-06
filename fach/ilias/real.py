"""Echtes ILIAS über PFERD. Alles PFERD-Spezifische steckt in pferd_runtime.py."""

from __future__ import annotations

import asyncio
import os
import socket
import sys
from pathlib import Path
from PFERD.auth import AuthError

from ..core.config import Course
from ..core.university import University
from . import pferd_runtime as rt
from .discover import course_id_from_url, parse_courses, parse_page_title
from .models import AuthFailed, CourseResult, FoundCourse, IliasError, ProgressFn, Unreachable

_NET_HINTS = ("ClientConnectorError", "ConnectionTimeoutError", "ServerDisconnectedError", "Cannot connect to host",
              "Connection timeout", "Temporary failure in name resolution", "TimeoutError", "ClientOSError")


def _looks_offline(messages: list[str]) -> bool:
    return bool(messages) and all(any(h in m for h in _NET_HINTS) for m in messages)


class RealIlias:
    def __init__(self, uni: University, state_dir: Path):
        self.uni = uni
        self.state_dir = state_dir
        self.cookie_file = state_dir / "cookies.txt"
        state_dir.mkdir(parents=True, exist_ok=True)
        rt.install(uni.base_url)

    # --- Hilfen ------------------------------------------------------------

    def _report_path(self, course_id: str) -> Path:
        return self.state_dir / f"{course_id}.report"

    def _protect_cookies(self) -> None:
        if sys.platform != "win32" and self.cookie_file.exists():
            os.chmod(self.cookie_file, 0o600)

    def _target(self, course_id: str) -> str:
        kind, ref = course_id.split("_", 1)
        if kind == "crs":
            return ref  # PFERD prüft dann zusätzlich, ob wirklich dieser Kurs geöffnet wurde
        return f"{self.uni.base_url}/goto.php?target={kind}_{ref}"

    async def reachable(self, timeout: float = 8.0) -> bool:
        def probe() -> bool:
            try:
                socket.create_connection((self.uni.host, self.uni.port), timeout=timeout).close()
                return True
            except OSError:
                return False

        return await asyncio.get_running_loop().run_in_executor(None, probe)

    async def _fetch_pages(self, username: str, password: str, urls: list[str]) -> list[tuple[str, str]]:
        """Seiten eingeloggt abrufen – mit PFERDs Login, ohne etwas herunterzuladen."""
        pages: list[tuple[str, str]] = []

        class PageFetcher(rt.FachCrawler):
            async def _run(self) -> None:
                for url in urls:
                    soup = await self._get_page(url, root_page_allowed=True)
                    pages.append((soup.page_url, str(soup.soup)))

        scratch = self.state_dir / "_scratch"
        section = rt.course_section(self.uni.base_url, self.uni.client_id, "desktop", "_scratch", False)
        cfg = rt.build_config(self.state_dir, {"crawl:fetch": section})
        name, sec = cfg.crawl_sections()[0]
        crawler = PageFetcher(name, sec, cfg, {"auth:fach": rt.AppAuthenticator(username, password)},
                              report_path=scratch / "fetch.report", cookie_file=self.cookie_file)
        await self._run_crawler(crawler)
        return pages

    async def _run_crawler(self, crawler: rt.FachCrawler) -> None:
        try:
            await crawler.run()
        except AuthError as e:
            raise AuthFailed("Kennung oder Passwort stimmen nicht.", str(e)) from e
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if _looks_offline([msg]):
                raise Unreachable("ILIAS ist gerade nicht erreichbar.", msg) from e
            raise IliasError("ILIAS hat unerwartet geantwortet.", msg) from e
        finally:
            self._protect_cookies()

    # --- Schnittstelle ----------------------------------------------------

    async def discover(self, username: str, password: str, fresh_login: bool = False) -> list[FoundCourse]:
        if fresh_login:
            # Sonst würde eine noch gültige Sitzung ein falsches neues Passwort „bestätigen“.
            self.cookie_file.unlink(missing_ok=True)
        if not await self.reachable():
            raise Unreachable("ILIAS ist gerade nicht erreichbar. Bist du online?")
        base = self.uni.base_url
        pages = await self._fetch_pages(username, password, [
            f"{base}/ilias.php?baseClass=ilmembershipoverviewgui",
            f"{base}/ilias.php?baseClass=ilDashboardGUI&cmd=show",
        ])
        seen: dict[str, FoundCourse] = {}
        for url, html in pages:
            for c in parse_courses(html, base):
                seen.setdefault(c.id, c)
        return list(seen.values())

    async def resolve(self, username: str, password: str, url: str) -> FoundCourse:
        cid = course_id_from_url(url)
        if not cid:
            raise IliasError("Das sieht nicht nach einem Kurs-Link aus. Kopiere den Link aus der Adresszeile des Kurses.")
        kind, ref = cid.split("_", 1)
        page_url = f"{self.uni.base_url}/goto.php/{kind}/{ref}"
        pages = await self._fetch_pages(username, password, [page_url])
        title = parse_page_title(pages[0][1]) if pages else ""
        return FoundCourse(cid, title or f"Kurs {ref}", page_url)

    async def sync_course(self, username: str, password: str, course: Course, target_dir: Path,
                          videos: bool, on_progress: ProgressFn) -> CourseResult:
        report_path = self._report_path(course.id)
        initial = not report_path.exists()
        section = rt.course_section(self.uni.base_url, self.uni.client_id, self._target(course.id),
                                    course.folder, videos, course.rules)
        cfg = rt.build_config(target_dir, {f"crawl:{course.id}": section})
        name, sec = cfg.crawl_sections()[0]
        crawler = rt.FachCrawler(name, sec, cfg, {"auth:fach": rt.AppAuthenticator(username, password)},
                                 report_path=report_path, cookie_file=self.cookie_file, on_progress=on_progress)
        result = CourseResult(course.id, initial=initial)
        try:
            await self._run_crawler(crawler)
        except AuthFailed:
            raise
        except IliasError as e:
            result.errors.append(e.detail or e.message)
        report = crawler.report
        result.added = sorted(p.as_posix() for p in report.added_files)
        result.changed = sorted(p.as_posix() for p in report.changed_files)
        result.warnings = list(report.encountered_warnings)
        result.errors = list(dict.fromkeys([*report.encountered_errors, *result.errors]))
        result.offline = _looks_offline(result.errors + result.warnings) and not (result.added or result.changed)
        return result

    def set_log_stream(self, stream) -> None:
        rt.set_log_stream(stream)

    def set_byte_hook(self, fn) -> None:
        rt.set_byte_hook(fn)

    def forget(self, course_id: str) -> None:
        self._report_path(course_id).unlink(missing_ok=True)

    def logout(self) -> None:
        self.cookie_file.unlink(missing_ok=True)

