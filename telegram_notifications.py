import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Sequence

import requests
from http.client import RemoteDisconnected
from requests import Response
from requests.exceptions import (ConnectionError as RequestsConnectionError,
                                 ReadTimeout, RequestException, Timeout)
from urllib3.exceptions import ProtocolError

BACKOFF_SCHEDULE: Sequence[float] = (0.5, 1, 2, 4, 8)
FAILED_NOTIFICATIONS_PATH = os.path.expanduser(
    "~/projects/content_factory/failed_notifications.txt"
)
FATAL_STATUS_CODES = {401, 403}
RETRYABLE_STATUS_CODES = {429, *range(500, 600)}
RETRYABLE_EXCEPTIONS = (
    RequestsConnectionError,
    Timeout,
    ReadTimeout,
    RemoteDisconnected,
    ProtocolError,
)


@dataclass
class TelegramSendResult:
    success: bool
    attempts: int
    reason: Optional[str] = None


class TelegramRetryTelemetry:
    def __init__(self, summary_interval: float = 60.0) -> None:
        self.summary_interval = summary_interval
        self.last_summary_time = time.monotonic()

        self.total_sent = 0
        self.total_retried = 0
        self.total_failed = 0

        self.consecutive_failures = 0
        self.last_failure_reason: Optional[str] = None

        self._window_attempts: list[int] = []
        self._window_sent = 0
        self._window_retried = 0
        self._window_failed = 0

    def record_result(self, attempts: int, success: bool, reason: Optional[str] = None) -> None:
        attempts = max(1, attempts)
        self._window_attempts.append(attempts)

        if success:
            self.total_sent += 1
            self._window_sent += 1
            if attempts > 1:
                self.total_retried += 1
                self._window_retried += 1

            if self.consecutive_failures >= 3:
                logging.info(
                    "✅ Telegram delivery recovered after %d consecutive failures",
                    self.consecutive_failures,
                )

            self.consecutive_failures = 0
        else:
            self.total_failed += 1
            self._window_failed += 1
            self.consecutive_failures += 1
            self.last_failure_reason = reason

            if self.consecutive_failures > 3:
                logging.error(
                    "🚨 Telegram: %d consecutive failures. Проверьте статус Telegram API.",
                    self.consecutive_failures,
                )

        self.maybe_log_summary()

    def maybe_log_summary(self) -> None:
        now = time.monotonic()
        if now - self.last_summary_time < self.summary_interval:
            return

        if self._window_attempts:
            avg_attempts = sum(self._window_attempts) / len(self._window_attempts)
        else:
            avg_attempts = 0.0

        logging.info(
            "📊 Telegram summary: total_sent=%d, total_retried=%d, total_failed=%d | "
            "window_sent=%d, window_retried=%d, window_failed=%d, avg_attempts=%.2f",
            self.total_sent,
            self.total_retried,
            self.total_failed,
            self._window_sent,
            self._window_retried,
            self._window_failed,
            avg_attempts,
        )

        if self._window_failed and self.last_failure_reason:
            logging.info("   Последняя ошибка: %s", self.last_failure_reason)

        self._window_attempts.clear()
        self._window_sent = 0
        self._window_retried = 0
        self._window_failed = 0
        self.last_summary_time = now


