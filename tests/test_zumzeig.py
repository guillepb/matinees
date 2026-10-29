from datetime import date
from pathlib import Path

import pytest

from scraper.sources.zumzeig import build_sessions, parse_calendar, parse_film, parse_version_field

FIXTURES = Path(__file__).parent / "fixtures"
CINEMA = {"id": "zumzeig", "name": "Zumzeig", "tickets_url": "https://zumzeigcine.coop/es/cine/sesiones/"}
NAZA = "https://zumzeigcine.coop/es/cine/films/naza/"
BOLA = "https://zumzeigcine.coop/es/cine/films/la-bola-negra/"
# Los fixtures se descargaron el jueves 29/10/2026
TODAY = date(2026, 10, 29)


@pytest.fixture(scope="module")
def calendar():
    return parse_calendar((FIXTURES / "zumzeig_calendari.html").read_bytes())


@pytest.fixture(scope="module")
def films():
    return {
        NAZA: parse_film((FIXTURES / "zumzeig_film_naza.html").read_bytes()),
        BOLA: parse_film((FIXTURES / "zumzeig_film_la-bola-negra.html").read_bytes()),
    }


def test_calendar_covers_whole_months(calendar):
    assert len(calendar) == 134
    assert min(c["date"] for c in calendar) == "2026-10-01"
    assert max(c["date"] for c in calendar) == "2026-12-03"


def test_calendar_session(calendar):
    assert {"date": "2026-11-03", "time": "12:00", "special": False, "title": "Naza",
            "film_url": NAZA} in calendar


def test_calendar_asterisk_is_special(calendar):
    s = next(c for c in calendar if c["date"] == "2026-10-29" and c["time"] == "19:00")
    assert s["title"] == "Suportant el paradís" and s["special"]


def test_calendar_has_more_than_cartelera_cards(calendar):
    # La tarjeta de La bola negra en /sesiones/ se corta en 3 fechas con "+"
    bola = [c for c in calendar if c["film_url"] == BOLA and c["date"] >= "2026-10-29"]
    assert len(bola) > 3


def test_film_page(films):
    naza = films[NAZA]
    assert (naza["version"], naza["version_raw"]) == ("VOSE", "VOSE")
    assert naza["tickets"][("2026-11-03", "12:00")] == \
        "https://www.codetickets.com/portal/zumzeigcooperativa/online/37717/102486"
    assert len(naza["tickets"]) == 3
    assert naza["more_url"] == "https://www.codetickets.com/portal/zumzeigcooperativa/online/37717/naza"


def test_spanish_vo_is_not_vose(films):
    bola = films[BOLA]
    assert (bola["version"], bola["version_raw"]) == ("Doblada", "VO")
    assert bola["overrides"] == {"2026-10-29": ("Doblada", "VOCAP")}


def test_build_sessions(calendar, films):
    ss = build_sessions(calendar, films, CINEMA, TODAY)
    assert min(s.date for s in ss) == "2026-10-29"  # fuera el pasado del mes
    by_key = {(s.film_url, s.date, s.time): s for s in ss}
    # sesión con enlace propio
    assert by_key[(NAZA, "2026-11-03", "12:00")].ticket_url.endswith("/37717/102486")
    # más allá de las 3 primeras: página de la película en codetickets
    assert by_key[(BOLA, "2026-11-04", "11:30")].ticket_url.endswith("/37225/la-bola-negra")
    # película sin ficha descargada: versión por defecto y enlace genérico
    other = next(s for s in ss if s.film_url not in (NAZA, BOLA))
    assert other.version == "VOSE" and other.ticket_url == CINEMA["tickets_url"]
    # excepción por día
    assert by_key[(BOLA, "2026-10-29", "21:15")].version_raw == "VOCAP"
    assert all(s.source == "zumzeig" for s in ss)


@pytest.mark.parametrize(
    "raw, lang, expected",
    [
        ("VOSE", "Hebreo, inglés", ("VOSE", "VOSE", {})),
        ("VO", "Francés", ("VOSE", "VO", {})),
        ("VO", "Catalán", ("Català", "VO", {})),
        ("Mi 28.10.26 y Mi 4.11.26 VOSCAT, el resto VOSE", "Inglés, húngaro",
         ("VOSE", "VOSE", {"2026-10-28": ("VOSE", "VOSCAT"), "2026-11-04": ("VOSE", "VOSCAT")})),
        ("Doblada al catalán, con subtítulos para fomentar la lectura", "", ("Català", "Doblada al catalán", {})),
        ("Doblada al castellano", "", ("Doblada", "Doblada al castellano", {})),
        ("VOSE - VOSI", "Inglés, árabe, castellano", ("VOSE", "VOSE - VOSI", {})),
        ("VOSI - VOSF", "Castellano", ("VOSE inglés", "VOSI - VOSF", {})),
        ("Pendiente de confirmar", "Portugués", ("VOSE", "Pendiente de confirmar", {})),
        ("", "Sin diálogos", ("Desconocida", "Sin diálogos", {})),
        ("", "", ("VOSE", "", {})),
    ],
)
def test_parse_version_field(raw, lang, expected):
    assert parse_version_field(raw, lang) == expected
