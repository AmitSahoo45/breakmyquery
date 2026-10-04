"""Process-local admission control for one shared provider project.

Keep one instance for all app sessions, regardless of the API key. The rolling
24-hour allowance, minute budgets and cooldown are memory-only: restarting the
process resets them, and separate processes do not share these limits. This is
a conservative demo budget, not the provider's authoritative quota tracker.

Callers supply an integer input-token estimate; no key, SQL or prompt is stored.
Counting UTF-8 bytes plus overhead is a conservative heuristic, not a tokenizer
guarantee. A successful admission counts even if the provider request fails.
Always call release() in a finally block after a successful acquire().
"""

from collections import deque
from collections.abc import Callable
import math
from threading import Lock
import time
from typing import Literal


AdmissionFailure = Literal[
    'busy', 'cooldown', 'minute_requests', 'minute_tokens',
    'daily_requests', 'request_too_large',
]


class QuotaLimiter:
    def __init__(
        self, *, clock: Callable[[], float] = time.monotonic,
        max_requests: int = 6, max_input_tokens: int = 12_000,
        max_daily_requests: int = 1000,
    ):
        self._clock = clock
        self._max_requests = max_requests
        self._max_input_tokens = max_input_tokens
        self._max_daily_requests = max_daily_requests
        self._minute: deque[tuple[float, int]] = deque()
        self._daily: deque[float] = deque()
        self._minute_tokens = 0
        self._active = False
        self._cooldown_until = 0.0
        self._lock = Lock()

    def acquire(self, tokens: int) -> AdmissionFailure | None:
        """Reserve one request immediately; return a reason when not admitted."""
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0:
            raise ValueError('The input estimate must be a positive integer.')
        with self._lock:
            now = self._clock()
            while self._minute and self._minute[0][0] <= now - 60:
                _, expired_tokens = self._minute.popleft()
                self._minute_tokens -= expired_tokens
            while self._daily and self._daily[0] <= now - 86_400:
                self._daily.popleft()

            if tokens > self._max_input_tokens:
                return 'request_too_large'
            if now < self._cooldown_until:
                return 'cooldown'
            if self._active:
                return 'busy'
            if len(self._daily) >= self._max_daily_requests:
                return 'daily_requests'
            if len(self._minute) >= self._max_requests:
                return 'minute_requests'
            if self._minute_tokens + tokens > self._max_input_tokens:
                return 'minute_tokens'

            self._minute.append((now, tokens))
            self._daily.append(now)
            self._minute_tokens += tokens
            self._active = True
            return None

    def release(self) -> None:
        """Release the active request without refunding any quota allowance."""
        with self._lock:
            self._active = False

    def cool_down(self, seconds: float) -> None:
        """Apply a provider cooldown, bounded to one hour and never shortened."""
        if not math.isfinite(seconds):
            raise ValueError('Cooldown seconds must be finite.')
        seconds = max(0.0, min(seconds, 3600.0))
        with self._lock:
            self._cooldown_until = max(self._cooldown_until, self._clock() + seconds)
