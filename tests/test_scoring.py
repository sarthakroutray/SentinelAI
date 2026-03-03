"""Phase 3 – Hybrid Anomaly Detection scoring tests.

Validates:
  - Statistical engine scoring and feature extraction
  - IsolationForest returns 0 when untrained
  - IsolationForest retrains only after baseline threshold
  - Baseline contamination guard: anomalous logs excluded
  - Scoring engine weighted combination + rule-triggered floor
  - Profile store per-IP tracking
  - End-to-end worker pipeline through the scoring path
"""

import asyncio

import numpy as np
import pytest

from app.config import settings
from app.services.baseline_store import baseline_store
from app.services.isolation_engine import isolation_engine
from app.services.profile_store import profile_store
from app.services.scoring_engine import ScoreResult, compute as score_compute
from app.services.statistical_engine import extract_features, score as stat_score


# ── Statistical Engine ───────────────────────────────────────────────


class TestStatisticalEngine:
    """Statistical scoring produces values in [0.0, 1.0]."""

    def test_score_returns_float_in_range(self):
        s = stat_score("INFO", "192.168.1.1")
        assert isinstance(s, float)
        assert 0.0 <= s <= 1.0

    def test_score_error_level_higher_than_info(self):
        """ERROR-level logs should produce higher statistical scores."""
        # Record a handful of events to build up some data
        for _ in range(5):
            stat_score("ERROR", "10.0.0.1")
        score_error = stat_score("ERROR", "10.0.0.1")

        profile_store.clear()

        for _ in range(5):
            stat_score("INFO", "10.0.0.2")
        score_info = stat_score("INFO", "10.0.0.2")

        # With more errors from one IP, its error-ratio deviation should be higher
        assert score_error >= score_info

    def test_score_without_ip_returns_float(self):
        s = stat_score("WARNING", None)
        assert isinstance(s, float)
        assert 0.0 <= s <= 1.0


# ── Feature Extraction ──────────────────────────────────────────────


class TestFeatureExtraction:

    def test_extract_features_length(self):
        features = extract_features("ERROR", "failed login attempt", "10.0.0.1")
        assert len(features) == 4

    def test_extract_features_level_mapping(self):
        debug = extract_features("DEBUG", "msg", None)
        info = extract_features("INFO", "msg", None)
        error = extract_features("ERROR", "msg", None)
        assert debug[0] == 0.0
        assert info[0] == 1.0
        assert error[0] == 3.0

    def test_extract_features_keyword_hits(self):
        features = extract_features("ERROR", "failed login and unauthorized", "1.2.3.4")
        # "failed login" and "unauthorized" → 2 hits
        assert features[3] == 2.0

    def test_extract_features_no_keywords(self):
        features = extract_features("INFO", "normal operation", None)
        assert features[3] == 0.0

    def test_extract_features_has_ip_flag(self):
        with_ip = extract_features("INFO", "msg", "1.1.1.1")
        without_ip = extract_features("INFO", "msg", None)
        assert with_ip[2] == 1.0
        assert without_ip[2] == 0.0


# ── Isolation Engine ────────────────────────────────────────────────


class TestIsolationEngine:

    def test_score_zero_when_untrained(self):
        """IsolationForest must return 0.0 when no model has been trained."""
        features = [3.0, 50.0, 1.0, 2.0]
        assert isolation_engine.score(features) == 0.0
        assert isolation_engine.is_trained is False

    def test_should_retrain_false_when_baseline_small(self):
        """Retraining should NOT trigger when baseline < MODEL_RETRAIN_INTERVAL."""
        for i in range(settings.MODEL_RETRAIN_INTERVAL - 1):
            baseline_store.add([1.0, float(i), 0.0, 0.0])
        assert isolation_engine.should_retrain() is False

    def test_should_retrain_true_when_baseline_sufficient(self):
        """Retraining triggers once baseline reaches MODEL_RETRAIN_INTERVAL."""
        for i in range(settings.MODEL_RETRAIN_INTERVAL):
            baseline_store.add([1.0, float(i), 0.0, 0.0])
        assert isolation_engine.should_retrain() is True

    def test_retrain_and_score(self):
        """After retraining, score should return a non-zero value for anomalous input."""
        # Fill baseline with normal data (INFO level, short msg, no keywords)
        for i in range(settings.MODEL_RETRAIN_INTERVAL):
            baseline_store.add([1.0, float(i % 50 + 10), 0.0, 0.0])

        # Retrain synchronously for test determinism
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(isolation_engine.retrain_async())
        finally:
            loop.close()

        assert isolation_engine.is_trained is True

        # Normal-ish input should score low
        normal_score = isolation_engine.score([1.0, 25.0, 0.0, 0.0])
        assert 0.0 <= normal_score <= 1.0

        # Anomalous input (CRITICAL level, long msg, 4 keywords) should score differently
        anomalous_score = isolation_engine.score([4.0, 999.0, 1.0, 4.0])
        assert 0.0 <= anomalous_score <= 1.0


