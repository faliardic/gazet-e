"""Bounded RSS-only network adapter for the Q06 source registry."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import feedparser
import requests

from services.edition_news_models import (
    ArticleCandidate,
    CollectionResult,
    FetchResult,
    SourceDefinition,
)
from services.edition_news_normalize import (
    CandidateNormalizationError,
    normalize_entry,
)
from services.edition_news_registry import REGISTRY_VERSION, RSS_REGISTRY

USER_AGENT = "Gazet+E/2.0 (+https://github.com/faliardic/gazet-e; RSS reader)"
CONNECT_TIMEOUT_SECONDS = 3.0
READ_TIMEOUT_SECONDS = 7.0
MAX_FETCH_ATTEMPTS = 2
MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_ITEMS_PER_FEED = 30
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}


class EditionNewsCollector:
    def __init__(
        self,
        *,
        registry: Sequence[SourceDefinition] = RSS_REGISTRY,
        session: Any | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._registry = tuple(registry)
        _validate_registry(self._registry)
        if session is None:
            production_session = requests.Session()
            production_session.max_redirects = MAX_REDIRECTS
            self._session = production_session
        else:
            self._session = session
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sleeper = sleeper

    def collect(self) -> CollectionResult:
        collected_at = self._clock()
        results = tuple(self._fetch_source(source) for source in self._registry)
        candidates = tuple(
            candidate
            for result in results
            for candidate in result.candidates
        )
        return CollectionResult(
            policy_version=REGISTRY_VERSION,
            collected_at=collected_at,
            fetch_results=results,
            candidates=candidates,
        )

    def _fetch_source(self, source: SourceDefinition) -> FetchResult:
        fetched_at = self._clock()
        last_status: int | None = None
        for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
            response = None
            try:
                response = self._session.get(
                    source.feed_url,
                    headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml;q=0.9"},
                    timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
                    allow_redirects=True,
                    stream=True,
                )
                last_status = int(response.status_code)
                if not _redirect_chain_is_https(response):
                    return _failure(source, fetched_at, "unsafe_redirect", last_status)
                if last_status in RETRYABLE_HTTP_STATUSES:
                    if attempt < MAX_FETCH_ATTEMPTS:
                        self._sleeper(0.2 * attempt)
                        continue
                    return _failure(source, fetched_at, "http_retry_exhausted", last_status)
                if last_status < 200 or last_status >= 300:
                    return _failure(source, fetched_at, "http_error", last_status)
                payload = _read_bounded(response)
                return self._parse_payload(source, fetched_at, last_status, payload)
            except _ResponseTooLarge:
                return _failure(source, fetched_at, "response_too_large", last_status)
            except requests.RequestException:
                if attempt < MAX_FETCH_ATTEMPTS:
                    self._sleeper(0.2 * attempt)
                    continue
                return _failure(source, fetched_at, "network_error", last_status)
            except Exception:
                return _failure(source, fetched_at, "fetch_error", last_status)
            finally:
                if response is not None:
                    response.close()
        return _failure(source, fetched_at, "fetch_error", last_status)

    def _parse_payload(
        self,
        source: SourceDefinition,
        fetched_at: datetime,
        http_status: int,
        payload: bytes,
    ) -> FetchResult:
        parsed = feedparser.parse(payload)
        entries = tuple(parsed.entries[:MAX_ITEMS_PER_FEED])
        if not entries and getattr(parsed, "bozo", False):
            return _failure(source, fetched_at, "invalid_feed", http_status)

        candidates: list[ArticleCandidate] = []
        errors: list[str] = []
        for entry in entries:
            try:
                candidates.append(normalize_entry(entry, source, fetched_at))
            except CandidateNormalizationError as error:
                errors.append(error.reason_code)
            except Exception:
                errors.append("invalid_feed_entry")
        return FetchResult(
            publisher_id=source.publisher_id,
            source_id=source.source_id,
            fetched_at=fetched_at,
            success=True,
            status="ok",
            http_status=http_status,
            item_count=len(candidates),
            rejected_item_count=len(errors),
            diagnostic="RSS feed parsed within bounded limits.",
            item_errors=tuple(errors[:MAX_ITEMS_PER_FEED]),
            candidates=tuple(candidates),
        )


class _ResponseTooLarge(RuntimeError):
    pass


def _read_bounded(response: Any) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise _ResponseTooLarge
        chunks.append(bytes(chunk))
    return b"".join(chunks)


def _redirect_chain_is_https(response: Any) -> bool:
    chain = [*getattr(response, "history", ()), response]
    return all(urlsplit(str(item.url)).scheme.lower() == "https" for item in chain)


def _failure(
    source: SourceDefinition,
    fetched_at: datetime,
    status: str,
    http_status: int | None,
) -> FetchResult:
    return FetchResult(
        publisher_id=source.publisher_id,
        source_id=source.source_id,
        fetched_at=fetched_at,
        success=False,
        status=status,
        http_status=http_status,
        diagnostic="Feed was unavailable within the bounded RSS policy.",
    )


def _validate_registry(registry: tuple[SourceDefinition, ...]) -> None:
    if not registry:
        raise ValueError("RSS registry must not be empty.")
    source_ids = [source.source_id for source in registry]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("RSS registry source IDs must be unique.")
    if any(urlsplit(source.feed_url).scheme.lower() != "https" for source in registry):
        raise ValueError("RSS registry URLs must be HTTPS.")
