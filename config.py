"""Configuration helpers for Upbit Notice Bot."""

import argparse
import os
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

DEFAULT_MODE = "api"
VALID_MODES = {"api", "html"}
ENV_MODE_VAR = "UPBIT_MODE"
API_ERROR_THRESHOLD_ENV = "UPBIT_API_ERROR_THRESHOLD"
API_RECOVERY_OK_ENV = "UPBIT_API_RECOVERY_OK"
API_SLEEP_MS_ENV = "UPBIT_API_SLEEP_MS"
HTML_REFRESH_MS_ENV = "UPBIT_HTML_REFRESH_MS"
JITTER_MS_ENV = "UPBIT_JITTER_MS"
NO_AUTOFALLBACK_ENV = "UPBIT_NO_AUTOFALLBACK"
AGGRESSIVE_MODE_ENV = "UPBIT_AGGRESSIVE_MODE"

DEFAULT_API_ERROR_THRESHOLD = 5
DEFAULT_API_RECOVERY_OK = 20
DEFAULT_API_SLEEP_MS = (100, 300)  # Base sleep range in ms
DEFAULT_HTML_REFRESH_MS = (800, 1200)  # HTML refresh range in ms
DEFAULT_JITTER_MS = (20, 40)  # Jitter range in ms
SUMMARY_INTERVAL_SECONDS = 60
API_IDLE_BASE_RANGE: Tuple[float, float] = (0.1, 0.3)
API_IDLE_JITTER_RANGE: Tuple[float, float] = (0.02, 0.04)

# Aggressive mode settings
AGGRESSIVE_SLEEP_MS = 200  # Fixed 200ms for aggressive mode
AGGRESSIVE_429_THRESHOLD_LOW = 10  # Backoff to 500ms at 10 429s in 60s
AGGRESSIVE_429_THRESHOLD_HIGH = 20  # Backoff to 1000ms at 20 429s in 60s
AGGRESSIVE_429_WINDOW_SECONDS = 60  # Rolling window for 429 detection
AGGRESSIVE_RECOVERY_CLEAR_SECONDS = 300  # 5 minutes of no 429s to resume aggressive
AGGRESSIVE_CONSECUTIVE_ERROR_THRESHOLD = 50  # Backoff at 50 consecutive errors
AGGRESSIVE_429_PERSIST_THRESHOLD = 600  # 10 minutes of 429s suggests HTML fallback


@dataclass
class ModeSelection:
    """Represents the resolved bot mode and resolution trace."""

    mode: str
    resolution_path: List[str]
    cli_source: Optional[str] = None
    env_source: Optional[str] = None


