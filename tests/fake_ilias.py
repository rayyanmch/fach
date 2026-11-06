"""Ein winziges Schein-ILIAS unter /ilias – gerade genug, damit PFERDs Login und unsere Kurssuche laufen.

Wichtig: Es liegt wie in Köln unter einem Unterpfad. Ohne den urljoin-Fix würde PFERD
/login.php statt /ilias/login.php aufrufen und hier eine 404 bekommen.
"""

from __future__ import annotations

from aiohttp import web

USER, PASSWORD = "jmuster1", "richtig"
SESSION = "sess-123"

METABAR_IN = '<div class="il-maincontrols-metabar"><a href="ilias.php?cmd=logout">Abmelden</a></div>'


def page(body: str) -> str:
    return f"<!doctype html><html><head><title>ILIAS</title></head><body>{METABAR_IN}<main>{body}</main></body></html>"


MEMBERSHIPS = page("""
<div class="il-item il-std-item">
  <div class="il-item-title"><a href="https://ilias.test/ilias/goto.php/crs/6997658">Softwaretechnik (WiSe 2026/27)</a></div>
  <div class="il-item-properties">Zeitraum 12.10.2026 - 05.02.2027</div>
</div>
<div class="il-item il-std-item">
  <a href="/ilias/goto.php?target=crs_6997182&client_id=uk"><img alt=""></a>
  <div class="il-item-title"><a href="/ilias/goto.php?target=crs_6997182&client_id=uk">Information Systems Management</a></div>
</div>
<div class="il-item il-std-item">
  <div class="il-item-title"><a href="goto_uk_grp_555.html">Übungsgruppe 3</a></div>
</div>
""")


def make_app(seen: list[str]) -> web.Application:
    async def record(request: web.Request, handler):
        seen.append(request.path)
        return await handler(request)

    app = web.Application(middlewares=[web.middleware(record)])

    def logged_in(request: web.Request) -> bool:
        return request.cookies.get("PHPSESSID") == SESSION

    async def login_page(request: web.Request) -> web.Response:
        return web.Response(content_type="text/html", text=(
            "<html><body><form name=\"login_form\" method=\"post\" "
            "action=\"ilias.php?baseClass=ilstartupgui&cmd=post&fallbackCmd=doStandardAuthentication\">"
            "<input name=\"login_form/input_3/input_4\"><input name=\"login_form/input_3/input_5\"></form></body></html>"))

    async def ilias_php(request: web.Request) -> web.Response:
        if request.method == "POST":
            data = await request.post()
            if data.get("login_form/input_3/input_4") == USER and data.get("login_form/input_3/input_5") == PASSWORD:
                resp = web.Response(content_type="text/html", text=page("Willkommen"))
                resp.set_cookie("PHPSESSID", SESSION, path="/ilias")
                return resp
            return await login_page(request)
        if not logged_in(request):
            return await login_page(request)
        if request.query.get("baseClass", "").lower() == "ilmembershipoverviewgui":
            return web.Response(content_type="text/html", text=MEMBERSHIPS)
        return web.Response(content_type="text/html", text=page("Dashboard"))

    app.router.add_get("/ilias/login.php", login_page)
    app.router.add_route("*", "/ilias/ilias.php", ilias_php)
    return app
