from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scraper.build import filter_matinees
from scraper.sources.publicine import _ticket_url, infer_year, parse

FIXTURE = Path(__file__).parent / "fixtures" / "publicine_kinepolis_splau.html"
CINEMA = {
    "id": "kinepolis-splau",
    "name": "Kinépolis Full Splau",
    "tickets_url": "https://kinepolis.es/?complex=PFULL",
}
# El fixture se descargó el jueves 29/10/2026 ("Hoy 29/10")
TODAY = date(2026, 10, 29)


@pytest.fixture(scope="module")
def sessions():
    return parse(FIXTURE.read_bytes(), CINEMA, TODAY)


@pytest.mark.parametrize(
    "day, month, today, expected",
    [
        (29, 10, date(2026, 10, 29), date(2026, 10, 29)),
        (4, 11, date(2026, 10, 29), date(2026, 11, 4)),
        (2, 1, date(2026, 12, 28), date(2027, 1, 2)),     # diciembre -> enero
        (30, 12, date(2027, 1, 2), date(2026, 12, 30)),   # página vieja vista en enero
        (29, 2, date(2028, 2, 27), date(2028, 2, 29)),    # bisiesto
    ],
)
def test_infer_year(day, month, today, expected):
    assert infer_year(day, month, today) == expected


def test_ticket_url_decodes_base64():
    href = "/venda/16328/33/aHR0cHM6Ly9raW5lcG9saXMuZXMvcHJvZ3JhbS9idXkvMS8xMDEwMjU2MTA1L2ZpbGVzLzAvMA"
    assert _ticket_url(href) == "https://kinepolis.es/program/buy/1/1010256105/files/0/0"
    assert _ticket_url("") is None
    assert _ticket_url("/venda/1/2/%%%") is None


def test_parses_all_sessions(sessions):
    assert len(sessions) == 406
    assert {s.date for s in sessions} == {f"2026-{d}" for d in
                                          ("10-29", "10-30", "10-31", "11-01", "11-02", "11-03", "11-04")}
    assert {s.version for s in sessions} == {"Doblada", "VOSE", "Català"}
    assert all(s.source == "publicine" and s.cinema_id == "kinepolis-splau" for s in sessions)


def test_first_session(sessions):
    s = sessions[0]
    assert (s.film_title, s.date, s.time, s.version, s.version_raw) == (
        "Arriba Tutto", "2026-10-29", "11:30", "Doblada", "DIGITAL")
    assert s.ticket_url == "https://kinepolis.es/program/buy/1/1010256105/files/0/0"
    assert s.film_url == "https://www.publicine.net/pelicula/16328/arriba-tutto"
    assert not s.special


def test_vose_and_catala(sessions):
    clayface_vose = [s for s in sessions if s.film_title == "Clayface" and s.version == "VOSE"]
    assert ("2026-10-29", "16:00") in {(s.date, s.time) for s in clayface_vose}
    assert any(s.version == "Català" and "(CAT)" in s.film_title.upper() for s in sessions)


def test_otros_eventos_are_special(sessions):
    special = [s for s in sessions if s.special]
    assert special and all("Ozzy" in s.film_title for s in special)


def test_matinees_from_fixture(sessions):
    now = datetime(2026, 10, 29, 6, 17, tzinfo=ZoneInfo("Europe/Madrid"))
    cfg = {"matinee": {"cutoff": "13:00", "weekdays": [0, 1, 2, 3, 4]}}
    m = filter_matinees(sessions, now, cfg)
    assert len(m) == 28
    assert {s.date for s in m} == {"2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03", "2026-11-04"}
    assert (m[0].time, m[-1].time) == ("11:00", "12:15")
