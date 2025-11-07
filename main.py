import os
import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import re
import random
import math
import json
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Tuple, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth

from telegram_notifications import TelegramRetryTelemetry, send_to_telegram

from config import (
    AGGRESSIVE_MODE_ENV,
    AGGRESSIVE_429_THRESHOLD_LOW,
    AGGRESSIVE_429_THRESHOLD_HIGH,
    AGGRESSIVE_429_WINDOW_SECONDS,
    AGGRESSIVE_RECOVERY_CLEAR_SECONDS,
    AGGRESSIVE_CONSECUTIVE_ERROR_THRESHOLD,
    AGGRESSIVE_429_PERSIST_THRESHOLD,
    AGGRESSIVE_SLEEP_MS,
    API_ERROR_THRESHOLD_ENV,
    API_IDLE_BASE_RANGE,
    API_IDLE_JITTER_RANGE,
    API_RECOVERY_OK_ENV,
    API_SLEEP_MS_ENV,
    DEFAULT_API_ERROR_THRESHOLD,
    DEFAULT_API_RECOVERY_OK,
    DEFAULT_API_SLEEP_MS,
    DEFAULT_HTML_REFRESH_MS,
    DEFAULT_JITTER_MS,
    DEFAULT_MODE,
    ENV_MODE_VAR,
    HTML_REFRESH_MS_ENV,
    JITTER_MS_ENV,
    NO_AUTOFALLBACK_ENV,
    SUMMARY_INTERVAL_SECONDS,
    VALID_MODES,
    get_api_error_threshold,
    get_api_recovery_ok,
    get_sleep_ranges,
    is_aggressive_mode_enabled,
    is_autofallback_disabled,
    parse_cli_args,
    resolve_mode,
)

load_dotenv()

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Global tracking for fallback invocations and strategy statistics
_last_parse_stats = {
    'fallback_invoked': False,
    'filter_stats': {},
    'total_raw_links': 0,
    'total_filtered_links': 0,
    'strategy_stats': {
        'strategy_used': None,
        'exact_id_attempts': 0,
        'exact_id_retry_time': 0.0,
        'exact_id_success': False,
        'fallback_reason': None,
        'dom_state_at_fallback': None
    }
}