def parse_cli_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Парсит аргументы командной строки для выбора режима запуска."""

    parser = argparse.ArgumentParser(description="Upbit Notice Bot")
    parser.add_argument("--api", action="store_true", help="Forces API mode")
    parser.add_argument("--html", action="store_true", help="Forces legacy HTML mode")
    parser.add_argument("--legacy", action="store_true", help="Alias for --html")
    parser.add_argument("--no-autofallback", action="store_true", help="Disable auto-fallback between API and HTML modes")
    return parser.parse_args(argv)


def resolve_mode(args: argparse.Namespace, env_value: Optional[str] = None) -> ModeSelection:
    """Определяет режим запуска на основе CLI, окружения и дефолта."""

    resolution_steps: List[str] = []

    cli_mode: Optional[str] = None
    cli_source: Optional[str] = None

    if getattr(args, "api", False) and (getattr(args, "html", False) or getattr(args, "legacy", False)):
        raise ValueError("Conflicting CLI flags: --api cannot be combined with --html/--legacy")

    if getattr(args, "api", False):
        cli_mode = "api"
        cli_source = "--api"
        resolution_steps.append("cli=api (--api)")
    elif getattr(args, "html", False) or getattr(args, "legacy", False):
        cli_mode = "html"
        cli_source = "--html" if getattr(args, "html", False) else "--legacy"
        resolution_steps.append(f"cli=html ({cli_source})")
    else:
        resolution_steps.append("cli=not provided")

    env_mode_raw = env_value if env_value is not None else os.getenv(ENV_MODE_VAR)
    env_source: Optional[str] = None
    env_mode: Optional[str] = None

    if env_mode_raw:
        normalized = env_mode_raw.strip().lower()
        if normalized in VALID_MODES:
            env_mode = normalized
            env_source = normalized
            resolution_steps.append(f"env {ENV_MODE_VAR}={normalized}")
        else:
            resolution_steps.append(f"env {ENV_MODE_VAR}={normalized} (invalid)")
    else:
        resolution_steps.append(f"env {ENV_MODE_VAR}=not set")

    if cli_mode:
        selected_mode = cli_mode
    elif env_mode:
        selected_mode = env_mode
    else:
        selected_mode = DEFAULT_MODE

    resolution_steps.append(f"default={DEFAULT_MODE}")

    return ModeSelection(
        mode=selected_mode,
        resolution_path=resolution_steps,
        cli_source=cli_source,
        env_source=env_source,
    )


def get_api_error_threshold() -> Tuple[int, Optional[str]]:
    """Возвращает порог ошибок API и исходное значение из окружения."""

    raw_value = os.getenv(API_ERROR_THRESHOLD_ENV)
    if raw_value is None:
        return DEFAULT_API_ERROR_THRESHOLD, None

    try:
        parsed = int(raw_value)
        if parsed < 1:
            return DEFAULT_API_ERROR_THRESHOLD, raw_value
        return parsed, raw_value
    except ValueError:
        return DEFAULT_API_ERROR_THRESHOLD, raw_value


def get_api_recovery_ok() -> Tuple[int, Optional[str]]:
    """Возвращает порог восстановления API и исходное значение из окружения."""

    raw_value = os.getenv(API_RECOVERY_OK_ENV)
    if raw_value is None:
        return DEFAULT_API_RECOVERY_OK, None

    try:
        parsed = int(raw_value)
        if parsed < 1:
            return DEFAULT_API_RECOVERY_OK, raw_value
        return parsed, raw_value
    except ValueError:
        return DEFAULT_API_RECOVERY_OK, raw_value


def get_sleep_ranges() -> Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int], Optional[str], Optional[str], Optional[str]]:
    """Возвращает диапазоны сна и джиттера в миллисекундах."""
    
    # API sleep range
    api_raw = os.getenv(API_SLEEP_MS_ENV)
    if api_raw:
        try:
            parts = [int(x.strip()) for x in api_raw.split(',')]
            if len(parts) == 2 and parts[0] > 0 and parts[1] > 0:
                api_range = (min(parts), max(parts))
            else:
                api_range = DEFAULT_API_SLEEP_MS
        except (ValueError, AttributeError):
            api_range = DEFAULT_API_SLEEP_MS
    else:
        api_range = DEFAULT_API_SLEEP_MS
    
    # HTML refresh range
    html_raw = os.getenv(HTML_REFRESH_MS_ENV)
    if html_raw:
        try:
            parts = [int(x.strip()) for x in html_raw.split(',')]
            if len(parts) == 2 and parts[0] > 0 and parts[1] > 0:
                html_range = (min(parts), max(parts))
            else:
                html_range = DEFAULT_HTML_REFRESH_MS
        except (ValueError, AttributeError):
            html_range = DEFAULT_HTML_REFRESH_MS
    else:
        html_range = DEFAULT_HTML_REFRESH_MS
    
    # Jitter range
    jitter_raw = os.getenv(JITTER_MS_ENV)
    if jitter_raw:
        try:
            parts = [int(x.strip()) for x in jitter_raw.split(',')]
            if len(parts) == 2 and parts[0] >= 0 and parts[1] >= 0:
                jitter_range = (min(parts), max(parts))
            else:
                jitter_range = DEFAULT_JITTER_MS
        except (ValueError, AttributeError):
            jitter_range = DEFAULT_JITTER_MS
    else:
        jitter_range = DEFAULT_JITTER_MS
    
    return api_range, html_range, jitter_range, api_raw, html_raw, jitter_raw


def is_autofallback_disabled() -> bool:
    """Проверяет, отключен ли авто-фоллбэк."""
    
    # Check CLI flag first
    import sys
    if '--no-autofallback' in sys.argv:
        return True
    
    # Then check environment variable
    env_value = os.getenv(NO_AUTOFALLBACK_ENV)
    if env_value:
        return env_value.strip().lower() in ('1', 'true', 'yes', 'on')
    
    return False


def is_aggressive_mode_enabled() -> bool:
    """Проверяет, включен ли агрессивный режим опроса."""
    
    # Check environment variable
    env_value = os.getenv(AGGRESSIVE_MODE_ENV)
    if env_value:
        return env_value.strip().lower() in ('1', 'true', 'yes', 'on')
    
    return False
