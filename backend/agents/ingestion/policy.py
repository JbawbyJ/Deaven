"""Per-source robots.txt check, terms note, and rate limiter.

RobotFileParser.parse reads a saved robots.txt body. RobotFileParser.read
is not used, because it fetches the URL.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.robotparser import RobotFileParser

from shared.schemas.deal import DealSource
from shared.schemas.market import Source, source_for

USER_AGENT = "DeavenListingBot/0.1"


@dataclass(frozen=True)
class SourcePolicy:
    code: DealSource
    user_agent: str
    min_interval_seconds: float
    tos_note: str

    @property
    def source(self) -> Source:
        """Catalog entry. robots_ok and tos_reviewed stay false."""
        return source_for(self.code)

    @property
    def robots_url(self) -> str:
        return self.source.base_url.rstrip("/") + "/robots.txt"


class RobotsDenied(PermissionError):
    def __init__(self, source: str, url: str) -> None:
        self.source = source
        self.url = url
        super().__init__(f"{source} robots.txt disallows {url}")


def robots_allowed(robots_txt: str, user_agent: str, url: str) -> bool:
    parser = RobotFileParser()
    parser.parse(robots_txt.splitlines())
    return bool(parser.can_fetch(user_agent, url))


class RateLimiter:
    """One limiter per source. Tests inject clock and sleep."""

    def __init__(
        self,
        min_interval_seconds: float,
        *,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must be >= 0")
        self.min_interval_seconds = float(min_interval_seconds)
        self._clock = clock
        self._sleep = sleep
        self._next: float | None = None

    def acquire(self) -> float:
        now = self._clock()
        waited = 0.0
        if self._next is not None and now < self._next:
            waited = self._next - now
            self._sleep(waited)
            now = self._clock()
        self._next = now + self.min_interval_seconds
        return waited


def authorize(policy: SourcePolicy, robots_txt: str, url: str, limiter: RateLimiter) -> None:
    """Refuse a URL robots.txt disallows, then consume one rate-limit slot."""
    if not robots_allowed(robots_txt, policy.user_agent, url):
        raise RobotsDenied(policy.code.value, url)
    limiter.acquire()