class MetricsLogger:
    """
    Логгер для записи детальных метрик производительности обработки новостей
    """
    def __init__(self, log_file="logs/performance_metrics.log", max_bytes=10*1024*1024, backup_count=5):
        self.log_file = log_file
        self.logger = logging.getLogger("MetricsLogger")
        self.logger.setLevel(logging.INFO)
        
        # Создаем RotatingFileHandler для автоматической ротации логов
        handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,  # 10MB по умолчанию
            backupCount=backup_count,  # Сохраняем 5 старых файлов
            encoding='utf-8'
        )
        
        # Формат без префикса уровня - чистый вывод
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        
        # Удаляем существующие handlers, если есть
        self.logger.handlers.clear()
        self.logger.addHandler(handler)
        self.logger.propagate = False  # Не передавать логи в root logger
    
    def log_article_metrics(self, notice_id, title, source, detected_at, processing_started, 
                           processing_completed, telegram_sent):
        """
        Логирует полные метрики обработки одной новости
        
        Args:
            notice_id: ID новости
            title: Заголовок новости
            source: Источник (например, "Upbit Notice")
            detected_at: datetime - момент обнаружения
            processing_started: datetime - начало обработки
            processing_completed: datetime - завершение обработки
            telegram_sent: datetime - отправка в Telegram
        """
        # Вычисляем метрики
        detection_lag = (processing_started - detected_at).total_seconds()
        processing_time = (processing_completed - processing_started).total_seconds()
        total_latency = (telegram_sent - detected_at).total_seconds()
        
        # Форматируем временные метки с миллисекундами
        detected_str = detected_at.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        started_str = processing_started.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        completed_str = processing_completed.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        sent_str = telegram_sent.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        # Формируем сообщение по шаблону
        log_message = f"""
[{detected_at.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] ━━━ NEW ARTICLE ━━━
Source: {source}
ID: {notice_id} | Title: "{title}"
Detected at: {detected_str}
Processing started: {started_str} (lag: {detection_lag:.3f}s)
Processing completed: {completed_str} (duration: {processing_time:.3f}s)
Sent to Telegram: {sent_str}
⚡️ TOTAL LATENCY: {total_latency:.3f}s
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        self.logger.info(log_message.strip())
    
    def log_error(self, notice_id, title, error_message):
        """
        Логирует ошибку обработки новости
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        log_message = f"""
[{timestamp}] ━━━ ERROR ━━━
ID: {notice_id} | Title: "{title}"
Error: {error_message}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        self.logger.error(log_message.strip())


# Создаем глобальный экземпляр MetricsLogger
metrics_logger = MetricsLogger()
telegram_retry_telemetry = TelegramRetryTelemetry()


class FailureDetector:
    """
    Tracks consecutive API failures and manages auto-fallback logic.
    
    Features:
    - Rolling window of failure timestamps (2-minute window)
    - Configurable failure and recovery thresholds
    - Detailed error tracking and summaries
    """
    
    def __init__(self, failure_threshold=5, recovery_threshold=20, window_seconds=120):
        self.failure_threshold = failure_threshold
        self.recovery_threshold = recovery_threshold
        self.window_seconds = window_seconds
        
        self.failure_timestamps = []  # List of (timestamp, error_message) tuples
        self.consecutive_successes = 0
        self.last_failure_summary = []
        self.total_failures = 0
        self.total_successes = 0
        
    def record_api_result(self, success: bool, error_message: str = None, timestamp: float = None):
        """Record an API call result and update state."""
        if timestamp is None:
            timestamp = time.time()
            
        # Clean old failures outside the window
        self._cleanup_old_failures(timestamp)
        
        if success:
            self.consecutive_successes += 1
            self.total_successes += 1
            return False, None  # No fallback triggered
        else:
            self.failure_timestamps.append((timestamp, error_message or "unknown"))
            self.consecutive_successes = 0
            self.total_failures += 1
            
            # Check if we should trigger fallback
            recent_failures = len(self.failure_timestamps)
            if recent_failures >= self.failure_threshold:
                self.last_failure_summary = [
                    f"  • {msg} at {datetime.fromtimestamp(ts).strftime('%H:%M:%S')}"
                    for ts, msg in self.failure_timestamps[-5:]  # Show last 5 errors
                ]
                return True, recent_failures
                
        return False, None
    
    def check_recovery_ready(self) -> bool:
        """Check if API is healthy enough to switch back."""
        return self.consecutive_successes >= self.recovery_threshold
    
    def _cleanup_old_failures(self, current_time: float):
        """Remove failures outside the rolling window."""
        cutoff_time = current_time - self.window_seconds
        self.failure_timestamps = [
            (ts, msg) for ts, msg in self.failure_timestamps 
            if ts >= cutoff_time
        ]
    
    def get_stats(self) -> dict:
        """Get current detector statistics."""
        return {
            "recent_failures": len(self.failure_timestamps),
            "consecutive_successes": self.consecutive_successes,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "failure_rate": self.total_failures / max(1, self.total_failures + self.total_successes),
            "in_failure_state": len(self.failure_timestamps) >= self.failure_threshold,
            "ready_for_recovery": self.check_recovery_ready()
        }
    
    def reset(self):
        """Reset detector state (used when switching modes)."""
        self.failure_timestamps.clear()
        self.consecutive_successes = 0
        self.last_failure_summary.clear()


class RateLimitDetector:
    """
    Advanced rate-limit detection and auto-backoff for aggressive polling mode.
    
    Features:
    - 429 error tracking in rolling windows
    - Automatic backoff based on 429 frequency
    - Consecutive error monitoring
    - Mode tracking (aggressive/normal/throttled)
    - Recovery detection and auto-resume
    """
    
    def __init__(self):
        # 429 tracking
        self._429_timestamps = []  # List of timestamps when 429 occurred
        self._last_429_window_check = time.time()
        
        # Consecutive error tracking
        self._consecutive_errors = 0
        self._last_success_time = time.time()
        
        # Mode tracking
        self._current_mode = "normal"  # aggressive, normal, throttled
        self._mode_changes = []  # List of (timestamp, old_mode, new_mode, reason)
        
        # Metrics
        self._total_api_calls = 0
        self._successful_calls = 0
        self._total_429_errors = 0
        self._total_timeouts = 0
        
    def record_api_call(self, success: bool, status_code: int = None, 
                       error_message: str = None, timestamp: float = None):
        """Record an API call result and update rate-limit state."""
        if timestamp is None:
            timestamp = time.time()
            
        self._total_api_calls += 1
        
        # Check for 429 errors
        is_429 = status_code == 429 or (error_message and "429" in error_message.lower())
        is_timeout = error_message and "timeout" in error_message.lower()
        
        if is_429:
            self._429_timestamps.append(timestamp)
            self._total_429_errors += 1
            self._consecutive_errors += 1
            logging.warning(f"🚫 429 Rate Limit detected (consecutive: {self._consecutive_errors})")
            
        elif is_timeout:
            self._total_timeouts += 1
            self._consecutive_errors += 1
            logging.warning(f"⏱️ API Timeout detected (consecutive: {self._consecutive_errors})")
            
        elif success:
            self._successful_calls += 1
            self._consecutive_errors = 0
            self._last_success_time = timestamp
        else:
            self._consecutive_errors += 1
            logging.warning(f"❌ API Error (consecutive: {self._consecutive_errors}): {error_message}")
        
        # Clean old 429s outside the window
        self._cleanup_old_429s(timestamp)
        
        # Determine if we need to change mode
        return self._evaluate_mode_change(timestamp)
    
    def _cleanup_old_429s(self, current_time: float):
        """Remove 429 timestamps outside the rolling window."""
        cutoff_time = current_time - AGGRESSIVE_429_WINDOW_SECONDS
        self._429_timestamps = [
            ts for ts in self._429_timestamps if ts >= cutoff_time
        ]
    
    def _evaluate_mode_change(self, timestamp: float) -> tuple:
        """Evaluate if we need to change polling mode based on current state."""
        recent_429s = len(self._429_timestamps)
        old_mode = self._current_mode
        reason = None
        
        # Check for aggressive mode conditions
        if self._current_mode == "aggressive":
            if recent_429s >= AGGRESSIVE_429_THRESHOLD_HIGH:
                self._current_mode = "throttled"
                reason = f"High 429 rate: {recent_429s} in {AGGRESSIVE_429_WINDOW_SECONDS}s (threshold: {AGGRESSIVE_429_THRESHOLD_HIGH})"
            elif recent_429s >= AGGRESSIVE_429_THRESHOLD_LOW:
                self._current_mode = "normal"
                reason = f"Moderate 429 rate: {recent_429s} in {AGGRESSIVE_429_WINDOW_SECONDS}s (threshold: {AGGRESSIVE_429_THRESHOLD_LOW})"
            elif self._consecutive_errors >= AGGRESSIVE_CONSECUTIVE_ERROR_THRESHOLD:
                self._current_mode = "normal"
                reason = f"High consecutive errors: {self._consecutive_errors} (threshold: {AGGRESSIVE_CONSECUTIVE_ERROR_THRESHOLD})"
        
        # Check for normal mode conditions
        elif self._current_mode == "normal":
            if recent_429s >= AGGRESSIVE_429_THRESHOLD_HIGH:
                self._current_mode = "throttled"
                reason = f"High 429 rate: {recent_429s} in {AGGRESSIVE_429_WINDOW_SECONDS}s (threshold: {AGGRESSIVE_429_THRESHOLD_HIGH})"
            elif self._consecutive_errors >= AGGRESSIVE_CONSECUTIVE_ERROR_THRESHOLD:
                self._current_mode = "throttled"
                reason = f"High consecutive errors: {self._consecutive_errors} (threshold: {AGGRESSIVE_CONSECUTIVE_ERROR_THRESHOLD})"
            # Check if we can resume aggressive mode
            elif (recent_429s == 0 and 
                  timestamp - self._last_success_time > AGGRESSIVE_RECOVERY_CLEAR_SECONDS and
                  self._consecutive_errors == 0):
                self._current_mode = "aggressive"
                reason = f"Recovery: No 429s for {AGGRESSIVE_RECOVERY_CLEAR_SECONDS}s, consecutive errors cleared"
        
        # Check for throttled mode conditions
        elif self._current_mode == "throttled":
            # Check if we can resume aggressive mode
            if (recent_429s == 0 and 
                timestamp - self._last_success_time > AGGRESSIVE_RECOVERY_CLEAR_SECONDS and
                self._consecutive_errors == 0):
                self._current_mode = "aggressive"
                reason = f"Recovery: No 429s for {AGGRESSIVE_RECOVERY_CLEAR_SECONDS}s, consecutive errors cleared"
            # Maybe we can go to normal mode instead
            elif (recent_429s < AGGRESSIVE_429_THRESHOLD_LOW and 
                  self._consecutive_errors < AGGRESSIVE_CONSECUTIVE_ERROR_THRESHOLD // 2):
                self._current_mode = "normal"
                reason = f"Partial recovery: 429s reduced to {recent_429s}, errors to {self._consecutive_errors}"
        
        # Record mode change if it happened
        if old_mode != self._current_mode:
            self._mode_changes.append((timestamp, old_mode, self._current_mode, reason))
            logging.warning(f"🔄 RATE-LIMIT MODE CHANGE: {old_mode.upper()} → {self._current_mode.upper()}")
            logging.warning(f"   Reason: {reason}")
            return True, old_mode, self._current_mode, reason
        
        return False, old_mode, self._current_mode, None
    
    def get_sleep_time_ms(self, base_sleep_range: tuple) -> int:
        """Get the appropriate sleep time based on current mode."""
        if self._current_mode == "aggressive":
            return AGGRESSIVE_SLEEP_MS
        elif self._current_mode == "normal":
            return random.randint(*base_sleep_range)
        elif self._current_mode == "throttled":
            # Use higher end of range or add extra delay
            return max(base_sleep_range[1], base_sleep_range[1] + random.randint(200, 500))
        else:
            return random.randint(*base_sleep_range)
    
    def should_suggest_html_fallback(self) -> bool:
        """Check if we should suggest switching to HTML mode."""
        # Check for persistent 429s
        if len(self._429_timestamps) > 0:
            latest_429 = max(self._429_timestamps)
            if time.time() - latest_429 < AGGRESSIVE_429_PERSIST_THRESHOLD:
                recent_429s = len(self._429_timestamps)
                if recent_429s >= AGGRESSIVE_429_THRESHOLD_HIGH:
                    return True
        
        # Check for extremely high consecutive errors
        if self._consecutive_errors >= AGGRESSIVE_CONSECUTIVE_ERROR_THRESHOLD * 2:
            return True
        
        return False
    
    def get_stats(self) -> dict:
        """Get comprehensive rate-limit statistics."""
        current_time = time.time()
        recent_429s = len(self._429_timestamps)
        
        success_rate = (self._successful_calls / max(1, self._total_api_calls)) * 100
        
        return {
            "current_mode": self._current_mode,
            "total_api_calls": self._total_api_calls,
            "successful_calls": self._successful_calls,
            "success_rate": success_rate,
            "total_429_errors": self._total_429_errors,
            "recent_429s_60s": recent_429s,
            "total_timeouts": self._total_timeouts,
            "consecutive_errors": self._consecutive_errors,
            "time_since_last_success": current_time - self._last_success_time,
            "mode_changes_count": len(self._mode_changes),
            "suggest_html_fallback": self.should_suggest_html_fallback(),
            "429_rate_per_minute": (recent_429s * 60) / AGGRESSIVE_429_WINDOW_SECONDS
        }
    
    def reset(self):
        """Reset all tracking state."""
        self._429_timestamps.clear()
        self._last_429_window_check = time.time()
        self._consecutive_errors = 0
        self._last_success_time = time.time()
        self._current_mode = "normal"
        self._mode_changes.clear()
        self._total_api_calls = 0
        self._successful_calls = 0
        self._total_429_errors = 0
        self._total_timeouts = 0


class ModeManager:
    """
    Manages mode switching between API and HTML with proper resource handling.
    """
    
    def __init__(self, initial_mode: str, autofallback_enabled: bool = True):
        self.current_mode = initial_mode
        self.autofallback_enabled = autofallback_enabled
        self.api_session = None
        self.html_driver = None
        self.last_transition_time = time.time()
        self.transition_count = 0
        self.mode_history = []  # List of (timestamp, mode, reason) tuples
        
    def initialize_api_session(self):
        """Initialize API session if not already active."""
        if self.api_session is None:
            self.api_session = create_api_session()
            logging.info("✅ API session initialized")
            
    def initialize_html_driver(self):
        """Initialize HTML driver if not already active."""
        if self.html_driver is None:
            self.html_driver = init_driver()
            if self.html_driver:
                logging.info("✅ HTML driver initialized")
            else:
                logging.error("❌ Failed to initialize HTML driver")
                return False
        return True
    
    def switch_to_html(self, reason: str, failure_count: int):
        """Switch from API to HTML mode."""
        if self.current_mode == "html":
            return False
            
        if not self.autofallback_enabled:
            logging.info("🔒 Auto-fallback disabled - staying in API mode")
            return False
            
        # Cleanup API resources
        if self.api_session:
            try:
                self.api_session.close()
                self.api_session = None
                logging.info("🧹 API session closed")
            except Exception as e:
                logging.warning(f"⚠️ Error closing API session: {e}")
        
        # Initialize HTML resources
        if not self.initialize_html_driver():
            logging.error("❌ Cannot switch to HTML mode - driver initialization failed")
            return False
            
        old_mode = self.current_mode
        self.current_mode = "html"
        self.last_transition_time = time.time()
        self.transition_count += 1
        
        # Record transition
        self.mode_history.append((time.time(), "html", reason))
        
        logging.warning(f"🔄 MODE SWITCH: {old_mode.upper()} → HTML")
        logging.warning(f"   Reason: {reason}")
        logging.warning(f"   Failure count: {failure_count}")
        logging.warning(f"   Transition #{self.transition_count}")
        
        return True
    
    def switch_to_api(self, reason: str):
        """Switch from HTML to API mode."""
        if self.current_mode == "api":
            return False
            
        if not self.autofallback_enabled:
            logging.info("🔒 Auto-fallback disabled - staying in HTML mode")
            return False
            
        # Cleanup HTML resources
        if self.html_driver:
            try:
                self.html_driver.quit()
                self.html_driver = None
                logging.info("🧹 HTML driver closed")
            except Exception as e:
                logging.warning(f"⚠️ Error closing HTML driver: {e}")
        
        # Initialize API resources
        self.initialize_api_session()
        
        old_mode = self.current_mode
        self.current_mode = "api"
        self.last_transition_time = time.time()
        self.transition_count += 1
        
        # Record transition
        self.mode_history.append((time.time(), "api", reason))
        
        logging.info(f"🔄 MODE SWITCH: {old_mode.upper()} → API")
        logging.info(f"   Reason: {reason}")
        logging.info(f"   Transition #{self.transition_count}")
        
        return True
    
    def get_mode_stats(self) -> dict:
        """Get current mode statistics."""
        return {
            "current_mode": self.current_mode,
            "autofallback_enabled": self.autofallback_enabled,
            "transition_count": self.transition_count,
            "last_transition_seconds_ago": time.time() - self.last_transition_time,
            "api_session_active": self.api_session is not None,
            "html_driver_active": self.html_driver is not None,
            "recent_transitions": len([
                ts for ts, _, _ in self.mode_history 
                if time.time() - ts < 300  # Last 5 minutes
            ])
        }
    
    def cleanup(self):
        """Clean up all resources."""
        if self.api_session:
            try:
                self.api_session.close()
                logging.info("🧹 API session closed during cleanup")
            except Exception as e:
                logging.warning(f"⚠️ Error closing API session during cleanup: {e}")
        
        if self.html_driver:
            try:
                self.html_driver.quit()
                logging.info("🧹 HTML driver closed during cleanup")
            except Exception as e:
                logging.warning(f"⚠️ Error closing HTML driver during cleanup: {e}")


class HybridTelemetry:
    """Enhanced telemetry for hybrid API/HTML mode with aggressive polling support."""
    
    def __init__(self, summary_interval=60):
        self.summary_interval = summary_interval
        self.last_summary_time = time.monotonic()
        self.last_10s_log_time = time.monotonic()
        self.reset()
    
    def reset(self):
        self.cycle_durations = []
        self.api_latencies = []
        self.html_latencies = []
        self.error_count = 0
        self.cycle_count = 0
        self.mode_durations = {"api": [], "html": []}
        self.last_known_id = None
        self.max_id = None
        
        # Aggressive mode specific metrics
        self.aggressive_cycles = 0
        self.normal_cycles = 0
        self.throttled_cycles = 0
        self.cycle_sleep_times = []  # Track actual sleep times
        self.detection_lags = []  # Track detection latencies when new notices found
    
    def record_cycle(self, cycle_duration, mode="unknown", api_latency=None, html_latency=None, 
                   error_occurred=False, last_known_id=None, max_id=None, sleep_time_ms=None,
                   rate_limit_mode=None, detection_lag=None):
        self.cycle_durations.append(cycle_duration)
        self.mode_durations[mode].append(cycle_duration)
        
        if api_latency is not None:
            self.api_latencies.append(api_latency)
        if html_latency is not None:
            self.html_latencies.append(html_latency)
            
        if error_occurred:
            self.error_count += 1
            
        if sleep_time_ms is not None:
            self.cycle_sleep_times.append(sleep_time_ms)
            
        if detection_lag is not None:
            self.detection_lags.append(detection_lag)
            
        # Track rate-limit mode cycles
        if rate_limit_mode == "aggressive":
            self.aggressive_cycles += 1
        elif rate_limit_mode == "normal":
            self.normal_cycles += 1
        elif rate_limit_mode == "throttled":
            self.throttled_cycles += 1
            
        self.cycle_count += 1
        self.last_known_id = last_known_id
        self.max_id = max_id
    
    def maybe_log_10s_summary(self, rate_limit_detector):
        """Log detailed 10-second summary for aggressive mode monitoring."""
        now = time.monotonic()
        if now - self.last_10s_log_time < 10 or self.cycle_count == 0:
            return
        
        stats = rate_limit_detector.get_stats()
        
        logging.info(
            "📊 10s rate-limit window: mode=%s, api_calls=%d, success_rate=%.1f%%, "
            "429s_60s=%d, consecutive_errors=%d, 429_rate=%.1f/min",
            stats["current_mode"].upper(),
            stats["total_api_calls"],
            stats["success_rate"],
            stats["recent_429s_60s"],
            stats["consecutive_errors"],
            stats["429_rate_per_minute"]
        )
        
        # Sleep time statistics
        if self.cycle_sleep_times:
            avg_sleep = sum(self.cycle_sleep_times[-10:]) / min(len(self.cycle_sleep_times), 10)  # Last 10 cycles
            logging.info(f"   💤 Recent avg sleep: {avg_sleep:.0f}ms")
        
        # Detection latency statistics
        if self.detection_lags:
            recent_lags = self.detection_lags[-5:]  # Last 5 detections
            avg_lag = sum(recent_lags) / len(recent_lags)
            logging.info(f"   ⚡ Recent detection lag: {avg_lag:.0f}ms")
        
        self.last_10s_log_time = now
    
    def maybe_log_summary(self, mode_manager: ModeManager, failure_detector: FailureDetector, 
                        rate_limit_detector: RateLimitDetector = None):
        now = time.monotonic()
        if now - self.last_summary_time < self.summary_interval or self.cycle_count == 0:
            return
        
        # Calculate statistics
        avg_cycle = sum(self.cycle_durations) / len(self.cycle_durations)
        p95_cycle = self._percentile(self.cycle_durations, 95)
        error_rate = self.error_count / self.cycle_count if self.cycle_count else 0
        
        # Mode-specific stats
        api_cycles = len(self.mode_durations.get("api", []))
        html_cycles = len(self.mode_durations.get("html", []))
        
        api_avg = sum(self.mode_durations.get("api", [])) / api_cycles if api_cycles > 0 else None
        html_avg = sum(self.mode_durations.get("html", [])) / html_cycles if html_cycles > 0 else None
        
        api_latency_avg = (
            sum(self.api_latencies) / len(self.api_latencies)
            if self.api_latencies else None
        )
        
        # Get mode and failure detector stats
        mode_stats = mode_manager.get_mode_stats()
        failure_stats = failure_detector.get_stats()
        
        # Format strings
        api_avg_str = f"{api_avg:.3f}s" if api_avg else "n/a"
        html_avg_str = f"{html_avg:.3f}s" if html_avg else "n/a"
        api_latency_str = f"{api_latency_avg:.3f}s" if api_latency_avg else "n/a"
        p95_str = f"{p95_cycle:.3f}s" if p95_cycle else "n/a"
        
        # Build the main summary log
        summary_parts = [
            f"📈 {self.summary_interval}s summary: mode={mode_stats['current_mode'].upper()}",
            f"cycles={self.cycle_count}",
            f"avg_cycle={avg_cycle:.3f}s",
            f"p95_cycle={p95_str}",
            f"error_rate={error_rate * 100:.2f}%",
            f"api_cycles={api_cycles}({api_avg_str})",
            f"html_cycles={html_cycles}({html_avg_str})",
            f"api_latency={api_latency_str}",
            f"failures={failure_stats['recent_failures']}",
            f"transitions={mode_stats['transition_count']}"
        ]
        
        # Add rate-limit stats if available
        if rate_limit_detector:
            rl_stats = rate_limit_detector.get_stats()
            summary_parts.extend([
                f"rl_mode={rl_stats['current_mode'].upper()}",
                f"429s_60s={rl_stats['recent_429s_60s']}",
                f"success_rate={rl_stats['success_rate']:.1f}%"
            ])
            
            # Add aggressive mode breakdown
            if self.aggressive_cycles > 0 or self.normal_cycles > 0 or self.throttled_cycles > 0:
                summary_parts.append(
                    f"modes=aggr:{self.aggressive_cycles}|norm:{self.normal_cycles}|throt:{self.throttled_cycles}"
                )
        
        logging.info(" ".join(summary_parts))
        
        # Additional details
        if self.last_known_id is not None and self.max_id is not None:
            gap = max(0, self.max_id - self.last_known_id) if self.last_known_id and self.max_id else 0
            logging.info(
                "   📊 ID tracking: last_known=%s, max=%s, gap=%d",
                self.last_known_id, self.max_id, gap
            )
        
        # Sleep time statistics
        if self.cycle_sleep_times:
            avg_sleep = sum(self.cycle_sleep_times) / len(self.cycle_sleep_times)
            min_sleep = min(self.cycle_sleep_times)
            max_sleep = max(self.cycle_sleep_times)
            logging.info(
                f"   💤 Sleep times: avg={avg_sleep:.0f}ms, min={min_sleep:.0f}ms, max={max_sleep:.0f}ms"
            )
        
        # Detection latency statistics
        if self.detection_lags:
            avg_lag = sum(self.detection_lags) / len(self.detection_lags)
            min_lag = min(self.detection_lags)
            max_lag = max(self.detection_lags)
            logging.info(
                f"   ⚡ Detection latency: avg={avg_lag:.0f}ms, min={min_lag:.0f}ms, max={max_lag:.0f}ms"
            )
        
        # HTML fallback suggestion
        if rate_limit_detector and rate_limit_detector.should_suggest_html_fallback():
            logging.warning("   ⚠️ SUGGESTION: Consider switching to HTML mode due to persistent rate limiting")
        
        self.reset()
        self.last_summary_time = now
    
    @staticmethod
    def _percentile(values, percentile):
        if not values:
            return None
        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, math.ceil(percentile / 100 * len(ordered)) - 1))
        return ordered[index]

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
UPBIT_NOTICE_URL = "https://upbit.com/service_center/notice"
LAST_NOTICE_FILE = "last_notice.txt"


def init_driver(enable_cdp=False):
    """
    Инициализирует Selenium WebDriver с агрессивными настройками для максимальной скорости.
    Цель: загрузка страницы за 0.3-0.5 секунды вместо 2+ секунд.
    
    Args:
        enable_cdp: Если True, включает Chrome DevTools Protocol для перехвата сетевых запросов
    """
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')  # Новый headless режим
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-software-rasterizer')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_argument('--disable-dev-tools')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-plugins')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-popup-blocking')
        
        # Агрессивная оптимизация скорости - блокировка всех ненужных ресурсов
        chrome_options.add_argument('--blink-settings=imagesEnabled=false')
        chrome_options.add_argument('--disable-remote-fonts')
        chrome_options.add_argument('--disable-background-networking')
        chrome_options.add_argument('--disable-default-apps')
        chrome_options.add_argument('--disable-sync')
        chrome_options.add_argument('--disable-translate')
        chrome_options.add_argument('--hide-scrollbars')
        chrome_options.add_argument('--mute-audio')
        chrome_options.add_argument('--disable-breakpad')
        chrome_options.add_argument('--disable-crash-reporter')
        
        # CDP logging - включаем только если необходимо (Selenium 4.x синтаксис)
        if enable_cdp:
            chrome_options.add_argument('--enable-logging')
            chrome_options.add_argument('--v=1')
            # Selenium 4.x: используем set_capability вместо desired_capabilities
            chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        else:
            chrome_options.add_argument('--disable-logging')
            chrome_options.add_argument('--log-level=3')
        
        # Блокировка всех медиа и ненужных ресурсов через prefs
        prefs = {
            'profile.managed_default_content_settings.images': 2,
            'profile.managed_default_content_settings.stylesheets': 2,  # Блокировать CSS
            'profile.default_content_setting_values': {
                'images': 2,          # Блокировать изображения
                'plugins': 2,         # Блокировать плагины
                'popups': 2,          # Блокировать всплывающие окна
                'media_stream': 2,    # Блокировать медиа-стримы
                'stylesheets': 2,     # Блокировать стили (может повлиять на структуру!)
            }
        }
        chrome_options.add_experimental_option('prefs', prefs)
        
        # КРИТИЧЕСКИ ВАЖНО: используем 'eager' вместо 'normal'
        # 'eager' не ждет загрузки всех ресурсов, только DOM
        chrome_options.page_load_strategy = 'eager'
        
        # Отключить обнаружение автоматизации
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        service = Service(ChromeDriverManager().install())
        
        # Selenium 4.x: только service и options (desired_capabilities убран!)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Применяем STEALTH для обхода детекции автоматизации
        stealth(driver,
            languages=["ko-KR", "ko", "en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )

        # Увеличиваем timeout до 10 секунд для обхода блокировки
        driver.set_page_load_timeout(10)
        
        # Убираем implicit wait - будем использовать explicit wait только для списка новостей
        driver.implicitly_wait(0)
        
        # Включаем CDP Network tracking если требуется
        if enable_cdp:
            try:
                driver.execute_cdp_cmd('Network.enable', {})
                logging.info("✅ Selenium WebDriver с STEALTH + CDP режимом инициализирован")
                logging.info("  ✓ Chrome DevTools Protocol enabled для перехвата API")
            except Exception as cdp_error:
                logging.warning(f"⚠️ CDP не удалось активировать: {cdp_error}")
                logging.info("  → Fallback на HTML парсинг")
        else:
            logging.info("✅ Selenium WebDriver с STEALTH режимом инициализирован")
        
        logging.info("  ✓ Скрыты признаки автоматизации")
        logging.info("  ✓ Реалистичный User-Agent")
        logging.info("  ✓ WebGL/Canvas fingerprint защита")
        return driver

    except Exception as e:
        logging.error(f"❌ Ошибка инициализации браузера: {e}")
        return None


def debug_save_html_and_find_selectors(driver):
    """
    Сохраняет HTML страницы и тестирует разные селекторы для диагностики проблем.
    Включает расширенный сбор метаданных о ссылках (классы, badges, data-атрибуты).
    """
    try:
        logging.info("🔍 ДИАГНОСТИКА: Начинаем анализ страницы...")
        
        # Сохраняем HTML
        html = driver.page_source
        debug_file = 'upbit_debug.html'
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(html)
        logging.info(f"💾 HTML сохранен в {debug_file}")
        
        # Тестируем разные селекторы через JavaScript с метаданными
        selectors_to_test = [
            'a[href*="/service_center/notice?id="]',
            'a[href*="/service_center/notice"]',
            'tr a[href*="notice"]',
            '.notice-list a',
            '[class*="notice"] a',
            'table a[href*="id="]',
            'a[href*="id="]',
            'tr a',
        ]
        
        logging.info("🔍 Тестируем селекторы с метаданными:")
        best_selector = None
        best_count = 0
        
        for selector in selectors_to_test:
            try:
                result = driver.execute_script(f"""
                    const links = document.querySelectorAll('{selector}');
                    const samples = [];
                    for (let i = 0; i < Math.min(3, links.length); i++) {{
                        const link = links[i];
                        const parentRow = link.closest('tr');
                        const badge = link.querySelector('.badge, .tag, [class*="badge"], [class*="pin"]');
                        
                        samples.push({{
                            href: link.getAttribute('href') || '',
                            text: link.textContent.trim().substring(0, 50),
                            parentClasses: parentRow ? parentRow.className : '',
                            badgeText: badge ? badge.textContent.trim() : '',
                            dataPinned: link.dataset.pinned || (parentRow ? parentRow.dataset.pinned : ''),
                            dataFixed: link.dataset.fixed || (parentRow ? parentRow.dataset.fixed : '')
                        }});
                    }}
                    return {{
                        count: links.length,
                        samples: samples
                    }};
                """)
                
                count = result['count']
                samples = result['samples']
                
                logging.info(f"  🔍 Селектор '{selector}': найдено {count} элементов")
                
                if count > best_count:
                    best_count = count
                    best_selector = selector
                
                if count > 0 and samples:
                    for s in samples[:3]:
                        text = s['text'][:50]
                        href = s['href'][:60] if s['href'] else 'NO HREF'
                        logging.info(f"     📄 {text} -> {href}")
                        
                        # Показываем метаданные если есть
                        if s.get('parentClasses'):
                            logging.info(f"        🏷️ Parent classes: {s['parentClasses'][:50]}")
                        if s.get('badgeText'):
                            logging.info(f"        🔖 Badge: {s['badgeText']}")
                        if s.get('dataPinned'):
                            logging.info(f"        📌 data-pinned: {s['dataPinned']}")
                        if s.get('dataFixed'):
                            logging.info(f"        📍 data-fixed: {s['dataFixed']}")
            except Exception as e:
                logging.error(f"  ❌ Ошибка тестирования селектора '{selector}': {e}")
        
        if best_selector:
            logging.info(f"✅ ЛУЧШИЙ СЕЛЕКТОР: '{best_selector}' ({best_count} элементов)")
            logging.info(f"💡 РЕКОМЕНДАЦИЯ: Используйте селектор '{best_selector}'")
        else:
            logging.error("❌ НЕ НАЙДЕНО подходящих селекторов!")
            logging.error("💡 Проверьте upbit_debug.html вручную")
        
        return best_selector
        
    except Exception as e:
        logging.error(f"❌ Ошибка диагностики: {e}")
        return None


def check_readiness_probe(driver):
    """
    Lightweight readiness probe that collects document state, visibility, 
    and link counts in a single execute_script call.
    
    Returns dict with:
        - ready: bool - whether content is ready
        - readyState: str - document.readyState
        - count: int - number of notice links found
        - strategy: str - which selector strategy found links
        - containerVisible: bool - whether notice container is visible
    """
    return driver.execute_script("""
        const result = {
            ready: false,
            readyState: document.readyState,
            count: 0,
            strategy: null,
            containerVisible: false
        };
        
        // Check if document is at least interactive
        if (document.readyState === 'loading') {
            return result;
        }
        
        // Check container visibility (common notice containers)
        const containers = document.querySelectorAll('table, .notice-list, [class*="notice"], tbody');
        result.containerVisible = containers.length > 0;
        
        // Strategy 1: Exact selector with ?id=
        let links = document.querySelectorAll('a[href*="/service_center/notice?id="]');
        if (links.length > 0) {
            result.count = links.length;
            result.strategy = 'exact_id';
            result.ready = true;
            return result;
        }
        
        // Strategy 2: Any links with /service_center/notice
        links = document.querySelectorAll('a[href*="/service_center/notice"]');
        if (links.length > 0) {
            result.count = links.length;
            result.strategy = 'all_notice';
            result.ready = true;
            return result;
        }
        
        // Strategy 3: Links in table rows
        links = document.querySelectorAll('tr a[href*="notice"]');
        if (links.length > 0) {
            result.count = links.length;
            result.strategy = 'tr_notice';
            result.ready = true;
            return result;
        }
        
        // Strategy 4: Any links with id=
        links = document.querySelectorAll('a[href*="id="]');
        if (links.length > 0) {
            result.count = links.length;
            result.strategy = 'any_id';
            result.ready = true;
            return result;
        }
        
        return result;
    """)


def check_dom_state_for_fallback(driver):
    """
    Checks broader selectors to determine if content exists but exact_id selector failed.
    
    Returns dict with:
        - broader_content_exists: bool - if any broader selector found links
        - exact_id_count: int - count for exact_id selector
        - all_notice_count: int - count for all_notice selector
        - tr_notice_count: int - count for tr_notice selector
        - any_id_count: int - count for any_id selector
        - readyState: str - document.readyState
        - containerVisible: bool - whether notice container is visible
    """
    return driver.execute_script("""
        const result = {
            broader_content_exists: false,
            exact_id_count: 0,
            all_notice_count: 0,
            tr_notice_count: 0,
            any_id_count: 0,
            readyState: document.readyState,
            containerVisible: false
        };
        
        // Check container visibility
        const containers = document.querySelectorAll('table, .notice-list, [class*="notice"], tbody');
        result.containerVisible = containers.length > 0;
        
        // Count for each strategy
        result.exact_id_count = document.querySelectorAll('a[href*="/service_center/notice?id="]').length;
        result.all_notice_count = document.querySelectorAll('a[href*="/service_center/notice"]').length;
        result.tr_notice_count = document.querySelectorAll('tr a[href*="notice"]').length;
        result.any_id_count = document.querySelectorAll('a[href*="id="]').length;
        
        // Broader content exists if any non-exact_id selector found links
        result.broader_content_exists = (
            result.all_notice_count > 0 || 
            result.tr_notice_count > 0 || 
            result.any_id_count > 0
        );
        
        return result;
    """)


def retry_exact_id_selector(driver, max_retries=5, retry_interval=0.04, max_total_time=0.2):
    """
    Retries the exact_id selector before falling back to broader strategies.
    
    Args:
        driver: Selenium WebDriver instance
        max_retries: Maximum number of retry attempts (default: 5)
        retry_interval: Time between retries in seconds (default: 0.04 = 40ms)
        max_total_time: Maximum total time for all retries (default: 0.2s)
    
    Returns:
        dict with:
            - success: bool - whether exact_id selector found links
            - count: int - number of links found
            - attempts: int - number of attempts made
            - elapsed_time: float - total time spent
            - dom_state: dict - DOM state at final attempt
    """
    start_time = time.time()
    attempts = 0
    
    for attempt in range(1, max_retries + 1):
        attempts = attempt
        
        # Check if we've exceeded max total time
        elapsed = time.time() - start_time
        if elapsed >= max_total_time:
            break
        
        # Try exact_id selector with DOM state check
        result = driver.execute_script("""
            const exactIdLinks = document.querySelectorAll('a[href*="/service_center/notice?id="]');
            const allNoticeLinks = document.querySelectorAll('a[href*="/service_center/notice"]');
            
            return {
                exact_id_count: exactIdLinks.length,
                all_notice_count: allNoticeLinks.length,
                readyState: document.readyState,
                containerVisible: document.querySelectorAll('table, .notice-list, [class*="notice"], tbody').length > 0
            };
        """)
        
        if result['exact_id_count'] > 0:
            # Success!
            elapsed_time = time.time() - start_time
            return {
                'success': True,
                'count': result['exact_id_count'],
                'attempts': attempts,
                'elapsed_time': elapsed_time,
                'dom_state': result
            }
        
        # Sleep before next attempt (but not after last attempt)
        if attempt < max_retries:
            remaining_time = max_total_time - (time.time() - start_time)
            if remaining_time > retry_interval:
                time.sleep(retry_interval)
            elif remaining_time > 0:
                time.sleep(remaining_time)
            else:
                break
    
    # Failed - get final DOM state
    elapsed_time = time.time() - start_time
    final_state = check_dom_state_for_fallback(driver)
    
    return {
        'success': False,
        'count': 0,
        'attempts': attempts,
        'elapsed_time': elapsed_time,
        'dom_state': final_state
    }


def wait_for_notices_js(driver, max_wait=0.3):
    """
    Ждет появления новостей, проверяя каждые 20ms.
    Использует lightweight readiness probe с отслеживанием стабильности.
    
    Returns:
        tuple: (ready: bool, probe_stats: dict)
            probe_stats содержит: duration, poll_count, strategy
    """
    start = time.time()
    check_interval = 0.02  # 20ms
    poll_count = 0
    
    last_count = -1
    stable_count = 0
    required_stable_samples = 2  # Require 2 consecutive stable samples
    
    detected_strategy = None
    
    while time.time() - start < max_wait:
        try:
            poll_count += 1
            probe_result = check_readiness_probe(driver)
            
            # Track stability - same count multiple times
            if probe_result['count'] == last_count and probe_result['count'] > 0:
                stable_count += 1
            else:
                stable_count = 0
                last_count = probe_result['count']
            
            # Short-circuit if ready and stable
            if probe_result['ready'] and stable_count >= required_stable_samples:
                elapsed = time.time() - start
                detected_strategy = probe_result['strategy']
                
                probe_stats = {
                    'duration': elapsed,
                    'poll_count': poll_count,
                    'strategy': detected_strategy,
                    'stable_samples': stable_count + 1,
                    'final_count': probe_result['count']
                }
                
                logging.info(
                    f"⚡ Notices ready: {elapsed*1000:.0f}ms "
                    f"(polls: {poll_count}, strategy: {detected_strategy}, "
                    f"count: {probe_result['count']}, stable: {stable_count + 1})"
                )
                return True, probe_stats
            
            # Also accept if ready without full stability (for speed)
            if probe_result['ready']:
                detected_strategy = probe_result['strategy']
        
        except Exception as e:
            logging.debug(f"Probe error: {e}")
        
        time.sleep(check_interval)
    
    elapsed = time.time() - start
    probe_stats = {
        'duration': elapsed,
        'poll_count': poll_count,
        'strategy': detected_strategy,
        'timed_out': True
    }
    
    logging.warning(
        f"⚠️ Wait timeout: {elapsed*1000:.0f}ms "
        f"(polls: {poll_count}, strategy: {detected_strategy or 'none'})"
    )
    return False, probe_stats


def get_all_notice_ids(driver, min_expected_count=20):
    """
    Извлекает ID новостей с расширенным извлечением метаданных и защитой от чрезмерной фильтрации.
    Фильтрация выполняется в Python с отслеживанием причин и защитным fallback механизмом.
    
    Приоритет 1: НАДЕЖНОСТЬ (никогда не возвращать 0 результатов при наличии валидных ссылок)
    Приоритет 2: ТОЧНОСТЬ (фильтровать только подтвержденно закрепленные)
    Приоритет 3: СКОРОСТЬ (< 0.5 сек парсинг)
    
    Args:
        min_expected_count: Минимальное ожидаемое количество новостей (по умолчанию 20)
    
    Возвращает список ID незакрепленных новостей: [5710, 5709, 5701, ...]
    При ошибке автоматически запускает диагностику.
    
    Fallback стратегии (те же что в диагностике):
    1. exact_id - точный селектор с ?id=
    2. all_notice - любые ссылки с /service_center/notice
    3. tr_notice - ссылки в таблице
    4. any_id - любые ссылки с параметром id=
    """
    parse_start = time.time()
    
    # JavaScript код для извлечения метаданных
    js_extract_metadata = """
        return Array.from(document.querySelectorAll(arguments[0]))
            .map(link => {
                const parentRow = link.closest('tr');
                const parentRowClasses = parentRow ? parentRow.className : '';
                
                // Ищем badge элементы
                const badge = link.querySelector('.badge, .tag, [class*="badge"], [class*="pin"]');
                const badgeText = badge ? badge.textContent.trim() : '';
                
                // Проверяем data-атрибуты
                const linkData = {
                    pinned: link.dataset.pinned || (parentRow ? parentRow.dataset.pinned : null),
                    fixed: link.dataset.fixed || (parentRow ? parentRow.dataset.fixed : null),
                    type: link.dataset.type || (parentRow ? parentRow.dataset.type : null)
                };
                
                return {
                    href: link.getAttribute('href'),
                    text: link.textContent.trim(),
                    parentClasses: parentRowClasses,
                    badgeText: badgeText,
                    dataAttrs: linkData
                };
            });
    """
    
    try:
        # Initialize tracking variables
        fallback_reason = None
        
        # === СТРАТЕГИЯ 1: Точный селектор с retry loop ===
        logging.info("🔍 Strategy 1 (exact_id): Starting with retry loop...")
        
        # Retry exact_id selector before fallback
        retry_result = retry_exact_id_selector(driver, max_retries=5, retry_interval=0.04, max_total_time=0.2)
        
        # Log instrumentation data
        logging.info(
            f"📊 Strategy 1 instrumentation: "
            f"attempts={retry_result['attempts']}, "
            f"time={retry_result['elapsed_time']*1000:.0f}ms, "
            f"success={retry_result['success']}"
        )
        
        if retry_result['success']:
            # Strategy 1 succeeded!
            links = driver.execute_script(js_extract_metadata, 'a[href*="/service_center/notice?id="]')
            strategy = 'exact_id'
            total_links = len(links)
            
            logging.info(
                f"✅ Strategy 1 (exact_id): {total_links} links "
                f"(found after {retry_result['attempts']} attempt(s), "
                f"{retry_result['elapsed_time']*1000:.0f}ms)"
            )
        else:
            # Strategy 1 failed after retries - check DOM state
            dom_state = retry_result['dom_state']
            
            # Determine fallback reason
            if dom_state.get('broader_content_exists', False):
                fallback_reason = 'exact_id_failed_but_broader_content_exists'
                logging.warning(
                    f"⚠️ Strategy 1 failed after {retry_result['attempts']} attempts "
                    f"({retry_result['elapsed_time']*1000:.0f}ms) "
                    f"BUT broader selectors see content:"
                )
                logging.warning(f"   • all_notice: {dom_state.get('all_notice_count', 0)} links")
                logging.warning(f"   • tr_notice: {dom_state.get('tr_notice_count', 0)} links")
                logging.warning(f"   • any_id: {dom_state.get('any_id_count', 0)} links")
                logging.warning(f"   • DOM: readyState={dom_state.get('readyState', 'unknown')}, "
                              f"container={dom_state.get('containerVisible', False)}")
            else:
                fallback_reason = 'no_content_detected'
                logging.info(
                    f"ℹ️ Strategy 1 failed and no broader content detected - "
                    f"page may still be loading"
                )
            
            links = []
        
        # === СТРАТЕГИЯ 2: Все notice ссылки (fallback) ===
        if len(links) == 0:
            links = driver.execute_script(js_extract_metadata, 'a[href*="/service_center/notice"]')
            strategy = 'all_notice'
            total_links = len(links)
            logging.info(f"🔍 Strategy 2 (all_notice): {total_links} links")
        
        # === СТРАТЕГИЯ 3: tr a с notice (fallback) ===
        if len(links) == 0:
            links = driver.execute_script(js_extract_metadata, 'tr a[href*="notice"]')
            strategy = 'tr_notice'
            total_links = len(links)
            logging.info(f"🔍 Strategy 3 (tr_notice): {total_links} links")
        
        # === СТРАТЕГИЯ 4: любые a с id= (последний fallback) ===
        if len(links) == 0:
            links = driver.execute_script(js_extract_metadata, 'a[href*="id="]')
            strategy = 'any_id'
            total_links = len(links)
            logging.info(f"🔍 Strategy 4 (any_id): {total_links} links")
        
        # === ИЗВЛЕЧЕНИЕ И ФИЛЬТРАЦИЯ в Python с отслеживанием причин ===
        all_notices = []  # Все распарсенные новости с метаданными
        filter_stats = {
            'pinned_badge': 0,
            'pinned_class': 0,
            'pinned_marker': 0,
            'short_navigation': 0,
            'no_id': 0,
            'total_filtered': 0
        }
        
        for link in links:
            href = link.get('href', '')
            text = link.get('text', '')
            parent_classes = link.get('parentClasses', '').lower()
            badge_text = link.get('badgeText', '')
            data_attrs = link.get('dataAttrs', {})
            
            # Извлекаем ID через regex в Python
            match = re.search(r'id=(\d+)', href)
            if not match:
                filter_stats['no_id'] += 1
                continue
            
            notice_id = int(match.group(1))
            
            # Сохраняем все данные для возможного fallback
            notice_data = {
                'id': notice_id,
                'text': text,
                'href': href,
                'parent_classes': parent_classes,
                'badge_text': badge_text,
                'data_attrs': data_attrs,
                'is_pinned': False,
                'filter_reason': None
            }
            
            # === ПРОВЕРКА НА ЗАКРЕПЛЕННОСТЬ (только с явными маркерами!) ===
            
            # Метод 1: Badge содержит маркер закрепления
            if badge_text and ('공지' in badge_text or 'pin' in badge_text.lower() or 'fixed' in badge_text.lower()):
                notice_data['is_pinned'] = True
                notice_data['filter_reason'] = 'pinned_badge'
                filter_stats['pinned_badge'] += 1
            
            # Метод 2: Класс родительского элемента содержит маркер
            elif 'pinned' in parent_classes or 'fixed' in parent_classes or 'sticky' in parent_classes:
                notice_data['is_pinned'] = True
                notice_data['filter_reason'] = 'pinned_class'
                filter_stats['pinned_class'] += 1
            
            # Метод 3: Data-атрибуты указывают на закрепление
            elif data_attrs.get('pinned') == 'true' or data_attrs.get('fixed') == 'true' or data_attrs.get('type') == 'pinned':
                notice_data['is_pinned'] = True
                notice_data['filter_reason'] = 'pinned_class'
                filter_stats['pinned_class'] += 1
            
            # Метод 4: Текст НАЧИНАЕТСЯ с маркера (не просто содержит где-то)
            elif text.startswith('공지') or text.startswith('[공지]') or text.startswith('[중요]'):
                notice_data['is_pinned'] = True
                notice_data['filter_reason'] = 'pinned_marker'
                filter_stats['pinned_marker'] += 1
            
            # Метод 5: Текст слишком короткий (явная навигация: "다음", "이전", "1", "2")
            elif len(text) < 3 or (len(text) < 5 and text.isdigit()):
                notice_data['is_pinned'] = True  # Технически не pinned, но фильтруем
                notice_data['filter_reason'] = 'short_navigation'
                filter_stats['short_navigation'] += 1
            
            all_notices.append(notice_data)
        
        # Подсчитываем отфильтрованные
        filtered_notices = [n for n in all_notices if not n['is_pinned']]
        filter_stats['total_filtered'] = len(all_notices) - len(filtered_notices)
        
        # === ЗАЩИТНЫЙ FALLBACK: предотвращаем чрезмерную фильтрацию ===
        fallback_invoked = False
        
        if len(filtered_notices) < min_expected_count and len(all_notices) >= min_expected_count:
            logging.warning(f"⚠️ FALLBACK TRIGGERED: Фильтрация слишком агрессивна!")
            logging.warning(f"   Было: {len(all_notices)} → После фильтрации: {len(filtered_notices)} < Ожидается: {min_expected_count}")
            logging.warning(f"   Смягчаем фильтрацию...")
            
            fallback_invoked = True
            
            # Стратегия fallback: возвращаем те, что отфильтрованы по менее строгим причинам
            relaxed_notices = [
                n for n in all_notices 
                if not n['is_pinned'] or n['filter_reason'] in ['short_navigation', 'pinned_marker']
            ]
            
            # Если все еще мало - берем только verified pinned (badge + class)
            if len(relaxed_notices) < min_expected_count:
                relaxed_notices = [
                    n for n in all_notices
                    if not n['is_pinned'] or n['filter_reason'] not in ['pinned_badge', 'pinned_class']
                ]
            
            # Последний fallback - берем все
            if len(relaxed_notices) < min_expected_count:
                logging.warning(f"   CRITICAL FALLBACK: Возвращаем все новости без фильтрации!")
                relaxed_notices = all_notices
            
            filtered_notices = relaxed_notices
            logging.info(f"   ✅ После fallback: {len(filtered_notices)} новостей")
        
        # === ФОРМИРОВАНИЕ РЕЗУЛЬТАТА ===
        notice_ids = [n['id'] for n in filtered_notices]
        samples = [{'id': n['id'], 'title': n['text'][:50]} for n in filtered_notices[:3]]
        
        # Обновляем глобальную статистику
        global _last_parse_stats
        _last_parse_stats = {
            'fallback_invoked': fallback_invoked,
            'filter_stats': filter_stats,
            'total_raw_links': len(all_notices),
            'total_filtered_links': len(filtered_notices),
            'strategy_stats': {
                'strategy_used': strategy,
                'exact_id_attempts': retry_result['attempts'],
                'exact_id_retry_time': retry_result['elapsed_time'],
                'exact_id_success': retry_result['success'],
                'fallback_reason': fallback_reason if not retry_result['success'] else None,
                'dom_state_at_fallback': retry_result['dom_state'] if not retry_result['success'] else None
            }
        }
        
        parse_time = time.time() - parse_start
        
        # === ПРОВЕРКА РЕЗУЛЬТАТА ===
        if len(notice_ids) == 0:
            logging.error(f"❌ Новости не найдены!")
            logging.error(f"   Strategy: {strategy}")
            logging.error(f"   Total links found: {total_links}")
            logging.error(f"   После фильтрации: {len(notice_ids)}")
            logging.error(f"   Filter stats: {filter_stats}")
            logging.error("💡 Запускаем диагностику...")
            debug_save_html_and_find_selectors(driver)
            return []
        
        # === УСПЕХ! ===
        logging.info(f"✅ Найдено {len(notice_ids)} новостей (strategy: {strategy}, total links: {total_links})")
        logging.info(f"🔢 ID: {notice_ids[:5]}{'...' if len(notice_ids) > 5 else ''}")
        
        # Статистика фильтрации
        if filter_stats['total_filtered'] > 0:
            logging.info(f"🗂️ Фильтрация: отброшено {filter_stats['total_filtered']} элементов")
            if filter_stats['pinned_badge'] > 0:
                logging.info(f"   • Pinned (badge): {filter_stats['pinned_badge']}")
            if filter_stats['pinned_class'] > 0:
                logging.info(f"   • Pinned (class/data): {filter_stats['pinned_class']}")
            if filter_stats['pinned_marker'] > 0:
                logging.info(f"   • Pinned (marker): {filter_stats['pinned_marker']}")
            if filter_stats['short_navigation'] > 0:
                logging.info(f"   • Navigation/short: {filter_stats['short_navigation']}")
            if filter_stats['no_id'] > 0:
                logging.info(f"   • No ID: {filter_stats['no_id']}")
        
        if fallback_invoked:
            logging.warning(f"🛡️ FALLBACK WAS INVOKED - фильтрация была смягчена")
        
        # Примеры новостей
        if samples:
            logging.info("📋 Примеры:")
            for sample in samples:
                logging.info(f"   • ID:{sample['id']} - {sample['title']}")
        
        logging.info(f"⏱️ Время парсинга: {parse_time:.3f}s")
        
        # Оценка скорости
        if parse_time > 1.0:
            logging.warning(f"⚠️ Медленно: {parse_time:.3f}s > 1.0s")
        elif parse_time > 0.5:
            logging.info(f"✅ Хорошо: {parse_time:.3f}s < 1.0s")
        else:
            logging.info(f"⚡ Отлично: {parse_time:.3f}s < 0.5s!")
        
        return notice_ids
        
    except Exception as e:
        parse_time = time.time() - parse_start
        logging.error(f"❌ Ошибка парсинга (время: {parse_time:.3f}s): {e}")
        import traceback
        logging.error(traceback.format_exc())
        logging.error("💡 Запускаем диагностику...")
        
        # Автоматически запускаем диагностику при ошибке
        try:
            debug_save_html_and_find_selectors(driver)
        except Exception as debug_error:
            logging.error(f"❌ Ошибка диагностики: {debug_error}")
        
        return []


def get_last_parse_stats():
    """
    Возвращает статистику последнего парсинга (для observability)
    """
    return _last_parse_stats.copy()


def get_notice_by_id(driver, notice_id):
    """
    Получает данные конкретной новости по её ID
    """
    js_code = f"""
    const links = document.querySelectorAll('tr a[href*="/service_center/notice"]');
    
    for (let link of links) {{
        const href = link.getAttribute('href');
        const match = href.match(/id=(\\d+)/);
        
        if (match && parseInt(match[1]) === {notice_id}) {{
            const titleSpan = link.querySelector('span.css-qju2q6, span.css-twx20f, span[class*="title"]');
            const title = titleSpan ? titleSpan.textContent.trim() : link.textContent.trim();
            
            return {{ title, href }};
        }}
    }}
    
    return null;
    """
    
    try:
        result = driver.execute_script(js_code)
        
        if not result:
            return None
        
        href = result['href']
        full_link = f"https://upbit.com{href}" if href.startswith('/') else href
        
        return {
            "id": notice_id,
            "title": result['title'],
            "link": full_link
        }
    except Exception as e:
        logging.error(f"[get_notice_by_id] Ошибка для ID {notice_id}: {e}")
        return None


def discover_api_endpoints(driver, save_to_file=True):
    """
    Режим обнаружения API endpoints - анализирует сетевые запросы
    и находит JSON API которые использует Upbit для загрузки новостей
    
    Args:
        driver: Selenium WebDriver с включенным CDP
        save_to_file: Сохранять ли результаты в api_discovery.json
    
    Returns:
        list: Список найденных API endpoints
    """
    logging.info("🔍 ━━━ РЕЖИМ ОБНАРУЖЕНИЯ API ━━━")
    logging.info("Загружаем страницу и анализируем сетевые запросы...")
    
    try:
        # Загружаем страницу
        driver.get(UPBIT_NOTICE_URL)
        time.sleep(3)  # Даём всем запросам завершиться
        
        # Получаем все логи производительности
        logs = driver.get_log('performance')
        logging.info(f"📊 Всего сетевых событий: {len(logs)}")
        
        # Анализируем запросы
        api_candidates = []
        json_responses = []
        
        for log in logs:
            try:
                message = json.loads(log['message'])
                msg_data = message.get('message', {})
                method = msg_data.get('method', '')
                
                # Ищем ответы на запросы
                if method == 'Network.responseReceived':
                    params = msg_data.get('params', {})
                    response = params.get('response', {})
                    url = response.get('url', '')
                    mime_type = response.get('mimeType', '')
                    status = response.get('status', 0)
                    
                    # Фильтруем JSON ответы
                    if 'json' in mime_type.lower() or 'application' in mime_type.lower():
                        json_responses.append({
                            'url': url,
                            'status': status,
                            'mimeType': mime_type,
                            'requestId': params.get('requestId', '')
                        })
                        
                        # Проверяем на наличие ключевых слов
                        url_lower = url.lower()
                        if any(keyword in url_lower for keyword in ['notice', 'announcement', 'news', 'board', 'list']):
                            api_candidates.append({
                                'url': url,
                                'status': status,
                                'mimeType': mime_type,
                                'requestId': params.get('requestId', ''),
                                'priority': 'HIGH'
                            })
                            logging.info(f"🎯 Найден потенциальный API: {url}")
            
            except (json.JSONDecodeError, KeyError) as e:
                # Пропускаем невалидные логи
                continue
        
        logging.info(f"\n📋 JSON ответы найдены: {len(json_responses)}")
        
        if api_candidates:
            logging.info(f"\n🎯 Потенциальные API endpoints: {len(api_candidates)}")
            for idx, candidate in enumerate(api_candidates, 1):
                logging.info(f"  {idx}. {candidate['url']}")
                logging.info(f"     Status: {candidate['status']}, Type: {candidate['mimeType']}")
        else:
            logging.warning("\n⚠️ Прямые API endpoints с ключевыми словами не найдены")
            logging.info("📋 Все JSON ответы:")
            for idx, resp in enumerate(json_responses[:10], 1):  # Показываем первые 10
                logging.info(f"  {idx}. {resp['url']}")
                logging.info(f"     Status: {resp['status']}, Type: {resp['mimeType']}")
        
        # Сохраняем результаты
        if save_to_file:
            discovery_data = {
                'timestamp': datetime.now().isoformat(),
                'total_network_events': len(logs),
                'json_responses': json_responses,
                'api_candidates': api_candidates
            }
            
            with open('api_discovery.json', 'w', encoding='utf-8') as f:
                json.dump(discovery_data, f, indent=2, ensure_ascii=False)
            
            logging.info("\n💾 Результаты сохранены в api_discovery.json")
        
        return api_candidates if api_candidates else json_responses
    
    except Exception as e:
        logging.error(f"❌ Ошибка обнаружения API: {e}")
        return []


def extract_ids_from_json(data):
    """
    Извлекает ID новостей из JSON ответа API
    Поддерживает различные структуры данных
    
    Args:
        data: JSON данные (dict или list)
    
    Returns:
        list: Список ID новостей (незакрепленных)
    """
    notice_ids = []
    
    try:
        # Вариант 1: data.data.list[] (наиболее вероятный для Upbit)
        if isinstance(data, dict) and 'data' in data:
            if isinstance(data['data'], dict) and 'list' in data['data']:
                items = data['data']['list']
                for item in items:
                    # Проверяем закреплённость
                    is_pinned = item.get('fixed', False) or item.get('pinned', False) or item.get('is_pinned', False)
                    if not is_pinned:
                        notice_id = item.get('id') or item.get('notice_id') or item.get('noticeId')
                        if notice_id:
                            notice_ids.append(int(notice_id))
                
                if notice_ids:
                    logging.info(f"✅ Структура: data.data.list[] - найдено {len(notice_ids)} ID")
                    return notice_ids
        
        # Вариант 2: data.notices[]
        if isinstance(data, dict) and 'notices' in data:
            items = data['notices']
            for item in items:
                is_pinned = item.get('fixed', False) or item.get('pinned', False)
                if not is_pinned:
                    notice_id = item.get('id') or item.get('notice_id')
                    if notice_id:
                        notice_ids.append(int(notice_id))
            
            if notice_ids:
                logging.info(f"✅ Структура: data.notices[] - найдено {len(notice_ids)} ID")
                return notice_ids
        
        # Вариант 3: data.data[] (прямой массив)
        if isinstance(data, dict) and 'data' in data and isinstance(data['data'], list):
            for item in data['data']:
                is_pinned = item.get('fixed', False) or item.get('pinned', False)
                if not is_pinned:
                    notice_id = item.get('id') or item.get('notice_id')
                    if notice_id:
                        notice_ids.append(int(notice_id))
            
            if notice_ids:
                logging.info(f"✅ Структура: data.data[] - найдено {len(notice_ids)} ID")
                return notice_ids
        
        # Вариант 4: data.list[]
        if isinstance(data, dict) and 'list' in data:
            for item in data['list']:
                is_pinned = item.get('fixed', False) or item.get('pinned', False)
                if not is_pinned:
                    notice_id = item.get('id') or item.get('notice_id')
                    if notice_id:
                        notice_ids.append(int(notice_id))
            
            if notice_ids:
                logging.info(f"✅ Структура: data.list[] - найдено {len(notice_ids)} ID")
                return notice_ids
        
        # Вариант 5: Прямой массив
        if isinstance(data, list):
            for item in data:
                is_pinned = item.get('fixed', False) or item.get('pinned', False)
                if not is_pinned:
                    notice_id = item.get('id') or item.get('notice_id')
                    if notice_id:
                        notice_ids.append(int(notice_id))
            
            if notice_ids:
                logging.info(f"✅ Структура: прямой массив - найдено {len(notice_ids)} ID")
                return notice_ids
        
        # Если ничего не нашли - показываем структуру для отладки
        logging.warning(f"⚠️ Неизвестная структура JSON")
        if isinstance(data, dict):
            logging.warning(f"   Доступные ключи: {list(data.keys())}")
            # Показываем первый уровень вложенности
            for key, value in list(data.items())[:3]:
                if isinstance(value, dict):
                    logging.warning(f"   {key}: dict с ключами {list(value.keys())[:5]}")
                elif isinstance(value, list):
                    logging.warning(f"   {key}: list длины {len(value)}")
                else:
                    logging.warning(f"   {key}: {type(value).__name__}")
        
    except Exception as e:
        logging.error(f"❌ Ошибка извлечения ID из JSON: {e}")
    
    return notice_ids


def load_known_endpoints():
    """
    Загружает известные API endpoints из api_discovery.json
    
    Returns:
        list: Список URL endpoints (может быть пустым)
    """
    endpoints = []
    try:
        if not os.path.exists('api_discovery.json'):
            return endpoints
        
        with open('api_discovery.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get('url'):
                    endpoints.append(item['url'])
        elif isinstance(data, dict):
            if data.get('api_candidates'):
                endpoints.extend(item['url'] for item in data['api_candidates'] if isinstance(item, dict) and item.get('url'))
            elif data.get('json_responses'):
                endpoints.extend(item['url'] for item in data['json_responses'] if isinstance(item, dict) and item.get('url'))
        
        # Удаляем пустые и дубли
        endpoints = [url for url in endpoints if url]
        endpoints = list(dict.fromkeys(endpoints))
        
        if endpoints:
            logging.info(f"📋 Загружено {len(endpoints)} известных API endpoints")
        else:
            logging.info("📋 Известные API endpoints не обнаружены в файле")
        
        return endpoints
    
    except Exception as e:
        logging.warning(f"⚠️ Ошибка загрузки api_discovery.json: {e}")
        return endpoints


def get_notices_from_api(driver, known_endpoints=None, max_wait=2.0, return_details=False):
    """
    Получает новости через перехват API запросов используя CDP
    
    Args:
        driver: Selenium WebDriver с включенным CDP
        known_endpoints: Список известных API endpoints (опционально)
        max_wait: Максимальное время ожидания API запроса (сек)
        return_details: Возвращать ли дополнительные метрики (dict)
    
    Returns:
        list | tuple: Список ID новостей или (list, details) если return_details=True
    """
    start_time = time.time()
    known_endpoints = known_endpoints or []
    
    try:
        # Загружаем страницу
        page_load_start = time.time()
        driver.get(UPBIT_NOTICE_URL)
        page_load_time = time.time() - page_load_start
        
        logging.info(f"  ⏱️ Загрузка страницы (API): {page_load_time:.3f}s")
        if known_endpoints:
            logging.info(f"  📋 Используем {len(known_endpoints)} известных endpoints для фильтрации")
        
        # Ждём появления API запросов
        wait_start = time.time()
        notices_data = None
        api_url_found = None
        
        while time.time() - wait_start < max_wait:
            try:
                logs = driver.get_log('performance')
                
                for log in logs:
                    try:
                        message = json.loads(log['message'])
                        msg_data = message.get('message', {})
                        method = msg_data.get('method', '')
                        
                        if method == 'Network.responseReceived':
                            params = msg_data.get('params', {})
                            response = params.get('response', {})
                            url = response.get('url', '')
                            mime_type = response.get('mimeType', '')
                            request_id = params.get('requestId', '')
                            
                            # Проверяем, это ли наш API endpoint
                            url_lower = url.lower()
                            is_json = 'json' in mime_type.lower() or 'application' in mime_type.lower()
                            is_notice_api = any(keyword in url_lower for keyword in ['notice', 'announcement', 'board', 'list'])
                            
                            # Если есть известные endpoints - проверяем их
                            if known_endpoints:
                                is_notice_api = is_notice_api or any(endpoint in url for endpoint in known_endpoints)
                            
                            if is_json and is_notice_api:
                                # Нашли API запрос! Получаем тело ответа
                                try:
                                    body_response = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                                    body_text = body_response.get('body', '')
                                    
                                    if body_text:
                                        # Парсим JSON
                                        notices_data = json.loads(body_text)
                                        api_url_found = url
                                        logging.info(f"✅ API запрос перехвачен: {url[:120]}...")
                                        break
                                
                                except Exception:
                                    # Тело ответа может быть недоступно - пропускаем
                                    continue
                    
                    except (json.JSONDecodeError, KeyError):
                        continue
                
                if notices_data:
                    break
                
                time.sleep(0.05)  # Проверяем каждые 50ms
            
            except Exception as poll_error:
                logging.debug(f"Ошибка при опросе логов: {poll_error}")
                time.sleep(0.05)
        
        wait_time = time.time() - wait_start
        
        if notices_data:
            # Парсим JSON и извлекаем ID
            parse_start = time.time()
            notice_ids = extract_ids_from_json(notices_data)
            parse_time = time.time() - parse_start
            
            total_time = time.time() - start_time
            
            if notice_ids:
                logging.info(f"  ⏱️ API запрос: {wait_time:.3f}s")
                logging.info(f"  ⏱️ Парсинг JSON: {parse_time:.3f}s")
                logging.info(f"✅ Найдено {len(notice_ids)} новостей (strategy: API)")
                logging.info(f"🔢 ID: {notice_ids[:5]}{'...' if len(notice_ids) > 5 else ''}")
                logging.info(f"⚡ API MODE: Load {page_load_time:.3f}s + API {wait_time:.3f}s + Parse {parse_time:.3f}s = {total_time:.3f}s")
                
                details = {
                    "endpoint": api_url_found,
                    "page_load_time": page_load_time,
                    "wait_time": wait_time,
                    "parse_time": parse_time,
                    "total_time": total_time,
                }
                
                return (notice_ids, details) if return_details else notice_ids
            else:
                logging.warning("⚠️ API перехвачен, но ID не извлечены (неизвестная структура)")
                logging.warning("   → Fallback на HTML парсинг")
                return (None, None) if return_details else None
        else:
            elapsed = time.time() - start_time
            logging.warning(f"⚠️ API endpoint не найден за {elapsed:.3f}s")
            logging.warning("   → Fallback на HTML парсинг")
            return (None, None) if return_details else None
    
    except Exception as e:
        elapsed = time.time() - start_time
        logging.error(f"❌ Ошибка перехвата API ({elapsed:.3f}s): {e}")
        logging.warning("   → Fallback на HTML парсинг")
        return (None, None) if return_details else None


def get_last_max_id():
    """
    Читает максимальный известный ID из файла
    Возвращает int или None
    """
    try:
        if os.path.exists(LAST_NOTICE_FILE):
            with open(LAST_NOTICE_FILE, "r") as f:
                content = f.read().strip()
                # Если в файле ссылка - извлекаем ID
                if "id=" in content:
                    match = re.search(r'id=(\d+)', content)
                    if match:
                        max_id = int(match.group(1))
                        logging.info(f"[get_last_max_id] Прочитан max_id из ссылки: {max_id}")
                        return max_id
                # Если просто число
                elif content.isdigit():
                    max_id = int(content)
                    logging.info(f"[get_last_max_id] Прочитан max_id: {max_id}")
                    return max_id
        
        logging.info("[get_last_max_id] Файл отсутствует или пустой")
        return None
    except Exception as e:
        logging.error(f"[get_last_max_id] Ошибка чтения: {e}")
        return None


def save_max_id(max_id):
    """
    Сохраняет максимальный ID в файл
    """
    try:
        with open(LAST_NOTICE_FILE, "w") as f:
            f.write(str(max_id))
        logging.info(f"[save_max_id] Сохранён max_id: {max_id}")
    except Exception as e:
        logging.error(f"[save_max_id] Ошибка записи: {e}")


def notify_about_new_ids(driver, new_ids, *, detection_start=None, pause_between=0.5):
    """
    Отправляет уведомления о новых новостях по их ID.
    Возвращает количество успешно обработанных новостей.
    """
    if not new_ids:
        return 0
    
    processed = 0
    sorted_ids = sorted(new_ids)
    
    for index, notice_id in enumerate(sorted_ids):
        # Время обнаружения
        detection_time = detection_start if detection_start is not None else datetime.now()
        
        # Начало обработки
        processing_start = datetime.now()
        
        # Получаем данные новости
        notice = get_notice_by_id(driver, notice_id)
        
        # Завершение обработки
        processing_completed = datetime.now()
        
        if not notice:
            logging.error(f"❌ Не удалось получить данные новости ID {notice_id}")
            metrics_logger.log_error(notice_id, "Unknown", "Failed to fetch notice data")
            continue
        
        logging.info(f"🔔 НОВАЯ НОВОСТЬ (ID {notice_id}): {notice['title']}")
        logging.info(f"🔗 Ссылка: {notice['link']}")
        
        # Отправляем в Telegram и получаем время отправки
        telegram_sent = send_telegram_notification(
            notice["title"],
            notice["link"],
            detection_time=detection_time,
            processing_completed_time=processing_completed
        )
        
        # Логируем метрики в отдельный файл
        try:
            metrics_logger.log_article_metrics(
                notice_id=notice_id,
                title=notice['title'],
                source="Upbit Notice",
                detected_at=detection_time,
                processing_started=processing_start,
                processing_completed=processing_completed,
                telegram_sent=telegram_sent
            )
        except Exception as e:
            logging.error(f"❌ Ошибка записи метрик: {e}")
        
        bot_latency = (telegram_sent - detection_time).total_seconds()
        
        logging.info(f"⏱️ Обнаружено: {detection_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        logging.info(f"📤 Отправлено: {telegram_sent.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        logging.info(f"⚡ Задержка бота: {bot_latency:.3f} сек")
        
        if bot_latency < 0.5:
            logging.info("✅ ОТЛИЧНО: Задержка < 0.5 сек")
        elif bot_latency < 1.0:
            logging.info("✅ ХОРОШО: Задержка < 1 сек")
        elif bot_latency < 2.0:
            logging.warning("⚠️ ПРИЕМЛЕМО: Задержка 1-2 сек")
        else:
            logging.error(f"❌ МЕДЛЕННО: Задержка {bot_latency:.3f} сек")
        
        processed += 1
        
        if pause_between and index < len(sorted_ids) - 1:
            time.sleep(pause_between)
    
    return processed


def send_telegram_notification(title, link, detection_time=None, processing_completed_time=None):
    """
    Отправляет уведомление в Telegram с точными метриками времени
    
    Args:
        title: Заголовок новости
        link: Ссылка на новость
        detection_time: datetime - время обнаружения новости
        processing_completed_time: datetime - время завершения обработки (опционально)
    
    Returns:
        datetime - время отправки в Telegram
    """
    # Момент отправки
    send_time = datetime.now()

    notice_id = None
    if link:
        match = re.search(r"id=(\d+)", link)
        if match:
            try:
                notice_id = int(match.group(1))
            except ValueError:
                notice_id = None
    
    # Базовое сообщение
    message = f"""🔔 <b>Новая новость Upbit</b>

