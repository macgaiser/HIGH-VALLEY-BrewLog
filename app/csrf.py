"""CSRF-Schutz per Herkunftspruefung.

Der Browser schickt die HTTP-Basic-Zugangsdaten automatisch mit - eine
fremde Webseite koennte daher im Namen eines angemeldeten Nutzers
aendernde Anfragen (POST) an die App stellen. Deshalb werden aendernde
Anfragen nur akzeptiert, wenn sie von der App selbst kommen:

* Sec-Fetch-Site "cross-site" wird abgelehnt.
* Ein Origin-Header (sonst Referer) muss auf denselben Host zeigen wie die
  Anfrage (auch hinter einem Reverse-Proxy: Host bzw. X-Forwarded-Host)
  oder in APP_TRUSTED_ORIGINS (kommagetrennte Hosts) stehen.
* Anfragen ganz ohne Origin/Referer (z.B. curl, Skripte) stammen nicht aus
  einem Browser-Formular und bleiben erlaubt.
"""

import os
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import PlainTextResponse

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _allowed_hosts(request: Request) -> set[str]:
    hosts = {request.headers.get("host", "").lower()}
    forwarded = request.headers.get("x-forwarded-host", "")
    if forwarded:
        hosts.add(forwarded.split(",")[0].strip().lower())
    extra = os.environ.get("APP_TRUSTED_ORIGINS", "")
    hosts.update(h.strip().lower() for h in extra.split(",") if h.strip())
    hosts.discard("")
    return hosts


def request_comes_from_same_site(request: Request) -> bool:
    if request.method not in _UNSAFE_METHODS:
        return True
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        return False
    origin = request.headers.get("origin")
    if origin is None:
        origin = request.headers.get("referer")
    if origin is None:
        return True
    host = urlparse(origin).netloc.lower()
    return bool(host) and host in _allowed_hosts(request)


async def csrf_origin_check(request: Request, call_next):
    if not request_comes_from_same_site(request):
        return PlainTextResponse(
            "Anfrage abgelehnt (CSRF-Schutz): Die Anfrage stammt nicht von dieser Seite.",
            status_code=403,
        )
    return await call_next(request)