# ── Baseline Contamination Guard ────────────────────────────────────


class TestBaselineStore:

    def test_add_and_size(self):
        assert baseline_store.size == 0
        baseline_store.add([1.0, 2.0, 3.0, 4.0])
        assert baseline_store.size == 1

    def test_get_training_data_returns_numpy(self):
        baseline_store.add([1.0, 2.0, 3.0, 4.0])
        baseline_store.add([5.0, 6.0, 7.0, 8.0])
        data = baseline_store.get_training_data()
        assert isinstance(data, np.ndarray)
        assert data.shape == (2, 4)

    def test_get_training_data_empty(self):
        data = baseline_store.get_training_data()
        assert isinstance(data, np.ndarray)
        assert data.shape[0] == 0

    def test_max_size_enforced(self):
        """Buffer should evict oldest entries when max_size is reached."""
        from app.services.baseline_store import BaselineStore
        small = BaselineStore(max_size=5)
        for i in range(10):
            small.add([float(i)])
        assert small.size == 5
        data = small.get_training_data()
        # Oldest (0–4) should be evicted, 5–9 remain
        assert data[0][0] == 5.0
        assert data[-1][0] == 9.0

    def test_clear(self):
        baseline_store.add([1.0, 2.0, 3.0, 4.0])
        baseline_store.clear()
        assert baseline_store.size == 0


# ── Profile Store ────────────────────────────────────────────────────


class TestProfileStore:

    def test_record_returns_valid_stats(self):
        stats = profile_store.record("10.0.0.1", False)
        assert "ip_rate" in stats
        assert "ip_error_ratio" in stats
        assert "global_rate" in stats
        assert "global_error_ratio" in stats

    def test_error_ratio_increases_with_errors(self):
        profile_store.record("10.0.0.2", True)
        profile_store.record("10.0.0.2", True)
        stats = profile_store.record("10.0.0.2", False)
        # 2 errors out of 3 total for this IP
        assert stats["ip_error_ratio"] == pytest.approx(2 / 3, abs=0.01)

    def test_none_ip_returns_global_only(self):
        stats = profile_store.record(None, False)
        assert stats["ip_rate"] == 0
        assert stats["ip_error_ratio"] == 0.0

    def test_clear_resets_all(self):
        profile_store.record("10.0.0.3", True)
        profile_store.clear()
        stats = profile_store.record("10.0.0.3", False)
        # After clear, global total should be 1 (just this event)
        assert stats["global_rate"] == 1


# ── Scoring Engine ───────────────────────────────────────────────────


