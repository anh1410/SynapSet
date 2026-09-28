"""Single source of "now" for anything time-sensitive (exam scheduling,
attempt deadlines). Call it as `clock.utcnow()` - not `from ... import
utcnow` - so tests can monkeypatch it to move time forward without sleeping."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)
