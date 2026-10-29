"""Publicine: parser genérico para cualquier página de cine
(https://www.publicine.net/cartelera-cine/<ciudad>/<cine>).

Estructura observada (29/10/2026), dentro de #esquerra:
  div.cartellera                    una película
    .sessions h2 / a[title]         título y ficha
    .box > .box_dia span.dia        "Hoy<br>29/10", "Sábado<br>31/10"...
         > .box_projeccions a       una sesión: .horari_pelicula "11.30" + .versio_pelicula "DIGITAL"
                                    data-href="/venda/<peli>/<cine>/<base64 url de compra>"
  div.titular.altres "Otros eventos"   lo que va detrás son eventos especiales
"""
from __future__ import annotations

import base64
import binascii
import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..config import load_config, tz
from ..http import Http
from ..models import Session, normalize_version

BASE = "https://www.publicine.net"
_DAY_RE = re.compile(r"(\d{1,2})/(\d{1,2})")
_TIME_RE = re.compile(r"(\d{1,2})[.:](\d{2})")


def infer_year(day: int, month: int, today: date) -> date:
    """Publicine da dd/mm sin año: elige el año que deja la fecha más cerca de hoy
    (cubre el salto diciembre -> enero en ambos sentidos)."""
    candidates = []
    for y in (today.year - 1, today.year, today.year + 1):
        try:
            candidates.append(date(y, month, day))
        except ValueError:  # 29/02 en año no bisiesto
            pass
    return min(candidates, key=lambda d: abs((d - today).days))


def _ticket_url(data_href: str | None) -> str | None:
    """El último tramo de /venda/<a>/<b>/<x> es la URL de compra del cine en base64."""
    if not data_href:
        return None
    token = data_href.rstrip("/").rsplit("/", 1)[-1]
    try:
        url = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    return url if url.startswith(("http://", "https://")) else None


def parse(html: bytes | str, cinema: dict, today: date) -> list[Session]:
    soup = BeautifulSoup(html, "lxml")
    container = soup.find(id="esquerra") or soup
    sessions: list[Session] = []
    special = False

    for block in container.find_all("div", recursive=False):
        classes = block.get("class") or []
        if "titular" in classes and "altres" in classes:
            special = True
            continue
        if "cartellera" not in classes:
            continue

        link = block.select_one(".sessions a[href]") or block.select_one("a[href]")
        h2 = block.find("h2")
        title = (link.get("title") if link else None) or (h2.get_text(strip=True) if h2 else "")
        title = title.strip()
        film_url = urljoin(BASE, link["href"]) if link else None
        box = block.select_one(".box")
        if not title or not box:
            continue

        current: date | None = None
        for child in box.find_all("div", recursive=False):
            cls = child.get("class") or []
            if "box_dia" in cls:
                m = _DAY_RE.search(child.get_text(" ", strip=True))
                current = infer_year(int(m.group(1)), int(m.group(2)), today) if m else None
            elif "box_projeccions" in cls and current is not None:
                for a in child.select("a"):
                    hour = a.select_one(".horari_pelicula")
                    ver = a.select_one(".versio_pelicula")
                    if not hour:
                        continue
                    version_raw = ver.get_text(strip=True) if ver else ""
                    if ver:
                        ver.extract()  # que no se mezcle con la hora
                    tm = _TIME_RE.search(hour.get_text(" ", strip=True))
                    if not tm:
                        continue
                    sessions.append(Session(
                        cinema_id=cinema["id"],
                        cinema_name=cinema["name"],
                        film_title=title,
                        date=current.isoformat(),
                        time=f"{int(tm.group(1)):02d}:{tm.group(2)}",
                        version=normalize_version(version_raw),
                        version_raw=version_raw,
                        ticket_url=_ticket_url(a.get("data-href")) or cinema.get("tickets_url"),
                        film_url=film_url,
                        special=special,
                        source="publicine",
                    ))
    return sessions


def fetch(cinema: dict, http: Http | None = None, today: date | None = None) -> list[Session]:
    http = http or Http()
    if today is None:
        today = datetime.now(tz(load_config())).date()
    r = http.get(cinema["url"])
    return parse(r.content, cinema, today)