<b>{title}</b>

🔗 {link}"""
    
    # Добавляем футер с метриками (согласно требованию)
    if detection_time:
        bot_latency = (send_time - detection_time).total_seconds()
        
        # Форматируем времена
        detection_str = detection_time.strftime('%H:%M:%S')
        send_str = send_time.strftime('%H:%M:%S')
        
        # Футер с метриками
        message += f"""

⏱ Обнаружено: {detection_str}
📤 Отправлено: {send_str}
⚡️ Задержка: {bot_latency:.1f} сек"""
    
    send_to_telegram(
        None,
        TELEGRAM_TOKEN,
        TELEGRAM_CHAT_ID,
        message,
        notice_id=notice_id,
        telemetry=telegram_retry_telemetry,
        parse_mode="HTML",
    )
    
    return send_time


def get_random_delay():
    """
    Возвращает случайную задержку между 0.5 и 1.5 секундами для имитации человека
    """
    return random.uniform(0.5, 1.5)


def get_refresh_interval():
    """
    Возвращает случайный интервал между refresh (1-2 секунды)
    """
    return random.uniform(1.0, 2.0)


def get_all_notice_ids_with_api(driver, known_endpoints=None, use_cdp=True):
    """
    Получает список ID новостей, пытаясь сначала использовать API, затем HTML fallback
    
    Args:
        driver: Selenium WebDriver
        known_endpoints: Список известных API endpoints
        use_cdp: Использовать ли CDP API (если False - только HTML)
    
    Returns:
        tuple: (notice_ids: list, method: str, timings: dict)
    """
    start_time = time.time()
    
    # Пытаемся API если CDP включен
    if use_cdp:
        try:
            api_result, api_details = get_notices_from_api(
                driver,
                known_endpoints=known_endpoints,
                max_wait=2.0,
                return_details=True
            )
            if api_result:
                total_time = api_details.get("total_time", time.time() - start_time)
                return api_result, "API", {"total": total_time, "api": api_details}
            else:
                logging.warning("⚠️ API не вернул результаты, выполняем HTML fallback")
        except Exception as e:
            logging.warning(f"⚠️ Ошибка API: {e}, выполняем HTML fallback")
    else:
        logging.info("ℹ️ CDP отключен, используем HTML парсинг")
    
    # HTML fallback с измерением времени
    try:
        page_load_start = time.time()
        driver.get(UPBIT_NOTICE_URL)
        page_load_time = time.time() - page_load_start
        logging.info(f"  ⏱️ Загрузка страницы (HTML): {page_load_time:.3f}s")
    except Exception as load_error:
        logging.error(f"❌ Ошибка загрузки страницы для HTML fallback: {load_error}")
        return [], "FAILED", {"total": time.time() - start_time}
    
    # БЫСТРАЯ ПРОВЕРКА: используем readiness probe
    wait_start = time.time()
    quick_check_start = time.time()
    probe_stats = None
    
    try:
        # Use the same readiness probe for quick check
        probe_result = check_readiness_probe(driver)
        quick_check_time = (time.time() - quick_check_start) * 1000
        
        if probe_result['ready']:
            # Новости УЖЕ ЕСТЬ! Не ждём дополнительно
            wait_time = time.time() - wait_start
            probe_stats = {
                'duration': wait_time,
                'poll_count': 1,
                'strategy': probe_result['strategy'],
                'quick_check': True,
                'final_count': probe_result['count']
            }
            logging.info(
                f"⚡ Notices ready immediately: {quick_check_time:.0f}ms "
                f"(strategy: {probe_result['strategy']}, count: {probe_result['count']}) - skip wait"
            )
        else:
            # Ждём появления
            logging.info(
                f"⏳ Notices not ready immediately ({quick_check_time:.0f}ms, "
                f"readyState: {probe_result['readyState']}) - waiting..."
            )
            notices_ready, probe_stats = wait_for_notices_js(driver, max_wait=0.3)
            wait_time = time.time() - wait_start
            
            if not notices_ready:
                logging.warning(f"  ⚠️ Notices not ready after {wait_time:.3f}s")
    except Exception as check_error:
        # Если быстрая проверка не сработала, используем обычное ожидание
        logging.debug(f"Quick check failed: {check_error}, using standard wait")
        notices_ready, probe_stats = wait_for_notices_js(driver, max_wait=0.3)
        wait_time = time.time() - wait_start
    
    # Log structured wait phase metrics
    if probe_stats:
        logging.info(
            f"  ⏱️ Wait phase (HTML): {wait_time:.3f}s "
            f"(polls: {probe_stats.get('poll_count', 0)}, "
            f"strategy: {probe_stats.get('strategy', 'unknown')})"
        )
    else:
        logging.info(f"  ⏱️ Wait phase (HTML): {wait_time:.3f}s")
    
    parse_start = time.time()
    notice_ids = get_all_notice_ids(driver)
    parse_time = time.time() - parse_start
    
    total_time = time.time() - start_time
    html_details = {
        "page_load": page_load_time,
        "wait": wait_time,
        "parse": parse_time,
        "probe_stats": probe_stats,
    }
    
    if notice_ids:
        logging.info(f"✅ HTML MODE: Получено {len(notice_ids)} ID за {total_time:.3f}s")
        logging.info(f"⏱️ ━━━ ИТОГО ЦИКЛ: {total_time:.3f}s ━━━")
        logging.info(f"   Strategy: HTML")
        
        if total_time < 1.5:
            logging.info("  ✅ ОТЛИЧНО: < 1.5 сек")
        elif total_time < 2.0:
            logging.info("  ✅ ПРИЕМЛЕМО: < 2 сек")
        else:
            logging.warning(f"  ⚠️ МЕДЛЕННО: Полный цикл {total_time:.3f} сек")
        
        # Enhanced logging with probe stats
        if probe_stats:
            logging.info(
                f"     ⏱️ Load {page_load_time:.3f}s | Wait {wait_time:.3f}s | Parse {parse_time:.3f}s | "
                f"Probe: {probe_stats.get('poll_count', 0)} polls, strategy: {probe_stats.get('strategy', 'unknown')}"
            )
        else:
            logging.info(f"     ⏱️ Load {page_load_time:.3f}s | Wait {wait_time:.3f}s | Parse {parse_time:.3f}s")
    
    return notice_ids, "HTML", {"total": total_time, "html": html_details}


# ============================================================================
# API MODE - Direct API calls without Selenium
# ============================================================================

def create_api_session():
    """
    Создает HTTP session с retry механизмом и exponential backoff
    
    Returns:
        requests.Session: Сконфигурированная сессия
    """
    session = requests.Session()
    
    # Настраиваем retry стратегию
    retry_strategy = Retry(
        total=3,  # Максимум 3 попытки
        backoff_factor=0.3,  # Exponential backoff: 0.3s, 0.6s, 1.2s
        status_forcelist=[429, 500, 502, 503, 504],  # Retry на эти HTTP коды
        allowed_methods=["GET"]  # Только GET запросы
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    return session


def get_notices_via_api(session, return_metadata=False):
    """
    Получение новостей через Upbit API
    
    Args:
        session: requests.Session с retry механизмом
        return_metadata: Вернуть подробные метаданные (latency, error)
    
    Returns:
        List[Dict] или Tuple[List[Dict], Dict]: Список новостей или кортеж при return_metadata=True
    """
    start_time = time.perf_counter()
    metadata = {
        "latency": None,
        "status": "unknown",
        "status_code": None,
        "error": None,
    }
    
    url = "https://api-manager.upbit.com/api/v1/announcements"
    params = {
        "os": "web",
        "page": 1,
        "per_page": 20,
        "category": "all"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    
    try:
        response = session.get(url, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        elapsed = time.perf_counter() - start_time
        metadata.update({
            "latency": elapsed,
            "status": "success" if data.get("success") else "error",
            "status_code": response.status_code,
        })
        
        if data.get("success"):
            notices = data["data"]["notices"]
            logging.debug(f"✅ API: {len(notices)} новостей за {elapsed:.3f}s")
            return (notices, metadata) if return_metadata else notices
        else:
            metadata["error"] = "success=false"
            logging.error("❌ API returned success=false")
    except requests.Timeout:
        elapsed = time.perf_counter() - start_time
        metadata.update({
            "latency": elapsed,
            "status": "error",
            "error": "timeout",
        })
        logging.error(f"⏱️ API timeout после {elapsed:.3f}s")
    except requests.ConnectionError as e:
        elapsed = time.perf_counter() - start_time
        metadata.update({
            "latency": elapsed,
            "status": "error",
            "error": f"connection_error: {e}",
        })
        logging.error(f"🔌 Connection error после {elapsed:.3f}s: {e}")
    except requests.HTTPError as e:
        elapsed = time.perf_counter() - start_time
        status_code = e.response.status_code if e.response else 'unknown'
        metadata.update({
            "latency": elapsed,
            "status": "error",
            "status_code": status_code,
            "error": f"http_{status_code}",
        })
        logging.error(f"❌ HTTP {status_code} после {elapsed:.3f}s: {e}")
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        metadata.update({
            "latency": elapsed,
            "status": "error",
            "error": f"unexpected: {e}",
        })
        logging.error(f"❌ API error после {elapsed:.3f}s: {e}")
    
    return ([], metadata) if return_metadata else []


def send_notice_with_delay(notice, session):
    """
    Отправляет уведомление с точной задержкой обнаружения
    
    Args:
        notice: Dict с данными новости из API
        session: requests.Session для отправки в Telegram
    """
    notice_id = notice["id"]
    title = notice["title"]
    category = notice.get("category", "unknown")
    
    # Парсим время публикации (ISO 8601 с timezone)
    published_at_str = notice["listed_at"]  # "2025-01-05T19:55:05+09:00"
    published_at = datetime.fromisoformat(published_at_str)
    
    # Текущее время в KST
    detected_at = datetime.now(ZoneInfo("Asia/Seoul"))
    
    # Вычисляем задержку обнаружения
    delay_seconds = max((detected_at - published_at).total_seconds(), 0.0)
    delay_ms = delay_seconds * 1000
    
    # Форматируем времена
    pub_time = published_at.strftime("%H:%M:%S")
    det_time = detected_at.strftime("%H:%M:%S")
    pub_date = published_at.strftime("%Y-%m-%d")
    
    # Логирование с эмодзи
    logging.info(f"🆕 НОВАЯ НОВОСТЬ #{notice_id}")
    logging.info(f"   📰 {title}")
    logging.info(f"   🏷️ Категория: {category}")
    logging.info(f"   🕐 Опубликовано: {pub_date} {pub_time} KST")
    logging.info(f"   🕐 Обнаружено:   {detected_at.strftime('%Y-%m-%d')} {det_time} KST")
    logging.info(f"   ⏱️ Задержка обнаружения: {delay_ms:.0f} ms ({delay_seconds:.3f}s)")
    
    # Telegram сообщение
    message = f"""🆕 <b>Новая новость Upbit!</b>

