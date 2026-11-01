from pathlib import Path

import pytest

from scraper.sources.filmagenda import extract_sessions, parse, version_of

FIXTURES = Path(__file__).parent / "fixtures"


def _load(slug, name="Cine"):
    cinema = {"id": slug, "name": name, "tickets_url": "https://cine.example/"}
    return parse((FIXTURES / f"filmagenda_{slug}.html").read_bytes(), cinema)


@pytest.mark.parametrize(
    "raw, languages, expected",
    [
        ("dubbed", ["en"], ("Doblada", "dubbed")),
        ("vose", ["he"], ("VOSE", "vose")),
        ("vose", ["es"], ("Doblada", "vose")),
        ("vose", ["ca"], ("Català", "vose")),
        ("vose", [], ("Desconocida", "VO")),
        (None, ["en"], ("Desconocida", "")),
    ],
)
def test_version_of(raw, languages, expected):
    assert version_of(raw, languages) == expected


@pytest.mark.parametrize(
    "slug, count",
    [("verdi-barcelona", 98), ("verdi-park", 96), ("cinemes-girona", 55), ("cinema-malda", 18),
     ("caixaforum-barcelona", 25)],
)
def test_parses_all_rows(slug, count):
    sessions = _load(slug)
    assert len(sessions) == count
    assert all(s.is_valid() and s.source == "filmagenda" and s.ticket_url for s in sessions)


def test_verdi_park_matinee():
    s = next(s for s in _load("verdi-park")
             if (s.film_title, s.date, s.time) == ("La bola negra", "2026-11-02", "11:30"))
    assert s.version == "Doblada"  # película española: "vose" no significa subtitulada
    assert s.ticket_url.startswith("https://verdibcn.admit-one.eu/seats/")


def test_foreign_film_is_vose():
    s = next(s for s in _load("verdi-park") if s.film_title == "Naza")
    assert s.version == "VOSE"


def test_ticket_falls_back_to_info_page():
    s = next(s for s in _load("cinema-malda") if s.film_title == "Vivir la tierra")
    assert (s.date, s.time) == ("2026-11-05", "12:15")
    assert s.ticket_url == "https://www.cinemamalda.com/vivir-la-tierra/"


def test_caixaforum_notes():
    sessions = {s.film_title: s for s in _load("caixaforum-barcelona")}
    minari = sessions["Minari. Historia de mi familia"]
    assert (minari.date, minari.time, minari.version, minari.special) == ("2026-11-18", "10:30", "Doblada", True)
    assert minari.ticket_url.startswith("https://ticket.caixaforum.org/")
    inclus = sessions["Sección Oficial 4"]
    assert (inclus.version, inclus.version_raw, inclus.special) == ("Desconocida", "", True)


def test_changed_page_is_an_error():
    with pytest.raises(ValueError):
        extract_sessions("<html>nada</html>")
