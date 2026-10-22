from __future__ import annotations

import threading
from collections import defaultdict
from contextlib import contextmanager

from sqlalchemy import or_

from app.extensions import database
from app.models import AiAccount, AiProvider, now


class ProviderUnavailable(RuntimeError):
    pass


class ProviderPool:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._in_flight: dict[str, int] = defaultdict(int)
        self._scores: dict[str, int] = defaultdict(int)
        self._weights: dict[str, int] = {}

    def select(self, candidates: list[tuple[AiAccount, AiProvider]]) -> tuple[AiAccount, AiProvider]:
        """Smooth weighted round robin per answer attempt, after capability filtering."""
        with self._lock:
            eligible = [pair for pair in candidates if self._in_flight[pair[0].id] < pair[0].concurrency_limit]
            if not eligible:
                raise ProviderUnavailable()
            weights = {account.id: max(account.weight, 1) for account, _ in eligible}
            if weights != self._weights:
                self._scores.clear()
                self._weights = weights
            for key, weight in weights.items():
                self._scores[key] += weight
            selected = max(eligible, key=lambda pair: self._scores[pair[0].id])
            self._scores[selected[0].id] -= sum(weights.values())
            return selected

    def candidates(self, excluded: set[str] | None = None) -> list[tuple[AiAccount, AiProvider]]:
        excluded = excluded or set()
        rows = database.session.query(AiAccount, AiProvider).join(
            AiProvider, AiProvider.id == AiAccount.provider_id
        ).filter(
            AiAccount.status == "ACTIVE",
            AiProvider.status == "ACTIVE",
            or_(AiAccount.cooldown_until.is_(None), AiAccount.cooldown_until <= now()),
        ).all()
        with self._lock:
            eligible = [(account, provider) for account, provider in rows
                        if account.id not in excluded and self._in_flight[account.id] < account.concurrency_limit]
            return sorted(eligible, key=lambda pair: (
                self._in_flight[pair[0].id] / max(pair[0].weight, 1), -pair[0].weight, pair[0].created_at
            ))

    @contextmanager
    def acquire(self, account: AiAccount):
        with self._lock:
            if self._in_flight[account.id] >= account.concurrency_limit:
                raise ProviderUnavailable()
            self._in_flight[account.id] += 1
        try:
            yield
        finally:
            with self._lock:
                self._in_flight[account.id] -= 1


provider_pool = ProviderPool()