📌 <b>ID:</b> {notice_id}
🏷️ <b>Категория:</b> {category}
📰 <b>{title}</b>

🕐 Опубликовано: {pub_time}
⏱️ Обнаружено через: {delay_ms:.0f} мс ({delay_seconds:.2f} сек)

🔗 https://upbit.com/service_center/notice?id={notice_id}"""
    
    # Отправляем в Telegram
    send_to_telegram(
        session,
        TELEGRAM_TOKEN,
        TELEGRAM_CHAT_ID,
        message,
        notice_id=notice_id,
        telemetry=telegram_retry_telemetry,
        parse_mode="HTML",
    )


def process_new_notices(notices, session):
    """
    Обрабатывает список новостей и отправляет уведомления о новых
    
    Args:
        notices: List[Dict] - список новостей из API
        session: requests.Session для отправки уведомлений
    
    Returns:
        dict: Метрики обработки (новые ID, max_id, last_known_id и т.д.)
    """
    metrics = {
        "total_notices": len(notices) if notices else 0,
        "max_id": None,
        "last_known_id": None,
        "updated_last_id": None,
        "new_ids": [],
        "processed": 0,
    }
    
    last_known_id = get_last_max_id()
    metrics["last_known_id"] = last_known_id
    
    if not notices:
        metrics["updated_last_id"] = last_known_id
        return metrics
    
    current_ids = {n["id"] for n in notices}
    max_id = max(current_ids)
    metrics["max_id"] = max_id
    
    if last_known_id is None:
        save_max_id(max_id)
        metrics["updated_last_id"] = max_id
        logging.info(f"📊 Первый запуск: сохранён max_id={max_id}")
        return metrics
    
    # Находим новые новости (ID больше последнего известного)
    new_notices = [n for n in notices if n["id"] > last_known_id]
    
    if new_notices:
        new_notices.sort(key=lambda x: x["id"])
        new_ids = [notice["id"] for notice in new_notices]
        metrics["new_ids"] = new_ids
        metrics["processed"] = len(new_ids)
        
        logging.info(f"🔔 Обнаружено {len(new_notices)} новых новостей")
        logging.info(f"   🆕 Новые ID: {new_ids}")
        
        for notice in new_notices:
            send_notice_with_delay(notice, session)
            if len(new_notices) > 1:
                time.sleep(0.5)
        
        save_max_id(max_id)
        metrics["updated_last_id"] = max_id
        logging.info(f"📊 Обновлён max_id: {last_known_id} → {max_id}")
    else:
        metrics["updated_last_id"] = last_known_id
    
    return metrics


