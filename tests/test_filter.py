from datetime import datetime
from zoneinfo import ZoneInfo

from scraper.build import filter_matinees
from scraper.models import Session

MADRID = ZoneInfo("Europe/Madrid")
CFG = {"matinee": {"cutoff": "13:00", "weekdays": [0, 1, 2, 3, 4]}}
# Martes 27/10/2026, 09:00 en Madrid
NOW = datetime(2026, 10, 27, 9, 0, tzinfo=MADRID)


def _s(date, time, title="Peli"):
    return Session(
        cinema_id="c", cinema_name="Cine", film_title=title, date=date, time=time,
        version="Doblada", version_raw="DIGITAL", ticket_url=None, film_url=None,
        special=False, source="publicine",
    )


def _keys(sessions):
    return [(s.date, s.time) for s in sessions]


def test_cutoff_is_inclusive():
    out = filter_matinees(
        [_s("2026-10-28", "12:59"), _s("2026-10-28", "13:00"), _s("2026-10-28", "13:01")],
        NOW, CFG,
    )
    assert _keys(out) == [("2026-10-28", "12:59"), ("2026-10-28", "13:00")]


def test_weekends_excluded():
    # 31/10 sábado, 01/11 domingo, 02/11 lunes
    out = filter_matinees(
        [_s("2026-10-31", "11:00"), _s("2026-11-01", "11:00"), _s("2026-11-02", "11:00")],
        NOW, CFG,
    )
    assert _keys(out) == [("2026-11-02", "11:00")]


def test_past_days_excluded_today_kept():
    # Hoy se conserva entera (aunque la sesión ya haya empezado: la web la atenúa)
    out = filter_matinees(
        [_s("2026-10-26", "11:00"), _s("2026-10-27", "08:00"), _s("2026-10-27", "11:30")],
        NOW, CFG,
    )
    assert _keys(out) == [("2026-10-27", "08:00"), ("2026-10-27", "11:30")]


def test_sorted_by_date_and_time():
    out = filter_matinees(
        [_s("2026-10-29", "10:00"), _s("2026-10-28", "12:00"), _s("2026-10-28", "11:00")],
        NOW, CFG,
    )
    assert _keys(out) == [("2026-10-28", "11:00"), ("2026-10-28", "12:00"), ("2026-10-29", "10:00")]


def test_cutoff_configurable():
    cfg = {"matinee": {"cutoff": "12:00", "weekdays": [0, 1, 2, 3, 4, 5, 6]}}
    out = filter_matinees([_s("2026-10-31", "12:00"), _s("2026-10-31", "12:01")], NOW, cfg)
    assert _keys(out) == [("2026-10-31", "12:00")]


def test_invalid_sessions_dropped():
    out = filter_matinees([_s("2026-10-28", "25:00"), _s("2026-10-28", "11:00")], NOW, CFG)
    assert _keys(out) == [("2026-10-28", "11:00")]


def test_horizon_two_weeks():
    # Hoy martes 27/10: con 14 días entra hasta el lunes 09/11, no el martes 10/11
    out = filter_matinees(
        [_s("2026-11-09", "11:00"), _s("2026-11-10", "11:00"), _s("2026-12-15", "11:00")],
        NOW, CFG,
    )
    assert _keys(out) == [("2026-11-09", "11:00")]


def test_horizon_configurable():
    cfg = {"matinee": {"cutoff": "13:00", "weekdays": [0, 1, 2, 3, 4], "horizon_days": 30}}
    out = filter_matinees([_s("2026-11-10", "11:00"), _s("2026-12-15", "11:00")], NOW, cfg)
    assert _keys(out) == [("2026-11-10", "11:00")]