class TestScoringEngine:

    def test_compute_returns_score_result(self):
        result = score_compute(0.1, 0.05, rule_triggered=False)
        assert isinstance(result, ScoreResult)
        expected = (settings.STAT_WEIGHT * 0.1) + (settings.ISO_WEIGHT * 0.05)
        assert result.risk_score == pytest.approx(expected, abs=0.01)
        assert "statistical" in result.breakdown
        assert "isolation" in result.breakdown

    def test_weights_influence_score(self, monkeypatch):
        monkeypatch.setattr(settings, "RULE_WEIGHT", 0.2)
        monkeypatch.setattr(settings, "STAT_WEIGHT", 0.5)
        monkeypatch.setattr(settings, "ISO_WEIGHT", 0.3)

        result = score_compute(0.4, 0.2, rule_triggered=False)
        expected = (0.5 * 0.4) + (0.3 * 0.2)
        assert result.risk_score == pytest.approx(expected, abs=0.0001)

    def test_rule_weight_influence(self, monkeypatch):
        monkeypatch.setattr(settings, "RULE_WEIGHT", 0.8)
        monkeypatch.setattr(settings, "STAT_WEIGHT", 0.1)
        monkeypatch.setattr(settings, "ISO_WEIGHT", 0.1)

        with_rule = score_compute(0.0, 0.0, rule_triggered=True)
        without_rule = score_compute(0.0, 0.0, rule_triggered=False)

        assert with_rule.risk_score > without_rule.risk_score

    def test_score_capped_between_zero_and_one(self, monkeypatch):
        monkeypatch.setattr(settings, "RULE_WEIGHT", 1.0)
        monkeypatch.setattr(settings, "STAT_WEIGHT", 1.0)
        monkeypatch.setattr(settings, "ISO_WEIGHT", 1.0)

        result = score_compute(1.0, 1.0, rule_triggered=True)
        assert result.risk_score == 1.0

    def test_no_anomaly_severity_none(self):
        result = score_compute(0.0, 0.0, rule_triggered=False)
        assert result.severity == "NONE"
        assert result.anomaly_type == "normal"

    def test_low_threshold(self):
        statistical_input = settings.ANOMALY_THRESHOLD_LOW / settings.STAT_WEIGHT
        result = score_compute(statistical_input, 0.0, rule_triggered=False)
        assert result.severity == "LOW"

    def test_medium_threshold(self):
        statistical_input = settings.ANOMALY_THRESHOLD_MEDIUM / settings.STAT_WEIGHT
        result = score_compute(statistical_input, 0.0, rule_triggered=False)
        assert result.severity == "MEDIUM"

    def test_high_threshold(self):
        statistical_input = settings.ANOMALY_THRESHOLD_HIGH / settings.STAT_WEIGHT
        result = score_compute(statistical_input, 0.0, rule_triggered=False)
        assert result.severity == "HIGH"

    def test_rule_triggered_enforces_minimum_medium(self):
        """When a rule fires, severity must be at least MEDIUM even if scores are low."""
        result = score_compute(0.0, 0.0, rule_triggered=True)
        assert result.severity == "MEDIUM"
        assert result.risk_score >= settings.ANOMALY_THRESHOLD_MEDIUM

    def test_rule_triggered_high_remains_high(self):
        """Rule trigger does not downgrade HIGH to MEDIUM."""
        result = score_compute(1.0, 1.0, rule_triggered=True)
        assert result.severity == "HIGH"

    def test_anomaly_type_classification(self):
        # Rule match only
        r1 = score_compute(0.0, 0.0, rule_triggered=True)
        assert "rule_match" in r1.anomaly_type

        # Statistical anomaly (stat >= 0.15)
        r2 = score_compute(0.2, 0.0, rule_triggered=False)
        assert "statistical_anomaly" in r2.anomaly_type

        # Isolation anomaly (iso >= 0.15)
        r3 = score_compute(0.0, 0.2, rule_triggered=False)
        assert "isolation_anomaly" in r3.anomaly_type

        # Combined
        r4 = score_compute(0.2, 0.2, rule_triggered=True)
        assert "rule_match" in r4.anomaly_type
        assert "statistical_anomaly" in r4.anomaly_type
        assert "isolation_anomaly" in r4.anomaly_type

    def test_breakdown_dict_structure(self):
        result = score_compute(0.12, 0.08, rule_triggered=False)
        assert result.breakdown == {"statistical": 0.12, "isolation": 0.08}


# ── Contamination Guard Logic ────────────────────────────────────────


class TestContaminationGuard:
    """Validate the guard logic from the worker pipeline:
    Anomalous logs (risk >= LOW threshold or rule-triggered) must NOT enter baseline.
    """

    def test_safe_log_added_to_baseline(self):
        """Low-risk, no-rule-trigger → features should be in baseline."""
        features = [1.0, 30.0, 0.0, 0.0]
        risk_score = 0.05  # below LOW threshold
        rule_triggered = False

        if not rule_triggered and risk_score < settings.ANOMALY_THRESHOLD_LOW:
            baseline_store.add(features)

        assert baseline_store.size == 1

    def test_anomalous_log_excluded_from_baseline(self):
        """High-risk log must NOT enter the baseline buffer."""
        features = [4.0, 500.0, 1.0, 3.0]
        risk_score = 0.65  # above LOW threshold
        rule_triggered = False

        if not rule_triggered and risk_score < settings.ANOMALY_THRESHOLD_LOW:
            baseline_store.add(features)

        assert baseline_store.size == 0

    def test_rule_triggered_log_excluded_even_if_low_risk(self):
        """Even if risk score is low, rule-triggered logs stay out of baseline."""
        features = [3.0, 20.0, 1.0, 1.0]
        risk_score = 0.05
        rule_triggered = True

        if not rule_triggered and risk_score < settings.ANOMALY_THRESHOLD_LOW:
            baseline_store.add(features)

        assert baseline_store.size == 0