def _truncate(text: str, limit: int = 200) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def append_failed_notification(
    notice_id: Optional[int],
    message: str,
    reason: Optional[str],
    attempts: int,
    parse_mode: Optional[str],
    *,
    path: Optional[str] = None,
) -> None:
    resolved_path = path or FAILED_NOTIFICATIONS_PATH
    directory = os.path.dirname(resolved_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)

    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "notice_id": notice_id,
        "reason": reason,
        "message": message,
        "attempts": attempts,
        "parse_mode": parse_mode,
    }

    with open(resolved_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    logging.error("💾 Сообщение сохранено в резервный файл: %s", resolved_path)


def send_to_telegram(
    session: Optional[requests.Session],
    token: Optional[str],
    chat_id: Optional[str],
    message: str,
    *,
    notice_id: Optional[int] = None,
    telemetry: Optional[TelegramRetryTelemetry] = None,
    timeout: float = 10.0,
    backoff_schedule: Optional[Sequence[float]] = None,
    sleep_func: Callable[[float], None] = time.sleep,
    parse_mode: str = "HTML",
    fallback_on_failure: bool = True,
) -> TelegramSendResult:
    if not token or not chat_id:
        reason = "missing telegram credentials"
        logging.error("❌ Telegram: TELEGRAM_TOKEN или TELEGRAM_CHAT_ID не заданы")
        if telemetry:
            telemetry.record_result(0, False, reason)
        if fallback_on_failure:
            append_failed_notification(notice_id, message, reason, 0, parse_mode)
        return TelegramSendResult(success=False, attempts=0, reason=reason)

    schedule = tuple(backoff_schedule) if backoff_schedule else BACKOFF_SCHEDULE
    max_attempts = 1 + len(schedule)

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    if parse_mode:
        payload["parse_mode"] = parse_mode

    temp_session = session or requests.Session()
    close_session = session is None

    attempts_made = 0
    last_reason: Optional[str] = None

    try:
        while attempts_made < max_attempts:
            attempts_made += 1
            try:
                response: Response = temp_session.post(api_url, json=payload, timeout=timeout)
            except RETRYABLE_EXCEPTIONS as exc:
                last_reason = f"{type(exc).__name__}: {exc}"
                if attempts_made >= max_attempts:
                    logging.error(
                        "❌ Telegram: попытка %d завершилась с ошибкой %s",
                        attempts_made,
                        last_reason,
                    )
                    break

                delay = schedule[attempts_made - 1]
                logging.warning(
                    "🔁 Telegram retry %d/%d: %s → следующая попытка через %.1fs",
                    attempts_made,
                    max_attempts,
                    last_reason,
                    delay,
                )
                sleep_func(delay)
                continue
            except RequestException as exc:
                last_reason = f"{type(exc).__name__}: {exc}"
                logging.error(
                    "❌ Telegram: необработанная ошибка на попытке %d: %s",
                    attempts_made,
                    last_reason,
                )
                break

            if response.status_code == 200:
                logging.info("✅ Отправлено (попытка %d)", attempts_made)
                if telemetry:
                    telemetry.record_result(attempts_made, True)
                return TelegramSendResult(success=True, attempts=attempts_made)

            body_preview = _truncate(response.text)

            if response.status_code in FATAL_STATUS_CODES:
                last_reason = f"HTTP {response.status_code}: {body_preview}"
                logging.critical(
                    "⛔ Telegram отклонил запрос (попытка %d): %s",
                    attempts_made,
                    last_reason,
                )
                break

            if response.status_code in RETRYABLE_STATUS_CODES:
                last_reason = f"HTTP {response.status_code}: {body_preview}"
                if attempts_made >= max_attempts:
                    logging.error(
                        "❌ Telegram: исчерпаны попытки отправки (%s)",
                        last_reason,
                    )
                    break

                delay = schedule[attempts_made - 1]
                logging.warning(
                    "🔁 Telegram retry %d/%d: %s → следующая попытка через %.1fs",
                    attempts_made,
                    max_attempts,
                    last_reason,
                    delay,
                )
                sleep_func(delay)
                continue

            last_reason = f"HTTP {response.status_code}: {body_preview}"
            logging.error(
                "❌ Telegram: неожиданный статус %s на попытке %d",
                response.status_code,
                attempts_made,
            )
            break

        fail_reason = last_reason or "unknown error"
        attempts_made = max(1, attempts_made)

        if telemetry:
            telemetry.record_result(attempts_made, False, fail_reason)

        logging.error(
            "❌ Telegram: не удалось отправить сообщение после %d попыток: %s",
            attempts_made,
            fail_reason,
        )

        if fallback_on_failure:
            append_failed_notification(
                notice_id,
                message,
                fail_reason,
                attempts_made,
                parse_mode,
            )

        return TelegramSendResult(
            success=False,
            attempts=attempts_made,
            reason=fail_reason,
        )
    finally:
        if close_session:
            temp_session.close()
