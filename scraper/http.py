"""Cliente HTTP educado: User-Agent identificable, pausa por dominio, robots.txt, 1 reintento."""
from __future__ import annotations

import logging
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

log = logging.getLogger(__name__)

USER_AGENT = "MatineesBCN/1.0 (+https://github.com/guillepb/matinees; scraper personal de horarios)"
TIMEOUT = 20
DELAY = 1.5  # segundos entre peticiones a un mismo dominio


class RobotsDisallowed(Exception):
    pass


class Http:
    def __init__(self, delay: float = DELAY, timeout: float = TIMEOUT):
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "es-ES,es;q=0.9"})
        self._last: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}

    def _wait(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            pause = self.delay - (time.monotonic() - last)
            if pause > 0:
                time.sleep(pause)
        self._last[host] = time.monotonic()

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            rp = RobotFileParser()
            try:
                self._wait(parts.netloc)
                r = self.session.get(base + "/robots.txt", timeout=self.timeout)
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except requests.RequestException:
                rp.parse([])  # sin robots.txt accesible: se permite
            self._robots[base] = rp
        return self._robots[base].can_fetch(USER_AGENT, url)

    def get(self, url: str, params: dict | None = None) -> requests.Response:
        if not self._allowed(url):
            raise RobotsDisallowed(url)
        host = urlsplit(url).netloc
        for attempt in (1, 2):
            self._wait(host)
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
                if r.status_code >= 500 and attempt == 1:
                    log.warning("HTTP %s en %s, reintentando", r.status_code, url)
                    continue
                r.raise_for_status()
                return r
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt == 2:
                    raise
                log.warning("%s en %s, reintentando", type(e).__name__, url)
        raise RuntimeError("unreachable")
