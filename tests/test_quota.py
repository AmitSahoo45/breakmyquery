"""Admission tests use a controllable monotonic clock and no provider calls."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def limiter_for(clock, **limits):
    from bmq.quota import QuotaLimiter

    return QuotaLimiter(clock=clock, **limits)


def test_only_one_call_can_be_active_and_release_allows_the_next():
    limiter = limiter_for(Clock())
    assert limiter.acquire(100) is None
    assert limiter.acquire(100) == 'busy'
    limiter.release()
    assert limiter.acquire(100) is None
    limiter.release()


def test_failure_release_keeps_the_attempt_in_the_minute_budget():
    limiter = limiter_for(Clock(), max_requests=1)
    assert limiter.acquire(100) is None
    with pytest.raises(RuntimeError, match='provider failed'):
        try:
            raise RuntimeError('provider failed')
        finally:
            limiter.release()
    assert limiter.acquire(100) == 'minute_requests'


def test_six_request_limit_expires_individual_attempts_after_sixty_seconds():
    clock = Clock()
    limiter = limiter_for(clock)
    assert limiter.acquire(1) is None
    limiter.release()
    clock.now = 10
    for _ in range(5):
        assert limiter.acquire(1) is None
        limiter.release()
    clock.now = 59.999
    assert limiter.acquire(1) == 'minute_requests'
    clock.now = 60
    assert limiter.acquire(1) is None
    limiter.release()
    assert limiter.acquire(1) == 'minute_requests'
    clock.now = 70
    assert limiter.acquire(1) is None
    limiter.release()


def test_token_budget_keeps_each_estimate_until_its_own_expiry():
    clock = Clock()
    limiter = limiter_for(clock)
    assert limiter.acquire(7000) is None
    limiter.release()
    clock.now = 20
    assert limiter.acquire(5000) is None
    limiter.release()
    assert limiter.acquire(1) == 'minute_tokens'
    clock.now = 60
    assert limiter.acquire(7000) is None
    limiter.release()
    assert limiter.acquire(1) == 'minute_tokens'
    clock.now = 80
    assert limiter.acquire(5000) is None
    limiter.release()


def test_oversized_request_is_rejected_without_consuming_a_slot_or_budget():
    limiter = limiter_for(Clock())
    assert limiter.acquire(12001) == 'request_too_large'
    assert limiter.acquire(12000) is None
    limiter.release()


def test_daily_budget_is_one_thousand_attempts_in_a_rolling_day():
    clock = Clock()
    limiter = limiter_for(clock)
    for index in range(1000):
        clock.now = index * 60
        assert limiter.acquire(1) is None
        limiter.release()
    clock.now = 86399
    assert limiter.acquire(1) == 'daily_requests'
    clock.now = 86400
    assert limiter.acquire(1) is None
    limiter.release()
    assert limiter.acquire(1) == 'daily_requests'
    clock.now = 86460
    assert limiter.acquire(1) is None
    limiter.release()


def test_cooldown_is_shared_and_shorter_updates_do_not_shorten_it():
    clock = Clock()
    limiter = limiter_for(clock)
    assert limiter.acquire(100) is None
    limiter.cool_down(30)
    limiter.release()
    assert limiter.acquire(100) == 'cooldown'
    clock.now = 10
    limiter.cool_down(5)
    clock.now = 29.999
    assert limiter.acquire(100) == 'cooldown'
    clock.now = 30
    assert limiter.acquire(100) is None
    limiter.release()


def test_cooldown_clamps_to_one_hour_and_rejections_do_not_consume_budget():
    clock = Clock()
    limiter = limiter_for(clock, max_requests=1)
    limiter.cool_down(999999)
    clock.now = 3599.999
    for _ in range(10):
        assert limiter.acquire(1) == 'cooldown'
    clock.now = 3600
    assert limiter.acquire(1) is None
    limiter.release()


def test_negative_cooldown_does_not_block_or_shorten_an_existing_cooldown():
    clock = Clock()
    limiter = limiter_for(clock)
    limiter.cool_down(-1)
    assert limiter.acquire(1) is None
    limiter.release()
    limiter.cool_down(20)
    clock.now = 5
    limiter.cool_down(-1)
    assert limiter.acquire(1) == 'cooldown'


def test_concurrent_admission_allows_exactly_one_active_call():
    limiter = limiter_for(Clock())
    barrier = Barrier(8)

    def acquire_together(_):
        barrier.wait(timeout=5)
        return limiter.acquire(100)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(acquire_together, range(8)))
    assert results.count(None) == 1
    assert results.count('busy') == 7
    limiter.release()
    assert limiter.acquire(100) is None
    limiter.release()


@pytest.mark.parametrize('tokens', [-1, 0, 1.5, True, '100'])
def test_invalid_estimates_are_rejected_without_consuming_budget(tokens):
    limiter = limiter_for(Clock(), max_requests=1)
    with pytest.raises(ValueError, match='positive integer'):
        limiter.acquire(tokens)
    assert limiter.acquire(100) is None
    limiter.release()


@pytest.mark.parametrize('seconds', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_cooldown_does_not_poison_the_limiter(seconds):
    limiter = limiter_for(Clock())
    with pytest.raises(ValueError, match='finite'):
        limiter.cool_down(seconds)
    assert limiter.acquire(100) is None
    limiter.release()