class ApiLoopTelemetry:
    """Сбор и агрегирование метрик API цикла."""

    def __init__(self, summary_interval=60):
        self.summary_interval = summary_interval
        self.last_summary_time = time.monotonic()
        self.reset()

    def reset(self):
        self.cycle_durations = []
        self.api_latencies = []
        self.error_count = 0
        self.cycle_count = 0

    @staticmethod
    def _percentile(values, percentile):
        if not values:
            return None
        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, math.ceil(percentile / 100 * len(ordered)) - 1))
        return ordered[index]

    def record_cycle(self, cycle_duration, api_latency=None, error_occurred=False):
        self.cycle_durations.append(cycle_duration)
        if api_latency is not None:
            self.api_latencies.append(api_latency)
        if error_occurred:
            self.error_count += 1
        self.cycle_count += 1

    def maybe_log_summary(self):
        now = time.monotonic()
        if now - self.last_summary_time < self.summary_interval or self.cycle_count == 0:
            return

        avg_cycle = sum(self.cycle_durations) / len(self.cycle_durations)
        p95_cycle = self._percentile(self.cycle_durations, 95)
        error_rate = self.error_count / self.cycle_count if self.cycle_count else 0
        avg_api_latency = (
            sum(self.api_latencies) / len(self.api_latencies)
            if self.api_latencies
            else None
        )

        latency_str = f"{avg_api_latency:.3f}s" if avg_api_latency is not None else "n/a"
        p95_str = f"{p95_cycle:.3f}s" if p95_cycle is not None else "n/a"

        logging.info(
            "📈 60s summary: cycles=%d, avg_cycle=%.3fs, p95_cycle=%s, api_error_rate=%.2f%%, avg_api_latency=%s",
            self.cycle_count,
            avg_cycle,
            p95_str,
            error_rate * 100,
            latency_str,
        )

        self.reset()
        self.last_summary_time = now


