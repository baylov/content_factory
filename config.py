"""Configuration helpers for Upbit Notice Bot."""

import argparse
import os
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

DEFAULT_MODE = "api"
VALID_MODES = {"api", "html"}
ENV_MODE_VAR = "UPBIT_MODE"
API_ERROR_THRESHOLD_ENV = "UPBIT_API_ERROR_THRESHOLD"
DEFAULT_API_ERROR_THRESHOLD = 5
SUMMARY_INTERVAL_SECONDS = 60
API_IDLE_BASE_RANGE: Tuple[float, float] = (0.1, 0.3)
API_IDLE_JITTER_RANGE: Tuple[float, float] = (0.02, 0.04)


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
