"""Robots and per-host spacing for the one ingestion fetch.

Stdlib only. Callers pass a transport so tests never open a socket.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

USER_AGENT = "DeavenBot/0.1 (+https://github.com/JbawbyJ/Deaven; listing-ingestion)"

Clock = Callable[[], float]
Sleeper = Callable[[float], None]
Transport = Callable[[str, dict[str, str]], tuple[int, str]]


class RobotsDisallowed(Exception):
    def __init__(self, url: str, reason: str = "robots_disallow"):
        self.url = url
        self.reason = reason
        super().__init__(f"{reason}: {url}")


@dataclass(frozen=True)
class RobotsDecision:
    allowed: bool
    crawl_delay_s: float
    reason: str


def host_of(url: str) -> str:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ValueError(f"refusing non-http URL: {url}")
    port = parsed.port
    default_port = 80 if parsed.scheme == "http" else 443
    if port and port != default_port:
        return f"{hostname}:{port}"
    return hostname


def robots_url_for(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{host_of(url)}/robots.txt"


def decide_robots(body: str, user_agent: str, url: str) -> RobotsDecision:
    parser = RobotFileParser()
    parser.parse(body.splitlines())
    allowed = parser.can_fetch(user_agent, url)
    delay = float(parser.crawl_delay(user_agent) or 0)
    return RobotsDecision(
        allowed=allowed,
        crawl_delay_s=delay,
        reason="allowed" if allowed else "robots_disallow",
    )


class DomainRateLimiter:
    """Space requests to one host. `sleep` is injected so tests do not wait."""

    def __init__(
        self,
        min_interval_s: float = 1.0,
        clock: Clock | None = None,
        sleep: Sleeper | None = None,
    ) -> None:
        if min_interval_s < 0:
            raise ValueError("min_interval_s must be >= 0")
        self.min_interval_s = min_interval_s
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._last_at: dict[str, float] = {}

    def acquire(self, domain: str, crawl_delay_s: float = 0.0) -> float:
        gap = max(self.min_interval_s, crawl_delay_s)
        now = self._clock()
        last = self._last_at.get(domain)
        if last is None:
            wait = 0.0
            self._last_at[domain] = now
        else:
            earliest = last + gap
            wait = max(0.0, earliest - now)
            self._last_at[domain] = max(now, earliest)
        if wait:
            self._sleep(wait)
        return wait


def default_transport(url: str, headers: dict[str, str]) -> tuple[int, str]:
    """Live HTTP GET. Tests pass their own transport and do not call this."""
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
            status = getattr(response, "status", 200)
            charset = response.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
        charset = "utf-8"
    return status, raw.decode(charset, errors="replace")
