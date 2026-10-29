import re
from datetime import date
from pathlib import Path

import pytest

from scraper.sources.verdi import parse_day, parse_film, parse_listing

FIXTURES = Path(__file__).parent / "fixtures"
CINEMA = {"id": "verdi", "name": "Cines Verdi", "tickets_url": "https://barcelona.cines-verdi.com/cartelera"}
FILM_URL = "https://barcelona.cines-verdi.com/la-bola-negra"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("jueves 29 OCT 2026", date(2026, 10, 29)),
        ("dijous 29 D’OCT 2026", date(2026, 10, 29)),
        ("dimarts 27 D'OCT 2026", date(2026, 10, 27)),
        ("dimecres 6 de gen. 2027", date(2027, 1, 6)),
        ("miércoles 6 ENE 2027", date(2027, 1, 6)),
        ("dilluns 7 DE DES 2026", date(2026, 12, 7)),
        ("viernes 31 DIC 2026", date(2026, 12, 31)),
        ("dissabte 2 D’AGO 2027", date(2027, 8, 2)),
        ("sábado 1 MAY 2027", date(2027, 5, 1)),
        ("dissabte 1 MAIG 2027", date(2027, 5, 1)),
        ("lunes 31 FEB 2027", None),
        ("sin fecha", None),
    ],
)
def test_parse_day(text, expected):
    assert parse_day(text) == expected


def test_parse_listing():
    urls = parse_listing((FIXTURES / "verdi_cartelera.html").read_bytes())
    assert len(urls) == 34
    assert FILM_URL in urls
    assert "https://barcelona.cines-verdi.com/otello-festival-de-salzburg" in urls
    # enlaces relativos sin barra inicial
    assert "https://barcelona.cines-verdi.com/sesion-cortometrajes-terror-2026" in urls
    # sin enlaces del menú
    assert not any(u.endswith(("/precios", "/matins-dopera-i-ballet", "/cartelera")) for u in urls)


@pytest.fixture(scope="module")
def bola_ca():
    return parse_film((FIXTURES / "verdi_la-bola-negra.html").read_bytes(), CINEMA, FILM_URL)


@pytest.fixture(scope="module")
def bola_es():
    return parse_film((FIXTURES / "verdi_la-bola-negra_es.html").read_bytes(), CINEMA, FILM_URL)


def test_film_catalan(bola_ca):
    s = bola_ca[0]
    assert (s.film_title, s.date, s.time, s.version, s.version_raw) == (
        "La bola negra", "2026-10-29", "11:30", "Doblada", "CASTELLÀ")
    assert s.ticket_url == "https://verdibcn.admit-one.eu/seats/221688/"
    assert s.film_url == FILM_URL and s.source == "verdi" and not s.special


def test_film_sorted(bola_ca):
    keys = [(s.date, s.time) for s in bola_ca]
    assert keys == sorted(keys)
    # en el HTML el 16:00 VOSE va después del 20:35
    assert [s.time for s in bola_ca if s.date == "2026-10-29"] == ["11:30", "16:00", "17:50", "20:35"]


def test_catalan_and_spanish_agree(bola_ca, bola_es):
    def key(ss):
        return {(s.date, s.time, s.version, s.ticket_url) for s in ss}
    assert key(bola_ca) == key(bola_es)
    assert {s.version_raw for s in bola_es} >= {"CASTELLANO", "V.O. SUB. CASTELLANO"}


def test_header_dates_match_ispast(bola_ca):
    # Sin el atributo x-show, la fecha sale solo de la cabecera del día y debe coincidir
    html = (FIXTURES / "verdi_la-bola-negra.html").read_text(encoding="utf-8")
    stripped = re.sub(r'x-show="[^"]*"', "", html)
    from_headers = parse_film(stripped, CINEMA, FILM_URL)
    assert [(s.date, s.time) for s in from_headers] == [(s.date, s.time) for s in bola_ca]


def test_vose_ingles_present(bola_es):
    assert any(s.version == "VOSE inglés" for s in bola_es)


def test_opera_session():
    ss = parse_film((FIXTURES / "verdi_otello.html").read_bytes(), CINEMA,
                    "https://barcelona.cines-verdi.com/otello-festival-de-salzburg")
    assert [(s.date, s.time, s.version_raw) for s in ss] == [("2026-11-01", "11:30", "OPERA")]
    assert not ss[0].special  # el ciclo de ópera va como sesión normal


def test_film_without_sessions():
    assert parse_film("<html><h1>Próximamente</h1></html>", CINEMA, FILM_URL) == []
