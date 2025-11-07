#!/usr/bin/env python3
"""Повторная отправка Telegram уведомлений из fallback файла."""

import json
import logging
import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

from telegram_notifications import (
    FAILED_NOTIFICATIONS_PATH,
    TelegramRetryTelemetry,
    send_to_telegram,
)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()],
    )


def _load_failed_notifications(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []

    entries: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for index, raw_line in enumerate(fh, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                logging.error(
                    "⚠️ Не удалось разобрать строку #%d в fallback файле: %s (%s)",
                    index,
                    line,
                    exc,
                )
                continue
            entries.append(entry)
    return entries


def _persist_failed_notifications(path: str, entries: list[dict]) -> None:
    if not entries:
        if os.path.exists(path):
            os.remove(path)
        return

    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> int:
    load_dotenv()
    _configure_logging()

    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    entries = _load_failed_notifications(FAILED_NOTIFICATIONS_PATH)
    if not entries:
        logging.info("🎉 Нет неотправленных уведомлений в fallback файле")
        return 0

    if not token or not chat_id:
        logging.critical(
            "❌ Невозможно выполнить повторную отправку: TELEGRAM_TOKEN/TELEGRAM_CHAT_ID не заданы"
        )
        return 1

    telemetry = TelegramRetryTelemetry()
    remaining: list[dict] = []
    successes = 0

    with requests.Session() as session:
        for entry in entries:
            message = entry.get("message", "")
            notice_id = entry.get("notice_id")
            reason = entry.get("reason")
            parse_mode = entry.get("parse_mode", "HTML")

            logging.info(
                "🔄 Повторная отправка ID=%s (предыдущая ошибка: %s)",
                notice_id or "n/a",
                reason or "неизвестно",
            )

            result = send_to_telegram(
                session,
                token,
                chat_id,
                message,
                notice_id=notice_id,
                telemetry=telemetry,
                parse_mode=parse_mode,
                fallback_on_failure=False,
            )

            if result.success:
                successes += 1
                continue

            entry["reason"] = result.reason
            entry["attempts"] = result.attempts
            entry["last_retry_at"] = datetime.utcnow().isoformat() + "Z"
            remaining.append(entry)

    _persist_failed_notifications(FAILED_NOTIFICATIONS_PATH, remaining)

    logging.info(
        "📦 Повторная отправка завершена: всего=%d, отправлено=%d, осталось=%d",
        len(entries),
        successes,
        len(remaining),
    )

    return 0 if not remaining else 1


if __name__ == "__main__":
    sys.exit(main())
