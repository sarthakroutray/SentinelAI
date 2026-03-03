"""Weighted risk scoring engine.

Combines statistical + isolation scores into a final risk assessment.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings


@dataclass(frozen=True, slots=True)
class ScoreResult:
    risk_score: float
    breakdown: dict[str, float]
    anomaly_type: str
    severity: str


def compute(
    statistical_score: float,
    isolation_score: float,
    rule_triggered: bool,
) -> ScoreResult:
    """Compute final risk score and determine severity.

    risk_score = (rule * RULE_WEIGHT) + (statistical * STAT_WEIGHT) + (isolation * ISO_WEIGHT)
    Rule-triggered alerts are enforced to at least MEDIUM severity.
    """
    rule_score = 1.0 if rule_triggered else 0.0
    weighted_score = (
        settings.RULE_WEIGHT * rule_score
        + settings.STAT_WEIGHT * statistical_score
        + settings.ISO_WEIGHT * isolation_score
    )
    risk_score = min(1.0, max(0.0, round(weighted_score, 4)))

    # Determine severity from thresholds
    if risk_score >= settings.ANOMALY_THRESHOLD_HIGH:
        severity = "HIGH"
    elif risk_score >= settings.ANOMALY_THRESHOLD_MEDIUM:
        severity = "MEDIUM"
    elif risk_score >= settings.ANOMALY_THRESHOLD_LOW:
        severity = "LOW"
    else:
        severity = "NONE"

    # If rule engine fired, enforce at least MEDIUM
    if rule_triggered and severity in ("NONE", "LOW"):
        severity = "MEDIUM"
        risk_score = max(risk_score, settings.ANOMALY_THRESHOLD_MEDIUM)

    # Determine anomaly type label
    anomaly_type = _classify(statistical_score, isolation_score, rule_triggered)

    return ScoreResult(
        risk_score=risk_score,
        breakdown={
            "rule": rule_score,
            "statistical": statistical_score,
            "isolation": isolation_score,
        },
        anomaly_type=anomaly_type,
        severity=severity,
    )


def _classify(stat: float, iso: float, rule_hit: bool) -> str:
    parts: list[str] = []
    if rule_hit:
        parts.append("rule_match")
    if stat >= 0.15:
        parts.append("statistical_anomaly")
    if iso >= 0.15:
        parts.append("isolation_anomaly")
    return "+".join(parts) if parts else "normal"
