import json
import os
from unittest.mock import Mock

import pytest
import requests

import telegram_notifications
from telegram_notifications import TelegramRetryTelemetry, send_to_telegram


@pytest.fixture(autouse=True)
def _patch_failed_notifications_path(tmp_path, monkeypatch):
    fallback_path = tmp_path / "failed_notifications.txt"
    monkeypatch.setattr(telegram_notifications, "FAILED_NOTIFICATIONS_PATH", str(fallback_path))
    return fallback_path


def test_send_to_telegram_retries_on_connection_error(monkeypatch):
    session = Mock(spec=requests.Session)

    responses = [
        requests.exceptions.ConnectionError("connection aborted"),
        Mock(status_code=200, text="OK"),
    ]

    def side_effect(*args, **kwargs):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    session.post.side_effect = side_effect

    telemetry = TelegramRetryTelemetry(summary_interval=3600)

    result = send_to_telegram(
        session,
        "token",
        "chat",
        "hello",
        notice_id=123,
        telemetry=telemetry,
        sleep_func=lambda _: None,
    )

    assert result.success is True
    assert result.attempts == 2
    assert session.post.call_count == 2
    assert telemetry.total_sent == 1
    assert telemetry.total_retried == 1
    assert telemetry.total_failed == 0
    assert not os.path.exists(telegram_notifications.FAILED_NOTIFICATIONS_PATH)


def test_send_to_telegram_handles_fatal_error():
    session = Mock(spec=requests.Session)
    response = Mock(status_code=403, text="Forbidden")
    session.post.return_value = response

    telemetry = TelegramRetryTelemetry(summary_interval=3600)

    result = send_to_telegram(
        session,
        "token",
        "chat",
        "hello",
        notice_id=321,
        telemetry=telemetry,
        sleep_func=lambda _: None,
    )

    assert result.success is False
    assert result.attempts == 1
    assert session.post.call_count == 1
    assert telemetry.total_failed == 1
    assert telemetry.consecutive_failures == 1

    fallback_path = telegram_notifications.FAILED_NOTIFICATIONS_PATH
    assert fallback_path
    with open(fallback_path, "r", encoding="utf-8") as fh:
        lines = [line.strip() for line in fh if line.strip()]

    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["notice_id"] == 321
    assert entry["attempts"] == 1
    assert entry["parse_mode"] == "HTML"
    assert "403" in entry["reason"]
    assert entry["message"] == "hello"
