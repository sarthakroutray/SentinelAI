"""Statistical anomaly scoring engine.

Score range: 0.0 – 1.0

Uses per-IP rate, error-ratio deviation, and spike detection
against rolling baselines via profile_store.
"""

from __future__ import annotations

from app.config import settings
from app.services.profile_store import profile_store


def score(
    log_level: str,
    ip_address: str | None,
) -> float:
    """Return a statistical anomaly score in [0.0, 1.0].

    Components:
        1. IP request-rate ratio vs threshold  (max 0.40)
        2. IP error-ratio deviation from global baseline  (max 0.35)
        3. Global spike factor  (max 0.25)
    """
    is_error = log_level.upper() in ("ERROR", "CRITICAL", "FATAL")
    stats = profile_store.record(ip_address, is_error)

    # 1) IP rate component – how close to / exceeding threshold
    ip_rate = stats["ip_rate"]
    threshold = settings.IP_RATE_THRESHOLD
    rate_ratio = min(ip_rate / max(threshold, 1), 2.0)  # cap at 2×
    ip_rate_score = (rate_ratio / 2.0) * 0.40  # max 0.40

    # 2) IP error-ratio deviation
    ip_err = stats["ip_error_ratio"]
    global_err = stats["global_error_ratio"]
    err_deviation = max(ip_err - global_err, 0.0)
    err_score = min(err_deviation, 1.0) * 0.35  # max 0.35

    # 3) Global spike – if global rate > 3× threshold, something is happening
    global_rate = stats["global_rate"]
    spike_ratio = min(global_rate / max(threshold * 3, 1), 2.0)
    spike_score = (spike_ratio / 2.0) * 0.25  # max 0.25

    total = ip_rate_score + err_score + spike_score
    return round(min(total, 1.0), 4)


def extract_features(
    log_level: str,
    message: str,
    ip_address: str | None,
) -> list[float]:
    """Build a numeric feature vector for the IsolationForest.

    Features:
        [0] log_level_numeric  (0=DEBUG,1=INFO,2=WARNING,3=ERROR,4=CRITICAL)
        [1] message_length
        [2] has_ip  (0 or 1)
        [3] keyword_hit_count  (failed login, unauthorized, error, etc.)
    """
    level_map = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "WARN": 2, "ERROR": 3, "CRITICAL": 4, "FATAL": 4}
    level_num = float(level_map.get(log_level.upper(), 1))

    msg_lower = message.lower()
    keywords = ("failed login", "unauthorized", "error", "denied", "timeout", "attack")
    keyword_hits = float(sum(1 for kw in keywords if kw in msg_lower))

    return [
        level_num,
        float(min(len(message), 1000)),  # cap length
        float(1 if ip_address else 0),
        keyword_hits,
    ]