def main_hybrid(
    mode_selection=None,
    summary_interval=60,
):
    """Hybrid main loop with auto-fallback between API and HTML modes with aggressive polling support."""
    timezone = ZoneInfo("Asia/Seoul")
    
    # Get configuration values
    api_error_threshold, _ = get_api_error_threshold()
    api_recovery_threshold, _ = get_api_recovery_ok()
    api_sleep_range, html_refresh_range, jitter_range, api_raw, html_raw, jitter_raw = get_sleep_ranges()
    autofallback_disabled = is_autofallback_disabled()
    aggressive_mode_enabled = is_aggressive_mode_enabled()
    
    # Convert ms ranges to seconds for internal use
    api_sleep_range_sec = (api_sleep_range[0] / 1000.0, api_sleep_range[1] / 1000.0)
    html_refresh_range_sec = (html_refresh_range[0] / 1000.0, html_refresh_range[1] / 1000.0)
    jitter_range_sec = (jitter_range[0] / 1000.0, jitter_range[1] / 1000.0)
    
    # Initialize components
    initial_mode = mode_selection.mode if mode_selection else DEFAULT_MODE
    mode_manager = ModeManager(initial_mode, not autofallback_disabled)
    failure_detector = FailureDetector(api_error_threshold, api_recovery_threshold)
    rate_limit_detector = RateLimitDetector()
    telemetry = HybridTelemetry(summary_interval=summary_interval)
    
    # Set initial rate-limit mode
    if aggressive_mode_enabled and initial_mode == "api":
        rate_limit_detector._current_mode = "aggressive"
        logging.warning("⚠️ AGGRESSIVE MODE: 200ms polling — high risk of rate-limit")
    
    # Initialize resources for initial mode
    if initial_mode == "api":
        mode_manager.initialize_api_session()
    else:
        if not mode_manager.initialize_html_driver():
            logging.error("❌ Failed to initialize HTML driver, exiting")
            return
    
    # Log startup information
    logging.info("🚀 Upbit Notice Bot запущен (HYBRID MODE)")
    if mode_selection:
        resolution_trace = " → ".join(mode_selection.resolution_path)
        logging.info(f"🧭 Mode resolution: {resolution_trace}")
    
    logging.info("📡 Режим: ГИБРИДНЫЙ (API + HTML с авто-фоллбэком)")
    logging.info("   • Initial mode: %s", initial_mode.upper())
    logging.info("   • Auto-fallback: %s", "DISABLED" if autofallback_disabled else "ENABLED")
    logging.info("   • Aggressive mode: %s", "ENABLED" if aggressive_mode_enabled else "DISABLED")
    if aggressive_mode_enabled:
        logging.info("   • Rate-limit thresholds: %d/%d 429s in %ds, %d consecutive errors", 
                    AGGRESSIVE_429_THRESHOLD_LOW, AGGRESSIVE_429_THRESHOLD_HIGH, 
                    AGGRESSIVE_429_WINDOW_SECONDS, AGGRESSIVE_CONSECUTIVE_ERROR_THRESHOLD)
    logging.info("   • Timezone: Asia/Seoul")
    logging.info("   • ID tracking file: %s", LAST_NOTICE_FILE)
    logging.info("")
    
    logging.info("⚙️ API Configuration:")
    logging.info("   • Endpoint: https://api-manager.upbit.com/api/v1/announcements")
    if aggressive_mode_enabled:
        logging.info("   • Aggressive polling: %dms (fixed)", AGGRESSIVE_SLEEP_MS)
        logging.info("   • Auto-backoff: 500ms at %d 429s, 1000ms at %d 429s", 
                    AGGRESSIVE_429_THRESHOLD_LOW, AGGRESSIVE_429_THRESHOLD_HIGH)
    else:
        logging.info("   • Sleep cycle: %d-%dms + jitter %d-%dms", 
                     api_sleep_range[0], api_sleep_range[1], jitter_range[0], jitter_range[1])
    logging.info("   • Failure threshold: %d errors", api_error_threshold)
    logging.info("   • Recovery threshold: %d successes", api_recovery_threshold)
    if api_raw:
        logging.info("   • API sleep override: %sms", api_raw)
    
    logging.info("")
    logging.info("⚙️ HTML Configuration:")
    logging.info("   • Refresh cycle: %d-%dms + jitter %d-%dms",
                 html_refresh_range[0], html_refresh_range[1], jitter_range[0], jitter_range[1])
    if html_raw:
        logging.info("   • HTML refresh override: %sms", html_raw)
    
    if jitter_raw:
        logging.info("   • Jitter override: %sms", jitter_raw)
    
    logging.info("")
    logging.info('🛡️ HTTP session: retry total=3, backoff=0.3, status codes=[429, 500, 502, 503, 504]')
    logging.info("")
    
    cycle = 0
    last_detection_time = None
    
    try:
        while True:
            cycle += 1
            cycle_start = time.perf_counter()
            current_kst = datetime.now(timezone)
            timestamp_str = current_kst.strftime('%H:%M:%S.%f')[:-3]
            
            # Variables for this cycle
            notices = []
            error_occurred = False
            error_message = None
            api_latency = None
            html_latency = None
            last_known_id = None
            max_id = None
            new_ids = []
            detection_lag = None
            
            try:
                if mode_manager.current_mode == "api":
                    # API MODE with aggressive polling support
                    api_call_start = time.perf_counter()
                    notices, metadata = get_notices_via_api(mode_manager.api_session, return_metadata=True)
                    api_latency = metadata.get("latency")
                    error_message = metadata.get("error")
                    status = metadata.get("status", "unknown")
                    status_code = metadata.get("status_code")
                    
                    error_occurred = bool(error_message) or status == "error"
                    
                    # Record API call for rate-limit detection
                    mode_changed, old_mode, new_mode, reason = rate_limit_detector.record_api_call(
                        success=not error_occurred,
                        status_code=status_code,
                        error_message=error_message,
                        timestamp=time.time()
                    )
                    
                    # Process notices if successful
                    if not error_occurred and notices:
                        metrics = process_new_notices(notices, mode_manager.api_session)
                        last_known_id = metrics.get("last_known_id")
                        max_id = metrics.get("max_id")
                        new_ids = metrics.get("new_ids") or []
                        
                        # Calculate detection lag if we have new notices
                        if new_ids and last_detection_time:
                            detection_lag = (current_kst - last_detection_time).total_seconds() * 1000
                            last_detection_time = current_kst
                        elif new_ids:
                            last_detection_time = current_kst
                    
                    # Record API result for failure detection
                    should_fallback, failure_count = failure_detector.record_api_result(
                        not error_occurred, error_message, time.time()
                    )
                    
                    # Check if we should switch to HTML
                    if should_fallback:
                        reason = f"API failures: {failure_count} in {failure_detector.window_seconds}s"
                        if failure_detector.last_failure_summary:
                            reason += "\nRecent errors:\n" + "\n".join(failure_detector.last_failure_summary)
                        
                        if mode_manager.switch_to_html(reason, failure_count):
                            failure_detector.reset()  # Reset failure detector after switch
                            rate_limit_detector.reset()  # Reset rate-limit detector
                            # Continue with HTML mode in this cycle
                            mode_manager.current_mode = "html"
                        else:
                            logging.warning("⚠️ Failed to switch to HTML mode, continuing with API")
                    
                    # Check if rate-limit detector suggests HTML fallback
                    if rate_limit_detector.should_suggest_html_fallback():
                        logging.warning("⚠️ RATE-LIMIT DETECTOR suggests considering HTML mode due to persistent 429s")
                        logging.warning("   → Run with --html flag to force HTML mode if rate limiting continues")
                
                if mode_manager.current_mode == "html":
                    # HTML MODE
                    if not mode_manager.html_driver:
                        if not mode_manager.initialize_html_driver():
                            logging.error("❌ HTML driver not available, cannot continue")
                            break
                    
                    # Get notices via HTML
                    html_start = time.perf_counter()
                    all_ids, method, timings = get_all_notice_ids_with_api(
                        mode_manager.html_driver, known_endpoints=[], use_cdp=False
                    )
                    html_latency = time.perf_counter() - html_start
                    
                    if all_ids:
                        # Convert to notice-like format for processing
                        max_id = max(all_ids)
                        last_known_id = get_last_max_id()
                        
                        if last_known_id is None:
                            save_max_id(max_id)
                            last_known_id = max_id
                            logging.info(f"📊 HTML mode: First run, saved max_id={max_id}")
                        else:
                            # Find new IDs
                            new_ids = [nid for nid in all_ids if nid > last_known_id]
                            new_ids.sort()
                            
                            if new_ids:
                                logging.info(f"🔔 HTML mode: {len(new_ids)} новых новостей → ID: {new_ids}")
                                
                                # Calculate detection lag
                                if last_detection_time:
                                    detection_lag = (current_kst - last_detection_time).total_seconds() * 1000
                                last_detection_time = current_kst
                                
                                # Send notifications (simulated for HTML mode)
                                for notice_id in new_ids:
                                    message = f"""🆕 <b>Новая новость Upbit!</b>

📌 <b>ID:</b> {notice_id}
📰 <b>Обнаружено через HTML режим</b>

🕐 Обнаружено: {current_kst.strftime('%H:%M:%S')} KST

🔗 https://upbit.com/service_center/notice?id={notice_id}"""
                                    
                                    send_to_telegram(
                                        None,
                                        TELEGRAM_TOKEN,
                                        TELEGRAM_CHAT_ID,
                                        message,
                                        notice_id=notice_id,
                                        telemetry=telegram_retry_telemetry,
                                        parse_mode="HTML",
                                    )
                                
                                save_max_id(max_id)
                                last_known_id = max_id
                    
                    # In HTML mode, we simulate API success for recovery detection
                    # after some time of successful HTML operation
                    if failure_detector.get_stats()["in_failure_state"]:
                        # Simulate success to allow recovery back to API
                        failure_detector.record_api_result(True, None, time.time())
                        
                        # Check if ready to recover to API
                        if failure_detector.check_recovery_ready():
                            reason = f"API recovered after {api_recovery_threshold} successful checks"
                            if mode_manager.switch_to_api(reason):
                                failure_detector.reset()
                                rate_limit_detector.reset()
                
                # Record cycle metrics
                cycle_duration = time.perf_counter() - cycle_start
                
                # Determine sleep time based on rate-limit mode
                if mode_manager.current_mode == "api" and aggressive_mode_enabled:
                    sleep_time_ms = rate_limit_detector.get_sleep_time_ms(api_sleep_range)
                    rate_limit_mode = rate_limit_detector._current_mode
                elif mode_manager.current_mode == "api":
                    sleep_time_ms = random.randint(*api_sleep_range)
                    rate_limit_mode = "normal"
                else:
                    sleep_time_ms = random.randint(*html_refresh_range)
                    rate_limit_mode = "html"
                
                telemetry.record_cycle(
                    cycle_duration=cycle_duration,
                    mode=mode_manager.current_mode,
                    api_latency=api_latency,
                    html_latency=html_latency,
                    error_occurred=error_occurred,
                    last_known_id=last_known_id,
                    max_id=max_id,
                    sleep_time_ms=sleep_time_ms,
                    rate_limit_mode=rate_limit_mode,
                    detection_lag=detection_lag
                )
                
                # Log cycle information with enhanced metrics
                latency_str = f"{api_latency:.3f}s" if api_latency is not None else "n/a"
                html_latency_str = f"{html_latency:.3f}s" if html_latency is not None else "n/a"
                total_notices = len(notices) if notices else (len(new_ids) if new_ids else 0)
                new_ids_display = new_ids if new_ids else "-"
                
                # Enhanced logging for aggressive mode
                if aggressive_mode_enabled and mode_manager.current_mode == "api":
                    rl_stats = rate_limit_detector.get_stats()
                    logging.info(
                        "🔄 Cycle #%d | ts_kst=%s | mode=%s | rl_mode=%s | status=%s | cycle=%.3fs | api=%s | sleep=%dms | notices=%d | max_id=%s | new_ids=%s | 429s_60s=%d",
                        cycle,
                        timestamp_str,
                        mode_manager.current_mode.upper(),
                        rl_stats["current_mode"].upper(),
                        "error" if error_occurred else "ok",
                        cycle_duration,
                        latency_str,
                        sleep_time_ms,
                        total_notices,
                        max_id if max_id is not None else "-",
                        last_known_id if last_known_id is not None else "-",
                        new_ids_display,
                        rl_stats["recent_429s_60s"]
                    )
                else:
                    logging.info(
                        "🔄 Cycle #%d | ts_kst=%s | mode=%s | status=%s | cycle=%.3fs | api=%s | html=%s | notices=%d | max_id=%s | last_known=%s | new_ids=%s",
                        cycle,
                        timestamp_str,
                        mode_manager.current_mode.upper(),
                        "error" if error_occurred else "ok",
                        cycle_duration,
                        latency_str,
                        html_latency_str,
                        total_notices,
                        max_id if max_id is not None else "-",
                        last_known_id if last_known_id is not None else "-",
                        new_ids_display,
                    )
                
                # Log telemetry summaries
                telemetry.maybe_log_summary(mode_manager, failure_detector, rate_limit_detector)
                if aggressive_mode_enabled:
                    telemetry.maybe_log_10s_summary(rate_limit_detector)
                
                # Sleep with appropriate timing
                sleep_time_sec = sleep_time_ms / 1000.0
                
                if aggressive_mode_enabled and mode_manager.current_mode == "api":
                    # In aggressive mode, minimal jitter for consistency
                    jitter = random.uniform(0, 10) / 1000.0  # 0-10ms jitter
                else:
                    jitter = random.uniform(*jitter_range_sec)
                
                final_sleep_time = max(0.0, sleep_time_sec + jitter)
                
                logging.debug(
                    "💤 Сон %.0fms (base %.0fms + jitter %.0fms)",
                    final_sleep_time * 1000,
                    sleep_time_ms,
                    jitter * 1000,
                )
                time.sleep(final_sleep_time)
                
            except Exception as cycle_error:
                logging.error("❌ Неожиданная ошибка в цикле #%d: %s", cycle, cycle_error)
                logging.debug("Traceback:", exc_info=True)
                
                # Record error in telemetry
                cycle_duration = time.perf_counter() - cycle_start
                telemetry.record_cycle(
                    cycle_duration=cycle_duration,
                    mode=mode_manager.current_mode,
                    error_occurred=True
                )
                
                telemetry.maybe_log_summary(mode_manager, failure_detector, rate_limit_detector)
                time.sleep(1)
    
    except KeyboardInterrupt:
        logging.info("⏹️ Остановка (Ctrl+C)")
    finally:
        # Cleanup resources
        mode_manager.cleanup()
        logging.info("✅ Все ресурсы очищены")


def main():
    logging.info("🚀 Upbit Notice Bot запущен")
    logging.info("")
    
    # CDP API отключён - используем только HTML парсинг
    known_endpoints = []
    use_cdp = False  # CDP API временно отключён
    
    logging.info("📡 Режим: ОПТИМИЗИРОВАННЫЙ HTML ПАРСИНГ")
    logging.info("  ✓ CDP API отключён (временно)")
    logging.info("  ✓ Прямой HTML парсинг")
    logging.info("  🎯 ЦЕЛЕВАЯ СКОРОСТЬ: < 1.5 секунды")
    logging.info("")
    logging.info("🔄 Интервал проверки: 1-2 секунды")
    logging.info("")
    logging.info("⚡ ОПТИМИЗАЦИИ:")
    logging.info("  ✓ Selenium headless Chrome с STEALTH")
    logging.info("  ✓ Отключены изображения, CSS, media")
    logging.info("  ✓ page_load_strategy='eager'")
    logging.info("  ✓ Lightweight readiness probe (document state + visibility)")
    logging.info("  ✓ Быстрая проверка сразу после refresh")
    logging.info("  ✓ Умное ожидание (polling 20ms, max 0.3s)")
    logging.info("  ✓ Consecutive stable samples tracking")
    logging.info("  ✓ Быстрый HTML парсинг")
    logging.info("  ✓ Автодиагностика при ошибках")
    logging.info("  ✓ Детальные метрики на каждом этапе")
    logging.info("")
    
    # Инициализация драйвера без CDP (только HTML парсинг)
    driver = init_driver(enable_cdp=use_cdp)
    if not driver:
        logging.error("❌ Не удалось запустить браузер")
        return
    
    # CDP discovery отключён (use_cdp=False)
    # Код оставлен для будущего использования
    if use_cdp and not known_endpoints:
        logging.info("🔍 Запускаем автоматическое обнаружение API endpoints...")
        try:
            discover_api_endpoints(driver, save_to_file=True)
            known_endpoints = load_known_endpoints()
            if known_endpoints:
                logging.info(f"📡 Обнаружено и загружено {len(known_endpoints)} endpoints")
            else:
                logging.warning("⚠️ API endpoints не обнаружены, используем HTML fallback")
        except Exception as discovery_error:
            logging.warning(f"⚠️ Ошибка обнаружения API: {discovery_error}")
    
    # Переменная для отслеживания 429 ошибок
    rate_limit_backoff = 0  # Дополнительная задержка при 429
    last_429_time = None
    
    try:
        # Первая загрузка с подробным логированием времени
        logging.info("📡 Подключаемся к Upbit...")
        
        cycle_start = time.time()
        
        # Используем HTML парсинг (CDP отключён)
        all_ids, method, timings = get_all_notice_ids_with_api(driver, known_endpoints=known_endpoints, use_cdp=use_cdp)
        
        # Итоговое время всего цикла
        total_cycle_time = time.time() - cycle_start
        
        logging.info(f"⏱️ ━━━ ИТОГО ЦИКЛ: {total_cycle_time:.3f}s ━━━")
        logging.info(f"   Strategy: {method}")
        
        # Оценка общей производительности (HTML режим)
        if total_cycle_time < 1.0:
            logging.info("✅ ⚡ ОТЛИЧНО: Полный цикл < 1 сек!")
        elif total_cycle_time < 1.5:
            logging.info("✅ ХОРОШО: Полный цикл < 1.5 сек")
        elif total_cycle_time < 2.0:
            logging.info("✅ ПРИЕМЛЕМО: Полный цикл < 2 сек")
        else:
            logging.warning(f"⚠️ МЕДЛЕННО: Полный цикл {total_cycle_time:.3f} сек")
        
        # Показываем детальные метрики HTML парсинга
        if method == "HTML" and isinstance(timings, dict):
            html_info = timings.get("html", {})
            if html_info:
                logging.info(
                    "     ⏱️ Load {0:.3f}s | Wait {1:.3f}s | Parse {2:.3f}s".format(
                        html_info.get("page_load", 0.0),
                        html_info.get("wait", 0.0),
                        html_info.get("parse", 0.0)
                    )
                )
        
        if not all_ids:
            logging.error("❌ Не удалось получить ID новостей")
            return
        
        # Находим максимальный ID на странице
        page_max_id = max(all_ids)
        logging.info(f"🔢 Максимальный ID на странице: {page_max_id}")
        
        # Читаем последний известный max_id
        last_known_max_id = get_last_max_id()
        tracked_max_id = last_known_max_id if last_known_max_id is not None else page_max_id
        
        if last_known_max_id is None:
            # ПЕРВЫЙ ЗАПУСК - отправляем уведомление о текущей максимальной новости
            logging.info("🆕 ПЕРВЫЙ ЗАПУСК - инициализация")
            
            # Время обнаружения
            detection_start = datetime.now()
            
            # Начало обработки
            processing_start = datetime.now()
            
            notice = get_notice_by_id(driver, page_max_id)
            
            # Завершение обработки
            processing_completed = datetime.now()
            
            if not notice:
                logging.error(f"❌ Не удалось получить данные новости ID {page_max_id}")
                return
            
            logging.info(f"🔔 ПЕРВЫЙ ЗАПУСК - текущая новость (ID {page_max_id}): {notice['title']}")
            logging.info(f"🔗 Ссылка: {notice['link']}")
            
            telegram_sent = send_telegram_notification(
                notice["title"],
                notice["link"],
                detection_time=detection_start,
                processing_completed_time=processing_completed
            )
            
            # Логируем метрики
            try:
                metrics_logger.log_article_metrics(
                    notice_id=page_max_id,
                    title=notice['title'],
                    source="Upbit Notice",
                    detected_at=detection_start,
                    processing_started=processing_start,
                    processing_completed=processing_completed,
                    telegram_sent=telegram_sent
                )
            except Exception as e:
                logging.error(f"❌ Ошибка записи метрик: {e}")
            
            bot_latency = (telegram_sent - detection_start).total_seconds()
            
            logging.info(f"⏱️ Обнаружено: {detection_start.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
            logging.info(f"📤 Отправлено: {telegram_sent.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
            logging.info(f"⚡ Задержка бота: {bot_latency:.3f} сек")
            
            save_max_id(page_max_id)
            tracked_max_id = page_max_id
            logging.info("✅ Начинаем мониторинг...")
        
        elif page_max_id > last_known_max_id:
            # ЕСТЬ НОВЫЕ НОВОСТИ - отправляем все, которых не было
            logging.info(f"🆕 ОБНАРУЖЕНЫ НОВЫЕ НОВОСТИ!")
            logging.info(f"📊 Последний известный ID: {last_known_max_id}")
            logging.info(f"📊 Максимальный ID сейчас: {page_max_id}")
            
            # Находим все новые ID
            new_ids = [nid for nid in all_ids if nid > last_known_max_id]
            new_ids.sort()  # От меньшего к большему
            
            logging.info(f"🔔 Новых новостей: {len(new_ids)} → ID: {new_ids}")
            
            # Отправляем уведомления для каждой новой новости
            notify_about_new_ids(driver, new_ids, pause_between=0.5)
            
            # Обновляем max_id
            save_max_id(page_max_id)
            logging.info("✅ Начинаем мониторинг...")
            tracked_max_id = page_max_id
        
        else:
            # НЕТ НОВЫХ НОВОСТЕЙ
            logging.info(f"📊 Последний известный ID: {last_known_max_id}")
            logging.info(f"📊 Максимальный ID сейчас: {page_max_id}")
            logging.info("✅ Новых новостей нет. Начинаем мониторинг...")
            tracked_max_id = max(page_max_id, last_known_max_id)
        
        # Цикл мониторинга с частым refresh
        current_max_id = tracked_max_id
        refresh_count = 0
        
        logging.info("🔄 Начинаем polling с refresh каждые 1-2 секунды...")
        
        while True:
            try:
                # Вычисляем интервал для следующего refresh
                base_interval = get_refresh_interval()  # 1-2 секунды
                human_delay = get_random_delay()  # 0.5-1.5 секунды
                
                # Добавляем backoff если была 429 ошибка
                total_delay = base_interval + human_delay + rate_limit_backoff
                
                logging.debug(f"💤 Ожидание {total_delay:.2f}с (base: {base_interval:.2f}s, random: {human_delay:.2f}s, backoff: {rate_limit_backoff:.2f}s)")
                time.sleep(total_delay)
                
                # Время начала refresh
                refresh_start_time = datetime.now()
                refresh_count += 1
                
                logging.info(f"🔄 Refresh #{refresh_count} в {refresh_start_time.strftime('%H:%M:%S')}...")
                
                try:
                    # Время начала всего цикла refresh
                    cycle_start = time.time()
                    
                    all_ids, method, timings = get_all_notice_ids_with_api(driver, known_endpoints=known_endpoints, use_cdp=use_cdp)
                    total_cycle_time = time.time() - cycle_start
                    
                    logging.info(f"  ⏱️ ━━━ ИТОГО ЦИКЛ: {total_cycle_time:.3f}s ━━━")
                    logging.info(f"     Strategy: {method}")
                    
                    # HTML режим - показываем детальные метрики
                    if method == "HTML":
                        html_info = timings.get("html", {}) if isinstance(timings, dict) else {}
                        logging.info(
                            "     ⏱️ Load {0:.3f}s | Wait {1:.3f}s | Parse {2:.3f}s".format(
                                html_info.get("page_load", 0.0),
                                html_info.get("wait", 0.0),
                                html_info.get("parse", 0.0)
                            )
                        )
                        # Оценка производительности
                        if total_cycle_time < 1.0:
                            logging.info("  ⚡ ОТЛИЧНО: < 1 сек!")
                        elif total_cycle_time < 1.5:
                            logging.info("  ✅ ХОРОШО: < 1.5 сек")
                        elif total_cycle_time < 2.0:
                            logging.info("  ✅ ПРИЕМЛЕМО: < 2 сек")
                        else:
                            logging.warning(f"  ⚠️ МЕДЛЕННО: {total_cycle_time:.3f} сек")
                    else:
                        logging.error(f"  ❌ {method} MODE: Получено за {total_cycle_time:.3f}s")
                    
                    # Сбрасываем backoff если цикл успешен
                    if rate_limit_backoff > 0:
                        logging.info("✅ Цикл успешен, сбрасываем backoff")
                        rate_limit_backoff = 0
                        last_429_time = None
                    
                except TimeoutException:
                    logging.warning("⚠️ Timeout при загрузке, пропускаем цикл")
                    continue
                
                # Получаем время после загрузки - момент обнаружения новостей
                detection_time = datetime.now()
                
                if not all_ids:
                    logging.warning("⚠️ Не удалось получить ID после refresh")
                    continue
                
                # Находим максимальный ID
                page_max_id = max(all_ids)
                
                # Проверяем есть ли новые новости
                if page_max_id > current_max_id:
                    logging.info(f"🆕 ОБНАРУЖЕНЫ НОВЫЕ НОВОСТИ!")
                    logging.info(f"📊 Было max_id: {current_max_id}")
                    logging.info(f"📊 Стало max_id: {page_max_id}")
                    
                    # Находим все новые ID
                    new_ids = [nid for nid in all_ids if nid > current_max_id]
                    new_ids.sort()
                    
                    logging.info(f"🔔 Новых новостей: {len(new_ids)} → ID: {new_ids}")
                    
                    # Отправляем уведомления
                    notify_about_new_ids(driver, new_ids, detection_start=detection_time, pause_between=0.5)
                    
                    # Обновляем текущий max_id
                    current_max_id = page_max_id
                    save_max_id(current_max_id)
                    
                    logging.info("👀 Продолжаем мониторинг...")
                else:
                    logging.debug(f"✓ Проверка #{refresh_count}: новостей нет (max_id: {page_max_id})")
                
            except WebDriverException as e:
                error_msg = str(e).lower()
                
                # Проверяем на 429 ошибку
                if '429' in error_msg or 'rate limit' in error_msg or 'too many requests' in error_msg:
                    rate_limit_backoff = random.uniform(10, 30)
                    last_429_time = datetime.now()
                    logging.error(f"❌ Обнаружена 429 ошибка! Увеличиваем задержку на {rate_limit_backoff:.1f}с")
                    continue
                
                # Проверяем на session error
                if 'session' in error_msg or 'disconnected' in error_msg:
                    logging.error(f"❌ Ошибка сессии браузера: {e}")
                    logging.warning("⚠️ Переинициализация браузера...")
                    
                    try:
                        driver.quit()
                    except:
                        pass
                    
                    driver = init_driver(enable_cdp=use_cdp)
                    if not driver:
                        logging.error("❌ Не удалось переинициализировать браузер, останавливаемся")
                        break
                    
                    # Получаем актуальный max_id с новым драйвером
                    reloaded_ids, method, timings = get_all_notice_ids_with_api(driver, known_endpoints=known_endpoints, use_cdp=use_cdp)
                    if reloaded_ids:
                        all_ids = reloaded_ids
                        page_max_id = max(all_ids)
                        if page_max_id > current_max_id:
                            logging.info("🆕 После переинициализации: обнаружены новые ID!")
                            new_ids = [nid for nid in all_ids if nid > current_max_id]
                            new_ids.sort()
                            detection_start = datetime.now()
                            notify_about_new_ids(driver, new_ids, detection_start=detection_start, pause_between=0.5)
                            current_max_id = page_max_id
                            save_max_id(current_max_id)
                        else:
                            current_max_id = max(current_max_id, page_max_id)
                    
                    logging.info("✅ Браузер переинициализирован, продолжаем мониторинг...")
                    continue
                
                # Другие ошибки
                logging.error(f"❌ WebDriver ошибка: {e}")
                time.sleep(5)
                
            except Exception as exc:
                logging.error(f"❌ Неожиданная ошибка: {type(exc).__name__}: {exc}")
                time.sleep(5)
                
    except KeyboardInterrupt:
        logging.info("⏹️ Остановка (Ctrl+C)")
    finally:
        if driver:
            driver.quit()
            logging.info("✅ Браузер закрыт")


if __name__ == "__main__":
    args = parse_cli_args()

    try:
        mode_selection = resolve_mode(args)
    except ValueError as exc:
        logging.error("❌ %s", exc)
        raise SystemExit(1) from exc

    resolution_chain = " → ".join(mode_selection.resolution_path)
    logging.info("🧭 Mode resolution chain: %s", resolution_chain)
    logging.info("🎯 Selected mode: %s", mode_selection.mode.upper())
    logging.info("   CLI flag: %s", mode_selection.cli_source or "none")

    env_raw_value = os.getenv(ENV_MODE_VAR)
    if mode_selection.env_source:
        logging.info("   Env override: %s=%s", ENV_MODE_VAR, mode_selection.env_source)
    elif env_raw_value:
        logging.warning(
            "⚠️ Ignoring invalid %s=%s (allowed: %s)",
            ENV_MODE_VAR,
            env_raw_value,
            ", ".join(sorted(VALID_MODES)),
        )
    else:
        logging.info("   Env override: %s=not set", ENV_MODE_VAR)

    logging.info("   Default fallback: %s", DEFAULT_MODE)

    # Get all configuration values
    api_error_threshold, raw_threshold = get_api_error_threshold()
    api_recovery_threshold, raw_recovery = get_api_recovery_ok()
    api_sleep_range, html_refresh_range, jitter_range, api_raw, html_raw, jitter_raw = get_sleep_ranges()
    autofallback_disabled = is_autofallback_disabled()
    aggressive_mode_enabled = is_aggressive_mode_enabled()
    
    # Log API error threshold
    if raw_threshold is not None:
        try:
            parsed_raw = int(raw_threshold)
        except ValueError:
            parsed_raw = None
        if parsed_raw is None or parsed_raw < 1:
            logging.warning(
                "⚠️ Invalid %s=%s. Using default value %d.",
                API_ERROR_THRESHOLD_ENV,
                raw_threshold,
                DEFAULT_API_ERROR_THRESHOLD,
            )
            api_error_threshold = DEFAULT_API_ERROR_THRESHOLD
        else:
            logging.info(
                "   API error warning threshold: %d (from %s)",
                api_error_threshold,
                API_ERROR_THRESHOLD_ENV,
            )
    else:
        logging.info(
            "   API error warning threshold: %d (default)",
            api_error_threshold,
        )
    
    # Log API recovery threshold
    if raw_recovery is not None:
        try:
            parsed_recovery = int(raw_recovery)
        except ValueError:
            parsed_recovery = None
        if parsed_recovery is None or parsed_recovery < 1:
            logging.warning(
                "⚠️ Invalid %s=%s. Using default value %d.",
                API_RECOVERY_OK_ENV,
                raw_recovery,
                DEFAULT_API_RECOVERY_OK,
            )
            api_recovery_threshold = DEFAULT_API_RECOVERY_OK
        else:
            logging.info(
                "   API recovery threshold: %d (from %s)",
                api_recovery_threshold,
                API_RECOVERY_OK_ENV,
            )
    else:
        logging.info(
            "   API recovery threshold: %d (default)",
            api_recovery_threshold,
        )
    
    # Log sleep ranges
    logging.info("   API sleep range: %d-%dms %s", 
                 api_sleep_range[0], api_sleep_range[1], 
                 f"(override: {api_raw})" if api_raw else "(default)")
    logging.info("   HTML refresh range: %d-%dms %s", 
                 html_refresh_range[0], html_refresh_range[1],
                 f"(override: {html_raw})" if html_raw else "(default)")
    logging.info("   Jitter range: %d-%dms %s",
                 jitter_range[0], jitter_range[1],
                 f"(override: {jitter_raw})" if jitter_raw else "(default)")
    
    # Log aggressive mode status
    if aggressive_mode_enabled:
        logging.info("   Aggressive mode: ENABLED (%s=true)", AGGRESSIVE_MODE_ENV)
        logging.warning("⚠️ AGGRESSIVE MODE: 200ms polling — high risk of rate-limit")
        logging.info("   • Auto-backoff: 500ms at %d 429s, 1000ms at %d 429s", 
                    AGGRESSIVE_429_THRESHOLD_LOW, AGGRESSIVE_429_THRESHOLD_HIGH)
        logging.info("   • Recovery: Resume aggressive after %ds of no 429s", AGGRESSIVE_RECOVERY_CLEAR_SECONDS)
    else:
        logging.info("   Aggressive mode: DISABLED (%s not set or false)", AGGRESSIVE_MODE_ENV)
    
    # Log auto-fallback status
    if autofallback_disabled:
        logging.info("   Auto-fallback: DISABLED (via --no-autofallback or %s)", NO_AUTOFALLBACK_ENV)
    else:
        logging.info("   Auto-fallback: ENABLED")

    # Use hybrid mode for all cases except forced HTML mode
    if mode_selection.mode == "html" and getattr(args, 'html', False) or getattr(args, 'legacy', False):
        # Forced HTML mode - use legacy main function
        logging.info("📡 Режим: legacy HTML (forced via CLI)")
        logging.info("   Для гибридного режима запустите без флагов или используйте --api")
        main()
    else:
        # Use hybrid mode with auto-fallback
        main_hybrid(
            mode_selection=mode_selection,
            summary_interval=SUMMARY_INTERVAL_SECONDS,
        )
